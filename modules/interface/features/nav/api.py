"""功能与文字：改功能名/图标/说明、隐藏功能、调整侧边栏顺序。

存到 `userdata/shell-overrides.json`（由 `core/registry.py` 读取并应用）。
* 只写「和默认不一样」的项：没改的功能，名字以后跟着模块自己的 manifest 走；
* 白名单校验：id 必须在当前扫描结果里真实存在，文字有长度上限，顺序是整数；
* 这份文件在 userdata 里 → 升级不丢，也不会进发给别人的包。
"""

from __future__ import annotations

from typing import Any

from core import config, registry
from core.feature_api import api

MAX_NAME = 24
MAX_DESCRIPTION = 160
MAX_ICON = 4


def _clean_text(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip().replace("\n", " ").replace("\r", " ")
    return text[:limit]


def _valid_keys() -> tuple[set[str], set[str]]:
    """当前真实存在的键：模块键 module:<id>、功能键 <模块id>/<功能id>。"""
    module_keys: set[str] = set()
    feature_keys: set[str] = set()
    modules, _ = registry.scan()
    for module in modules:
        module_keys.add(f"module:{module.id}")
        for feature in module.features:
            feature_keys.add(f"{module.id}/{feature.id}")
    return module_keys, feature_keys


def sanitize(overrides: Any) -> dict[str, Any]:
    if not isinstance(overrides, dict):
        return {}
    module_keys, feature_keys = _valid_keys()
    valid = module_keys | feature_keys

    out: dict[str, Any] = {}

    labels_in = overrides.get("labels")
    labels: dict[str, dict[str, str]] = {}
    if isinstance(labels_in, dict):
        for key, patch in labels_in.items():
            if key not in valid or not isinstance(patch, dict):
                continue
            entry: dict[str, str] = {}
            name = _clean_text(patch.get("name"), MAX_NAME)
            icon = _clean_text(patch.get("icon"), MAX_ICON)
            description = _clean_text(patch.get("description"), MAX_DESCRIPTION)
            if name:
                entry["name"] = name
            if icon:
                entry["icon"] = icon
            if description and key in feature_keys:
                entry["description"] = description
            if entry:
                labels[key] = entry
    if labels:
        out["labels"] = labels

    hidden_in = overrides.get("hidden")
    if isinstance(hidden_in, list):
        hidden = [str(item) for item in hidden_in if str(item) in valid]
        if hidden:
            out["hidden"] = sorted(set(hidden))

    order_in = overrides.get("order")
    order: dict[str, int] = {}
    if isinstance(order_in, dict):
        for key, value in order_in.items():
            if key not in valid:
                continue
            try:
                number = int(value)
            except (TypeError, ValueError):
                continue
            order[key] = max(0, min(999, number))
    if order:
        out["order"] = order

    return out


@api("load")
def load(payload: dict[str, Any], ctx) -> dict[str, Any]:
    """返回当前（已应用覆盖的）导航结构 + 原始覆盖内容，供界面编辑。"""
    modules, errors = registry.scan()
    return {
        "modules": [
            {
                "id": module.id,
                "name": module.name,
                "icon": module.icon,
                "order": module.order,
                "description": module.description,
                "features": [
                    {
                        "id": feature.id,
                        "name": feature.name,
                        "icon": feature.icon,
                        "description": feature.description,
                        "order": feature.order,
                    }
                    for feature in module.features
                ],
            }
            for module in modules
        ],
        "overrides": config.load_overrides(),
        "errors": errors,
    }


@api("save")
def save(payload: dict[str, Any], ctx) -> dict[str, Any]:
    """保存覆盖（清洗后落盘）。"""
    cleaned = sanitize(payload.get("overrides") or {})
    # shell-overrides.json 和「文字替换」共用：只替换本功能管的键，texts 原样保留
    with config.USERDATA_LOCK:
        current = config.load_overrides()
        merged = {**cleaned, **({"texts": current["texts"]} if "texts" in current else {})}
        path = config.save_overrides(merged)
    return {"overrides": cleaned, "saved": True, "path": str(path)}


@api("reset")
def reset(payload: dict[str, Any], ctx) -> dict[str, Any]:
    """恢复默认：清空覆盖文件（功能名/顺序全部回到各模块自己的定义）。"""
    with config.USERDATA_LOCK:
        current = config.load_overrides()
        kept = {"texts": current["texts"]} if "texts" in current else {}
        path = config.save_overrides(kept)
    return {"overrides": {}, "saved": True, "path": str(path)}
