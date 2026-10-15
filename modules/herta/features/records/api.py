"""低配通关记录：从多个镜像拉 herta-data 的 latest.json，校验 SHA-256，缓存到 userdata。

镜像按顺序试（短超时），第一个「json 和 sha256 都取到且校验一致」的胜出；
全部失败就用 userdata/herta/records_cache.json 里的上次结果，并标 offline。
web_api.js 是这里的浏览器端移植（用 fetch 直接拉镜像）。
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from core.feature_api import api

REPO = "Ca5tor1ce-vesna/herta-data"
RAW = f"https://raw.githubusercontent.com/{REPO}/main/data/"
MIRRORS: list[dict[str, str]] = [
    {"name": "GitHub Raw", "base": RAW},
    {"name": "jsDelivr", "base": f"https://cdn.jsdelivr.net/gh/{REPO}@main/data/"},
    {"name": "jsDelivr Fastly", "base": f"https://fastly.jsdelivr.net/gh/{REPO}@main/data/"},
    {"name": "jsDelivr Gcore", "base": f"https://gcore.jsdelivr.net/gh/{REPO}@main/data/"},
    {"name": "ghfast.top", "base": "https://ghfast.top/" + RAW},
    {"name": "gh-proxy.com", "base": "https://gh-proxy.com/" + RAW},
]
TIMEOUT = 4.0
CACHE = "records_cache"
CACHE_FRESH_SECONDS = 3600
TZ8 = timezone(timedelta(hours=8))
MODES = ("混沌回忆", "虚构叙事", "末日幻影", "异相仲裁")


def _get(url: str, timeout: float) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "game-toolbox"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(8 * 1024 * 1024)


def validate(data: Any) -> None:
    if not isinstance(data, dict) or not isinstance(data.get("targets"), list) or not data["targets"]:
        raise ValueError("数据结构不对：缺少 targets")
    for t in data["targets"]:
        if not isinstance(t, dict) or t.get("mode") not in MODES or not isinstance(t.get("records"), list):
            raise ValueError("数据结构不对：target 异常")
        for r in t["records"]:
            if not isinstance(r, dict) or not isinstance(r.get("lineup"), list):
                raise ValueError("数据结构不对：record 异常")


def fetch_mirror(base: str, fetch: Callable[[str, float], bytes] = _get, timeout: float = TIMEOUT) -> tuple[dict, str]:
    sha_text = fetch(base + "latest.sha256", timeout).decode("utf-8", "replace").strip()
    expected = sha_text.split()[0].lower() if sha_text else ""
    if len(expected) != 64:
        raise ValueError("sha256 文件格式不对")
    body = fetch(base + "latest.json", timeout)
    actual = hashlib.sha256(body).hexdigest()
    if actual != expected:
        raise ValueError("校验不一致（镜像缓存未同步？）")
    data = json.loads(body.decode("utf-8-sig"))
    validate(data)
    return data, actual


def try_mirrors(fetch: Callable[[str, float], bytes] = _get, mirrors=None, timeout: float = TIMEOUT):
    attempts = []
    for m in mirrors or MIRRORS:
        start = time.monotonic()
        try:
            data, sha = fetch_mirror(m["base"], fetch, timeout)
            attempts.append({"name": m["name"], "ok": True, "ms": int((time.monotonic() - start) * 1000), "error": ""})
            return m, data, sha, attempts
        except Exception as exc:  # 任何错误都只是「这个镜像不行」
            attempts.append({"name": m["name"], "ok": False, "ms": int((time.monotonic() - start) * 1000),
                             "error": str(exc)[:120] or type(exc).__name__})
    return None, None, None, attempts


def _now() -> str:
    return datetime.now(TZ8).strftime("%Y-%m-%d %H:%M")


def load(payload: dict, ctx, fetch: Callable[[str, float], bytes] = _get) -> dict:
    cache = ctx.user_data(CACHE) or None
    if cache and not payload.get("refresh") and time.time() - float(cache.get("ts") or 0) < CACHE_FRESH_SECONDS:
        return {**cache["result"], "from_cache": True}
    mirror, data, sha, attempts = try_mirrors(fetch)
    if mirror:
        result = {"data": data, "mirror": mirror["name"], "sha256": sha, "offline": False, "note": "",
                  "fetched_at": _now(), "attempts": attempts}
        ctx.save_user_data(CACHE, {"ts": time.time(), "result": result})
        return result
    if cache:
        return {**cache["result"], "offline": True, "attempts": attempts, "from_cache": True,
                "note": f"所有镜像都连不上，显示的是 {cache['result'].get('fetched_at')} 缓存的数据（离线）。"}
    raise ValueError("所有镜像都连不上，且没有本地缓存。请检查网络后点刷新。")


@api("load")
def _load(payload, ctx):
    return load(payload, ctx)


@api("mirrors")
def _mirrors(payload, ctx):
    return {"mirrors": MIRRORS, "timeout": TIMEOUT}
