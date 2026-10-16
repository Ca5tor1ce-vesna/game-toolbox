"""【阿哈时刻】配速 —— 后端模拟引擎。

这个功能算两件事：
  1. 【阿哈时刻】（Aha Instant）的实战速度：欢愉队友速度加权 + 星神★阿哈升格底速；
  2. 4 人小队 + 【阿哈时刻】在 `[0, maxAV]` 内的行动值排轴（含额外回合、拉条、
     欢愉技、笑点/愿力/热意等资源结算）。

`web_api.js` 是这份代码的逐位移植：Python 服务端和独立网页走同一套算法、同一个
payload / 输出结构，两边 JSON 输出必须完全一致（tests 之外另有 node 对拍脚本）。

底层公式（与《行动、回能与全角色/光锥/遗器排轴模拟数据库》一致）
--------------------------------------------------------------
基础行动距离 Dist_Base = 10000。角色实战速度：

    current_spd = (base_spd + lc_base_spd) × (1 + (perm_pct + buff_pct) / 100)
                  + perm_flat + buff_flat + trace_spd

注意：行迹速度 trace_spd 在百分比乘区**之外**；光锥基础速度 lc_base_spd（如
星神★阿哈专武《当第一声「阿哈」响起》+12）在百分比乘区**之内**。

拉条（AA）：rem_dist = max(0, rem_dist − 10000 × aa_pct / 100)，剩余行动值
= rem_dist / current_spd。单位正在自己行动（rem_dist == 0）时触发的**自身**拉条
（如风套 4 件套开大 25%）存进 pending_post_turn_aa，等回合结束 rem_dist 重置成
10000 之后再扣（25% → 从 7500 起跑）。**外部**拉条（舞！舞！舞！/真珠终结技/
星期日战技）打在 rem_dist > 0 的单位上立即扣减（封底 0）。

变速保留已跑进度：任何单位速度变化时 rem_dist 不动，剩余行动值 = rem_dist / 新速度。

【阿哈时刻】速度：
    把欢愉队友速度从高到低排成 V1 ≥ V2 ≥ V3 ≥ V4（不足补 0），
    编入星神★阿哈（或 useAeonAha）时底速 = aeon_aha_base_spd + aeon_aha_lc_base_spd
    （默认 94 + 12 = 106），否则底速 80；
    aha_spd = (底速 + 0.2V1 + 0.1V2 + 0.05V3 + 0.025V4 + aha_flat_bonus)
              × (1 + aha_spd_pct / 100)。
    任何欢愉队友变速或 aha_flat_bonus 变化时，保留 aha_rem_dist，只重算
    aha_rem_av = aha_rem_dist / aha_spd。

轮次（MoC）：av ≤ 150 是 0T；150 < av ≤ 250 是 1T；250 < av ≤ 350 是 2T……
（边界取 1e-9 容差。）

payload（simulate）
-------------------
    {
      "maxAV": 300,                    // 模拟窗口，(0, 1000]
      "useAeonAha": true,              // 不给则「队伍里有 1511」推断
      "useTech": true,                 // 秘技进战
      "trace3Advance": true,           // 星神★阿哈行迹3：进战自身拉条 30%
      "ultAdvanceAha": 20,             // 阿哈终结技拉条【阿哈时刻】%
      "e1Wishpower": 5,                // 阿哈 E1 开局愿力（默认 5）
      "e6FirstUltMode": "extra40",     // 或 "advance100"
      "ultSpdPct": 30,                 // 砂金•戏浪终结技自提速%（4回合）
      "sanduTeamSpdPct": 15,           // 三赌牌局全队提速%
      "sanduFervorGain": 1,            // 三赌牌局每次队友攻击热意
      "sanduPunchlineGain": 1,         // 三赌牌局每次队友攻击笑点
      "dancePct": 24,                  // 叠5 舞！舞！舞！全队拉条%
      "summerLcSpdPct": 24,            // 向浪花掷下盛夏【风口】自提速%
      "sigLcPunchline": 10,            // 阿哈专武战技笑点（S1 10 ~ S5 18）
      "aeonAhaBaseSpd": 94,            // 阿哈时刻底速（1511 在队时默认取 1511）
      "aeonAhaLcBaseSpd": 12,
      "ahaSpdPct": 0,                  // 阿哈时刻额外速度%（乘在加权之后）
      "ahaAdvancePct": 0,              // 开局拉条【阿哈时刻】%
      "feiyingHaohuoEnergyMode": "punchline",  // 或 "flat"
      "feiyingHaohuoEnergy": 20,       // flat 模式下绯英获得好活当赏回能
      "team": [                        // 1~4 人
        {
          "id": "1511",                // 或别名 xuzhao / aeon_aha / pearl / ...
          "name": "自定义名",           // 可覆盖
          "baseSpd": 94, "lcBaseSpd": 12, "traceSpd": 5,
          "permPct": 0, "permFlat": 0, "buffPct": 0, "buffFlat": 0,
          "err": 0, "eidolon": 0, "elation": true,
          "initAdv": 0,                // 开局额外拉条%
          "targetSlot": 0,             // 指定目标（令使/美学底本/星期日战技等）
          "maxSp": 8, "rotation": "skill",   // auto | basic | skill
          "equipment": {
            "vonwacq": false, "godJoy": false,
            "windSet4": false, "danceS5": false,
            "hasSigLc": true, "hasSummerLc": false
          }
        }
      ]
    }

输出：{maxAV, aha, units, timeline, summary, resources, warnings, notes}。
timeline 每条：{av, t, kind, slot, name, type, extra, label, details, res}。

模拟口径（默认动作策略，都是确定性的）
--------------------------------------
* 终结技**一满就放**（能量/愿力/隐藏分达到阈值立即施放，允许插入在任意事件中间），
  风套/舞舞舞等「开大触发」因此会出现在轴上的真实时点。
* 每个角色的默认出招固定（catalog 里有说明），可用 unit.rotation 覆盖：
  1511 战技（令使 + 追击）、1503 有【深度学习】用强化普攻否则战技、1513/1304/1502/
  1501/8009/1505/1506/1313/1309 战技；1506 在【无敌玩家】里用强化普攻。
* 欢愉技（Elation Skill）：【阿哈时刻】每次行动时全体欢愉角色各放 1 次，
  固定 +20 笑点；1513 放《举杯！敬炽烈一夏》/《All in！》，1511 +1 愿力。
* 额外回合：不重置 rem_dist、不递减常规 Buff 回合数；【阿哈时刻】额外回合
  不消耗笑点池、按固定 20/40 记账。

数值假设（规格没写死、这里定死的口径）
--------------------------------------
* 《向浪花掷下盛夏》的【风口】提速按**常驻**处理（文案没写持续回合）。
* 通用欢愉技固定 +20 笑点；1506 强化普攻 +5 笑点（与她的战技同值）。
* 1505 绯英获得【好活当赏】时回能 = 该次好活当赏记账的笑点数
  （feiyingHaohuoEnergyMode="flat" 时改为固定 feiyingHaohuoEnergy）。
* 真珠的「+N 好活当赏」（秘技/战技/终结技）与砂金•戏浪秘技的 +20 好活当赏
  发给**全队**（持续 2 回合，记账数 = N）。
* 额外回合照常产生该角色的出招资源（能量/笑点），但不推进回合数相关的结算。
* 星期日终结技回能 = max(40, 20% 能量上限)，固定回能（不吃 ERR）。
* 砂金（存护）【盲注】按「每次攻击 +1 层」计（自己的追击不再叠层），7 层触发追击。
* 舞！舞！舞！开大者自己正在行动时不吃自己那口拉条（游戏原文如此）。
* 队伍里任意单位的攻击事件（普攻/战技/强化普攻/终结技攻击/追击/欢愉技）都会
  走统一钩子；砂金•戏浪天赋只认「除自己外」的普攻/战技/强化普攻/终结技/追击
  （规格原文没把欢愉技列进天赋触发面），纵享惊涛认所有攻击（含欢愉技）。
"""

from __future__ import annotations

import math
import re
from typing import Any

from core.feature_api import api

# --------------------------------------------------------------------------- #
# 常量
# --------------------------------------------------------------------------- #

DIST_BASE = 10000.0
CYCLE0_AV = 150.0
CYCLE_AV = 100.0
EPS = 1e-9
NUM_LIMIT = 1e9
MAX_TEAM = 4
MAX_TIMELINE = 4000
MAX_NEST = 24
MAX_LOOP = 20000
MAX_AV = 1000.0

AHA_WEIGHTS = (0.2, 0.1, 0.05, 0.025)
AHA_DIVISORS = (5, 10, 20, 40)

# 砂金•戏浪【热意】阈值：E0 只有 10；E1 加 20/30；E2 加 40/50（上限 50）
FERVOR_THRESHOLDS = (
    (10.0,),
    (10.0, 20.0, 30.0),
    (10.0, 20.0, 30.0, 40.0, 50.0),
)
FERVOR_CAP = 50.0

# 天赋「抛注，听深渊回响」触发面（不含欢愉技——规格原文枚举的是这五类）
TALENT_ATTACK_KINDS = ("basic", "skill", "enhanced_basic", "ultimate", "fua")


# --------------------------------------------------------------------------- #
# 角色表（内置数据；payload 可逐项覆盖）
# --------------------------------------------------------------------------- #

