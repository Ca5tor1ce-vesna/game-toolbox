"""数据审计 + 排序工具。

    python tools/audit_data.py            # 审计：nanoka vs 本地，列出差异
    python tools/audit_data.py --order    # 用 nanoka 的 release 时间戳重排角色（越新越靠上）

审计的判据：nanoka 文案里出现「速度/行动提前 + 数字」的条目，本地必须能对上一个同值的效果。
已知且**故意排除**的几类（敌方减速、召唤物速度、只改已有层数上限）单独统计，不算差异。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NK = ROOT / "tools" / "nanoka"
DATA = ROOT / "modules" / "honkai-star-rail" / "data"
TAG = re.compile(r"<[^>]+>")
PLACEHOLDER = re.compile(r"#(\d+)\[(\w+)\](\%)?")

SPEED_RE = [
    re.compile(r"速度[^，。；\n]{0,10}?(\d+(?:\.\d+)?)\s*%"),
    re.compile(r"速度[^，。；\n]{0,10}?(\d+(?:\.\d+)?)\s*点"),
    re.compile(r"行动提前\s*(\d+(?:\.\d+)?)"),
]
# 故意排除：敌方减速 / 召唤物 / 只改上限
EXCLUDE_HINTS = (
    "敌方", "敌人", "使目标的速度", "目标的速度降低",   # 给敌人减速，不是自己提速
    "移动速度",                                        # 大世界冲刺速度，不参与战斗
    "忆灵", "衣匠", "共舞者", "晴空乐手", "卡厄斯兰那",  # 召唤物 / 忆灵的速度
    "层数上限",                                        # 只改已有上限，不是新提速
    "等同于",                                          # 按比例给队友提速（本人不吃）
)


def render(desc: str, params: list) -> str:
    def sub(match: re.Match) -> str:
        index = int(match.group(1)) - 1
        if index >= len(params):
            return match.group(0)
        value = float(params[index]) * (100 if match.group(3) else 1)
        return f"{value:g}" + ("%" if match.group(3) else "")

    return TAG.sub("", PLACEHOLDER.sub(sub, desc or ""))


def numbers(text: str) -> list[float]:
    found: list[float] = []
    for pattern in SPEED_RE:
        found += [float(item) for item in pattern.findall(text)]
    return found


def nanoka_params(entry: dict) -> list:
    params = entry.get("param_list")
    if isinstance(params, list) and params:
        return params
    levels = entry.get("level")
    if isinstance(levels, dict) and levels:
        key = sorted(levels, key=lambda k: int(k) if str(k).isdigit() else 0)[-1]
        last = levels.get(key)
        if isinstance(last, dict) and isinstance(last.get("param_list"), list):
            return last["param_list"]
    return []


def apply_order() -> None:
    """角色排序改用 nanoka 的 release：越新 → order 越小（界面上越靠上）。"""
    releases = {
        cid: info["release"]
        for cid, info in json.loads((NK / "character.json").read_text(encoding="utf-8")).items()
        if info.get("release")
    }
    path = DATA / "characters.json"
    chars = json.loads(path.read_text(encoding="utf-8"))
    ordered = sorted(releases.items(), key=lambda item: item[1], reverse=True)
    rank = {cid: index for index, (cid, _) in enumerate(ordered)}
    changed = 0
    for char in chars:
        new = rank.get(str(char["id"]))
        if new is None:
            continue  # nanoka 没上线时间的不动
        if char.get("order") != new:
            char["order"] = new
            char["releaseAt"] = releases[str(char["id"])]
            changed += 1
    path.write_text(json.dumps(chars, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    newest = [cid for cid, _ in ordered[:6]]
    by_id = {str(c["id"]): c["name"] for c in chars}
    print(f"  已按 release 重排：{changed} 个角色的顺序变了")
    print(f"  最新 6 个：{[by_id.get(cid, cid) for cid in newest]}")


def audit() -> int:
    chars = json.loads((DATA / "characters.json").read_text(encoding="utf-8"))
    local = {str(c["id"]): c for c in chars}
    missing: list[str] = []
    excluded: list[str] = []
    checked = 0

    dir_path = NK / "zh" / "character"
    for path in sorted(dir_path.glob("*.json")):
        char = local.get(path.stem)
        if not char:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        sections: list[tuple[str, int | None, str, list]] = []
        for index, rank in (data.get("ranks") or {}).items():
            if isinstance(rank, dict):
                sections.append(("星魂", int(index), rank.get("desc") or "", nanoka_params(rank)))
        for skill in (data.get("skills") or {}).values():
            if isinstance(skill, dict):
                sections.append(("技能", None, skill.get("desc") or "", nanoka_params(skill)))
        for tree in (data.get("skill_trees") or {}).values():
            if not isinstance(tree, dict):
                continue
            best, best_params = "", []
            for level in tree.values():
                if isinstance(level, dict) and (level.get("desc") or ""):
                    best, best_params = level.get("desc"), level.get("param_list") or []
            if best:
                sections.append(("行迹", None, best, best_params))

        for source, rank, desc, params in sections:
            text = render(desc, params)
            if not text or ("速度" not in text and "行动提前" not in text):
                continue
            values = numbers(text)
            if not values:
                continue
            checked += 1
            tag = f"{char['name']} {rank}魂" if rank else f"{char['name']} {source}"
            if any(hint in text for hint in EXCLUDE_HINTS):
                excluded.append(f"{tag}：{text[:60]}")
                continue
            have = {
                (e.get("kind"), round(abs(float(e.get("value") or 0)), 3))
                for e in (char.get("effects") or [])
                if (rank is None or str(e.get("rank")) == str(rank))
            }
            wanted = [("pct" if "%" in text else "flat", round(v, 3)) for v in values]
            if not any(item in have or ("advance", item[1]) in have for item in wanted):
                missing.append(f"{tag}：nanoka 有 {'/'.join(str(v) for v in values)}，本地没有 → {text[:64]}")

    print(f"\n  审计：nanoka 里带速度/拉条数字的条目 {checked} 条")
    print(f"  本地缺失：{len(missing)} 条")
    for line in missing[:15]:
        print(f"    [X] {line}")
    print(f"  故意排除（敌方/召唤物/改上限）：{len(excluded)} 条")
    return 1 if missing else 0


if __name__ == "__main__":
    if "--order" in sys.argv:
        apply_order()
    sys.exit(audit())
