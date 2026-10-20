"""应用编辑状态：与浏览器配置分离，跟随 userdata，旧请求不能覆盖新状态。"""
import hashlib
import json
import math
import re

from . import config


def load():
    path = config.USERDATA_DIR / "ui-state.json"
    with config.USERDATA_LOCK:
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except FileNotFoundError:
            data = {"version": 1, "entries": {}}
        except (ValueError, UnicodeError):
            config.quarantine(path)
            data = {"version": 1, "entries": {}}
        if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("entries"), dict):
            raise ValueError("本地编辑状态格式或版本不支持，原文件已保留。")
        for entry in data["entries"].values():
            if not isinstance(entry, dict) or entry.get("version") != 1 or not isinstance(entry.get("value"), dict):
                raise ValueError("本地编辑状态条目格式不支持，原文件已保留。")
            stamp = entry.get("updatedAt")
            if isinstance(stamp, bool) or not isinstance(stamp, (int, float)) or not math.isfinite(stamp) or stamp <= 0:
                raise ValueError("本地编辑状态时间戳无效，原文件已保留。")
        return data


def read():
    return {**load(), "storageId": hashlib.sha256(str(config.USERDATA_DIR.resolve()).encode()).hexdigest()[:24]}


def save(payload):
    key, entry = payload.get("key"), payload.get("entry")
    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9/_-]{1,120}", key):
        raise ValueError("非法页面状态名称。")
    if not isinstance(entry, dict) or not isinstance(entry.get("value"), dict) or entry.get("version") != 1:
        raise ValueError("页面状态需要版本号和对象内容。")
    stamp = entry.get("updatedAt")
    if isinstance(stamp, bool) or not isinstance(stamp, (int, float)) or not math.isfinite(stamp) or stamp <= 0:
        raise ValueError("页面状态的更新时间无效。")
    try:
        size = len(json.dumps(entry, allow_nan=False, ensure_ascii=False).encode("utf-8"))
    except (ValueError, TypeError):
        raise ValueError("页面状态包含无效数值。") from None
    if size > 512 * 1024:
        raise ValueError("页面状态超过 512 KB，请勿保存计算结果或图片。")
    with config.USERDATA_LOCK:
        store = load()
        old = store["entries"].get(key)
        if old and old.get("updatedAt", 0) >= stamp:
            return {"saved": False, "entry": old}
        store["entries"][key] = entry
        config.write_json_atomic(config.USERDATA_DIR / "ui-state.json", store)
    return {"saved": True, "entry": entry}
