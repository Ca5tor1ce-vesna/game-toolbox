#!/usr/bin/env python
"""把你（作者）在 userdata 里做过的所有自定义汇总成一份报告。

    python tools/dump_overrides.py

我（助手）在动手改任何东西之前会先跑这个，避免把你的选择覆盖掉。
报表包含：
  * 外观主题（userdata/interface/theme.json）
  * 功能改名/隐藏/排序（userdata/shell-overrides.json）
  * 配速查询的「我的配装」预设（userdata/honkai-star-rail/speed-plan-presets.json）
  * 其它模块 userdata 目录里出现的文件（新加的设置会被自动列出来）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import config  # noqa: E402


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"__读取失败__": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    userdata = config.USERDATA_DIR
    if not userdata.is_dir():
        print(f"没有 userdata 目录（你没有改过任何东西）：{userdata}")
        return 0

    print("=" * 62)
    print("你在 userdata 里的自定义（助手动手前会先看这份）")
    print("=" * 62)
    print(f"目录：{userdata}")
    print()

    # 1) 外观主题
    theme_path = userdata / "interface" / "theme.json"
    print("【外观主题】" + (str(theme_path) if theme_path.is_file() else "（没改过，用默认外观）"))
    if theme_path.is_file():
        print(json.dumps(read_json(theme_path), ensure_ascii=False, indent=2))
    print()

    # 2) 功能改名/隐藏/排序
    overrides = config.load_overrides()
    print(f"【功能与文字】{config.OVERRIDES_PATH}")
    if overrides:
        labels = overrides.get("labels") or {}
        hidden = overrides.get("hidden") or []
        order = overrides.get("order") or {}
        print(f"  改了名字/图标的：{len(labels)} 个")
        for key, patch in labels.items():
            print(f"    {key} → {patch}")
        print(f"  隐藏的：{hidden or '（无）'}")
        print(f"  调过顺序的：{order or '（无）'}")
    else:
        print("  （没改过）")
    print()

    # 2.5) 界面文字替换
    texts = overrides.get("texts") or {}
    print(f"【界面文字】{config.OVERRIDES_PATH} 的 texts 段")
    if texts:
        for key, value in texts.items():
            print(f"    {key} → {value}")
    else:
        print("  （没改过）")
    print()

    # 3) 配速预设
    presets_path = userdata / "honkai-star-rail" / "speed-plan-presets.json"
    print(f"【配速查询·我的配装】{presets_path}")
    if presets_path.is_file():
        presets = read_json(presets_path)
        if isinstance(presets, dict):
            for char_id, item in presets.items():
                name = item.get("name") if isinstance(item, dict) else "?"
                saved = item.get("savedAt") if isinstance(item, dict) else ""
                print(f"  {char_id} {name}（{saved}）")
        else:
            print(f"  {presets}")
    else:
        print("  （没存过）")
    print()

    # 4) 其它模块的 userdata（未来加的新设置会自动出现）
    print("【其它 userdata 文件】")
    others = []
    for path in sorted(userdata.rglob("*.json")):
        rel = path.relative_to(userdata)
        if rel.parts[0] == ".asset-cache" or "edge-profile" in rel.parts:
            continue
        if path in (theme_path, presets_path) or path == config.OVERRIDES_PATH:
            continue
        others.append(rel)
    for rel in others:
        print(f"  {rel}")
    if not others:
        print("  （无）")

    cache = userdata / ".asset-cache"
    if cache.is_dir():
        count = len([p for p in cache.iterdir() if p.suffix != ".meta"])
        print()
        print(f"【图片缓存】{cache}：{count} 张（删掉也不影响，会按需重新下载）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