ROSTER: dict[str, dict[str, Any]] = {
    "1511": {
        "name": "星神★阿哈",
        "aliases": ("xuzhao", "aeon_aha"),
        "path": "欢愉",
        "elation": True,
        "baseSpd": 94.0,
        "traceSpd": 5.0,
        "lcBaseSpd": 12.0,  # 默认按佩戴专武《当第一声「阿哈」响起》+12
        "maxSp": 8.0,
        "energy": "wishpower",
        "energyName": "愿力",
        "rotation": "skill",
        "mechanics": [
            "特殊能量【愿力】：上限 8（可溢出到 10），不受 ERR 加成",
            "专属被动【阿哈时刻在】：【阿哈时刻】底速 = 本体基础速度（含专武）",
            "行迹3【盒中蕴藏的世界】：进战自身拉条 30%（速度 ≥125/150 时欢愉度 +120%/+150%）",
            "战技：指定【「欢愉」令使】并发动量子欢愉追击（净耗 0 战技点）",
            "终结技：拉条【阿哈时刻】20%，进入【欢愉万相】3 回合",
        ],
    },
    "1503": {
        "name": "真珠",
        "aliases": ("pearl",),
        "path": "欢愉",
        "elation": True,
        "baseSpd": 99.0,
        "traceSpd": 9.0,
        "lcBaseSpd": 0.0,
        "maxSp": 180.0,
        "energy": "standard",
        "energyName": "能量",
        "rotation": "auto",
        "mechanics": [
            "指定【美学底本】（不能是自己）",
            "战技：群疗 + 全队好活当赏 +15（基础回能 30 × ERR）",
            "有【深度学习】时自动打强化普攻（群攻群疗，基础回能 20 × ERR）",
            "终结技：真珠全体拉条 10%/15%/30%（按欢愉人数）；4 欢愉时给【美学底本】额外回合",
            "行迹3【艺术壁垒】：【美学底本】（欢愉）下一次开大时真珠 +90 固定能量",
        ],
    },
    "1513": {
        "name": "砂金•戏浪",
        "aliases": ("aventurine_sp",),
        "path": "欢愉",
        "elation": True,
        "baseSpd": 107.0,
        "traceSpd": 9.0,
        "lcBaseSpd": 0.0,
        "maxSp": 130.0,
        "energy": "standard",
        "energyName": "能量",
        "rotation": "skill",
        "mechanics": [
            "天赋：队友每次攻击 +1 热意 +1 笑点；行迹3【旧梦淘金】再 +2 热意（6 次/战技周期）",
            "战技：+4 笑点 +4 热意，【旧梦淘金】充能重置 6（基础回能 30 × ERR）",
            "终结技：+6 笑点 +8 热意，自身速度 +30%（4 回合）",
            "热意过阈值（10/20/30/40/50）立刻在回合外放欢愉技《举杯！敬炽烈一夏》，并把下一次阿哈时刻欢愉技升级为《All in！》",
            "行迹2【纵享惊涛】：单欢愉或三赌牌局时队友攻击 → 【阿哈时刻】+25 固定速度",
        ],
    },
    "1304": {
        "name": "砂金(存护)",
        "aliases": ("aventurine",),
        "path": "存护",
        "elation": False,
        "baseSpd": 106.0,
        "traceSpd": 0.0,
        "lcBaseSpd": 0.0,
        "maxSp": 110.0,
        "energy": "standard",
        "energyName": "能量",
        "rotation": "skill",
        "mechanics": [
            "战技/追击给全队护盾 → 触发阿哈行迹2（+1 愿力）",
            "【盲注】：每次攻击 +1 层，7 层触发 7 段追击（基础回能 7 × ERR）",
        ],
    },
    "1502": {
        "name": "爻光",
        "aliases": ("yaoguang",),
        "path": "欢愉",
        "elation": True,
        "baseSpd": 101.0,
        "traceSpd": 9.0,
        "lcBaseSpd": 0.0,
        "maxSp": 180.0,
        "energy": "standard",
        "energyName": "能量",
        "rotation": "skill",
        "mechanics": [
            "普攻基础回能 30（战技 30，终结技返还 5）",
            "秘技/战技：展开 3 回合结界；结界内自己普攻/战技 +3 笑点，E2 全队速度 +12%",
            "终结技：+5 笑点并给【阿哈时刻】1 个额外回合（20 笑点，E1 为 40）",
            "欢愉万相★心灵感应：阿哈【欢愉万相】期间终结技额外 +12 固定能量 +10 笑点",
        ],
    },
    "1501": {
        "name": "火花",
        "aliases": ("sparxie",),
        "path": "欢愉",
        "elation": True,
        "baseSpd": 107.0,
        "traceSpd": 0.0,
        "lcBaseSpd": 0.0,
        "maxSp": 160.0,
        "energy": "standard",
        "energyName": "能量",
        "rotation": "skill",
        "mechanics": [
            "战技/普攻 +4 笑点（基础回能 30）",
            "终结技：2 + (2/4/8 按其他欢愉人数) 笑点，E4 再 +5",
            "E2：【阿哈时刻】每次结束立刻获得 1 个额外回合",
        ],
    },
    "8009": {
        "name": "开拓者•欢愉",
        "aliases": ("tb_elation",),
        "path": "欢愉",
        "elation": True,
        "baseSpd": 106.0,
        "traceSpd": 0.0,
        "lcBaseSpd": 0.0,
        "maxSp": 160.0,
        "energy": "standard",
        "energyName": "能量",
        "rotation": "skill",
        "mechanics": [
            "天赋：普攻/战技后 +10 固定能量 +3 笑点",
            "终结技：+5 笑点；指定目标是欢愉则立刻放 1 次欢愉技，否则拉条 50%",
        ],
    },
    "1505": {
        "name": "绯英",
        "aliases": ("feiying",),
        "path": "欢愉",
        "elation": True,
        "baseSpd": 104.0,
        "traceSpd": 5.0,
        "lcBaseSpd": 0.0,
        "maxSp": 480.0,
        "energy": "special",
        "energyName": "特殊能量",
        "rotation": "skill",
        "mechanics": [
            "战技：+10 笑点 +60 特殊能量（固定）",
            "获得【好活当赏】时额外回能（默认 = 记账笑点数）",
            "累计每 240 能量触发【狐狸老师】追击（+10 能量，算队友攻击）",
            "480 能量开大；若她是【美学底本】会触发真珠【艺术壁垒】+90",
        ],
    },
    "1506": {
        "name": "银狼LV.999",
        "aliases": ("silverwolf999",),
        "path": "欢愉",
        "elation": True,
        "baseSpd": 110.0,
        "traceSpd": 9.0,
        "lcBaseSpd": 0.0,
        "maxSp": 60.0,
        "energy": "hidden",
        "energyName": "隐藏分",
        "rotation": "skill",
        "mechanics": [
            "战技 +5 笑点；隐藏分 = 全队获得的笑点（欢愉技再 +15）",
            "隐藏分 ≥ 60 开大：自身拉条 100%，进入【无敌玩家】打 3 次强化普攻",
        ],
    },
    "1313": {
        "name": "星期日",
        "aliases": ("sunday",),
        "path": "同谐",
        "elation": False,
        "baseSpd": 96.0,
        "traceSpd": 0.0,
        "lcBaseSpd": 0.0,
        "maxSp": 130.0,
        "energy": "standard",
        "energyName": "能量",
        "rotation": "skill",
        "mechanics": [
            "战技：指定目标拉条 100%",
            "终结技：给指定目标回能 max(40, 20% 能量上限)（固定回能）",
        ],
    },
    "1309": {
        "name": "知更鸟",
        "aliases": ("robin",),
        "path": "同谐",
        "elation": False,
        "baseSpd": 102.0,
        "traceSpd": 5.0,
        "lcBaseSpd": 0.0,
        "maxSp": 160.0,
        "energy": "standard",
        "energyName": "能量",
        "rotation": "skill",
        "mechanics": [
            "终结技：其他队友全体拉条 100%，并召唤 90 速【协奏】倒计时",
        ],
    },
}

ALIASES: dict[str, str] = {}
for _uid, _spec in ROSTER.items():
    for _alias in _spec.get("aliases") or ():
        ALIASES[_alias.lower()] = _uid

EQUIPMENT_META = [
    {"id": "vonwacq", "name": "生命的翁瓦克 (2pc)", "text": "ERR +5%；进战时速度 ≥ 120 则开局拉条 40%"},
    {"id": "godJoy", "name": "神的瞬息欢愉 (2pc)", "text": "速度 +6%；开局拉条 40%"},
    {"id": "windSet4", "name": "晨昏交界的翔鹰 (4pc)", "text": "施放终结技后自身拉条 25%（回合内开大则回合结束再扣）"},
    {"id": "danceS5", "name": "叠5 舞！舞！舞！", "text": "施放终结技后我方全体拉条 24%（可调 dancePct）"},
    {"id": "hasSigLc", "name": "星神★阿哈专武《当第一声「阿哈」响起》", "text": "基础速度 +12；战技给笑点（每 2 回合 1 次）"},
    {"id": "hasSummerLc", "name": "《向浪花掷下盛夏》", "text": "施放欢愉技获【风口】：自身速度 +24%~40%（按常驻处理）"},
]

CONFIG_META = [
    {"key": "maxAV", "label": "模拟上限 (AV)", "default": 300.0, "type": "number", "min": 1, "max": 1000},
    {"key": "useAeonAha", "label": "启用【阿哈时刻在】升格底速", "default": None, "type": "bool"},
    {"key": "useTech", "label": "计入秘技进战效果", "default": True, "type": "bool"},
    {"key": "trace3Advance", "label": "阿哈行迹3 进战自身拉条 30%", "default": True, "type": "bool"},
    {"key": "ultAdvanceAha", "label": "阿哈终结技拉条【阿哈时刻】%", "default": 20.0, "type": "number", "min": 0, "max": 100},
    {"key": "e1Wishpower", "label": "阿哈 E1 开局愿力", "default": 5.0, "type": "number", "min": 0, "max": 10},
    {"key": "e6FirstUltMode", "label": "阿哈 E6 首次终结技", "default": "extra40", "type": "choice", "choices": ["extra40", "advance100"]},
    {"key": "ultSpdPct", "label": "砂金•戏浪终结技自提速%", "default": 30.0, "type": "number", "min": 0, "max": 200},
    {"key": "sanduTeamSpdPct", "label": "三赌牌局全队提速%", "default": 15.0, "type": "number", "min": 0, "max": 200},
    {"key": "sanduFervorGain", "label": "三赌牌局每次队友攻击热意", "default": 1.0, "type": "number", "min": 0, "max": 10},
    {"key": "sanduPunchlineGain", "label": "三赌牌局每次队友攻击笑点", "default": 1.0, "type": "number", "min": 0, "max": 10},
    {"key": "dancePct", "label": "舞！舞！舞！全队拉条%", "default": 24.0, "type": "number", "min": 0, "max": 100},
    {"key": "summerLcSpdPct", "label": "【风口】自提速%", "default": 24.0, "type": "number", "min": 0, "max": 200},
    {"key": "sigLcPunchline", "label": "阿哈专武战技笑点", "default": 10.0, "type": "number", "min": 0, "max": 100},
    {"key": "aeonAhaBaseSpd", "label": "【阿哈时刻】底速", "default": 94.0, "type": "number", "min": 0, "max": 1000},
    {"key": "aeonAhaLcBaseSpd", "label": "【阿哈时刻】专武基础速度", "default": 12.0, "type": "number", "min": 0, "max": 1000},
    {"key": "ahaSpdPct", "label": "【阿哈时刻】额外速度%", "default": 0.0, "type": "number", "min": -100, "max": 1000},
    {"key": "ahaAdvancePct", "label": "开局拉条【阿哈时刻】%", "default": 0.0, "type": "number", "min": 0, "max": 100},
    {"key": "feiyingHaohuoEnergyMode", "label": "绯英好活当赏回能方式", "default": "punchline", "type": "choice", "choices": ["punchline", "flat"]},
    {"key": "feiyingHaohuoEnergy", "label": "绯英好活当赏固定回能（flat）", "default": 20.0, "type": "number", "min": 0, "max": 480},
]

AV_NODES = [
    {"t": 0, "av": 150.0, "label": "0T 首轮 (150 AV)"},
    {"t": 1, "av": 250.0, "label": "1T 次轮 (250 AV)"},
    {"t": 2, "av": 350.0, "label": "2T 三轮 (350 AV)"},
    {"t": 3, "av": 450.0, "label": "3T 四轮 (450 AV)"},
]


# --------------------------------------------------------------------------- #
# 小工具
# --------------------------------------------------------------------------- #

