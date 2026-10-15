"""手动验证「配速查询」的后端（临时脚本）。"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import feature_api, registry  # noqa: E402

MODULE = "honkai-star-rail"
FEATURE = "speed-plan"


def load() -> list[dict]:
    modules, errors = registry.scan()
    for module in modules:
        for feature in module.features:
            api_path = feature.dir / feature.api_file
            if api_path.is_file():
                feature_api.load_feature_api(
                    module.id, feature.id, api_path, module.dir, feature.dir, errors
                )
    return errors


def call(action, payload=None):
    return feature_api.call(MODULE, FEATURE, action, payload or {})


errors = load()
print("加载错误：", errors or "无")

catalog = call("catalog")
print(f"\n=== catalog ===")
print(f"角色 {len(catalog['characters'])} 个，命途 {catalog['paths']}")
print(f"模式：{[m['name'] + '(最多' + str(m['maxT']) + 'T)' for m in catalog['modes']]}")
print(f"2 件套速度遗器 {len(catalog['speedSets'])} 个，例如：{[s['name'] + ' +' + str(s['pct']) + '%' for s in catalog['speedSets'][:4]]}")
print(f"数据来源：{catalog['sources'].get('generatedAt')}")

sample = catalog["characters"][0]
print(f"\n第一个角色：{sample}")

# 找卡芙卡（101 速那种基础值好算）
kafka = next((c for c in catalog["characters"] if c["name"] == "卡芙卡"), None)
print(f"\n卡芙卡：{kafka}")

cones = call("lightcones", {"path": kafka["path"]})
print(f"\n=== 卡芙卡（{kafka['pathName']}）可用的光锥 {len(cones['lightcones'])} 把 ===")
for cone in cones["lightcones"][:6]:
    print(f"  {cone['name']} {cone['rarity']}★ 配速相关={cone['speedRelated']}")

result = call(
    "plan",
    {
        "characterId": kafka["id"],
        "lightconeId": cones["lightcones"][0]["id"],
        "superimpose": 5,
        "eidolon": 0,
        "relic": {"speedBoots": True, "substatSpeed": 0},
        "advance": {"windUlts": 0, "danceUlts": 0, "vonwacq": True, "custom": 0},
        "target": {"t": 0, "actions": 2},
    },
)
print(f"\n=== plan（卡芙卡 + 速度鞋 + 翁瓦克）===")
print("速度公式：", result["speed"]["formula"])
print("实际速度：", round(result["speed"]["final"], 2))
print("拉条：", result["advance"])
print("结论：", result["verdict"]["text"])
print("效果条数：速度类", len(result["effects"]["speed"]), "拉条类", len(result["effects"]["advance"]))

mode = result["tables"][0]
print(f"\n=== {mode['name']} 阈值表（前 4 行）===")
print("T：", mode["tValues"], "总AV：", [150 + t * 100 for t in mode["tValues"]])
for row in mode["rows"][:4]:
    cells = "  ".join(f"{c['speed']:.1f}{'✓' if c['reachable'] else '×'}" for c in row["cells"])
    print(f"  {row['actions']} 动: {cells}")

print("\n=== 交叉验证 ===")
print("0T 2动 无拉条 需求 = 20000/150 =", round(20000 / 150, 2))
print("0T 2动 翁瓦克40% 需求 = 16000/150 =", round(16000 / 150, 2))
print("1T 3动 无拉条 需求 = 30000/250 =", round(30000 / 250, 2))
