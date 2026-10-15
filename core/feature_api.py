"""功能后端 API 的注册与分发。

功能作者只需要在 `features/<功能>/api.py` 里写：

    from core.feature_api import api

    @api("greet")
    def greet(payload, ctx):
        return {"hello": payload.get("name", "world")}

前端这样调：

    ctx.call("greet", {name: "崩铁"})

约定
----
* `payload` 一定是 dict（前端不传就是 `{}`）。
* 返回值必须能 JSON 序列化。
* `ctx` 提供 `data()` / `user_data()` / `save_user_data()`，用来读写本模块的数据。
* 动作名就是前端调用名，同一个功能内不要重名。
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import threading
import traceback
from pathlib import Path
from typing import Any, Callable

from . import config

# 加载期上下文：告诉 @api 当前注册的是哪个功能。
_loader = threading.local()

# (module_id, feature_id) -> {动作名: 处理函数}
HANDLERS: dict[tuple[str, str], dict[str, Callable[..., Any]]] = {}
CONTEXTS: dict[tuple[str, str], "FeatureContext"] = {}


def api(action: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """把一个函数注册成 `POST /api/call` 上的一个动作。"""

    def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
        key = getattr(_loader, "key", None)
        if key is None:
            raise RuntimeError(
                "@api 只能在功能目录的 api.py 顶层使用（加载器导入时会设置上下文）"
            )
        if not isinstance(action, str) or not action.strip():
            raise ValueError("@api 的动作名必须是非空字符串")
        HANDLERS.setdefault(key, {})[action.strip()] = fn
        return fn

    return decorate


def _merge(base: Any, overlay: Any) -> Any:
    """用户数据覆盖模块数据：字典浅合并，其它类型直接替换。"""
    if overlay is None:
        return base
    if isinstance(base, dict) and isinstance(overlay, dict):
        merged = dict(base)
        merged.update(overlay)
        return merged
    return overlay


class FeatureContext:
    """一个功能的后端上下文：读模块数据、读写用户数据。"""

    def __init__(
        self,
        module_id: str,
        feature_id: str,
        module_dir: Path,
        feature_dir: Path,
    ) -> None:
        self.module_id = module_id
        self.feature_id = feature_id
        self.module_dir = module_dir
        self.feature_dir = feature_dir

    # ---------------- 数据 ----------------

    @staticmethod
    def _read_json(path: Path, default: Any = None) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return default
        except Exception as exc:  # 数据坏了只该影响这一个功能，不该拖垮工具箱
            raise ValueError(f"数据文件解析失败：{path}（{exc}）") from exc

    _NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,80}$")

    @classmethod
    def _key(cls, name: str) -> str:
        key = name[:-5] if isinstance(name, str) and name.endswith(".json") else str(name)
        # 拒绝 ..、斜杠和盘符。Windows 上反斜杠会被当成路径分隔符。
        if not cls._NAME.fullmatch(key):
            raise ValueError(f"非法数据名：{name!r}")
        return key

    def module_data_path(self, name: str) -> Path:
        return self.module_dir / "data" / f"{self._key(name)}.json"

    def user_path(self, name: str) -> Path:
        return config.USERDATA_DIR / self.module_id / f"{self._key(name)}.json"

    def data(self, name: str, default: Any = None) -> Any:
        """读模块数据，用户覆盖层优先（用户改过的值不会被升级覆盖回去）。"""
        base = self._read_json(self.module_data_path(name), default)
        overlay = self._read_json(self.user_path(name), None)
        return _merge(base, overlay)

    def raw_data(self, name: str, default: Any = None) -> Any:
        """只读模块自带的数据，忽略用户覆盖。"""
        return self._read_json(self.module_data_path(name), default)

    def user_data(self, name: str, default: Any = None) -> Any:
        return self._read_json(self.user_path(name), default)

    def save_user_data(self, name: str, value: Any) -> str:
        path = self.user_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return str(path)


def load_feature_api(
    module_id: str,
    feature_id: str,
    api_path: Path,
    module_dir: Path,
    feature_dir: Path,
    errors: list[dict[str, Any]],
) -> bool:
    """导入一个功能的 api.py；失败只记录错误，不影响其它功能。"""
    key = (module_id, feature_id)
    HANDLERS.pop(key, None)
    CONTEXTS[key] = FeatureContext(module_id, feature_id, module_dir, feature_dir)

    module_name = f"_toolbox_feature_{module_id}_{feature_id}".replace("-", "_").replace(
        ".", "_"
    )
    _loader.key = key
    try:
        spec = importlib.util.spec_from_file_location(module_name, api_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"无法为 {api_path} 创建模块规格")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return True
    except Exception as exc:
        errors.append(
            {
                "scope": f"{module_id}/{feature_id}",
                "file": str(api_path),
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(limit=8),
            }
        )
        return False
    finally:
        _loader.key = None


def call(module_id: str, feature_id: str, action: str, payload: dict[str, Any] | None = None) -> Any:
    handlers = HANDLERS.get((module_id, feature_id))
    if not handlers:
        raise KeyError(f"功能 {module_id}/{feature_id} 没有注册任何后端动作")
    handler = handlers.get(action)
    if handler is None:
        raise KeyError(
            f"功能 {module_id}/{feature_id} 没有动作 {action!r}；已注册：{sorted(handlers)}"
        )
    return handler(dict(payload or {}), CONTEXTS[(module_id, feature_id)])


def actions(module_id: str, feature_id: str) -> list[str]:
    return sorted(HANDLERS.get((module_id, feature_id), {}))