def fmt(x: float, digits: int = 2) -> str:
    """数字格式化：与 web_api.js 的 fmt() 逐位一致（放大后 half-up 再拼串）。

    不用 f"{x:.2f}"：Python 的 ties-to-even 和 JS toFixed 的边界舍入不一致，
    两边输出的文本会差一个末位，对拍就会炸。
    """
    neg = x < 0
    scaled = abs(float(x)) * (10.0 ** digits)
    n = int(math.floor(scaled + 0.5))
    base = 10 ** digits
    ip = n // base
    fp = n % base
    if digits > 0:
        s = f"{ip}.{fp:0{digits}d}"
    else:
        s = f"{ip}"
    if neg and n:
        s = "-" + s
    return s


def fmt_auto(x: float) -> str:
    """报错文案里的数字：整数不带小数点，其余保留 2 位（与 web_api.js 一致）。"""
    s = fmt(x, 2)
    return s[:-3] if s.endswith(".00") else s


def _id_str(value: Any) -> str:
    """id 统一成字符串；1511.0 这种整数值浮点当成 "1511"。"""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def resolve_uid(raw: Any) -> str:
    key = _id_str(raw if raw is not None else "").strip()
    if not key:
        raise ValueError("队伍里有角色没给 id")
    low = key.lower()
    if low in ALIASES:
        return ALIASES[low]
    return key


# 数字串只认十进制写法（与 web_api.js 同一条正则）：Python 的 float() 认 "1_000"
# 这种下划线写法、JS 的 Number() 认 "0x10"，两边各认各的会对不齐。
_NUM_RE = re.compile(r"^[+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]+)?$")


def _num(container: dict[str, Any], key: str, default: float,
         lo: float = -NUM_LIMIT, hi: float = NUM_LIMIT) -> float:
    value = container.get(key, default)
    if value is None or value == "":
        return float(default)
    if isinstance(value, str):
        text = value.strip()
        if not _NUM_RE.match(text):
            raise ValueError(f"参数 {key} 需要是数字，收到 {value!r}")
        number = float(text)
    else:
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"参数 {key} 需要是数字，收到 {value!r}") from exc
    if not math.isfinite(number) or abs(number) > NUM_LIMIT:
        raise ValueError(f"参数 {key} 超出范围，收到 {value!r}")
    if number < lo or number > hi:
        raise ValueError(
            f"参数 {key} 需要在 {fmt_auto(lo)}~{fmt_auto(hi)} 之间，收到 {fmt_auto(number)}"
        )
    return number


def _bool(container: dict[str, Any], key: str, default: bool) -> bool:
    value = container.get(key, default)
    if value is None:
        return bool(default)
    return bool(value)


def cycle_of(av: float) -> int:
    """行动值 → MoC 轮次：av ≤ 150 是 0T，(150, 250] 是 1T，(250, 350] 是 2T……"""
    if av <= CYCLE0_AV + EPS:
        return 0
    return int(math.ceil((av - CYCLE0_AV) / CYCLE_AV - EPS))


# --------------------------------------------------------------------------- #
# 单位
# --------------------------------------------------------------------------- #

class Unit:
    """一个跑条单位（队伍成员）；【阿哈时刻】与协奏倒计时用轻量结构另建。"""

    def __init__(self, slot: int, uid: str, name: str, spec: dict[str, Any],
                 raw: dict[str, Any]) -> None:
        equip = raw.get("equipment") if isinstance(raw.get("equipment"), dict) else {}
        has_sig_lc = _bool(equip, "hasSigLc", uid == "1511")
        self.slot = slot
        self.uid = uid
        self.name = name
        self.elation = _bool(raw, "elation", bool(spec.get("elation", False)))
        self.base_spd = _num(raw, "baseSpd", float(spec.get("baseSpd", 100.0)), 0.0, 10000.0)
        # 光锥基础速度在百分比乘区内：默认只在 hasSigLc 时算专武白值
        lc_default = float(spec.get("lcBaseSpd", 0.0)) if has_sig_lc else 0.0
        self.lc_base_spd = _num(raw, "lcBaseSpd", lc_default, 0.0, 10000.0)
        self.trace_spd = _num(raw, "traceSpd", float(spec.get("traceSpd", 0.0)), -1000.0, 10000.0)
        self.perm_pct = _num(raw, "permPct", 0.0, -100.0, 10000.0)
        self.perm_flat = _num(raw, "permFlat", 0.0, -10000.0, 10000.0)
        self.buff_pct = _num(raw, "buffPct", 0.0, -100.0, 10000.0)
        self.buff_flat = _num(raw, "buffFlat", 0.0, -10000.0, 10000.0)
        self.err = _num(raw, "err", 0.0, -100.0, 10000.0)
        self.eidolon = int(_num(raw, "eidolon", 0.0, 0.0, 6.0))
        self.init_adv = _num(raw, "initAdv", 0.0, 0.0, 100.0)
        self.max_sp = _num(raw, "maxSp", float(spec.get("maxSp", 120.0)), 1.0, 100000.0)
        rotation = str(raw.get("rotation") or spec.get("rotation") or "skill")
        if rotation not in ("auto", "basic", "skill"):
            raise ValueError(f"参数 rotation 需要是 auto/basic/skill，收到 {rotation!r}")
        self.rotation = rotation
        self.energy_type = str(spec.get("energy") or "standard")
        self.energy_name = str(spec.get("energyName") or "能量")
        target = raw.get("targetSlot")
        self.target_slot = None
        if target is not None and target != "":
            self.target_slot = int(_num(raw, "targetSlot", 0.0, 0.0, 3.0))

        # 遗器/光锥开关
        self.equip = {
            "vonwacq": _bool(equip, "vonwacq", False),
            "godJoy": _bool(equip, "godJoy", False),
            "windSet4": _bool(equip, "windSet4", False),
            "danceS5": _bool(equip, "danceS5", False),
            "hasSigLc": has_sig_lc,
            "hasSummerLc": _bool(equip, "hasSummerLc", False),
        }
        if self.equip["vonwacq"]:
            self.err += 5.0
        if self.equip["godJoy"]:
            self.perm_pct += 6.0

        # 行动条状态
        self.rem_dist = DIST_BASE
        self.pending_aa = 0.0
        self.in_turn = False
        self.timed: list[dict[str, Any]] = []  # {"kind","value","turns"(None=常驻),"label"}
        self.haohuo: list[dict[str, Any]] = []  # {"turns","count","label"}
        self.notes: list[str] = []

        # 资源
        self.energy = 0.0
        self.energy_total = 0.0
        self.action_count = 0
        self.turn_count = 0
        self.ult_count = 0
        self.extra_count = 0
        self.fua_count = 0

        # 角色专属状态
        self.huanyu = 0            # 1511：【欢愉万相】剩余回合
        self.trace2_used = False   # 1511：受治疗/护盾回愿力（每个终结技周期 1 次）
        self.sig_lc_cd = 0         # 1511：专武笑点冷却（回合）
        self.depth = 0             # 1503：【深度学习】层数
        self.barrier = False       # 1503：【艺术壁垒】已武装
        self.fervor = 0.0          # 1513：热意
        self.fervor_armed = [False, False, False, False, False]
        self.all_in = False        # 1513：下一次阿哈时刻欢愉技升级为 All in
        self.jiumeng = 6           # 1513：旧梦淘金剩余次数
        self.blind = 0             # 1304：盲注层数
        self.field = 0             # 1502：结界剩余回合
        self.feiy_total = 0.0      # 1505：累计能量
        self.invincible = 0        # 1506：【无敌玩家】剩余强化普攻次数

        self.initial_spd = 0.0


# --------------------------------------------------------------------------- #
# 模拟引擎
# --------------------------------------------------------------------------- #

