#!/usr/bin/env python
"""崩铁数据导入器：把官方图鉴 + 游戏数值抓成本地数据文件。

数据来源
--------
1. **米游社官方 wiki**（官方发布）：角色 / 光锥 / 遗器 的图鉴目录、命途、属性、星级、图标、官方页面 id。
2. **StarRailRes**（社区维护的游戏数据镜像）：基础速度、星魂与技能文案、光锥叠影文案、遗器套装属性。

用法
----
    python tools/import_hsr_data.py              # 联网抓取（结果缓存在 tools/.cache）
    python tools/import_hsr_data.py --refresh    # 忽略缓存，重新抓
    python tools/import_hsr_data.py --offline    # 只用缓存，重新生成数据文件

产出（modules/honkai-star-rail/data/）
--------------------------------------
* `characters.json`  角色：基础速度、命途、属性、星级，以及从技能/星魂/行迹里**自动抽取**出的速度类效果
* `lightcones.json`  光锥：命途、星级、各叠影档位的速度类效果
* `relic_sets.json`  遗器套装：效果文案 + 结构化属性
* `sources.json`     这次导入的数据来源、时间、条目数（界面上会显示，方便判断数据新旧）

自动抽取只是「把可能的加速效果找出来」，条件是否成立要看实战（比如"装备者为同谐角色时"），
所以界面上会把这些效果连同原文一起列出来让你勾选，而不是替你决定。
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "modules" / "honkai-star-rail" / "data"
CACHE_DIR = Path(__file__).resolve().parent / ".cache"

MIYOUSHE_LIST = (
    "https://api-static.mihoyo.com/common/blackboard/sr_wiki/v1/home/content/list"
    "?app_sn=sr_wiki&channel_id=17"
)
SRR = "https://raw.githubusercontent.com/Mar-7th/StarRailRes/master/index_min/cn/"
# 游戏内的角色立绘预览图（不带米游社 wiki 的「首发/复刻」角标）
SRR_PREVIEW = "https://raw.githubusercontent.com/Mar-7th/StarRailRes/master/image/character_preview/{}.png"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36"

# 从文案里抽取速度类效果。顺序有意义：先匹配带单位的，再匹配不带单位的。
EFFECT_PATTERNS: list[tuple[str, str, int]] = [
    (r"速度提高\s*(\d+(?:\.\d+)?)%", "pct", 1),
    (r"速度提升\s*(\d+(?:\.\d+)?)%", "pct", 1),
    (r"速度增加\s*(\d+(?:\.\d+)?)%", "pct", 1),
    (r"速度降低\s*(\d+(?:\.\d+)?)%", "pct", -1),
    (r"速度减少\s*(\d+(?:\.\d+)?)%", "pct", -1),
    (r"速度提高\s*(\d+(?:\.\d+)?)点", "flat", 1),
    (r"速度提升\s*(\d+(?:\.\d+)?)点", "flat", 1),
    (r"速度增加\s*(\d+(?:\.\d+)?)点", "flat", 1),
    (r"行动提前\s*(\d+(?:\.\d+)?)%", "advance", 1),
    (r"行动提前\s*(\d+(?:\.\d+)?)%", "advance", 1),
]

# 速度效果作用对象的三分类。判定只看**「速度提高」前面那一小段主语**，
# 因为一句话里可能既有前置条件又有别的目标，整句匹配会被干扰。
#
#   self  自身：使装备者/自身/自己的速度提高……  → 计入这个角色的速度
#   team  我方全体/全体：我方全体速度提高……      → 计入这个角色的速度（全队共享）
#   ally  只给队友：「被指定的我方目标」「得到【赐福】的我方单体」这类
#         → **不计入这个角色的速度**，界面上只做标注（配速算的是被指定者本人）
#
# 「我方单体」不能放宽成「我方」：否则「我方全体」会被 ally 先截走。
# team 要先判：像信使 4 件套「当装备者对我方目标施放终结技时，**我方全体**速度提高 12%」
# 这种，速度是加给全队的，只是触发条件里提到了「我方目标」。
ALLY_HINTS = ("我方单体", "被指定的", "赐福")
TEAM_HINTS = ("我方全体", "全体队友", "所有队友", "全体", "队友")
SELF_HINTS = ("自身", "自己", "装备者", "本角色")
# 作用在敌人身上的速度变化（减速 / 敌方提速）：永远不计入本角色速度
ENEMY_HINTS = ("敌方", "敌人")
# 只会挂在敌人身上的减益状态：文案里不写「敌方」也是敌方（银狼【缺陷】、梦应归于何处【溃败】）
ENEMY_DEBUFF_HINTS = ("【缺陷】", "【溃败】")

# 「速度提高」前面 12 个字：足够包住「得到【赐福】的我方单体施放终结技后」里的
# 「我方单体」，又不会把前一句的无关内容卷进来。
SPEED_CLAUSE_RE = re.compile(r"(?:速度(?:提高|提升|增加|降低|减少)|行动提前)")
SUBJECT_WINDOW = 12
CLAUSE_SPLIT_RE = re.compile(r"[，。；、,\n]")

# 「持续 N 回合」= 接下来自己的 N 次行动内有效；「最多叠加 N 层」= 每行动一次叠一层。
DURATION_RE = re.compile(r"持续\s*(\d+)\s*回合")
MAX_STACKS_RE = re.compile(r"最多叠[加]?\s*(\d+)\s*层")

# 游戏数据里主角的名字是占位符，显示出来很难看；顺手修掉
NAME_FIXES = {"{NICKNAME}": "开拓者"}

# 米游社的图挂在阿里云 OSS 上，可以用参数让服务端直接返回小图，
# 下拉列表里的图标用 128px 的 webp 就够了（177KB → 5KB）。
ICON_RESIZE = "x-oss-process=image/resize,w_128/format,webp"
SPLASH_RESIZE = "x-oss-process=image/resize,w_480/format,webp"


def resized(url: str | None, process: str) -> str | None:
    if not url:
        return None
    # 米游社的图都在自家 OSS 上（act-upload / uploadstatic），都能吃缩略参数
    if "mihoyo.com" not in url or "upload" not in url:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{process}"


def trace_speed(character: dict, trees: dict) -> tuple[float, float, list[dict]]:
    """把行迹（属性加成）里的速度加成读出来。

    游戏里「速度强化」这类行迹的数值不在 desc 里，而在 levels[].properties，
    类型是 SpeedDelta（固定值）或 SpeedAddedRatio（百分比）。
    同一条行迹在数据里有一份重复条目（id 前面多一个 1），按 (名字, anchor) 去重。
    """
    flat = 0.0
    pct = 0.0
    details: list[dict] = []
    seen: set[tuple] = set()

    for tree_id in character.get("skill_trees") or []:
        tree = trees.get(tree_id) or {}
        name = tree.get("name") or ""
        if "速度" not in name:
            continue
        anchor = tree.get("anchor") or tree_id
        if (name, anchor) in seen:
            continue
        seen.add((name, anchor))

        for level in tree.get("levels") or []:
            for prop in level.get("properties") or []:
                prop_type = prop.get("type")
                try:
                    value = float(prop.get("value") or 0)
                except (TypeError, ValueError):
                    continue
                if prop_type == "SpeedDelta":
                    flat += value
                    details.append({"name": name, "kind": "flat", "value": value})
                elif prop_type in ("SpeedAddedRatio", "SpeedRatio"):
                    ratio = value * 100 if abs(value) <= 1 else value
                    pct += ratio
                    details.append({"name": name, "kind": "pct", "value": ratio})
    return flat, pct, details


def normalise_name(name: str) -> str:
    fixed = NAME_FIXES.get(str(name).strip(), str(name).strip())
    return fixed or str(name)


def find_official(official: dict, star_rail_name: str, path_name: str = "") -> dict:
    """在图鉴里找这个角色。主角在图鉴里叫「开拓者·毁灭」「开拓者•欢愉」（两种分隔符都有）。"""
    entry = official.get(star_rail_name)
    if entry:
        return entry
    if path_name:
        for candidate in (f"开拓者·{path_name}", f"开拓者•{path_name}"):
            if candidate in official:
                return official[candidate]
    return {}


def dedupe_characters(items: list[dict]) -> list[dict]:
    """去掉同一个角色的重复条目（主角每条命途在数据里都有一对）。"""
    seen: set[tuple] = set()
    result: list[dict] = []
    for item in items:
        key = (
            item.get("name"),
            item.get("pathName"),
            item.get("elementName"),
            item.get("rarity"),
            item.get("baseSpeed"),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result

# 光锥/技能文案里的数值占位符，例如 `#1[i]%`、`#2[f1]点`。
# 规则：后面紧跟 `%` 的，原始值是比例（0.24 表示 24%），要 ×100；其它按原值显示。
PLACEHOLDER = re.compile(r"#(\d+)\[([^\]]+)\](%?)")


def best_variant(entry_id: str, table: dict) -> dict:
    """同一内容有新旧两个版本时，取内容更全的那份。

    StarRailRes 里常见 `1130601` 与 `130601` 这种成对条目：带 `1` 前缀的是**新版本**
    （官方后补或改写的文案），而角色的 ranks / skills 数组往往只引用了旧版本。
    旧版本里没有的效果（例如花火 1 魂「战斗开始时或施放战技时速度提高15%」）就这么漏掉了。
    这里同时看两个 id，取渲染后更长的那份。
    """
    base = table.get(entry_id) or {}
    variant = table.get("1" + str(entry_id)) or {}
    if not variant:
        return base
    if not base:
        return variant
    base_len = len(render_description(base.get("desc") or "", effect_params(base)))
    variant_len = len(render_description(variant.get("desc") or "", effect_params(variant)))
    return variant if variant_len > base_len else base


def effect_params(entry: dict) -> list:
    """取一条技能/星魂/行迹的参数表。

    三种数据的存放位置不一样：
      * 星魂 / 光锥：条目上直接有 params
      * 技能：levels[].params（每级一份）
      * 行迹：params 是「每级一组」的嵌套表
    取不到就返回空表，render_description 会原样返回文案（不会更差）。
    """
    params = entry.get("params")
    if isinstance(params, list) and params:
        first = params[0]
        if isinstance(first, list):  # 嵌套：每级一组
            return first
        return params
    levels = entry.get("levels") or []
    if levels:
        last = levels[-1] or {}
        if isinstance(last.get("params"), list):
            return last["params"] or []
    return []


def render_description(desc: str, params: list) -> str:
    """把 `#1[i]%` 这类占位符换成该叠影档位的实际数值（连同后面的 % 一起吃掉）。"""
    if not desc or not params:
        return desc or ""

    def replace(match: re.Match) -> str:
        index = int(match.group(1)) - 1
        style = match.group(2)
        is_percent = match.group(3) == "%"
        if index >= len(params):
            return match.group(0)
        raw = params[index]
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return str(raw)
        if is_percent:
            value *= 100
        if style.startswith("f"):
            try:
                digits = int(style[1:])
            except (TypeError, ValueError):
                digits = 1
            number = f"{value:.{digits}f}"
        else:
            number = f"{value:.1f}".rstrip("0").rstrip(".")
        return number + ("%" if is_percent else "")

    return PLACEHOLDER.sub(replace, desc)


# --------------------------------------------------------------------------- #
# 抓取
# --------------------------------------------------------------------------- #

def fetch(url: str, cache_name: str, refresh: bool = False, offline: bool = False,
          retries: int = 3) -> dict | None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / cache_name
    if cache_path.is_file() and not refresh:
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    if offline:
        print(f"  ! 离线模式且没有缓存：{cache_name}")
        return None

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=90) as response:
                raw = response.read()
            data = json.loads(raw.decode("utf-8"))
            cache_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            print(f"  + {cache_name}  {len(raw) / 1024:.0f} KB")
            return data
        except Exception as exc:  # 网络抖动很常见，重试几次
            last_error = exc
            print(f"  ... {cache_name} 第 {attempt} 次失败：{type(exc).__name__}")
            time.sleep(1.5 * attempt)
    print(f"  × {cache_name} 抓取失败：{last_error}")
    return None


# --------------------------------------------------------------------------- #
# 米游社官方图鉴
# --------------------------------------------------------------------------- #

def parse_miyoushe_catalog(raw: dict) -> dict[str, list[dict]]:
    """把米游社的图鉴树摊平成 {分类: [{name, contentId, icon, 星级/命途/属性}]}。"""
    catalog: dict[str, list[dict]] = {}
    if not raw:
        return catalog

    def walk(node: dict) -> None:
        name = node.get("name")
        items = node.get("list") or []
        if name != "游戏图鉴" and items and not node.get("children"):
            entries = []
            for index, item in enumerate(items):
                entry = {
                    "name": item.get("title"),
                    "contentId": item.get("content_id"),
                    "icon": item.get("icon"),
                    # 米游社图鉴是「新的排前面」，所以这个下标就是推出顺序（越小越新）
                    "order": index,
                }
                ext = item.get("ext")
                if ext:
                    try:
                        block = json.loads(ext)
                        section = block.get("c_18") or {}
                        filters = (section.get("filter") or {}).get("text", "[]")
                        for tag in json.loads(filters):
                            if "/" in tag:
                                key, value = tag.split("/", 1)
                                entry[key] = value
                        picture = (section.get("picture") or {}).get("list") or []
                        if picture:
                            entry["splash"] = picture[0]
                    except Exception:
                        pass
                entries.append(entry)
            catalog[name] = entries
        for child in node.get("children") or []:
            walk(child)

    for top in raw.get("data", {}).get("list", []):
        walk(top)
    return catalog


# --------------------------------------------------------------------------- #
# 效果抽取
# --------------------------------------------------------------------------- #

def split_sentences(text: str) -> list[str]:
    parts = re.split(r"[。；\n]", text or "")
    return [part.strip() for part in parts if part.strip()]


def is_speed_noise(sentence: str) -> bool:
    """排除「不是这个角色战斗速度」的干扰项。

    从文案里抓「速度」两个字很容易抓到两类完全无关的东西：
      * 敌方减益：杰帕德 2 魂「目标的速度降低 20%」——这是给敌人减速，不是自己提速；
      * 大地图移速：赛飞儿「移动速度提高 50%」——跑图用的，和战斗配速无关。
    这类混进来会直接算错速度，所以在抽取阶段就丢掉。
    """
    if "移动速度" in sentence or "探索" in sentence and "速度" in sentence:
        return True
    enemy_markers = ("目标的速度降低", "使敌方", "敌方目标的速度", "敌人的速度", "使目标速度降低")
    return any(marker in sentence for marker in enemy_markers)


def apply_of(sentence: str) -> str:
    """这条速度效果加在谁身上：self / team / ally / enemy（敌方，不计入）。

    只加信息，不过滤：以前判成 team 的现在可能变成 ally（「只给队友的提速」），
    界面上会标注「仅队友」，配速时不计入本角色速度。

    判定用「速度提高」**前面这 12 个字里最后出现的作用对象**：
      * 先看有没有 ally 特征词（我方单体 / 我方目标 / 被指定的 / 赐福）；
      * 再看 team（我方全体、全体、队友…）；
      * 都没有就是自己。

    这样处理得了两种容易翻车的写法：
      「当装备者**对我方目标**施放终结技时，**我方全体**速度提高 12%」→ 取到「我方全体」（team），
      「**我方目标**生命值降低时，速度提高 30%」→ 取到「我方目标」（ally）。
    """
    subject = ""
    for match in SPEED_CLAUSE_RE.finditer(sentence or ""):
        if _enemy_subject(sentence or "", match):
            subject = "enemy"
            continue
        window = (sentence or "")[max(0, match.start() - SUBJECT_WINDOW) : match.start()]
        found = ""
        for hint in ALLY_HINTS:
            index = window.rfind(hint)
            if index >= 0 and (not found or index > found[0]):
                found = (index, "ally")
        for hint in TEAM_HINTS:
            index = window.rfind(hint)
            if index >= 0 and (not found or index > found[0]):
                found = (index, "team")
        if found:
            subject = found[1]
        elif not subject:
            subject = "self"
    return subject or "self"


def _enemy_subject(sentence: str, match: "re.Match[str]") -> bool:
    """这一处速度变化是不是作用在敌人身上。

    * 减速（速度降低/减少）：句中它前面最后出现的作用对象是「敌方/敌人」→ 敌方。
      能跨逗号：「禁锢状态下，敌方目标行动延后6%，速度降低10%」。
    * 提速：只看**同一小句**里紧挨着的主语（「敌方目标速度提高」），
      不能跨逗号——「使装备者在消灭敌方目标后，速度提高10%」是自己提速。
    """
    before = sentence[: match.start()]
    others = SELF_HINTS + ALLY_HINTS + TEAM_HINTS + ("我方",)
    last_other = max((before.rfind(h) for h in others), default=-1)
    if match.group(0).endswith(("降低", "减少")):
        if any(h in sentence for h in ENEMY_DEBUFF_HINTS):
            return True
        last_enemy = max((before.rfind(h) for h in ENEMY_HINTS), default=-1)
        return last_enemy > last_other
    clause = CLAUSE_SPLIT_RE.split(before)[-1]
    last_enemy = max((clause.rfind(h) for h in ENEMY_HINTS), default=-1)
    last_other_c = max((clause.rfind(h) for h in others), default=-1)
    # 「对指定敌方单体造成伤害」这类不是主语：敌方词后面紧跟的必须就是速度子句
    return last_enemy >= 0 and last_enemy > last_other_c and clause[last_enemy:].endswith(
        ("敌方目标", "敌方单体", "敌方全体", "敌人", "敌方目标的")
    )


def duration_of(sentence: str) -> int:
    """「持续 N 回合」→ N；没写就是 0（0 = 一直有效到窗口结束）。"""
    match = DURATION_RE.search(sentence or "")
    return int(match.group(1)) if match else 0


def max_stacks_of(sentence: str) -> int:
    """「最多叠加 N 层」→ N；没写就是 0（0 = 不是叠层效果）。"""
    match = MAX_STACKS_RE.search(sentence or "")
    return int(match.group(1)) if match else 0


def extract_effects(text: str, *, source: str, name: str = "", rank: int | None = None,
                    superimpose: int | None = None) -> list[dict]:
    """从一段文案里抽出速度类效果；带上原文，方便人判断条件是否成立。"""
    found: list[dict] = []
    seen: set[tuple] = set()
    for sentence in split_sentences(text):
        if is_speed_noise(sentence):
            continue
        for pattern, kind, sign in EFFECT_PATTERNS:
            for match in re.finditer(pattern, sentence):
                try:
                    value = float(match.group(1)) * sign
                except (TypeError, ValueError):
                    continue
                key = (kind, value, sentence)
                if key in seen:
                    continue
                seen.add(key)
                apply_to = apply_of(sentence)
                found.append(
                    {
                        "source": source,
                        "name": name,
                        "kind": kind,          # pct=百分比速度 / flat=固定速度 / advance=拉条
                        "value": value,
                        "apply": apply_to,     # self=自身 / team=我方全体 / ally=只给队友（不计入本角色）
                        "durationTurns": duration_of(sentence),    # 持续 N 回合 → 自己的 N 次行动
                        "maxStacks": max_stacks_of(sentence),      # 最多叠 N 层 → 每次行动叠一层
                        "rank": rank,          # 星魂档位
                        "superimpose": superimpose,  # 叠影档位
                        "text": sentence,
                    }
                )
    return found


# --------------------------------------------------------------------------- #
# 组装
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# nanoka 补充源（tools/nanoka/zh/character/<id>.json）
#
# 用途：官方数据里有些效果（尤其是「行动提前」）在 StarRailRes 那边没有，
# nanoka 有。这里只做**补充**——本地已有的效果一律保留，不覆盖、不改写。
# --------------------------------------------------------------------------- #

NANOKA_DIR = Path(__file__).resolve().parent / "nanoka" / "zh" / "character"
NANOKA_TAG_RE = re.compile(r"<[^>]+>")


def nanoka_params(entry: dict) -> list:
    """从 nanoka 条目里取参数表：param_list 或 level.<最高级>.param_list。"""
    params = entry.get("param_list")
    if isinstance(params, list) and params:
        return params
    levels = entry.get("level")
    if isinstance(levels, dict) and levels:
        last = levels.get(sorted(levels, key=lambda k: int(k) if str(k).isdigit() else 0)[-1])
        if isinstance(last, dict) and isinstance(last.get("param_list"), list):
            return last["param_list"]
    return []


def nanoka_sections(char_id: str) -> list[tuple[str, int | None, str, list]]:
    """读出 (来源, 星魂序号, 文案, 参数) 四元组列表；没有这个角色的文件就返回空。"""
    path = NANOKA_DIR / f"{char_id}.json"
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    out: list[tuple[str, int | None, str, list]] = []

    for index, rank in (data.get("ranks") or {}).items():
        if not isinstance(rank, dict):
            continue
        desc = rank.get("desc") or ""
        out.append(("星魂", int(index) if str(index).isdigit() else None, desc, nanoka_params(rank)))

    for skill in (data.get("skills") or {}).values():
        if not isinstance(skill, dict):
            continue
        desc = skill.get("desc") or ""
        out.append(("技能", None, desc, nanoka_params(skill)))

    for tree in (data.get("skill_trees") or {}).values():
        if not isinstance(tree, dict):
            continue
        # 行迹/额外能力：每级一份，取内容最全的那份
        best = ""
        best_params: list = []
        for level in tree.values():
            if not isinstance(level, dict):
                continue
            desc = level.get("desc") or ""
            params = level.get("param_list") or []
            rendered = render_description(desc, params) if params else desc
            if len(rendered) > len(render_description(best, best_params) if best_params else best):
                best, best_params = desc, params
        if best:
            out.append(("行迹", None, best, best_params))

    return out


def nanoka_extra_effects(char_id: str, existing: list[dict]) -> list[dict]:
    """本地没有的 nanoka 效果（只补不改）。"""
    if not NANOKA_DIR.is_dir():
        return []
    seen = {
        (effect.get("kind"), round(abs(float(effect.get("value") or 0)), 3), effect.get("rank"))
        for effect in existing
    }
    added: list[dict] = []
    for source, rank, desc, params in nanoka_sections(char_id):
        rendered = render_description(desc, params)
        rendered = NANOKA_TAG_RE.sub("", rendered)
        for effect in extract_effects(rendered, source=source, name="", rank=rank):
            key = (effect.get("kind"), round(abs(float(effect.get("value") or 0)), 3), rank)
            if key in seen:
                continue
            seen.add(key)
            added.append(effect)
    return added


def build_characters(srr: dict, catalog: dict) -> list[dict]:
    characters = srr.get("characters") or {}
    promotions = srr.get("character_promotions") or {}
    ranks = srr.get("character_ranks") or {}
    skills = srr.get("character_skills") or {}
    trees = srr.get("character_skill_trees") or {}
    paths = srr.get("paths") or {}
    elements = srr.get("elements") or {}

    official = {entry["name"]: entry for entry in catalog.get("角色", [])}

    out: list[dict] = []
    for char_id, char in characters.items():
        values = (promotions.get(char_id) or {}).get("values") or []
        base_speed = None
        if values:
            spd = values[-1].get("spd") or {}
            base_speed = spd.get("base")

        effects: list[dict] = []
        for skill_id in char.get("skills") or []:
            skill = best_variant(skill_id, skills)
            effects += extract_effects(
                render_description(skill.get("desc") or "", effect_params(skill)),
                source="技能",
                name=skill.get("name") or "",
            )
        for index, rank_id in enumerate(char.get("ranks") or [], start=1):
            rank = best_variant(rank_id, ranks)
            effects += extract_effects(
                render_description(rank.get("desc") or "", effect_params(rank)),
                source="星魂",
                name=rank.get("name") or "",
                rank=index,
            )
        for tree_id in char.get("skill_trees") or []:
            tree = trees.get(tree_id) or {}
            effects += extract_effects(
                render_description(tree.get("desc") or "", effect_params(tree)),
                source="行迹",
                name=tree.get("name") or "",
            )

        # nanoka 补充源：只补本地没有的效果（尤其是漏掉的行提前）
        extra = nanoka_extra_effects(char_id, effects)
        if extra:
            effects += extra

        path_name = (paths.get(char.get("path")) or {}).get("name", char.get("path"))
        entry = find_official(official, char["name"], path_name)
        trace_flat, trace_pct, trace_details = trace_speed(char, trees)
        out.append(
            {
                "id": char_id,
                "name": normalise_name(char["name"]),
                "rarity": char.get("rarity"),
                "path": char.get("path"),
                "pathName": path_name,
                "element": char.get("element"),
                "elementName": (elements.get(char.get("element")) or {}).get("name", char.get("element")),
                "baseSpeed": base_speed,
                # 行迹（属性加成）里的速度，游戏面板上是常驻的；界面会自动算进去
                "traceSpeed": trace_flat,
                "traceSpeedPct": trace_pct,
                "traceSpeedDetails": trace_details,
                "effectiveBaseSpeed": (base_speed or 0) + trace_flat,
                "contentId": entry.get("contentId"),
                "icon": entry.get("icon"),
                "iconSmall": resized(entry.get("icon"), ICON_RESIZE),
                # 立绘优先用游戏内预览图（没有角标），米游社那张作为兜底
                "splash": SRR_PREVIEW.format(char_id),
                "splashFallback": entry.get("splash"),
                "splashSmall": resized(entry.get("splash"), SPLASH_RESIZE),
                "releaseOrder": entry.get("order"),
                "effects": effects,
            }
        )
    # 图鉴顺序就是推出顺序（新的在前），直接照这个输出，界面不用再排
    out.sort(key=lambda item: (item.get("releaseOrder") is None, item.get("releaseOrder") or 0))
    return dedupe_characters(out)


def build_lightcones(srr: dict, catalog: dict) -> list[dict]:
    cones = srr.get("light_cones") or {}
    ranks = srr.get("light_cone_ranks") or {}
    paths = srr.get("paths") or {}
    official = {entry["name"]: entry for entry in catalog.get("光锥", [])}

    out: list[dict] = []
    for cone_id, cone in cones.items():
        effects: list[dict] = []
        raw = ranks.get(cone_id) or {}
        desc = raw.get("desc") or ""
        params = raw.get("params") or []
        # 一档叠影一条：params 有 5 组（叠影1~5），逐档渲染文案再抽效果
        for level in range(1, 6):
            row = params[level - 1] if level - 1 < len(params) else None
            text = render_description(desc, row) if row else desc
            effects += extract_effects(
                text, source="光锥", name=cone["name"], superimpose=level
            )

        entry = official.get(cone["name"]) or {}
        out.append(
            {
                "id": cone_id,
                "name": cone["name"],
                "rarity": cone.get("rarity"),
                "path": cone.get("path"),
                "pathName": (paths.get(cone.get("path")) or {}).get("name", cone.get("path")),
                "contentId": entry.get("contentId"),
                "icon": entry.get("icon"),
                "iconSmall": resized(entry.get("icon"), ICON_RESIZE),
                "releaseOrder": entry.get("order"),
                "effects": effects,
            }
        )
    out.sort(key=lambda item: (-(item.get("rarity") or 0), item["name"]))
    return out


def build_relics(srr: dict, catalog: dict) -> list[dict]:
    sets = srr.get("relic_sets") or {}
    official = {entry["name"]: entry for entry in catalog.get("遗器", [])}
    out: list[dict] = []
    for relic_id, relic in sets.items():
        entry = official.get(relic["name"]) or {}
        effects: list[dict] = []
        for index, desc in enumerate(relic.get("desc") or []):
            piece = ("2件套", "4件套")[index] if index < 2 else f"额外第{index + 1}条"
            effects += extract_effects(
                desc or "", source=f"遗器·{piece}", name=relic["name"]
            )
        out.append(
            {
                "id": relic_id,
                "name": relic["name"],
                "desc": relic.get("desc") or [],
                "properties": relic.get("properties") or [],
                "contentId": entry.get("contentId"),
                "icon": entry.get("icon"),
                "iconSmall": resized(entry.get("icon"), ICON_RESIZE),
                "releaseOrder": entry.get("order"),
                "effects": effects,
            }
        )
    out.sort(key=lambda item: item["name"])
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="导入崩铁数据")
    parser.add_argument("--refresh", action="store_true", help="忽略缓存重新抓取")
    parser.add_argument("--offline", action="store_true", help="只用缓存")
    args = parser.parse_args()

    print("① 米游社官方图鉴")
    miyoushe_raw = fetch(MIYOUSHE_LIST, "miyoushe_channel17.json", args.refresh, args.offline)
    catalog = parse_miyoushe_catalog(miyoushe_raw) if miyoushe_raw else {}
    for key, entries in catalog.items():
        print(f"    {key}: {len(entries)} 条")

    print("② StarRailRes 数值")
    files = [
        "characters.json", "character_promotions.json", "character_ranks.json",
        "character_skills.json", "character_skill_trees.json", "light_cones.json",
        "light_cone_ranks.json", "relic_sets.json", "paths.json", "elements.json",
    ]
    srr: dict[str, dict] = {}
    for name in files:
        data = fetch(SRR + name, "srr_" + name, args.refresh, args.offline)
        if data is not None:
            srr[name.replace(".json", "")] = data

    print("③ 组装")
    characters = build_characters(srr, catalog)
    light_cones = build_lightcones(srr, catalog)
    relics = build_relics(srr, catalog)

    without_speed = [c["name"] for c in characters if not c.get("baseSpeed")]
    char_effects = sum(len(c["effects"]) for c in characters)
    cone_effects = sum(len(c["effects"]) for c in light_cones)
    relic_effects = sum(len(r["effects"]) for r in relics)

    print(f"    角色 {len(characters)}（无基础速度 {len(without_speed)}）")
    print(f"    光锥 {len(light_cones)}")
    print(f"    遗器 {len(relics)}")
    print(f"    抽到的速度类效果：角色 {char_effects} / 光锥 {cone_effects} / 遗器 {relic_effects}")
    if without_speed:
        print("    缺速度的角色：" + "、".join(without_speed[:10]))

    sources = {
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "sources": [
            {
                "name": "米游社官方 wiki 图鉴",
                "url": MIYOUSHE_LIST,
                "usedFor": "角色/光锥/遗器的官方名称、命途、属性、星级、图标、官方页面 id",
            },
            {
                "name": "StarRailRes（社区维护的游戏数据镜像）",
                "url": SRR,
                "usedFor": "基础速度、技能/星魂/行迹文案、光锥叠影文案、遗器套装属性",
            },
        ],
        "counts": {
            "characters": len(characters),
            "lightcones": len(light_cones),
            "relics": len(relics),
            "charactersWithoutBaseSpeed": len(without_speed),
        },
        "note": "速度类效果是自动从文案里抽取的候选，条件是否成立要看实战，界面上请自行勾选确认。",
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for filename, payload in (
        ("characters.json", characters),
        ("lightcones.json", light_cones),
        ("relic_sets.json", relics),
        ("sources.json", sources),
    ):
        path = DATA_DIR / filename
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
        print(f"    → {path.relative_to(ROOT)}  {path.stat().st_size / 1024:.0f} KB")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
