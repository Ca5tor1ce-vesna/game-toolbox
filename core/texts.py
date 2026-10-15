"""给外壳与功能界面里的固定文案打 key，方便用后台替换。

替换生效链路：
    userdata/shell-overrides.json 的 "texts" 段
      → 服务端 /api/overrides 读出来
      → app.js 的 GTText.apply() 把带 data-text="key" 的元素文字换成覆盖值
      → MutationObserver 盯着动态渲染的内容，挂载功能后再刷一次

key 的命名：`<模块或 shell>.<位置>.<名字>`，尽量一眼看出在哪。
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHELL_CATALOG = ROOT / "app" / "texts.json"
MODULES_DIR = ROOT / "modules"


def read_catalog(path: Path) -> dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): str(value) for key, value in data.items()}


def feature_catalogs() -> dict[str, dict[str, str]]:
    """每个功能自己的 texts.json（没有就没有）。"""
    out: dict[str, dict[str, str]] = {}
    if not MODULES_DIR.is_dir():
        return out
    for path in sorted(MODULES_DIR.glob("*/features/*/texts.json")):
        feature_dir = path.parent
        module_dir = feature_dir.parent.parent
        key = f"{module_dir.name}/{feature_dir.name}"
        catalog = read_catalog(path)
        if catalog:
            out[key] = catalog
    return out


def all_texts() -> dict[str, str]:
    """所有可替换的文案（key → 默认值）。"""
    merged = read_catalog(SHELL_CATALOG)
    for catalog in feature_catalogs().values():
        merged.update(catalog)
    return merged
