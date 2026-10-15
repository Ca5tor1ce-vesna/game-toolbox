"""从 Python 实现里生成标准答案，用来对拍网页版（JS）实现。

产出：tests/fixtures/web_oracle.json

网页版（单文件 HTML）里会内嵌这份基准，打开页面时自动跑一遍自检；
`tools/check_web_port.mjs` 也会用 node 直接跑同一份基准。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import feature_api, registry  # noqa: E402

MODULE_ID = "honkai-star-rail"
FEATURE = "speed-plan"

errors: list[dict] = []
for module in registry.scan()[0]:
    for feature in module.features:
        api_path = feature.dir / feature.api_file
        if api_path.is_file():
            feature_api.load_feature_api(module.id, feature.id, api_path, module.dir, feature.dir, errors)


def call(action: str, payload: dict | None = None):
    return feature_api.call(MODULE_ID, FEATURE, action, payload or {})


catalog = call("catalog")
by_name = {char["name"]: char for char in catalog["characters"]}
by_id = {char["id"]: char for char in catalog["characters"]}

# 挑几个有代表性的角色：有行迹速度的、没有的、不同命途
def pick(name: str) -> str:
    char = by_name.get(name)
    if char is None:
        raise SystemExit(f"找不到角色 {name}")
    return char["id"]


CONE_BY_NAME = {cone["name"]: cone for cone in call("lightcones")["lightcones"]}


def cone_id(name: str) -> str:
    if name not in CONE_BY_NAME:
        raise SystemExit(f"找不到光锥 {name}")
    return CONE_BY_NAME[name]["id"]


WIND = next(item["id"] for item in catalog["fourPieceSets"] if item["name"] == "晨昏交界的翔鹰")
VONWACQ = next(item["id"] for item in catalog["ornamentSets"] if item["name"] == "生命的翁瓦克")
DANCE = CONE_BY_NAME.get("舞！舞！舞！", {}).get("id")

# 一个「没有速度效果」的 4 件套，用来验证零贡献
PLAIN = next(item["id"] for item in catalog["fourPieceSets"] if not item["hasSpeedEffect"])

KAFKA = pick("卡芙卡")
MIRROR = pick("镜流")
PEARL = pick("真珠")
SILVER = pick("银狼")

CONFIGS: list[dict] = [
    {"label": "卡芙卡·裸装", "payload": {"characterId": KAFKA, "relic": {}, "advance": {}, "target": {"mode": "moc", "t": 0, "actions": 2}}},
    {"label": "卡芙卡·速度鞋", "payload": {"characterId": KAFKA, "relic": {"speedBoots": True}, "advance": {}, "target": {"mode": "moc", "t": 0, "actions": 2}}},
    {"label": "卡芙卡·鞋+副词条10", "payload": {"characterId": KAFKA, "relic": {"speedBoots": True, "substatSpeed": 10}, "advance": {}, "target": {"mode": "moc", "t": 1, "actions": 3}}},
    {"label": "卡芙卡·手填百分比+固定", "payload": {"characterId": KAFKA, "relic": {"speedBoots": True, "customPct": 20, "customFlat": 5}, "advance": {}, "target": {"mode": "moc", "t": 0, "actions": 2}}},
    {"label": "镜流·行迹速度", "payload": {"characterId": MIRROR, "relic": {}, "advance": {}, "target": {"mode": "moc", "t": 0, "actions": 2}}},
    {"label": "镜流·鞋+风套2次开大", "payload": {"characterId": MIRROR, "relic": {"speedBoots": True, "fourPieceId": WIND, "fourPieceUlts": 2}, "advance": {}, "target": {"mode": "moc", "t": 0, "actions": 3}}},
    {"label": "镜流·风套+轴底开大", "payload": {"characterId": MIRROR, "relic": {"speedBoots": True, "fourPieceId": WIND, "fourPieceUlts": 2}, "advance": {"excludeLastUlt": True}, "target": {"mode": "moc", "t": 0, "actions": 3}}},
    {"label": "镜流·翁瓦克进战拉条", "payload": {"characterId": MIRROR, "relic": {"speedBoots": True, "ornamentIds": [VONWACQ]}, "advance": {}, "target": {"mode": "moc", "t": 0, "actions": 2}}},
    {"label": "镜流·风套+翁瓦克+舞舞舞3次", "payload": {"characterId": MIRROR, "relic": {"speedBoots": True, "fourPieceId": WIND, "fourPieceUlts": 3, "ornamentIds": [VONWACQ]}, "advance": {"danceUlts": 3, "danceSuperimpose": 5}, "target": {"mode": "moc", "t": 0, "actions": 4}}},
    {"label": "真珠·专武叠影5", "payload": {"characterId": PEARL, "lightconeId": cone_id("当她决定看见"), "superimpose": 5, "relic": {"speedBoots": True}, "advance": {}, "target": {"mode": "moc", "t": 0, "actions": 2}}},
    {"label": "真珠·专武叠影1", "payload": {"characterId": PEARL, "lightconeId": cone_id("当她决定看见"), "superimpose": 1, "relic": {"speedBoots": True}, "advance": {}, "target": {"mode": "moc", "t": 0, "actions": 2}}},
    {"label": "银狼·虚无专武+6魂", "payload": {"characterId": SILVER, "lightconeId": cone_id("谎言在风中飘扬"), "superimpose": 5, "eidolon": 6, "relic": {"speedBoots": True}, "advance": {}, "target": {"mode": "moc", "t": 0, "actions": 2}}},
    {"label": "无速度效果的4件套=零贡献", "payload": {"characterId": KAFKA, "relic": {"speedBoots": True, "fourPieceId": PLAIN}, "advance": {}, "target": {"mode": "moc", "t": 0, "actions": 2}}},
    {"label": "异相仲裁 0T", "payload": {"characterId": KAFKA, "relic": {"speedBoots": True}, "advance": {}, "target": {"mode": "yixiang", "t": 0, "actions": 6}}},
    {"label": "异相仲裁 1T", "payload": {"characterId": KAFKA, "relic": {"speedBoots": True}, "advance": {}, "target": {"mode": "yixiang", "t": 1, "actions": 6}}},
    {"label": "异相仲裁·绝境 2T", "payload": {"characterId": KAFKA, "relic": {"speedBoots": True}, "advance": {}, "target": {"mode": "yixiang_juejing", "t": 2, "actions": 6}}},
    {"label": "虚构叙事 3T 8动", "payload": {"characterId": KAFKA, "relic": {"speedBoots": True}, "advance": {}, "target": {"mode": "xugou", "t": 3, "actions": 8}}},
    {"label": "末日幻影 4T 9动", "payload": {"characterId": KAFKA, "relic": {"speedBoots": True}, "advance": {}, "target": {"mode": "mori", "t": 4, "actions": 9}}},
    {"label": "自定义行动值 300", "payload": {"characterId": KAFKA, "relic": {"speedBoots": True}, "advance": {}, "target": {"mode": "moc", "t": 0, "actions": 2, "customAV": 300}}},
]

# 勾选具体效果：效果清单是 plan 返回的一部分（effects.speed），默认勾选状态由 Python 决定
probe = call(
    "plan",
    {"characterId": MIRROR, "eidolon": 6, "relic": {}, "advance": {}, "target": {"t": 0, "actions": 2}},
)
speed_effect_ids = [item["id"] for item in probe["effects"]["speed"] if item.get("defaultEnabled")]
all_effect_ids = [item["id"] for item in probe["effects"]["speed"]]

# 触发方式的样本：遗器里那条「开大才提速」的 4 件套，以及光锥里的进战/开大提速
MESSENGER = next(
    (item["id"] for item in catalog["fourPieceSets"] if item["name"] == "骇域漫游的信使"), None
)

CONFIGS.append(
    {
        "label": "全部速度效果都勾上（含开大/进战/有条件）",
        "payload": {
            "characterId": MIRROR,
            "eidolon": 6,
            "enabledEffects": all_effect_ids,
            "relic": {"speedBoots": True},
            "advance": {},
            "target": {"mode": "moc", "t": 0, "actions": 3},
        },
    }
)

if MESSENGER:
    # 「骇域漫游的信使」4 件套：开大时全队速度 +12%（以前会被算法静默丢掉）
    for label, ults, extra in (
        ("信使4件套·开大2次", 2, {}),
        ("信使4件套·开大0次（提速不生效）", 0, {}),
        ("信使4件套·开大2次+轴底开大", 2, {"excludeLastUlt": True}),
    ):
        CONFIGS.append(
            {
                "label": label,
                "payload": {
                    "characterId": KAFKA,
                    "relic": {
                        "speedBoots": True,
                        "fourPieceId": MESSENGER,
                        "fourPieceUlts": ults,
                        "ultTargetsAlly": ults > 0,
                    },
                    "advance": extra,
                    "target": {"mode": "moc", "t": 0, "actions": 3},
                },
            }
        )

CONFIGS.append(
    {
        "label": "镜流·默认勾选的效果全开",
        "payload": {
            "characterId": MIRROR,
            "eidolon": 6,
            "enabledEffects": speed_effect_ids,
            "relic": {"speedBoots": True},
            "advance": {},
            "target": {"mode": "moc", "t": 0, "actions": 3},
        },
    }
)

# ---- 行动模拟内核：开大触发 / 叠层 / 仅队友 这几条路径都要有基准 ----
WAIT = CONE_BY_NAME.get("只需等待", {}).get("id")  # 叠层类：每次施放攻击后速度提高，最多叠 3 层
KAFKA_ULT = pick("卡芙卡")

if MESSENGER:
    # 信使 4 件套：开大触发 +12%、持续 1 回合 —— 从第一次开大之后的那次行动起才生效
    for label, first_ult, ults in (
        ("信使4件套·第1次行动后开大", 1, 2),
        ("信使4件套·开局就开大（firstUltAction=0）", 0, 2),
        ("信使4件套·第3次行动后才开大", 3, 2),
    ):
        CONFIGS.append(
            {
                "label": label,
                "payload": {
                    "characterId": KAFKA_ULT,
                    "relic": {
                        "speedBoots": True,
                        "fourPieceId": MESSENGER,
                        "fourPieceUlts": ults,
                        "ultTargetsAlly": True,
                    },
                    "advance": {},
                    "target": {"mode": "moc", "t": 0, "actions": 4},
                    "simulation": {"firstUltAction": first_ult},
                },
            }
        )

if WAIT:
    # 叠层效果是 conditional，默认不勾：先探一次拿到它的 id 再显式勾上，才测得到叠层路径
    wait_effect = next(
        (
            item
            for item in call(
                "plan",
                {
                    "characterId": KAFKA_ULT,
                    "lightconeId": WAIT,
                    "superimpose": 5,
                    "relic": {"speedBoots": True},
                    "advance": {},
                    "target": {"mode": "moc", "t": 0, "actions": 4},
                },
            )["effects"]["speed"]
            if item.get("maxStacks")
        ),
        None,
    )
    if wait_effect:
        for label, superimpose, target in (
            ("卡芙卡·只需等待叠层（逐层加速）", 5, {"mode": "moc", "t": 2, "actions": 6}),
            (
                "卡芙卡·只需等待叠层+自定义行动值 300",
                1,
                {"mode": "moc", "t": 0, "actions": 4, "customAV": 300},
            ),
        ):
            CONFIGS.append(
                {
                    "label": label,
                    "payload": {
                        "characterId": KAFKA_ULT,
                        "lightconeId": WAIT,
                        "superimpose": superimpose,
                        "enabledEffects": [wait_effect["id"]],
                        "relic": {"speedBoots": True},
                        "advance": {},
                        "target": target,
                    },
                }
            )

# 仅队友的提速（布洛妮娅 2 魂「被指定的我方目标…」）：勾上也不该计入本角色速度
BRONYA = pick("布洛妮娅")
bronya_enabled = [
    item["id"]
    for item in call(
        "plan",
        {"characterId": BRONYA, "eidolon": 6, "relic": {}, "advance": {}, "target": {"t": 0, "actions": 2}},
    )["effects"]["speed"]
]
if bronya_enabled:
    CONFIGS.append(
        {
            "label": "布洛妮娅·全部速度效果都勾上（含仅队友）",
            "payload": {
                "characterId": BRONYA,
                "eidolon": 6,
                "enabledEffects": bronya_enabled,
                "relic": {"speedBoots": True},
                "advance": {},
                "target": {"mode": "moc", "t": 0, "actions": 2},
            },
        }
    )


def round_floats(value, digits: int = 6):
    if isinstance(value, float):
        return round(value, digits)
    if isinstance(value, dict):
        return {key: round_floats(item, digits) for key, item in value.items()}
    if isinstance(value, list):
        return [round_floats(item, digits) for item in value]
    return value


oracle: list[dict] = []
for config in CONFIGS:
    result = call("plan", config["payload"])
    entry = {
        "label": config["label"],
        "payload": config["payload"],
        "speed": {
            "base": result["speed"]["base"],
            "baseRaw": result["speed"]["baseRaw"],
            "traceSpeed": result["speed"]["traceSpeed"],
            "traceSpeedPct": result["speed"]["traceSpeedPct"],
            "pct": result["speed"]["pct"],
            "flat": result["speed"]["flat"],
            "final": result["speed"]["final"],
        },
        "advance": {
            "total": result["advance"]["total"],
            "items": [item["percent"] for item in result["advance"]["items"]],
            "labels": [item["label"] for item in result["advance"]["items"]],
        },
        "verdict": {
            "t": result["verdict"]["t"],
            "actions": result["verdict"]["actions"],
            "totalAV": result["verdict"]["totalAV"],
            "requiredSpeed": result["verdict"]["requiredSpeed"],
            "currentSpeed": result["verdict"]["currentSpeed"],
            "gap": result["verdict"]["gap"],
            "achievableActions": result["verdict"]["achievableActions"],
        },
        "relicSetCount": len(result["relicSets"] or []),
        "warningCount": len(result["warnings"] or []),
        # 效果清单（含触发方式）也是对拍对象：分类错了速度就会跟着错
        "effects": [
            {
                "id": item["id"],
                "kind": item["kind"],
                "value": item["value"],
                "apply": item["apply"],
                "trigger": item.get("trigger"),
                "defaultEnabled": item["defaultEnabled"],
            }
            for item in result["effects"]["speed"]
        ],
    }
    # 表格只对前三个配置全量对拍（表格只取决于拉条与模式，样本够了）
    if len(oracle) < 3:
        entry["tables"] = [
            {
                "id": table["id"],
                "firstCycleAV": table["firstCycleAV"],
                "cycleAV": table["cycleAV"],
                "tValues": table["tValues"],
                "cells": [
                    [round(cell["speed"], 6) for cell in row["cells"]] for row in table["rows"]
                ],
            }
            for table in result["tables"]
        ]
    # 行动模拟：只给「真的有随行动变化的加速」的配置对拍时间线，
    # 否则基准里会塞一堆完全相同的常驻时间线（文件白白变大）。
    if result["speed"].get("hasTimeline"):
        simulation = result["simulation"]
        entry["simulation"] = {
            "firstUltAction": simulation["firstUltAction"],
            "windowAV": simulation["windowAV"],
            "achievedActions": simulation["achievedActions"],
            "completedActions": simulation["completedActions"],
            "notes": simulation["notes"],
            "timeline": [
                {
                    "action": item["action"],
                    "speed": item["speed"],
                    "av": item["av"],
                    "pct": item["pct"],
                    "flat": item["flat"],
                    "active": item["active"],
                }
                for item in simulation["timeline"]
            ],
        }
    oracle.append(round_floats(entry))

# 推荐引擎：只对拍「假设 + 前 5 名的关键数值 + 穷举数量」
rec_cases = [
    {"label": "卡芙卡 3动", "payload": {"characterId": KAFKA, "target": {"mode": "moc", "t": 0, "actions": 3}}},
    {
        "label": "镜流 4动 + 轴底开大",
        "payload": {
            "characterId": MIRROR,
            "target": {"mode": "yixiang", "t": 1, "actions": 5},
            "coneUlts": 2,
            "fourPieceUlts": 2,
            "excludeLastUlt": True,
        },
    },
]
recommend_oracle: list[dict] = []
for case in rec_cases:
    result = call("recommend", case["payload"])
    recommend_oracle.append(
        round_floats(
            {
                "label": case["label"],
                "payload": case["payload"],
                "assumptions": result["assumptions"],
                "evaluated": result["evaluated"],
                "results": [
                    {
                        "coneId": item["coneId"],
                        "coneName": item["coneName"],
                        "fourPieceId": item["fourPieceId"],
                        "fourPieceName": item["fourPieceName"],
                        "ornamentIds": item["ornamentIds"],
                        "speed": item["speed"],
                        "advance": item["advance"],
                        "required": item["required"],
                        "neededSubstatSpeed": item["neededSubstatSpeed"],
                        "ok": item["ok"],
                    }
                    for item in result["results"][:5]
                ],
            }
        )
    )

out = {
    "generatedFrom": "Python 实现（modules/honkai-star-rail/features/speed-plan/api.py）",
    "plans": oracle,
    "recommends": recommend_oracle,
}
target = ROOT / "tests" / "fixtures" / "web_oracle.json"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"配置 {len(oracle)} 条、推荐 {len(recommend_oracle)} 条 → {target}")
print(f"文件大小：{target.stat().st_size / 1024:.1f} KB")
