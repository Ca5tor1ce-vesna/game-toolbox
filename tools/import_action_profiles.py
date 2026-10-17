#!/usr/bin/env python
"""把崩铁角色的「行动/能量档案」从 StarRailRes 与 nanoka 拉下来，写进行动值排轴模块。

    python tools\\import_action_profiles.py                    # 全部 87 名适用角色 + 7 名隔离角色
    python tools\\import_action_profiles.py --ids 1502 1001    # 指定角色
    python tools\\import_action_profiles.py --offline          # 只用缓存重新生成

产出：modules/action-value/data/profiles.json

行尾：本脚本写入的文件固定用 LF（仓库里 JSON 都是 LF），二进制写，绝不让 Python 翻行尾。
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "modules" / "action-value" / "data"
CACHE_DIR = Path(__file__).resolve().parent / ".cache" / "srr"
SRR = "https://raw.githubusercontent.com/Mar-7th/StarRailRes/master/index_min/cn/"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36"

# 完整保留全量技能 params 的重点欢愉角色
FULL_SKILL_IDS = {"1501", "1502", "1503", "1511", "1513", "8009"}

# 第六部分：暂不计入常规能量循环的 7 名特殊角色隔离名单
EXCLUDED_SPECIAL_CHARACTERS: dict[str, dict] = {
    "1308": {
        "id": "1308",
        "name": "黄泉",
        "rarity": 5,
        "path": "Warlock",
        "pathName": "虚无",
        "element": "Thunder",
        "elementName": "雷",
        "baseSpeed": 101,
        "traceSpeed": 0.0,
        "specialResource": "9点【残梦】",
        "reason": "特殊能量（负面状态叠层激活终结技，这套回能公式不适用）",
    },
    "1220": {
        "id": "1220",
        "name": "飞霄",
        "rarity": 5,
        "path": "Rogue",
        "pathName": "巡猎",
        "element": "Wind",
        "elementName": "风",
        "baseSpeed": 112,
        "traceSpeed": 0.0,
        "specialResource": "12点【飞黄】",
        "reason": "特殊能量（我方攻击次数叠层，每6点可释放1次终结技，这套回能公式不适用）",
    },
    "1407": {
        "id": "1407",
        "name": "遐蝶",
        "rarity": 5,
        "path": "Memory",
        "pathName": "记忆",
        "element": "Quantum",
        "elementName": "量子",
        "baseSpeed": 95,
        "traceSpeed": 0.0,
        "specialResource": "34000点【新蕊】",
        "reason": "特殊能量（按全队生命值损耗与治疗量转化充能，这套回能公式不适用）",
    },
    "1408": {
        "id": "1408",
        "name": "白厄",
        "rarity": 5,
        "path": "Warrior",
        "pathName": "毁灭",
        "element": "Physical",
        "elementName": "物理",
        "baseSpeed": 94,
        "traceSpeed": 5.0,
        "specialResource": "12点【火种】",
        "reason": "特殊能量（专属【火种】计数与境界额外回合机制，这套回能公式不适用）",
    },
    "1415": {
        "id": "1415",
        "name": "昔涟",
        "rarity": 5,
        "path": "Memory",
        "pathName": "记忆",
        "element": "Ice",
        "elementName": "冰",
        "baseSpeed": 101,
        "traceSpeed": 9.0,
        "specialResource": "12点【追忆】",
        "reason": "特殊能量（专属【追忆】点数机制，这套回能公式不适用）",
    },
    "1506": {
        "id": "1506",
        "name": "银狼LV.999",
        "rarity": 5,
        "path": "Elation",
        "pathName": "欢愉",
        "element": "Imaginary",
        "elementName": "虚数",
        "baseSpeed": 110,
        "traceSpeed": 9.0,
        "specialResource": "60点【隐藏分】",
        "reason": "特殊能量（专属【隐藏分】点数机制，这套回能公式不适用）",
    },
    "1505": {
        "id": "1505",
        "name": "绯英",
        "rarity": 5,
        "path": "Elation",
        "pathName": "欢愉",
        "element": "Physical",
        "elementName": "物理",
        "baseSpeed": 104,
        "traceSpeed": 5.0,
        "specialResource": "480（好活当赏/能量特殊联动）",
        "reason": "专属特殊回能机制（能量获取高度绑定【阿哈时刻】与【好活当赏】结算，这套回能公式不适用）",
    },
}

# 唯一单独计入排轴库的特殊能量角色：1511 星神·啊哈（nanoka.cc #1511）
AEON_AHA_PROFILE: dict = {
    "id": "1511",
    "name": "星神★阿哈",
    "displayName": "星神★阿哈",
    "tag": "aeon_aha",
    "rarity": 5,
    "path": "Elation",
    "pathName": "欢愉",
    "element": "Quantum",
    "elementName": "量子",
    "maxSp": 8,
    "energyType": "wishpower",
    "icon": "icon/character/1511.png",
    "speed": {
        "baseSpeed": 94,
        "traceSpeed": 5.0,
        "effectiveBaseSpeed": 99.0,
        "lcBaseSpeedBonus": 12.0,
        "traceSpeedDetails": [
            {"name": "速度强化", "kind": "flat", "value": 2.0},
            {"name": "速度强化", "kind": "flat", "value": 3.0},
        ],
        "_source": "nanoka.cc #1511",
    },
    "energy": {
        "普攻": {"value": 1.0, "source": "固定", "fixed": True, "unit": "愿力"},
        "战技": {"value": 1.0, "source": "固定", "fixed": True, "unit": "愿力"},
        "终结技": {"value": 0.0, "source": "固定", "fixed": True, "unit": "愿力"},
        "欢愉技": {"value": 1.0, "source": "固定", "fixed": True, "unit": "愿力"},
        "令使回合开始": {"value": 1.0, "source": "固定", "fixed": True, "unit": "愿力"},
        "笑点达40": {"value": 1.0, "source": "固定", "fixed": True, "unit": "愿力"},
        "受治疗或护盾": {"value": 1.0, "source": "固定", "fixed": True, "unit": "愿力"},
    },
    "mechanismNote": "唯一计入的特殊能量角色（8点【愿力】激活终结技，不吃ERR）；专属【阿哈时刻在】使阿哈时刻底速升至94（配专武106）；开大拉条阿哈20%并开启3回合【欢愉万相】升格；战技指定【欢愉令使】并在令使回合开始+1愿力，追击回1战技点",
    "skills": [
        {
            "id": "151101",
            "name": "点星，开幕！",
            "type": "Normal",
            "typeLabel": "普攻",
            "effect": "SingleAttack",
            "effectLabel": "单攻",
            "maxLevel": 6,
            "simpleDesc": "对指定敌方单体造成量子属性欢愉伤害，获得1点【愿力】。",
            "desc": "对指定敌方单体造成70%的量子属性欢愉伤害。",
            "params": [[0.7]],
        },
        {
            "id": "151102",
            "name": "此乃令使，阿哈认证",
            "type": "BPSkill",
            "typeLabel": "战技",
            "effect": "Support",
            "effectLabel": "辅助",
            "maxLevel": 10,
            "simpleDesc": "使除自身外指定我方单体获得常驻【「欢愉」令使】（欢愉度+20%，回合开始使星神获得1点【愿力】），并立即发动全体量子欢愉追加攻击（行迹恢复1点战技点）。",
            "desc": "使除自身以外的指定我方单体角色获得【「欢愉」令使】状态，随后立即发动追加攻击，对敌方全体造成50%的量子属性欢愉伤害。【「欢愉」令使】状态持续整场战斗直至切换到下一个目标，持有【「欢愉」令使】状态的目标欢愉度提高20%并在回合开始时使星神获得1点【愿力】。",
            "params": [[0.5, 0.2, 1]],
        },
        {
            "id": "151103",
            "name": "啊哈！宇宙笑点大爆炸",
            "type": "Ultra",
            "typeLabel": "终结技",
            "effect": "AoEAttack",
            "effectLabel": "群攻",
            "maxLevel": 10,
            "simpleDesc": "使【阿哈时刻】行动提前20%，获得3回合【欢愉万相】使欢愉命途升格（阿哈时刻结束返还10%消耗笑点）。",
            "desc": "使阿哈行动提前20%，星神获得【欢愉万相】状态，持续3回合，每回合开始时持续时间-1。对敌方全体造成200%的量子属性欢愉伤害，随后造成5次伤害，每次对敌方随机单体造成60%的量子属性欢愉伤害。",
            "params": [[0.2, 3, 2.0, 5, 0.6]],
        },
        {
            "id": "151104",
            "name": "与祂共演，奇迹新篇",
            "type": "Talent",
            "typeLabel": "天赋",
            "effect": "Enhance",
            "effectLabel": "强化",
            "maxLevel": 10,
            "simpleDesc": "【愿力】达8点激活终结技（可溢出至10点）。施放普攻/战技/欢愉技后+1【愿力】；笑点首次达40点后+1【愿力】并使全队暴伤提高（阿哈时刻后重置）。",
            "desc": "【愿力】达到8点后可激活终结技，达到上限后还可溢出至10点。施放普攻、战技、欢愉技后获得1点【愿力】。我方笑点首次达到40点后，立即获得1点【愿力】，随后使我方全体暴击伤害提高40%，持续3回合，阿哈回合结束后可再次触发。",
            "params": [[8, 10, 1, 40, 0.4, 3]],
        },
        {
            "id": "151107",
            "name": "ABRACADABRA！",
            "type": "Maze",
            "typeLabel": "秘技",
            "effect": "Support",
            "effectLabel": "辅助",
            "maxLevel": 1,
            "simpleDesc": "进战使【阿哈时刻】立即获得1个固定计入20笑点的额外回合。",
            "desc": "进入战斗后使阿哈立即获得1个固定计入20笑点的额外回合。",
            "params": [[20]],
        },
        {
            "id": "151120",
            "name": "满月，是神在的时间",
            "type": "ElationDamage",
            "typeLabel": "欢愉技",
            "effect": "AoEAttack",
            "effectLabel": "群攻",
            "maxLevel": 10,
            "simpleDesc": "始终在阿哈时刻最后施放，造成全体量子欢愉伤害并附加真实伤害。",
            "desc": "无视参演编号，始终在阿哈时刻最后施放。对敌方全体造成60%的量子属性欢愉伤害，并基于本次阿哈时刻我方目标造成的非真实伤害总和的20%造成真实伤害，由敌方全体均分。",
            "params": [[0.6, 0.2]],
        },
    ],
    "traces": [
        {
            "id": "1511101",
            "name": "愚弄众神的玩笑",
            "desc": "战技的追加攻击额外造成持有【「欢愉」令使】状态的目标20%的对应属性欢愉伤害并恢复1点战技点。",
            "params": [[0.2, 1]],
            "kind": "额外行迹",
            "levelUpSkills": [],
        },
        {
            "id": "1511102",
            "name": "戏中人的异想国",
            "desc": "受到队友提供的治疗效果或护盾时，获得1点【愿力】，最多触发1次，施放终结技后重置可触发次数。",
            "params": [[1]],
            "kind": "额外行迹",
            "levelUpSkills": [],
        },
        {
            "id": "1511103",
            "name": "盒中蕴藏的世界",
            "desc": "当速度大于等于125/150点时，欢愉度提高120%/150%。战斗开始时，使自身行动提前30%。",
            "params": [[125, 150, 1.2, 1.5, 0.3]],
            "kind": "额外行迹",
            "levelUpSkills": [],
        },
    ],
    "ranks": [
        {"id": "151101", "rank": 1, "name": "谁在太初噤声时笑场", "desc": "进入战斗时，立即获得4~5点【愿力】。在场时我方全体造成的欢愉伤害增笑15%。"},
        {"id": "151102", "rank": 2, "name": "在祂的眼睛和你之间", "desc": "使「欢愉」命途升格效果获得加强。"},
        {"id": "151104", "rank": 4, "name": "黑箱一个玩笑的命运", "desc": "欢愉技造成的真实伤害倍率提高原倍率的25%，欢愉伤害额外计入队友【好活当赏】总和的100%。"},
        {"id": "151106", "rank": 6, "name": "因为神说：你就是欢愉", "desc": "首次施放终结技时使阿哈行动提前100%并获得100笑点（或获得1个固定计入40笑点的额外回合），后续每次开大可使阿哈行动提前20%。"},
    ],
}

# 特殊角色回能覆盖与机制备注（严格对照《行动值排轴-修改建议.md》与《hsr_character_speed_energy_database (3).md》）
SPECIAL_ENERGY_OVERRIDES: dict[str, dict[str, dict]] = {
    "1502": {  # 爻光
        "普攻": {"value": 30.0, "source": "文案", "fixed": False},
    },
    "1310": {  # 流萤：战技恢复60%能量上限（144点）固定能量，不吃ERR
        "战技": {"value": 144.0, "source": "固定", "fixed": True, "note": "战技固定恢复60%能量上限（144点），不吃ERR"},
    },
    "1202": {  # 停云：终结技为指定我方单体恢复50（6魂60）点固定能量，不吃ERR
        "终结技": {"value": 50.0, "source": "固定", "fixed": True, "selfReturn": 5.0, "note": "终结技为指定目标固定恢复50点（6魂60点）能量，不吃ERR；自身返还5点"},
    },
    "1208": {  # 符玄：穷观阵期间战技额外+20基础回能（合计50）
        "战技": {"value": 50.0, "source": "文案", "fixed": False, "note": "穷观阵在场时战技30+20=50基础回能（吃ERR）"},
    },
    "1212": {  # 镜流：强化战技回能20点
        "强化战技": {"value": 20.0, "source": "文案", "fixed": False, "note": "进入【转魄】100%行动提前，强化战技恢复20点基础能量"},
    },
    "1213": {  # 丹恒•饮月：强化普攻1/2/3段回能30/35/40点
        "强化普攻3段": {"value": 40.0, "source": "文案", "fixed": False, "note": "1/2/3段强化普攻分别恢复30/35/40点基础能量"},
    },
    "1201": {  # 青雀：战技抽牌不结束回合（0回能），强化普攻20回能
        "战技": {"value": 0.0, "source": "文案", "fixed": True, "note": "战技海底捞月抽牌立即继续行动，不结束回合且战技本身不回能，靠后续普攻回20"},
    },
    "1217": {  # 藿藿：终结技恢复队友20%能量上限，天赋+1基础回能
        "天赋": {"value": 1.0, "source": "文案", "fixed": False, "note": "终结技为除自身外队友恢复20%能量上限；天赋触发自身+1基础回能（吃ERR）"},
    },
}

MECHANISM_NOTES: dict[str, str] = {
    "1503": "终结技指定【美学底本】，按队内欢愉人数1/2/3+使其行动提前10%/15%/30%，4欢愉额外给1个额外回合（+60笑点）；2魂使其他欢愉队友同步拉条；行迹【艺术壁垒】在欢愉底本开大时为真珠固定恢复90点能量（不吃ERR）",
    "1513": "终结技使自身速度提高30%~39%（持续4回合）；队友攻击叠【热意】，满10点立即在回合外施放欢愉技；单欢愉或星神阿哈升格【三赌牌局】下队友攻击使阿哈速度+25、全队速度+15%/25%",
    "1501": "战技【互动陷阱】产笑点与战技点；2魂在每次【阿哈时刻】结束时使火花获得1个额外回合",
    "1502": "普攻30点基础回能（文案）；战技展开3回合结界（随自身回合开始递减，覆盖3次自身行动，2魂结界全队提速12%）；终结技使【阿哈时刻】立即获得1个额外回合（计入20/40笑点）",
    "8009": "天赋每次施放攻击后固定恢复10点能量（不吃ERR）并+3笑点；终结技对有欢愉技队友立即触发欢愉技，对无欢愉技队友使其行动提前50%",
    "1310": "战技固定恢复60%能量上限（144点，不吃ERR）；终结技100%行动提前进入【完全燃烧】（高额固定加速+固定70速倒计时，2魂击破/击杀额外回合）",
    "1202": "终结技为我方单体恢复50点（6魂60点）固定能量（不吃ERR）；行迹回合开始固定回能5点",
    "1212": "进入【转魄】100%行动提前（立即行动）；强化战技恢复20点基础能量",
    "1209": "暴击触发速度提升；天赋追加攻击+10基础回能（吃ERR）",
    "1217": "终结技为除自身外队友恢复各自能量上限20%的固定比例能量；天赋触发自身+1基础回能（吃ERR）",
    "1201": "战技抽牌立即继续行动（不结束回合），仅普攻/强化普攻恢复20点基础能量；4层暗杠强化普攻后提速",
    "1402": "召唤忆灵「衣匠」，叠层大幅提速与连携回能，能量上限350",
    "1401": "终结技后自身立即行动（100%拉条），队友攻击叠层触发固定回能，能量上限220",
    "1413": "召唤忆灵，自身忆灵立即行动与能量恢复，能量上限240",
}

SKILL_TYPE_LABEL = {
    "Normal": "普攻",
    "BPSkill": "战技",
    "Ultra": "终结技",
    "Talent": "天赋",
    "Maze": "秘技",
    "MazeNormal": "秘技(攻击)",
    "ElationDamage": "欢愉技",
}

ENERGY_PATTERNS = [
    (r"普攻恢复的能量提高至\s*(\d+(?:\.\d+)?)\s*点", "普攻", "提高至"),
    (r"施放普攻[^。；\n]{0,30}?恢复\s*(\d+(?:\.\d+)?)\s*点能量", "普攻", "恢复"),
    (r"施放战技[^。；\n]{0,30}?恢复\s*(\d+(?:\.\d+)?)\s*点能量", "战技", "恢复"),
    (r"施放终结技[^。；\n]{0,30}?恢复\s*(\d+(?:\.\d+)?)\s*点能量", "终结技", "恢复"),
]

BASE_ENERGY_FALLBACK = {
    "普攻": {"value": 20, "source": "通用", "fixed": False},
    "战技": {"value": 30, "source": "通用", "fixed": False},
    "终结技": {"value": 5, "source": "通用", "fixed": False},
}


def fetch(name: str, *, refresh: bool, offline: bool) -> dict:
    """取一个 index_min/cn 的 json（带磁盘缓存）。"""
    path = CACHE_DIR / f"{name}.json"
    if refresh or not path.is_file():
        if offline:
            raise SystemExit(f"--offline 但缓存里没有 {name}.json（{path}）")
        url = SRR + f"{name}.json"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read()
        except urllib.error.URLError as exc:
            raise SystemExit(f"拉取失败 {url}：{exc}") from exc
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    return json.loads(path.read_text(encoding="utf-8"))


def extract_energy_from_text(text: str) -> list[dict]:
    out = []
    for pattern, slot, kind in ENERGY_PATTERNS:
        for m in re.finditer(pattern, text or ""):
            fixed = "固定" in m.group(0)
            out.append({
                "slot": slot,
                "value": float(m.group(1)),
                "source": "固定" if fixed else "文案",
                "fixed": fixed,
                "kind": kind,
            })
    return out


def load_rail_catalog() -> dict[str, dict]:
    path = ROOT / "modules" / "honkai-star-rail" / "data" / "characters.json"
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw if isinstance(raw, list) else (raw.get("items") or next(iter(raw.values()), []))
    out: dict[str, dict] = {}
    for c in items or []:
        if not isinstance(c, dict) or not c.get("id"):
            continue
        out[str(c["id"])] = c
    return out


# 欢愉万相★固有行迹。nanoka 4.6.53，角色页 https://hsr.nanoka.cc/character/{id}/
# JSON：https://static.nanoka.cc/hsr/4.6.53/zh/character/{id}.json
# 文案里的 #n[i] 按原样留着。模拟用 1 级；星神★阿哈 2 魂只用他自己这一条的 2 级。
_ASCENSION_ACTIVE_WHEN = (
    "星神★阿哈终结技获得【欢愉万相】后生效。持续 3 回合，星神★阿哈每回合开始时持续时间 -1。"
    "来源：终结技「啊哈！宇宙笑点大爆炸」参数第 6 项为 3；"
    "固有行迹「欢愉万相★无中生有」写明持有【欢愉万相】时命途升格。"
)


def _ascension_trace(cid: str, sid: str, name: str, desc: str, simple: str,
                     params: list, **extra: object) -> dict:
    row = {
        "id": sid,
        "name": name,
        "desc": desc,
        "simpleDesc": simple,
        "params": params,
        "kind": "固有行迹",
        "levelUpSkills": [],
        "activeWhen": _ASCENSION_ACTIVE_WHEN,
        "sourceUrl": f"https://hsr.nanoka.cc/character/{cid}/",
        "dataUrl": f"https://static.nanoka.cc/hsr/4.6.53/zh/character/{cid}.json",
    }
    row.update(extra)
    return row


ASCENSION_TRACES: dict[str, dict] = {
    "1501": _ascension_trace(
        "1501", "150129", "欢愉万相★兔子戏法",
        "当「欢愉」命途升格时，欢愉技的伤害倍率提高原倍率的#5[i]%，我方目标造成伤害时无视敌方目标#1[i]%防御力，每持有#2[i]点【绝活共赏】，【红红火火】触发时额外提供#3[i]点爽点，最多额外提高#4[i]点。",
        "当「欢愉」命途升格时，欢愉技的伤害倍率提高，我方目标造成伤害时无视敌方目标部分防御力，【红红火火】触发时基于持有的【绝活共赏】点数额外提供爽点。",
        [[0.15, 10, 1, 8, 0.5], [0.2, 10, 1, 12, 1.2]],
    ),
    "1502": _ascension_trace(
        "1502", "150229", "欢愉万相★心灵感应",
        "当「欢愉」命途升格时，【大吉大利】效果的伤害倍率提高，提高数值等同于原伤害倍率的#1[i]%。爻光施放终结技后固定恢复#2[i]点能量并获得#4[i]笑点。",
        "当「欢愉」命途升格时，【大吉大利】效果的伤害倍率提高，爻光施放终结技后固定恢复能量并获得笑点。",
        [[0.2, 12, 0, 10], [0.4, 30, 0, 10]],
    ),
    "1503": _ascension_trace(
        "1503", "150329", "欢愉万相★跃然纸上",
        "当「欢愉」命途升格时，真珠的【绝活共赏】持有上限提高至#1[i]点。终结技提供的额外回合开始时获得的【好活当赏】和笑点提高效果，在额外回合结束时会保留#2[i]%和#3[i]%。",
        "当「欢愉」命途升格时，真珠的【绝活共赏】持有上限提高。终结技提供的额外回合开始时获得的【好活当赏】和笑点提高效果，在额外回合结束时会保留部分。",
        [[75, 0.1, 0.1], [75, 0.2, 0.2]],
    ),
    "1505": _ascension_trace(
        "1505", "150529", "欢愉万相★书中折花",
        "当「欢愉」命途升格时，可积攒最多#3[i]点溢出能量，施放终结技后清空并恢复相应的能量值，本次恢复不会触发天赋的获得好活当赏效果。造成的伤害无视敌方目标#2[i]%的防御力，每累计获得#4[i]点【绝活共赏】，使下一次终结技的伤害倍率提高原倍率的#1[i]%。",
        "当「欢愉」命途升格时，可积攒溢出能量，施放终结技后清空并恢复相应的能量值。本次恢复不会触发天赋的获得好活当赏效果。造成的伤害无视敌方目标部分防御力，累计获得一定【绝活共赏】时，使下一次终结技的伤害倍率提高。",
        [[0.75, 0.1, 60, 480], [1.5, 0.24, 240, 480]],
    ),
    "1506": _ascension_trace(
        "1506", "150629", "欢愉万相★全息幻象",
        "当「欢愉」命途升格时，【隐藏分】达到上限后可溢出至#1[i]，暴击伤害提高#3[i]%，获得【绝活共赏】时为「银狼LV.999」提供#2[i]%的【隐藏分】。",
        "当「欢愉」命途升格时，【隐藏分】达到上限后可额外溢出，暴击伤害提高，获得【绝活共赏】时为「银狼LV.999」提供【隐藏分】。",
        [[360, 0.2, 0.4], [999, 0.4, 0.4]],
    ),
    "1511": _ascension_trace(
        "1511", "151129", "欢愉万相★无中生有",
        "持有【欢愉万相】状态时，星神★阿哈使我方「欢愉」命途升格，笑点与【好活当赏】状态强化为爽点和【绝活共赏】状态。爽点会在阿哈时刻回合结束时，重新获得消耗笑点的#1[i]%。【欢愉万相】期间，星神★阿哈暴击率提高#3[i]%，造成的伤害无视敌方目标#2[i]%的防御力。",
        "持有【欢愉万相】状态时，将使我方「欢愉」命途升格，笑点与【好活当赏】状态强化为爽点和【绝活共赏】状态。爽点会在阿哈时刻回合结束时，重新获得消耗笑点的一部分。【欢愉万相】期间，星神★阿哈暴击率提高，造成的伤害无视敌方目标部分防御力。",
        [[0.1, 0.3, 0.12], [0.1, 0.6, 0.2]],
    ),
    "1513": _ascension_trace(
        "1513", "151329", "欢愉万相★三赌牌局",
        "当「欢愉」命途升格时，若只有星神★阿哈1位「欢愉」命途的队友，则行迹【纵享惊涛】中只存在砂金•戏浪1名「欢愉」命途角色时的效果也会生效，且该效果获得加强：我方全体速度提高#2[i]%，队友施放攻击后，砂金•戏浪额外获得#3[i]点【热意】以及#4[i]个爽点。",
        "当「欢愉」命途升格时，若只有星神★阿哈1位「欢愉」命途的队友，则行迹【纵享惊涛】中只存在砂金•戏浪1名「欢愉」命途角色时的效果也会生效，且该效果获得加强：我方全体速度提高，队友施放攻击后，砂金•戏浪获得额外的【热意】以及爽点。",
        [[0, 0.15, 1, 1], [0, 0.25, 2, 2]],
    ),
    "8009": _ascension_trace(
        "8009", "800929", "欢愉万相★主角光环",
        "当「欢愉」命途升格时，终结技的暴击伤害提高效果额外提高#1[i]%，并对我方全体生效。终结技触发星神★阿哈的欢愉技前，额外触发一次开拓者的欢愉技，本次欢愉技的伤害倍率提高原倍率的#2[i]%，并基于我方角色持有的【绝活共赏】最高值进行计算。随后触发的星神★阿哈欢愉技，其真实伤害改为按上述开拓者欢愉技造成伤害的#3[i]%计算，由敌方全体均分。",
        "当「欢愉」命途升格时，终结技提供的暴击伤害提高效果额外提高，并对我方全体生效。终结技触发星神★阿哈的欢愉技前，额外触发一次开拓者的欢愉技，本次欢愉技的伤害倍率提高，并基于我方角色持有的【绝活共赏】最高值进行计算。随后触发的星神★阿哈欢愉技，其真实伤害改为基于上述开拓者欢愉技造成的伤害计算，由敌方全体均分。",
        [[0.2, 2, 0.2], [0.3, 3, 0.2]],
        alsoRecordedAs={
            "id": "8010",
            "skillId": "801029",
            "name": "开拓者•欢愉",
            "note": "女性开拓者•欢愉（8010）与 8009 是同一条固有行迹，档案不另开角色。",
            "sourceUrl": "https://hsr.nanoka.cc/character/8010/",
            "dataUrl": "https://static.nanoka.cc/hsr/4.6.53/zh/character/8010.json",
        },
    ),
}


def attach_ascension_trace(profile: dict) -> dict:
    """把欢愉万相★固有行迹挂进角色自己的 traces。已有同 id 则不重复加。

    1511 的档案是手写的，重导时也要挂上。1505 / 1506 在隔离名单里，同样挂。
    """
    cid = str(profile.get("id") or "")
    spec = ASCENSION_TRACES.get(cid)
    if spec is None:
        return profile
    out = dict(profile)
    traces = [dict(t) for t in (profile.get("traces") or [])]
    if not any(str(t.get("id")) == spec["id"] for t in traces):
        traces.append(dict(spec))
    out["traces"] = traces
    return out


def build_profile(cid: str, chars: dict, skills: dict, trees: dict, ranks: dict,
                  rail_map: dict[str, dict]) -> dict:
    if cid == "1511":
        return dict(AEON_AHA_PROFILE)

    c = chars.get(cid)
    if not c:
        raise SystemExit(f"StarRailRes 里没有角色 {cid}")
    rc = rail_map.get(cid) or {}
    keep_full = cid in FULL_SKILL_IDS

    skill_list = []
    for sid in c.get("skills") or []:
        s = skills.get("1" + str(sid)) or skills.get(str(sid))
        if not s:
            continue
        stype = s.get("type") or ""
        label = s.get("type_text") or SKILL_TYPE_LABEL.get(stype, stype)
        raw_params = s.get("params") or []
        entry = {
            "id": sid,
            "name": s.get("name") or "",
            "type": stype,
            "typeLabel": label,
            "effect": s.get("effect") or "",
            "effectLabel": s.get("effect_text") or "",
            "maxLevel": s.get("max_level"),
            "simpleDesc": s.get("simple_desc") or "",
            "desc": s.get("desc") or "",
            "params": raw_params if keep_full else ([raw_params[-1]] if raw_params else []),
        }
        energy_hits = extract_energy_from_text(entry["desc"] + " " + entry["simpleDesc"])
        if energy_hits:
            entry["energyFromText"] = energy_hits
        skill_list.append(entry)

    energy: dict[str, dict] = {}
    for entry in skill_list:
        for hit in entry.get("energyFromText") or []:
            energy[hit["slot"]] = {
                "value": hit["value"],
                "source": hit["source"],
                "fixed": bool(hit.get("fixed")),
                "from": entry["id"],
                "kind": hit.get("kind"),
            }
    for slot, override in (SPECIAL_ENERGY_OVERRIDES.get(cid) or {}).items():
        energy[slot] = dict(override)
    for slot, info in BASE_ENERGY_FALLBACK.items():
        energy.setdefault(slot, dict(info))

    trace_list = []
    for tid in c.get("skill_trees") or []:
        t = trees.get(str(tid))
        if not t:
            continue
        ups = [u.get("id") for u in (t.get("level_up_skills") or [])]
        desc = (t.get("desc") or "").strip()
        name = (t.get("name") or "").strip()
        kind = "额外行迹" if desc else ("技能升级" if ups else "数值升级")
        if not keep_full and kind != "额外行迹":
            continue
        trace_list.append({
            "id": tid,
            "name": name,
            "desc": desc,
            "params": t.get("params") or [],
            "kind": kind,
            "levelUpSkills": ups,
        })

    rank_list = []
    for rid in c.get("ranks") or []:
        r = ranks.get("1" + str(rid)) or ranks.get(str(rid))
        if not r:
            continue
        rank_list.append({
            "id": rid,
            "rank": r.get("rank"),
            "name": r.get("name") or "",
            "desc": r.get("desc") or "",
        })

    raw_name = c.get("name") or ""
    if raw_name == "{NICKNAME}":
        raw_name = f"开拓者·{rc.get('pathName') or c.get('path') or ''}"
    elif rc.get("name") == "开拓者" and rc.get("pathName"):
        raw_name = f"开拓者·{rc['pathName']}"

    speed_info = {
        "baseSpeed": rc.get("baseSpeed"),
        "traceSpeed": rc.get("traceSpeed") or 0.0,
        "effectiveBaseSpeed": rc.get("effectiveBaseSpeed") or rc.get("baseSpeed"),
        "traceSpeedDetails": rc.get("traceSpeedDetails") or [],
        "_source": "modules/honkai-star-rail/data/characters.json",
    }

    return {
        "id": cid,
        "name": "爻光" if cid == "1502" else raw_name,
        "tag": c.get("tag") or "",
        "rarity": c.get("rarity"),
        "path": c.get("path") or "",
        "pathName": rc.get("pathName") or c.get("path") or "",
        "element": c.get("element") or "",
        "elementName": rc.get("elementName") or c.get("element") or "",
        "maxSp": c.get("max_sp"),
        "energyType": "standard",
        "icon": c.get("icon") or "",
        "speed": speed_info,
        "skills": skill_list,
        "energy": energy,
        "traces": trace_list,
        "ranks": rank_list,
        "mechanismNote": MECHANISM_NOTES.get(cid, ""),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ids", nargs="*", default=None, help="角色 id，不传则生成全部 87 名适用角色")
    parser.add_argument("--refresh", action="store_true", help="忽略缓存全部重抓")
    parser.add_argument("--offline", action="store_true", help="只用缓存，不联网")
    args = parser.parse_args(argv)

    chars = fetch("characters", refresh=args.refresh, offline=args.offline)
    skills = fetch("character_skills", refresh=args.refresh, offline=args.offline)
    trees = fetch("character_skill_trees", refresh=args.refresh, offline=args.offline)
    ranks = fetch("character_ranks", refresh=args.refresh, offline=args.offline)
    rail_map = load_rail_catalog()

    if args.ids:
        target_ids = list(args.ids)
    else:
        target_ids = ["1511"] + [
            cid for cid in rail_map.keys() if cid not in EXCLUDED_SPECIAL_CHARACTERS
        ]

    profiles = {}
    for cid in target_ids:
        profiles[cid] = attach_ascension_trace(
            build_profile(cid, chars, skills, trees, ranks, rail_map)
        )

    print(f"[OK] 已生成适用角色档案 {len(profiles)} 名（含 1511 星神·啊哈 + 86 名标准能量角色），"
          f"隔离特殊角色 {len(EXCLUDED_SPECIAL_CHARACTERS)} 名")

    out = {
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "sources": [
            {
                "name": "StarRailRes（社区维护的游戏数据镜像）与 nanoka.cc (#1511)",
                "url": SRR,
                "usedFor": "角色基础资料、能量上限 max_sp、技能/行迹/星魂文案与各等级 params",
            },
            {
                "name": "通用基础回能表（社区通行口径，非 StarRailRes 数据）",
                "url": "(内置在 tools/import_action_profiles.py 的 BASE_ENERGY_FALLBACK)",
                "usedFor": "技能文案没写明回能时的兜底值；界面标为「通用」，不要当成该角色实测值",
            },
        ],
        "note": "每技能基础回能按「文案 > 固定 > 通用」三级标注；86 名标准能量角色 + 唯一特殊计入角色「星神·啊哈（#1511）」，其余 7 名特殊能量角色列入 excludedProfiles。",
        "profiles": profiles,
        "excludedProfiles": {
            k: attach_ascension_trace(v) for k, v in EXCLUDED_SPECIAL_CHARACTERS.items()
        },
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    target = DATA_DIR / "profiles.json"
    text = json.dumps(out, ensure_ascii=False, indent=1).replace("\r\n", "\n")
    target.write_bytes(text.encode("utf-8"))
    print(f"写出 {target}（{target.stat().st_size / 1024:.1f} KB，LF）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
