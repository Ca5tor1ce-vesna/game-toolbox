"""文字替换：把界面上的固定文案改成你自己的说法。

* 可替换的 key 来自「文案目录」：`app/texts.json`（外壳）+ 各功能的 `texts.json`；
* 界面里对应元素带 `data-text="key"`，外壳读 `userdata/shell-overrides.json` 的 `texts` 段替换；
* 保存时**只动 texts 这一段**，不会碰你在「功能与文字」「外观与排版」里的设置。
"""

from __future__ import annotations

from typing import Any

from core import config, texts as text_catalog
from core.feature_api import api

MAX_TEXT = 200


def _scope_of(key: str) -> str:
    """把 key 归到一组，方便界面分块显示。"""
    if key.startswith("shell."):
        return "外壳（标题栏 / 侧边栏 / 顶栏）"
    if "/" in key:
        return key.split("/", 1)[0]
    head = key.split(".", 1)[0]
    return f"{head}（功能界面）"


def _clean(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text[:MAX_TEXT] or None


@api("load")
def load(payload: dict[str, Any], ctx) -> dict[str, Any]:
    """列出所有可替换文案 + 你当前改成了什么。"""
    catalog = text_catalog.all_texts()
    current = config.load_overrides().get("texts") or {}
    groups: dict[str, list[dict[str, Any]]] = {}
    for key, default in catalog.items():
        value = current.get(key)
        groups.setdefault(_scope_of(key), []).append(
            {"key": key, "default": default, "current": value if value != default else None}
        )
    for items in groups.values():
        items.sort(key=lambda item: item["key"])
    return {
        "groups": [{"scope": scope, "items": items} for scope, items in sorted(groups.items())],
        "count": len(catalog),
        "changed": sum(1 for value in current.values() if value),
    }


@api("save")
def save(payload: dict[str, Any], ctx) -> dict[str, Any]:
    """保存文字覆盖（只替换 texts 段，保留其它设置）。"""
    catalog = text_catalog.all_texts()
    incoming = payload.get("texts") or {}
    cleaned: dict[str, str] = {}
    if isinstance(incoming, dict):
        for key, value in incoming.items():
            if key not in catalog:  # 不认识的 key 一律不收
                continue
            text = _clean(value)
            if text and text != catalog[key]:  # 和默认一样就不必存
                cleaned[key] = text
    overrides = config.load_overrides()
    if cleaned:
        overrides["texts"] = cleaned
    else:
        overrides.pop("texts", None)
    path = config.save_overrides(overrides)
    return {"texts": cleaned, "saved": True, "path": str(path)}


@api("reset")
def reset(payload: dict[str, Any], ctx) -> dict[str, Any]:
    """只清掉文字替换，保留功能改名/隐藏/排序。"""
    overrides = config.load_overrides()
    overrides.pop("texts", None)
    path = config.save_overrides(overrides)
    return {"texts": {}, "saved": True, "path": str(path)}