class Sim:
    def __init__(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            raise ValueError("payload 需要是对象")
        self.cfg = self.parse_config(payload)
        self.units = self.build_units(payload)

        self.av = 0.0
        self.punchline = 0.0
        self.punchline40_done = False
        self.punchline_consumed = 0.0
        self.punchline_granted = 0.0
        self.aha_flat = 0.0
        self.aha = {"rem_dist": DIST_BASE, "pending": 0.0, "in_turn": False}
        self.summons: list[dict[str, Any]] = []
        self.timeline: list[dict[str, Any]] = []
        self.warnings: list[str] = []
        self.notes: list[str] = []
        self.depth = 0
        self.truncated = False
        self.aha_normal_count = 0
        self.aha_extra_count = 0

        # 指定目标
        pearl_char = self.by_uid("1503")
        self.aeste_slot = self.resolve_target_slot(pearl_char, prefer=0)  # 真珠的【美学底本】
        self.lingshi_slot = None  # 阿哈的【「欢愉」令使】（战技指定）
        aha_char = self.by_uid("1511")
        if aha_char is not None:
            self.lingshi_prefer = self.resolve_target_slot(aha_char, prefer=0)
        else:
            self.lingshi_prefer = None

        # 【阿哈时刻】底速解析
        self.use_aeon_aha = self.cfg["use_aeon_aha"]
        if self.use_aeon_aha is None:
            self.use_aeon_aha = aha_char is not None
        else:
            self.use_aeon_aha = bool(self.use_aeon_aha) or aha_char is not None
        if self.cfg["aeon_aha_base_spd"] is None:
            self.aha_base_spd = aha_char.base_spd if aha_char is not None else 94.0
        else:
            self.aha_base_spd = self.cfg["aeon_aha_base_spd"]
        if self.cfg["aeon_aha_lc_base_spd"] is None:
            self.aha_lc_base_spd = aha_char.lc_base_spd if aha_char is not None else 12.0
        else:
            self.aha_lc_base_spd = self.cfg["aeon_aha_lc_base_spd"]

        self.aha_initial_spd = 0.0

    # ----------------------------- 配置与队伍 ----------------------------- #

    def parse_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        e6_mode = str(payload.get("e6FirstUltMode") or "extra40")
        if e6_mode not in ("extra40", "advance100"):
            raise ValueError(f"参数 e6FirstUltMode 需要是 extra40/advance100，收到 {e6_mode!r}")
        fei_mode = str(payload.get("feiyingHaohuoEnergyMode") or "punchline")
        if fei_mode not in ("punchline", "flat"):
            raise ValueError(
                f"参数 feiyingHaohuoEnergyMode 需要是 punchline/flat，收到 {fei_mode!r}"
            )
        use_aeon = payload.get("useAeonAha")
        base_spd = payload.get("aeonAhaBaseSpd")
        lc_spd = payload.get("aeonAhaLcBaseSpd")
        return {
            "max_av": _num(payload, "maxAV", 300.0, 1.0, MAX_AV),
            "use_aeon_aha": None if use_aeon is None else bool(use_aeon),
            "use_tech": _bool(payload, "useTech", True),
            "trace3_advance": _bool(payload, "trace3Advance", True),
            "ult_advance_aha": _num(payload, "ultAdvanceAha", 20.0, 0.0, 100.0),
            "e1_wishpower": _num(payload, "e1Wishpower", 5.0, 0.0, 10.0),
            "e6_mode": e6_mode,
            "ult_spd_pct": _num(payload, "ultSpdPct", 30.0, -100.0, 1000.0),
            "sandu_team_spd_pct": _num(payload, "sanduTeamSpdPct", 15.0, -100.0, 1000.0),
            "sandu_fervor_gain": _num(payload, "sanduFervorGain", 1.0, 0.0, 10.0),
            "sandu_punchline_gain": _num(payload, "sanduPunchlineGain", 1.0, 0.0, 10.0),
            "dance_pct": _num(payload, "dancePct", 24.0, 0.0, 100.0),
            "summer_lc_spd_pct": _num(payload, "summerLcSpdPct", 24.0, -100.0, 1000.0),
            "sig_lc_punchline": _num(payload, "sigLcPunchline", 10.0, 0.0, 100.0),
            "aeon_aha_base_spd": None if base_spd in (None, "") else _num(payload, "aeonAhaBaseSpd", 94.0, 0.0, 1000.0),
            "aeon_aha_lc_base_spd": None if lc_spd in (None, "") else _num(payload, "aeonAhaLcBaseSpd", 12.0, 0.0, 1000.0),
            "aha_spd_pct": _num(payload, "ahaSpdPct", 0.0, -100.0, 1000.0),
            "aha_advance_pct": _num(payload, "ahaAdvancePct", 0.0, 0.0, 100.0),
            "feiying_haohuo_mode": fei_mode,
            "feiying_haohuo_energy": _num(payload, "feiyingHaohuoEnergy", 20.0, 0.0, 10000.0),
        }

    def build_units(self, payload: dict[str, Any]) -> list[Unit]:
        team = payload.get("team")
        if not isinstance(team, list) or not team:
            raise ValueError("参数 team 需要是 1~4 个成员的列表")
        if len(team) > MAX_TEAM:
            raise ValueError(f"参数 team 最多 {MAX_TEAM} 人，收到 {len(team)}")
        units: list[Unit] = []
        for slot, raw in enumerate(team):
            if not isinstance(raw, dict):
                raise ValueError(f"参数 team[{slot}] 需要是对象")
            uid = resolve_uid(raw.get("id"))
            spec = ROSTER.get(uid) or {}
            name = raw.get("name")
            name = str(name).strip() if isinstance(name, str) and name.strip() else str(spec.get("name") or uid)
            units.append(Unit(slot, uid, name, spec, raw))
        return units

    def resolve_target_slot(self, caster: Unit | None, prefer: int | None = None) -> int:
        """指定目标：优先用户给的 targetSlot（不能是自己），默认 slot 0（是自己就顺延）。"""
        n = len(self.units)
        if caster is not None and caster.target_slot is not None:
            requested = caster.target_slot
            if 0 <= requested < n and requested != caster.slot:
                return requested
        candidate = prefer if prefer is not None else 0
        if 0 <= candidate < n and (caster is None or candidate != caster.slot):
            return candidate
        if caster is not None:
            for unit in self.units:
                if unit.slot != caster.slot:
                    return unit.slot
            return caster.slot
        return 0

    # ----------------------------- 查询小工具 ----------------------------- #

    def by_uid(self, uid: str) -> Unit | None:
        for unit in self.units:
            if unit.uid == uid:
                return unit
        return None

    def unit_at(self, slot: int | None) -> Unit | None:
        if slot is None:
            return None
        for unit in self.units:
            if unit.slot == slot:
                return unit
        return None

    def elation_units(self) -> list[Unit]:
        return [u for u in self.units if u.elation]

    def elation_count(self) -> int:
        return len(self.elation_units())

    def huanyu_active(self) -> bool:
        a = self.by_uid("1511")
        return a is not None and a.huanyu > 0

    def single_elation_1513(self) -> bool:
        el = self.elation_units()
        return len(el) == 1 and el[0].uid == "1513"

    def sandu_active(self) -> bool:
        """三赌牌局：队伍里只有 1511+1513 两名欢愉，且 1511 的【欢愉万相】生效。"""
        if self.by_uid("1513") is None or self.by_uid("1511") is None:
            return False
        return self.elation_count() == 2 and self.huanyu_active()

    def trace2_condition(self) -> bool:
        """【纵享惊涛】：单欢愉（只有戏浪）或三赌牌局。"""
        return self.single_elation_1513() or self.sandu_active()

    # ----------------------------- 速度 ----------------------------- #

    def team_pct_extra(self, unit: Unit) -> float:
        extra = 0.0
        yao = self.by_uid("1502")
        if yao is not None and yao.field > 0 and yao.eidolon >= 2:
            extra += 12.0
        if self.sandu_active():
            extra += self.cfg["sandu_team_spd_pct"]
        return extra

    def unit_spd(self, unit: Unit) -> float:
        timed_pct = 0.0
        timed_flat = 0.0
        for buff in unit.timed:
            if buff["kind"] == "pct":
                timed_pct += float(buff["value"])
            else:
                timed_flat += float(buff["value"])
        pct = unit.perm_pct + unit.buff_pct + timed_pct + self.team_pct_extra(unit)
        flat = unit.perm_flat + unit.buff_flat + timed_flat
        spd = (unit.base_spd + unit.lc_base_spd) * (1.0 + pct / 100.0) + flat + unit.trace_spd
        return spd if spd > 0 else 0.0001

    def aha_spd(self) -> float:
        spds = sorted((self.unit_spd(u) for u in self.elation_units()), reverse=True)
        weighted = 0.0
        for i in range(4):
            v = spds[i] if i < len(spds) else 0.0
            weighted += AHA_WEIGHTS[i] * v
        base = (self.aha_base_spd + self.aha_lc_base_spd) if self.use_aeon_aha else 80.0
        return (base + weighted + self.aha_flat) * (1.0 + self.cfg["aha_spd_pct"] / 100.0)

    def aha_base_value(self) -> float:
        return (self.aha_base_spd + self.aha_lc_base_spd) if self.use_aeon_aha else 80.0

    # ----------------------------- 行动条 ----------------------------- #

    def advance_unit(self, unit: Unit, pct: float, self_source: bool = False,
                     reason: str = "") -> None:
        if pct <= 0:
            return
        if unit.rem_dist <= 0 and unit.in_turn:
            # 自己回合里触发的自身拉条挂起，回合结束重置 10000 后再扣；
            # 外部拉条打在正在行动的单位上不吃（舞！舞！舞！原文）。
            if self_source:
                unit.pending_aa += pct
            return
        unit.rem_dist = max(0.0, unit.rem_dist - DIST_BASE * pct / 100.0)

    def advance_aha(self, pct: float, reason: str = "") -> None:
        if pct <= 0:
            return
        a = self.aha
        if a["rem_dist"] <= 0 and a["in_turn"]:
            a["pending"] += pct
            return
        a["rem_dist"] = max(0.0, a["rem_dist"] - DIST_BASE * pct / 100.0)

    def advance_allies(self, source: Unit, pct: float) -> None:
        """舞！舞！舞！这类全队拉条：正在自己行动的开大者不吃自己那口。"""
        for unit in self.units:
            if unit is source and unit.in_turn:
                continue
            self.advance_unit(unit, pct, self_source=(unit is source))

    # ----------------------------- 资源 ----------------------------- #

    def gain_punchline(self, amount: float, reason: str = "") -> None:
        if amount == 0:
            return
        self.punchline += amount
        self.punchline_granted += amount
        wolf = self.by_uid("1506")
        if wolf is not None and amount > 0:
            self.gain_energy(wolf, amount, fixed=True, reason="隐藏分·笑点同步")
        self.check_punchline40()

    def check_punchline40(self) -> None:
        if self.punchline40_done or self.punchline < 40.0:
            return
        self.punchline40_done = True
        a = self.by_uid("1511")
        if a is not None:
            self.gain_wishpower(a, 1.0, "笑点首达 40")
            self.notes.append("笑点首达 40：星神★阿哈 +1 愿力，全队暴伤 +40%（3 回合，本工具不模拟伤害）")

    def gain_wishpower(self, unit: Unit, amount: float, reason: str = "") -> None:
        if amount <= 0:
            return
        unit.energy = min(10.0, unit.energy + amount)  # 愿力可溢出到 10
        unit.energy_total += amount
        self.maybe_ult(unit)

    def gain_fervor(self, unit: Unit, amount: float, reason: str = "") -> None:
        if amount <= 0 or unit.uid != "1513":
            return
        unit.fervor = min(FERVOR_CAP, unit.fervor + amount)
        self.check_fervor(unit)

    def gain_energy(self, unit: Unit, amount: float, fixed: bool = False,
                    reason: str = "") -> None:
        if amount == 0:
            return
        if unit.energy_type == "wishpower":
            self.gain_wishpower(unit, amount, reason)
            return
        if unit.energy_type in ("hidden", "special"):
            gain = amount
        else:
            gain = amount if fixed else amount * (1.0 + unit.err / 100.0)
        unit.energy = min(float(unit.max_sp), unit.energy + gain)
        unit.energy_total += gain
        if unit.uid == "1505":
            unit.feiy_total += gain
            self.check_feiying_milestone(unit)
        self.maybe_ult(unit)

    def check_feiying_milestone(self, unit: Unit) -> None:
        """绯英累计每 240 能量触发一次【狐狸老师】追击。"""
        if unit.uid != "1505":
            return
        while unit.feiy_total >= 240.0 and self.depth <= MAX_NEST:
            unit.feiy_total -= 240.0
            unit.fua_count += 1
            self.event("fua", unit, "【狐狸老师】追加攻击", ["+10 特殊能量（固定）"])
            self.gain_energy(unit, 10.0, fixed=True, reason="狐狸老师")
            self.on_attack(unit, "fua")

    def maybe_ult(self, unit: Unit) -> None:
        if self.depth > MAX_NEST:
            return
        threshold = 8.0 if unit.energy_type == "wishpower" else float(unit.max_sp)
        guard = 0
        while unit.energy >= threshold - EPS and guard < 4:
            guard += 1
            self.cast_ult(unit)

    # ----------------------------- Buff ----------------------------- #

    def add_timed_buff(self, unit: Unit, kind: str, value: float, turns: int | None,
                       label: str) -> None:
        for buff in unit.timed:
            if buff["label"] == label:
                buff["value"] = float(value)
                buff["turns"] = turns
                buff["kind"] = kind
                return
        unit.timed.append({"kind": kind, "value": float(value), "turns": turns, "label": label})

    def grant_haohuo(self, targets: list[Unit], count: float, label: str) -> None:
        for unit in targets:
            unit.haohuo.append({"turns": 2, "count": float(count), "label": label})
            if unit.uid == "1505":
                if self.cfg["feiying_haohuo_mode"] == "flat":
                    gain = self.cfg["feiying_haohuo_energy"]
                else:
                    gain = float(count)
                if gain > 0:
                    self.event("note", unit, "绯英·好活当赏回能",
                               [f"+{fmt(gain)} 特殊能量"])
                    self.gain_energy(unit, gain, fixed=True, reason="好活当赏")

    # ----------------------------- 事件 ----------------------------- #

    def event(self, ev_type: str, unit: Unit | None, label: str,
              details: list[str] | None = None, *, kind: str = "unit",
              extra: bool = False, name: str | None = None) -> None:
        if len(self.timeline) >= MAX_TIMELINE:
            self.truncated = True
            return
        a = self.by_uid("1511")
        sp = self.by_uid("1513")
        res = {
            "punchline": self.punchline,
            "wishpower": a.energy if a is not None else None,
            "fervor": sp.fervor if sp is not None else None,
            "energy": unit.energy if unit is not None and unit.energy_type != "wishpower" else None,
        }
        self.timeline.append({
            "av": self.av,
            "t": cycle_of(self.av),
            "kind": kind,
            "slot": unit.slot if unit is not None else None,
            "name": name or (unit.name if unit is not None else "【阿哈时刻】"),
            "type": ev_type,
            "extra": bool(extra),
            "label": label,
            "details": list(details or []),
            "res": res,
        })

    # ----------------------------- 攻击钩子 ----------------------------- #

    def on_attack(self, unit: Unit, kind: str) -> None:
        # 开拓者•欢愉 天赋：自己的普攻/战技后 +10 固定能量 +3 笑点
        if unit.uid == "8009" and kind in ("basic", "skill"):
            self.gain_energy(unit, 10.0, fixed=True, reason="天赋")
            self.gain_punchline(3.0, "天赋")

        # 砂金（存护）【盲注】：每次攻击 +1 层（自己的追击不再叠层）
        avent = self.by_uid("1304")
        if avent is not None and not (unit is avent and kind == "fua"):
            avent.blind += 1
            if avent.blind >= 7:
                avent.blind = 0
                self.do_aventurine_fua(avent)

        # 砂金•戏浪 天赋 / 旧梦淘金 / 三赌牌局
        sp = self.by_uid("1513")
        if sp is not None and unit is not sp and kind in TALENT_ATTACK_KINDS:
            self.gain_fervor(sp, 1.0, "天赋")
            self.gain_punchline(1.0, "戏浪天赋")
            if sp.jiumeng > 0:
                sp.jiumeng -= 1
                self.gain_fervor(sp, 2.0, "旧梦淘金")
            if self.sandu_active():
                self.gain_fervor(sp, self.cfg["sandu_fervor_gain"], "三赌牌局")
                self.gain_punchline(self.cfg["sandu_punchline_gain"], "三赌牌局")

        # 行迹2【纵享惊涛】：队友攻击 → 【阿哈时刻】+25 固定速度（到下一次阿哈时刻结束）
        if sp is not None and unit is not sp and self.trace2_condition():
            if self.aha_flat < 25.0:
                self.aha_flat = 25.0
                self.notes.append("【纵享惊涛】触发：【阿哈时刻】固定速度 +25（到下一次阿哈时刻结束）")

    def on_heal_or_shield(self, source: Unit, label: str) -> None:
        """阿哈行迹2【戏中人的异想国】：受队友治疗/护盾 +1 愿力（每个终结技周期 1 次）。"""
        a = self.by_uid("1511")
        if a is None or a.trace2_used:
            return
        a.trace2_used = True
        self.event("note", a, "戏中人的异想国", [f"{label} → 愿力 +1"])
        self.gain_wishpower(a, 1.0, "戏中人的异想国")

    def check_barrier(self, unit: Unit) -> None:
        """【艺术壁垒】：【美学底本】（欢愉）开大时真珠 +90 固定能量。"""
        pearl = self.by_uid("1503")
        if pearl is None or not pearl.barrier or pearl is unit:
            return
        if unit.slot != self.aeste_slot or not unit.elation:
            return
        pearl.barrier = False
        self.event("note", pearl, "艺术壁垒触发", ["真珠 +90 固定能量（不吃 ERR）"])
        self.gain_energy(pearl, 90.0, fixed=True, reason="艺术壁垒")

    # ----------------------------- 热意阈值 ----------------------------- #

    def check_fervor(self, sp: Unit, depth: int = 0) -> None:
        if sp.uid != "1513" or depth > MAX_NEST:
            return
        thresholds = FERVOR_THRESHOLDS[min(sp.eidolon, 2)]
        for i in range(5):
            if i < len(thresholds):
                t = thresholds[i]
                if sp.fervor >= t and not sp.fervor_armed[i]:
                    sp.fervor_armed[i] = True
                    self.trigger_juban(sp, depth + 1)
                elif sp.fervor < t:
                    sp.fervor_armed[i] = False

    def trigger_juban(self, sp: Unit, depth: int) -> None:
        """热意过阈值：回合外欢愉技《举杯！敬炽烈一夏》，并把下一次阿哈时刻欢愉技升级。"""
        self.event("elation_skill", sp, "举杯！敬炽烈一夏（回合外欢愉技）",
                   ["固定 +20 笑点", "下一次【阿哈时刻】欢愉技升级为《All in！》"], extra=True)
        self.gain_punchline(20.0, "举杯！敬炽烈一夏")
        sp.all_in = True
        self.elation_skill_common(sp, "举杯！敬炽烈一夏")
        if sp.eidolon >= 2:
            self.gain_fervor(sp, 4.0, "E2 欢愉技")
        self.on_attack(sp, "elation_skill")

    # ----------------------------- 欢愉技 ----------------------------- #

    def elation_skill_common(self, unit: Unit, label: str) -> None:
        """所有欢愉技共用的结算：银狼隐藏分 +15、专武【风口】（笑点由调用方给一次）。"""
        wolf = self.by_uid("1506")
        if wolf is not None:
            self.event("note", wolf, "隐藏分 +15", [f"{unit.name} 施放欢愉技"])
            self.gain_energy(wolf, 15.0, fixed=True, reason="欢愉技")
        if unit.equip["hasSummerLc"]:
            self.add_timed_buff(unit, "pct", self.cfg["summer_lc_spd_pct"], None, "【风口】")
            self.notes.append(f"{unit.name} 施放欢愉技触发【风口】：速度 +{fmt(self.cfg['summer_lc_spd_pct'], 0)}%")

    def cast_elation_skill(self, unit: Unit) -> None:
        if self.depth > MAX_NEST:
            return
        self.depth += 1
        try:
            if unit.uid == "1513":
                if unit.all_in:
                    unit.all_in = False
                    unit.fervor = 0.0
                    for i in range(5):
                        unit.fervor_armed[i] = False
                    label = "All in！敬炽烈一夏（欢愉技）"
                    details = ["固定 +20 笑点", "消耗全部热意"]
                else:
                    label = "举杯！敬炽烈一夏（欢愉技）"
                    details = ["固定 +20 笑点"]
                self.event("elation_skill", unit, label, details)
                self.gain_punchline(20.0, label)
                self.elation_skill_common(unit, label)
                if unit.eidolon >= 2:
                    self.gain_fervor(unit, 4.0, "E2 欢愉技")
                self.on_attack(unit, "elation_skill")
                return
            label = "欢愉技"
            details = ["固定 +20 笑点"]
            self.event("elation_skill", unit, f"{unit.name} 的欢愉技", details)
            self.gain_punchline(20.0, "欢愉技")
            if unit.uid == "1511":
                self.event("note", unit, "自身动作回能", ["愿力 +1"])
                self.gain_wishpower(unit, 1.0, "欢愉技")
            self.elation_skill_common(unit, label)
            self.on_attack(unit, "elation_skill")
        finally:
            self.depth -= 1

    # ----------------------------- 出招 ----------------------------- #

    def rotation_of(self, unit: Unit) -> str:
        return unit.rotation

    def do_action(self, unit: Unit, extra: bool = False) -> None:
        unit.action_count += 1
        if unit.uid == "1506" and unit.invincible > 0:
            unit.invincible -= 1
            self.do_enhanced_basic(unit, extra)
            return
        if unit.uid == "1503":
            if unit.depth > 0:
                self.do_pearl_enhanced_basic(unit, extra)
            else:
                self.do_skill(unit, extra)
            return
        if self.rotation_of(unit) == "basic":
            self.do_basic(unit, extra)
        else:
            self.do_skill(unit, extra)

    def do_basic(self, unit: Unit, extra: bool = False) -> None:
        details: list[str] = []
        energy_base = 30.0 if unit.uid == "1502" else 20.0
        if unit.uid == "1502":
            details.append("基础回能 30（普攻）")
        else:
            details.append("基础回能 20（普攻）")
        if unit.uid == "1501":
            self.gain_punchline(4.0, "普攻")
            details.append("笑点 +4")
        if unit.uid == "1502" and unit.field > 0:
            self.gain_punchline(3.0, "结界内普攻")
            details.append("结界内 +3 笑点")
        self.event("basic", unit, f"{unit.name} 的普攻", details, extra=extra)
        self.gain_energy(unit, energy_base, reason="普攻")
        self.on_attack(unit, "basic")

    def do_skill(self, unit: Unit, extra: bool = False) -> None:
        details: list[str] = []
        label = f"{unit.name} 的战技"
        if unit.uid == "1511":
            target = self.unit_at(self.lingshi_prefer)
            if self.lingshi_slot is None and target is not None:
                self.lingshi_slot = target.slot
                details.append(f"指定 {target.name} 为【「欢愉」令使】（欢愉度 +20%）")
            if unit.equip["hasSigLc"] and unit.sig_lc_cd <= 0:
                unit.sig_lc_cd = 2
                self.gain_punchline(self.cfg["sig_lc_punchline"], "专武")
                details.append(f"专武：笑点 +{fmt(self.cfg['sig_lc_punchline'], 0)}")
            details.append("愿力 +1")
            self.event("skill", unit, label, details, extra=extra)
            self.gain_wishpower(unit, 1.0, "战技")
            unit.fua_count += 1
            self.event("fua", unit, "此乃令使，阿哈认证™·量子欢愉追击",
                       ["算队友攻击（砂金•戏浪天赋/纵享惊涛）"], extra=extra)
            self.on_attack(unit, "fua")
            return
        if unit.uid == "1503":
            self.event("skill", unit, label, ["群疗", "全队好活当赏 +15", "基础回能 30 × (1+ERR)"],
                       extra=extra)
            self.grant_haohuo(list(self.units), 15.0, "真珠战技")
            self.gain_energy(unit, 30.0, reason="战技")
            self.on_heal_or_shield(unit, "真珠战技群疗")
            self.on_attack(unit, "skill")
            return
        if unit.uid == "1513":
            self.event("skill", unit, label,
                       ["笑点 +4", "热意 +4", "旧梦淘金充能重置 6", "基础回能 30 × (1+ERR)"],
                       extra=extra)
            self.gain_punchline(4.0, "战技")
            unit.jiumeng = 6
            self.gain_fervor(unit, 4.0, "战技")
            self.gain_energy(unit, 30.0, reason="战技")
            self.on_attack(unit, "skill")
            return
        if unit.uid == "1304":
            self.event("skill", unit, label, ["全队护盾", "基础回能 30 × (1+ERR)"], extra=extra)
            self.gain_energy(unit, 30.0, reason="战技")
            self.on_heal_or_shield(unit, "砂金战技护盾")
            self.on_attack(unit, "skill")
            return
        if unit.uid == "1502":
            unit.field = 3
            self.event("skill", unit, label,
                       ["结界 3 回合", "结界内自己普攻/战技 +3 笑点", "基础回能 30 × (1+ERR)"],
                       extra=extra)
            self.gain_punchline(3.0, "结界内战技")
            self.gain_energy(unit, 30.0, reason="战技")
            self.on_attack(unit, "skill")
            return
        if unit.uid == "1501":
            self.event("skill", unit, label, ["笑点 +4", "基础回能 30 × (1+ERR)"], extra=extra)
            self.gain_punchline(4.0, "战技")
            self.gain_energy(unit, 30.0, reason="战技")
            self.on_attack(unit, "skill")
            return
        if unit.uid == "8009":
            self.event("skill", unit, label,
                       ["基础回能 30 × (1+ERR)", "天赋：+10 固定能量 +3 笑点"], extra=extra)
            self.gain_energy(unit, 30.0, reason="战技")
            self.on_attack(unit, "skill")
            return
        if unit.uid == "1505":
            self.event("skill", unit, label,
                       ["笑点 +10", "特殊能量 +60（固定）"], extra=extra)
            self.gain_punchline(10.0, "战技")
            self.gain_energy(unit, 60.0, fixed=True, reason="战技")
            self.on_attack(unit, "skill")
            return
        if unit.uid == "1506":
            self.event("skill", unit, label, ["笑点 +5", "隐藏分同步全队笑点"], extra=extra)
            self.gain_punchline(5.0, "战技")
            self.on_attack(unit, "skill")
            return
        if unit.uid == "1313":
            target = self.unit_at(self.resolve_target_slot(unit))
            if target is not None:
                self.advance_unit(target, 100.0, reason="星期日战技")
                details.append(f"{target.name} 拉条 100%")
            self.event("skill", unit, label, details + ["基础回能 30 × (1+ERR)"], extra=extra)
            self.gain_energy(unit, 30.0, reason="战技")
            self.on_attack(unit, "skill")
            return
        # 其他/自定义角色
        self.event("skill", unit, label, ["基础回能 30 × (1+ERR)"], extra=extra)
        self.gain_energy(unit, 30.0, reason="战技")
        self.on_attack(unit, "skill")

    def do_enhanced_basic(self, unit: Unit, extra: bool = False) -> None:
        """银狼LV.999【无敌玩家】强化普攻（+5 笑点按她的战技同值处理）。"""
        self.event("enhanced_basic", unit, f"{unit.name} 的强化普攻（无敌玩家）",
                   ["笑点 +5"], extra=extra)
        self.gain_punchline(5.0, "强化普攻")
        self.on_attack(unit, "enhanced_basic")

    def do_pearl_enhanced_basic(self, unit: Unit, extra: bool = False) -> None:
        unit.depth -= 1
        self.event("enhanced_basic", unit, "真珠的强化普攻《行笔，幻造星月》",
                   ["消耗 1 层【深度学习】", "群攻群疗", "基础回能 20 × (1+ERR)"], extra=extra)
        self.gain_energy(unit, 20.0, reason="强化普攻")
        self.on_heal_or_shield(unit, "真珠强化普攻群疗")
        self.on_attack(unit, "enhanced_basic")

    def do_aventurine_fua(self, unit: Unit) -> None:
        unit.fua_count += 1
        self.event("fua", unit, "砂金的 7 段追加攻击（盲注满层）",
                   ["基础回能 7 × (1+ERR)", "全队护盾"])
        self.gain_energy(unit, 7.0, reason="追击")
        self.on_heal_or_shield(unit, "砂金追击护盾")
        self.on_attack(unit, "fua")

    # ----------------------------- 终结技 ----------------------------- #

    def cast_ult(self, unit: Unit) -> None:
        if self.depth > MAX_NEST:
            self.warnings.append("嵌套层数超过上限，跳过一次终结技结算")
            return
        self.depth += 1
        try:
            # 先扣资源再结算效果：嵌套事件（艺术壁垒回能、额外回合出招）里如果
            # 资源还没扣，会被满能量再次触发一次终结技（踩过：同一次行动连开两个大）。
            details: list[str] = []
            if unit.energy_type == "wishpower":
                unit.energy = max(0.0, unit.energy - 8.0)
                details.append("消耗 8 愿力")
            else:
                unit.energy = 0.0
            unit.ult_count += 1
            self.event("ultimate", unit, f"{unit.name} 的终结技", details)

            if unit.uid == "1511":
                self.ult_1511(unit)
            elif unit.uid == "1503":
                self.ult_1503(unit)
            elif unit.uid == "1513":
                self.ult_1513(unit)
            elif unit.uid == "1502":
                self.ult_1502(unit)
            elif unit.uid == "1501":
                self.ult_1501(unit)
            elif unit.uid == "8009":
                self.ult_8009(unit)
            elif unit.uid == "1506":
                self.ult_1506(unit)
            elif unit.uid == "1313":
                self.ult_1313(unit)
            elif unit.uid == "1309":
                self.ult_1309(unit)

            self.check_barrier(unit)

            # 通用遗器：风套自身拉条 25%、舞舞舞全队拉条
            if unit.equip["windSet4"]:
                self.event("note", unit, "晨昏交界的翔鹰", ["自身拉条 25%"])
                self.advance_unit(unit, 25.0, self_source=True, reason="风套")
            if unit.equip["danceS5"]:
                self.event("note", unit, "舞！舞！舞！", [f"我方全体拉条 {fmt(self.cfg['dance_pct'], 0)}%"])
                self.advance_allies(unit, self.cfg["dance_pct"])
            # 标准能量开大返还 +5（吃 ERR）
            if unit.energy_type == "standard":
                self.gain_energy(unit, 5.0, reason="终结技返还")
            self.maybe_ult(unit)
        finally:
            self.depth -= 1

    def ult_1511(self, u: Unit) -> None:
        u.trace2_used = False
        details: list[str] = []
        if u.eidolon >= 6 and u.ult_count == 1 and self.cfg["e6_mode"] == "advance100":
            self.aha["rem_dist"] = 0.0
            self.gain_punchline(100.0, "E6 首次终结技")
            details.append("E6 首次终结技：【阿哈时刻】拉条 100% + 笑点 +100")
        else:
            self.advance_aha(self.cfg["ult_advance_aha"], reason="阿哈终结技")
            details.append(f"【阿哈时刻】拉条 {fmt(self.cfg['ult_advance_aha'], 0)}%")
            if u.eidolon >= 6 and u.ult_count == 1 and self.cfg["e6_mode"] == "extra40":
                details.append("E6 首次终结技：【阿哈时刻】获得 1 个计入 40 笑点的额外回合")
        self.event("note", u, "啊哈！宇宙笑点大爆炸", details)
        u.huanyu = 3
        self.notes.append("星神★阿哈进入【欢愉万相】3 回合（笑点升格爽点，阿哈时刻结束返还 10%）")
        if self.sandu_active():
            self.notes.append("三赌牌局生效：全队速度 +%s%%" % fmt(self.cfg["sandu_team_spd_pct"], 0))
        if u.eidolon >= 6 and u.ult_count == 1 and self.cfg["e6_mode"] == "extra40":
            self.do_aha(is_extra=True, fixed=40.0)

    def ult_1503(self, u: Unit) -> None:
        self.grant_haohuo(list(self.units), 20.0, "真珠终结技")
        u.depth = 3
        u.barrier = True
        count = self.elation_count()
        pct = 10.0 if count == 1 else (15.0 if count == 2 else 30.0)
        target = self.unit_at(self.aeste_slot)
        details = [
            "全队好活当赏 +20",
            "【深度学习】充能 3",
            f"欢愉 {count} 人 → 【美学底本】拉条 {fmt(pct, 0)}%",
        ]
        if count >= 4:
            details.append("4 欢愉：【美学底本】额外回合（+60 笑点，E2 +120）")
        self.event("note", u, "鉴映灵魂的底色", details)
        if target is not None:
            self.advance_unit(target, pct, reason="真珠终结技")
        if count >= 4 and target is not None:
            grant = 120.0 if u.eidolon >= 2 else 60.0
            haohuo = 60.0 if u.eidolon >= 2 else 30.0
            self.do_extra_turn(target, "真珠终结技·【美学底本】额外回合",
                               grant_punchline=grant, grant_haohuo=haohuo)
        if u.eidolon >= 2:
            for x in self.elation_units():
                if x is not u and x.slot != self.aeste_slot:
                    self.advance_unit(x, pct, reason="真珠 E2")

    def ult_1513(self, u: Unit) -> None:
        self.event("note", u, "胜局，凌越飓浪之上",
                   ["笑点 +6", "热意 +8",
                    f"自身速度 +{fmt(self.cfg['ult_spd_pct'], 0)}%（4 回合）",
                    "基础回能返还 +5 × (1+ERR)"])
        self.gain_punchline(6.0, "终结技")
        self.gain_fervor(u, 8.0, "终结技")
        self.add_timed_buff(u, "pct", self.cfg["ult_spd_pct"], 4, "胜局，凌越飓浪之上")
        self.on_attack(u, "ultimate")

    def ult_1502(self, u: Unit) -> None:
        fixed = 40.0 if u.eidolon >= 1 else 20.0
        details = ["笑点 +5", f"【阿哈时刻】额外回合（计入 {fmt(fixed, 0)} 笑点，不消耗笑点池）"]
        if self.huanyu_active():
            details.append("欢愉万相★心灵感应：+12 固定能量 +10 笑点")
        self.event("note", u, "爻光终结技", details)
        self.gain_punchline(5.0, "终结技")
        self.do_aha(is_extra=True, fixed=fixed)
        if self.huanyu_active():
            self.gain_energy(u, 12.0, fixed=True, reason="心灵感应")
            self.gain_punchline(10.0, "心灵感应")

    def ult_1501(self, u: Unit) -> None:
        others = sum(1 for x in self.units if x.elation and x is not u)
        bonus = 8.0 if others >= 3 else (4.0 if others == 2 else (2.0 if others >= 1 else 0.0))
        gain = 2.0 + bonus + (5.0 if u.eidolon >= 4 else 0.0)
        self.event("note", u, "火花终结技",
                   [f"其他欢愉 {others} 人 → 笑点 +{fmt(gain, 0)}"])
        self.gain_punchline(gain, "终结技")

    def ult_8009(self, u: Unit) -> None:
        target = self.unit_at(self.resolve_target_slot(u))
        details = ["笑点 +5"]
        if target is not None and target.elation:
            details.append(f"{target.name} 立刻施放 1 次欢愉技（计入 20 笑点）")
        elif target is not None:
            details.append(f"{target.name} 拉条 50%")
        self.event("note", u, "开拓者•欢愉终结技", details)
        self.gain_punchline(5.0, "终结技")
        if target is not None:
            if target.elation:
                self.cast_elation_skill(target)
            else:
                self.advance_unit(target, 50.0, reason="开拓者终结技")

    def ult_1506(self, u: Unit) -> None:
        self.event("note", u, "无敌玩家，启动！",
                   ["自身拉条 100%", "【无敌玩家】：接下来 3 次强化普攻"])
        u.invincible = 3
        self.advance_unit(u, 100.0, self_source=True, reason="银狼终结技")

    def ult_1313(self, u: Unit) -> None:
        target = self.unit_at(self.resolve_target_slot(u))
        gain = 40.0
        if target is not None:
            gain = max(40.0, 0.2 * float(target.max_sp))
        self.event("note", u, "星期日终结技",
                   [f"指定目标回复 {fmt(gain)} 固定能量（不吃 ERR）" if target is not None else "没有合法目标"])
        if target is not None:
            self.gain_energy(target, gain, fixed=True, reason="星期日终结技")

    def ult_1309(self, u: Unit) -> None:
        self.event("note", u, "知更鸟终结技",
                   ["其他队友全体拉条 100%", "召唤 90 速【协奏】倒计时"])
        for x in self.units:
            if x is not u:
                self.advance_unit(x, 100.0, reason="知更鸟终结技")
        self.summons = [{"name": "【协奏】倒计时", "spd": 90.0, "rem_dist": DIST_BASE}]

    # ----------------------------- 额外回合 ----------------------------- #

    def do_extra_turn(self, unit: Unit, label: str, grant_punchline: float = 0.0,
                      grant_haohuo: float = 0.0) -> None:
        if self.depth > MAX_NEST:
            return
        self.depth += 1
        try:
            unit.extra_count += 1
            details: list[str] = ["不重置行动条距离、不递减常规 Buff 回合数"]
            if grant_punchline > 0:
                details.append(f"笑点 +{fmt(grant_punchline, 0)}（额外回合结束时结算）")
            if grant_haohuo > 0:
                details.append(f"好活当赏 +{fmt(grant_haohuo, 0)}")
            self.event("extra_turn", unit, label, details, extra=True)
            if grant_haohuo > 0:
                self.grant_haohuo([unit], grant_haohuo, label)
            if grant_punchline > 0:
                self.gain_punchline(grant_punchline, label)
            self.do_action(unit, extra=True)
            if grant_punchline > 0:
                removed = min(self.punchline, grant_punchline)
                self.punchline -= removed
                tail = ""
                if self.huanyu_active():
                    self.punchline += removed * 0.1
                    tail = "（欢愉万相返还 10%）"
                self.event("note", unit, "额外回合笑点结算",
                           [f"回收 {fmt(removed, 0)} 笑点{tail}"], extra=True)
        finally:
            self.depth -= 1

    # ----------------------------- 【阿哈时刻】 ----------------------------- #

    def do_aha(self, is_extra: bool = False, fixed: float = 0.0) -> None:
        if self.depth > MAX_NEST:
            return
        self.depth += 1
        try:
            a = self.aha
            a["in_turn"] = True
            participants = self.elation_units()
            if is_extra:
                self.aha_extra_count += 1
                self.event("aha_extra", None,
                           f"【阿哈时刻】额外回合（计入 {fmt(fixed, 0)} 笑点）",
                           ["不消耗笑点池", "不重置【阿哈时刻】行动条距离"],
                           kind="aha", extra=True)
            else:
                self.aha_normal_count += 1
                self.event("aha", None, "【阿哈时刻】触发",
                           ["解除欢愉角色负面", "全体欢愉角色各施放 1 次欢愉技", "结算并消耗全部笑点"],
                           kind="aha")
            for unit in participants:
                self.cast_elation_skill(unit)
            if is_extra:
                self.grant_haohuo(participants, fixed, "阿哈时刻额外回合")
            else:
                consumed = self.punchline
                self.punchline = 0.0
                self.punchline_consumed += consumed
                details = [f"消耗笑点 {fmt(consumed, 0)}"]
                if self.huanyu_active():
                    refund = consumed * 0.1
                    self.punchline += refund
                    details.append(f"欢愉万相返还 10%（+{fmt(refund)}）")
                self.event("note", None, "【阿哈时刻】笑点结算", details, kind="aha")
                self.grant_haohuo(participants, consumed, "阿哈时刻")
            self.punchline40_done = False
            self.aha_flat = 0.0
            # 1501 火花 E2：阿哈时刻每次结束立刻额外回合
            spark = self.by_uid("1501")
            has_e2 = spark is not None and spark.eidolon >= 2
            if not is_extra:
                a["rem_dist"] = max(0.0, DIST_BASE - DIST_BASE * a["pending"] / 100.0)
                a["pending"] = 0.0
            a["in_turn"] = False
            if has_e2:
                self.do_extra_turn(spark, "火花 E2·【阿哈时刻】结束额外回合")
        finally:
            self.depth -= 1

    # ----------------------------- 战斗开始 ----------------------------- #

    def battle_start(self) -> None:
        self.event("battle", None, "进入战斗", [f"模拟窗口 [0, {fmt(self.cfg['max_av'], 0)}] AV"],
                   kind="system", name="战斗")
        aha_extra_from_tech = False
        if self.cfg["use_tech"]:
            for unit in self.units:
                if unit.uid == "1511":
                    self.event("tech", unit, "秘技《ABRACADABRA！》",
                               ["【阿哈时刻】获得 1 个计入 20 笑点的额外回合"])
                    aha_extra_from_tech = True
                elif unit.uid == "1503":
                    unit.depth = 2
                    unit.barrier = True
                    self.event("tech", unit, "真珠秘技",
                               ["【深度学习】2 层", "全队好活当赏 +20", "【艺术壁垒】武装"])
                    self.grant_haohuo(list(self.units), 20.0, "真珠秘技")
                elif unit.uid == "1513":
                    self.event("tech", unit, "砂金•戏浪秘技", ["热意 +2", "全队好活当赏 +20"])
                    self.gain_fervor(unit, 2.0, "秘技")
                    self.grant_haohuo(list(self.units), 20.0, "砂金•戏浪秘技")
                elif unit.uid == "1502":
                    self.event("tech", unit, "爻光秘技：自动施放战技",
                               ["结界 3 回合（不吃战技点）"])
                    self.do_skill(unit)
            # 秘技给的额外回合等全部秘技结算完再走（口径更接近进战顺序）
            if aha_extra_from_tech:
                self.do_aha(is_extra=True, fixed=20.0)

        for unit in self.units:
            unit.initial_spd = self.unit_spd(unit)
        self.aha_initial_spd = self.aha_spd()

        for unit in self.units:
            if unit.equip["vonwacq"]:
                if unit.initial_spd >= 120.0:
                    self.event("note", unit, "生命的翁瓦克", ["速度 ≥ 120：开局拉条 40%"])
                    self.advance_unit(unit, 40.0, reason="翁瓦克")
                else:
                    self.event("note", unit, "生命的翁瓦克",
                               [f"速度 {fmt(unit.initial_spd, 1)} < 120：开局拉条不触发"])
            if unit.equip["godJoy"]:
                self.event("note", unit, "神的瞬息欢愉", ["开局拉条 40%"])
                self.advance_unit(unit, 40.0, reason="神的瞬息欢愉")
            if unit.init_adv > 0:
                self.advance_unit(unit, unit.init_adv, reason="开局拉条")

        aha = self.by_uid("1511")
        if aha is not None:
            if self.cfg["trace3_advance"]:
                self.event("note", aha, "行迹3【盒中蕴藏的世界】", ["进战自身拉条 30%"])
                self.advance_unit(aha, 30.0, reason="行迹3")
            if aha.eidolon >= 1 and self.cfg["e1_wishpower"] > 0:
                self.event("note", aha, "E1 开局回能",
                           [f"愿力 +{fmt(self.cfg['e1_wishpower'], 0)}"])
                self.gain_wishpower(aha, self.cfg["e1_wishpower"], "E1")
            if aha.initial_spd >= 150.0:
                aha.notes.append("实战速度 ≥ 150：欢愉度 +150%")
            elif aha.initial_spd >= 125.0:
                aha.notes.append("实战速度 ≥ 125：欢愉度 +120%")
            if aha.notes:
                self.event("note", aha, "行迹3 速度阈值", list(aha.notes))

        self.aha["rem_dist"] = max(
            0.0, DIST_BASE - DIST_BASE * self.cfg["aha_advance_pct"] / 100.0
        )

    # ----------------------------- 主循环 ----------------------------- #

    def next_actor(self):
        best = None
        best_av = 0.0
        for unit in self.units:
            av = self.av + unit.rem_dist / self.unit_spd(unit)
            if best is None or av < best_av:
                best = ("unit", unit)
                best_av = av
        a = self.aha
        av = self.av + a["rem_dist"] / self.aha_spd()
        if best is None or av < best_av:
            best = ("aha", None)
            best_av = av
        for summon in self.summons:
            av = self.av + summon["rem_dist"] / float(summon["spd"])
            if best is None or av < best_av:
                best = ("summon", summon)
                best_av = av
        return best, best_av

    def advance_time(self, av: float) -> None:
        """时间前进到 av：所有跑条单位的剩余距离按各自速度同步消耗。

        rem_dist 是「当前时刻距离下次行动还差的路程」——时间走了多远，路程就
        消耗多少（dt × speed）。漏掉这一步（只动 av 不动 rem_dist）会让每个单位
        的首动都从原点算，轴上的行动次数直接少一半（踩过）。
        """
        dt = av - self.av
        if dt > 0:
            for unit in self.units:
                unit.rem_dist = max(0.0, unit.rem_dist - dt * self.unit_spd(unit))
            a = self.aha
            a["rem_dist"] = max(0.0, a["rem_dist"] - dt * self.aha_spd())
            for summon in self.summons:
                summon["rem_dist"] = max(0.0, summon["rem_dist"] - dt * float(summon["spd"]))
        self.av = av

    def run(self) -> dict[str, Any]:
        self.battle_start()
        guard = 0
        while guard < MAX_LOOP:
            guard += 1
            actor, av = self.next_actor()
            if actor is None:
                break
            if av > self.cfg["max_av"] + EPS:
                break
            self.advance_time(av)
            kind, obj = actor
            if kind == "unit":
                self.do_turn(obj)
            elif kind == "aha":
                self.do_aha(False, 0.0)
            else:
                self.do_summon(obj)
        return self.build_output()

    def do_turn(self, unit: Unit) -> None:
        self.depth += 1
        try:
            unit.in_turn = True
            unit.turn_count += 1
            # 回合开始
            if unit.uid == "1511":
                if unit.huanyu > 0:
                    unit.huanyu -= 1
                    if unit.huanyu == 0:
                        self.event("note", unit, "【欢愉万相】结束", [])
                if unit.sig_lc_cd > 0:
                    unit.sig_lc_cd -= 1
            if self.lingshi_slot is not None and unit.slot == self.lingshi_slot:
                aha = self.by_uid("1511")
                if aha is not None:
                    self.event("note", unit, "【「欢愉」令使】回合开始", ["星神★阿哈愿力 +1"])
                    self.gain_wishpower(aha, 1.0, "令使回合开始")
            self.do_action(unit)
            self.turn_end(unit)
        finally:
            unit.in_turn = False
            self.depth -= 1

    def turn_end(self, unit: Unit) -> None:
        # Buff 递减（额外回合不走这里）
        kept: list[dict[str, Any]] = []
        changed = False
        for buff in unit.timed:
            if buff["turns"] is None:
                kept.append(buff)
                continue
            buff["turns"] = int(buff["turns"]) - 1
            if buff["turns"] > 0:
                kept.append(buff)
            else:
                changed = True
        unit.timed = kept
        if changed and unit.elation:
            self.notes.append(f"{unit.name} 的速度加成到期，【阿哈时刻】速度已重算")
        # 好活当赏递减
        kept = []
        for item in unit.haohuo:
            item["turns"] = int(item["turns"]) - 1
            if item["turns"] > 0:
                kept.append(item)
        unit.haohuo = kept
        # 1502 结界递减
        if unit.uid == "1502" and unit.field > 0:
            unit.field -= 1
            if unit.field == 0:
                self.event("note", unit, "结界结束", [])
        # 行动条重置（挂起的自身拉条在这里生效）
        unit.rem_dist = max(0.0, DIST_BASE - DIST_BASE * unit.pending_aa / 100.0)
        unit.pending_aa = 0.0

    def do_summon(self, summon: dict[str, Any]) -> None:
        self.event("summon", None, f"{summon['name']} 归零", ["【协奏】状态结束"],
                   kind="summon", name=str(summon["name"]))
        self.summons = [s for s in self.summons if s is not summon]

    # ----------------------------- 输出 ----------------------------- #

    def build_output(self) -> dict[str, Any]:
        aha_spd_now = self.aha_spd()
        el = self.elation_units()
        ranked = sorted(el, key=lambda u: -self.unit_spd(u))
        ranks: list[dict[str, Any]] = []
        weighted = 0.0
        for i in range(4):
            if i < len(ranked):
                unit = ranked[i]
                spd = self.unit_spd(unit)
                add = AHA_WEIGHTS[i] * spd
                weighted += add
                ranks.append({
                    "rank": i + 1,
                    "name": unit.name,
                    "slot": unit.slot,
                    "speed": spd,
                    "weight": AHA_WEIGHTS[i],
                    "divisor": AHA_DIVISORS[i],
                    "add": add,
                })
            else:
                weighted += 0.0
        base = self.aha_base_value()
        raw = base + weighted + self.aha_flat
        aha_out = {
            "useAeonAha": bool(self.use_aeon_aha),
            "base": base,
            "baseSpd": self.aha_base_spd,
            "lcBaseSpd": self.aha_lc_base_spd,
            "weighted": weighted,
            "flatBonus": self.aha_flat,
            "pct": self.cfg["aha_spd_pct"],
            "raw": raw,
            "speed": self.aha_initial_spd,
            "finalSpeed": aha_spd_now,
            "singleAV": DIST_BASE / self.aha_initial_spd if self.aha_initial_spd > 0 else 0.0,
            "singleFinalAV": DIST_BASE / aha_spd_now if aha_spd_now > 0 else 0.0,
            "triggerCount": self.aha_normal_count,
            "extraTriggerCount": self.aha_extra_count,
            "ranks": ranks,
            "formula": self.aha_formula(base, ranks, raw),
        }
        counts: dict[str, int] = {}
        for node in AV_NODES:
            counts[str(int(node["av"]))] = sum(
                1 for ev in self.timeline
                if ev["type"] in ("aha", "aha_extra") and ev["av"] <= node["av"] + EPS
            )
        key = fmt(self.cfg["max_av"], 0)
        counts[key] = sum(
            1 for ev in self.timeline
            if ev["type"] in ("aha", "aha_extra") and ev["av"] <= self.cfg["max_av"] + EPS
        )
        aha_out["counts"] = counts

        units_out = []
        for unit in self.units:
            spd = self.unit_spd(unit)
            units_out.append({
                "slot": unit.slot,
                "id": unit.uid,
                "name": unit.name,
                "elation": unit.elation,
                "energyType": unit.energy_type,
                "energyName": unit.energy_name,
                "baseSpd": unit.base_spd,
                "lcBaseSpd": unit.lc_base_spd,
                "traceSpd": unit.trace_spd,
                "permPct": unit.perm_pct,
                "permFlat": unit.perm_flat,
                "buffPct": unit.buff_pct,
                "buffFlat": unit.buff_flat,
                "err": unit.err,
                "eidolon": unit.eidolon,
                "maxSp": unit.max_sp,
                "initAdv": unit.init_adv,
                "targetSlot": unit.target_slot,
                "rotation": unit.rotation,
                "equipment": dict(unit.equip),
                "initialSpd": unit.initial_spd,
                "finalSpd": spd,
                "singleAV": DIST_BASE / spd if spd > 0 else 0.0,
                "deltaVsAha": spd - self.aha_initial_spd,
                "fasterThanAha": spd > self.aha_initial_spd + 0.05,
                "actionCount": unit.action_count,
                "turnCount": unit.turn_count,
                "ultCount": unit.ult_count,
                "extraTurnCount": unit.extra_count,
                "fuaCount": unit.fua_count,
                "finalEnergy": unit.energy,
                "finalRemDist": unit.rem_dist,
                "mechanics": self.unit_mechanics(unit),
                "notes": list(unit.notes),
            })

        unit_actions: dict[str, int] = {}
        for unit in self.units:
            unit_actions[unit.name] = unit.action_count
        unit_actions["【阿哈时刻】"] = self.aha_normal_count + self.aha_extra_count

        return {
            "maxAV": self.cfg["max_av"],
            "aha": aha_out,
            "units": units_out,
            "timeline": self.timeline,
            "summary": {
                "totalEvents": len(self.timeline),
                "unitActions": unit_actions,
                "ahaTriggers": self.aha_normal_count,
                "ahaExtraTriggers": self.aha_extra_count,
                "punchlineGranted": self.punchline_granted,
                "punchlineConsumed": self.punchline_consumed,
                "truncated": self.truncated,
            },
            "resources": {
                "punchline": self.punchline,
                "ahaFlatBonus": self.aha_flat,
                "huanyuWanxiangTurns": (self.by_uid("1511").huanyu
                                        if self.by_uid("1511") is not None else None),
                "sanduActive": self.sandu_active(),
                "lingshiSlot": self.lingshi_slot,
                "aesteSlot": self.aeste_slot,
            },
            "warnings": list(self.warnings),
            "notes": list(self.notes),
        }

    def aha_formula(self, base: float, ranks: list[dict[str, Any]], raw: float) -> str:
        if ranks:
            bits = " + ".join(f"{fmt(r['speed'], 1)}/{r['divisor']}" for r in ranks)
        else:
            bits = "无欢愉队友"
        pct_text = f" × (1+{fmt(self.cfg['aha_spd_pct'], 0)}%)" if self.cfg["aha_spd_pct"] else ""
        flat_text = f" + {fmt(self.aha_flat, 1)}" if self.aha_flat else ""
        return (
            f"基础 {fmt(base, 1)} + {bits}{flat_text} = {fmt(raw)}"
            f"{pct_text} → {fmt(self.aha_initial_spd)}"
        )

    def unit_mechanics(self, unit: Unit) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if unit.uid == "1511":
            out = {
                "wishpower": unit.energy,
                "wishpowerTotal": unit.energy_total,
                "huanyuWanxiangTurns": unit.huanyu,
                "trace2Used": unit.trace2_used,
                "lingshiSlot": self.lingshi_slot,
            }
        elif unit.uid == "1503":
            out = {
                "depthCharges": unit.depth,
                "barrierArmed": unit.barrier,
                "aesteSlot": self.aeste_slot,
            }
        elif unit.uid == "1513":
            out = {
                "fervor": unit.fervor,
                "jiumengLeft": unit.jiumeng,
                "allInArmed": unit.all_in,
            }
        elif unit.uid == "1304":
            out = {"blindStacks": unit.blind}
        elif unit.uid == "1502":
            out = {"fieldTurns": unit.field}
        elif unit.uid == "1505":
            out = {"energySinceFuA": unit.feiy_total}
        elif unit.uid == "1506":
            out = {"invincibleTurns": unit.invincible}
        out["haohuo"] = [
            {"turns": item["turns"], "count": item["count"], "label": item["label"]}
            for item in unit.haohuo
        ]
        return out


# --------------------------------------------------------------------------- #
# 接口
# --------------------------------------------------------------------------- #

@api("catalog")
def catalog(payload: dict[str, Any], ctx) -> dict[str, Any]:
    """角色表、装备开关、可调参数、行动值节点 —— 给界面建表用。"""
    roster = []
    for uid, spec in ROSTER.items():
        roster.append({
            "id": uid,
            "aliases": list(spec.get("aliases") or ()),
            "name": spec.get("name"),
            "path": spec.get("path"),
            "elation": bool(spec.get("elation")),
            "baseSpd": spec.get("baseSpd"),
            "traceSpd": spec.get("traceSpd"),
            "lcBaseSpd": spec.get("lcBaseSpd"),
            "maxSp": spec.get("maxSp"),
            "energy": spec.get("energy"),
            "energyName": spec.get("energyName"),
            "rotation": spec.get("rotation"),
            "mechanics": list(spec.get("mechanics") or ()),
        })
    return {
        "roster": roster,
        "equipment": EQUIPMENT_META,
        "config": CONFIG_META,
        "avNodes": AV_NODES,
        "cycles": {
            "distBase": DIST_BASE,
            "cycle0AV": CYCLE0_AV,
            "cycleAV": CYCLE_AV,
        },
        "ahaWeights": [
            {"rank": i + 1, "weight": AHA_WEIGHTS[i], "divisor": AHA_DIVISORS[i]}
            for i in range(4)
        ],
        "defaultTeam": [
            {"id": "1511", "elation": True},
            {"id": "1513", "elation": True},
            {"id": "1503", "elation": True, "targetSlot": 0},
            {"id": "1501", "elation": True},
        ],
    }


@api("simulate")
def simulate(payload: dict[str, Any], ctx) -> dict[str, Any]:
    """跑 4 人小队 + 【阿哈时刻】的行动值排轴。"""
    return Sim(payload).run()


@api("threshold")
def threshold(payload: dict[str, Any], ctx) -> dict[str, Any]:
    """速度阈值反推：N 轮 M 动（含累计拉条）需要的最低实战速度。

        需求速度 = 10000 × (动数 − 拉条%/100) ÷ 目标行动值
    """
    target_av = _num(payload, "targetAV", 0.0, 0.0, NUM_LIMIT)
    t_in = payload.get("t")
    if target_av <= 0 and t_in is not None and t_in != "":
        t_val = int(_num(payload, "t", 0.0, 0.0, 1000.0))
        target_av = CYCLE0_AV + t_val * CYCLE_AV
    if target_av <= 0:
        raise ValueError("需要 targetAV（或 t）指定目标行动值")
    actions = _num(payload, "actions", 2.0, 1.0, 200.0)
    advance_pct = _num(payload, "advancePct", 0.0, 0.0, 10000.0)
    effective = actions - advance_pct / 100.0
    required = DIST_BASE * effective / target_av
    return {
        "targetAV": target_av,
        "t": cycle_of(target_av),
        "actions": actions,
        "advancePct": advance_pct,
        "effectiveTurns": effective,
        "distance": DIST_BASE,
        "requiredSpeed": required,
        "cycleBoundary": CYCLE0_AV + cycle_of(target_av) * CYCLE_AV,
        "formula": (
            f"10000 × ({fmt(actions, 0)} − {fmt(advance_pct, 0)}%) ÷ {fmt(target_av, 0)}"
            f" = {fmt(required)}"
        ),
        "text": (
            f"{fmt(target_av, 0)} AV 内打 {fmt(actions, 0)} 动"
            + (f"（累计拉条 {fmt(advance_pct, 0)}%）" if advance_pct else "")
            + f"需要 {fmt(required)} 速"
        ),
    }
