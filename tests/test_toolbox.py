"""工具箱自测：把关键数值对拍公开资料，改坏了立刻知道。

运行：
    <python> tests/test_toolbox.py
    <python> -m unittest discover -s tests -v
"""

from __future__ import annotations

import atexit
import hashlib
import json
import math
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 测试把用户数据写到临时目录，不碰真 userdata（必须在导入 core.config 之前设置）。
# 别人显式设了 GT_USERDATA 时尊重别人的设置。
_TEMP_USERDATA: Path | None = None
if not os.environ.get("GT_USERDATA", "").strip():
    _TEMP_USERDATA = Path(tempfile.mkdtemp(prefix="gt-test-userdata-"))
    os.environ["GT_USERDATA"] = str(_TEMP_USERDATA)
    atexit.register(shutil.rmtree, _TEMP_USERDATA, True)

from core import config, feature_api, registry  # noqa: E402

MODULE_ID = "honkai-star-rail"


def _load() -> list[dict]:
    modules, errors = registry.scan()
    for module in modules:
        for feature in module.features:
            assert feature.dir is not None
            api_path = feature.dir / feature.api_file
            if api_path.is_file():
                feature_api.load_feature_api(
                    module.id, feature.id, api_path, module.dir, feature.dir, errors
                )
    return errors


ERRORS = _load()


def call(feature: str, action: str, payload: dict | None = None):
    return feature_api.call(MODULE_ID, feature, action, payload or {})


class TestRegistry(unittest.TestCase):
    def test_module_discovered(self) -> None:
        modules, _ = registry.scan()
        ids = [m.id for m in modules]
        self.assertIn(MODULE_ID, ids)

    def test_features_discovered(self) -> None:
        modules, _ = registry.scan()
        module = next(m for m in modules if m.id == MODULE_ID)
        ids = {f.id for f in module.features}
        self.assertLessEqual({"speed", "gacha"}, ids)

    def test_no_load_errors(self) -> None:
        self.assertEqual([], [e for e in ERRORS if e.get("scope", "").startswith(MODULE_ID)])


class TestSpeedThreshold(unittest.TestCase):
    """对拍 17173/米游社《怎么算速度阈值》里的公开数值。"""

    def test_first_cycle_two_actions(self) -> None:
        res = call("speed", "threshold", {"cycles": 1, "actions": 2})
        self.assertAlmostEqual(res["speedExact"], 133.33, places=2)
        self.assertEqual(res["speedCeil"], 134)

    def test_first_cycle_three_actions(self) -> None:
        res = call("speed", "threshold", {"cycles": 1, "actions": 3})
        self.assertAlmostEqual(res["speedExact"], 200.0, places=2)

    def test_four_cycles_eight_actions(self) -> None:
        res = call("speed", "threshold", {"cycles": 4, "actions": 8})
        self.assertAlmostEqual(res["speedExact"], 177.78, places=2)

    def test_four_cycles_nine_actions(self) -> None:
        res = call("speed", "threshold", {"cycles": 4, "actions": 9})
        self.assertAlmostEqual(res["speedExact"], 200.0, places=2)

    def test_firefly_case_with_wind_and_dance(self) -> None:
        # 花火：首轮三动，1 次开大，叠五舞舞舞 + 风套 → (30000−2400−2500)/150 = 167.33
        res = call("speed", "threshold", {"cycles": 1, "actions": 3, "windUlts": 1, "danceUlts": 1})
        self.assertAlmostEqual(res["speedExact"], 167.33, places=2)

    def test_wind_dance_vonwacq(self) -> None:
        # 再叠翁瓦克：(30000−2400−2500−4000)/150 = 140.67
        res = call(
            "speed",
            "threshold",
            {"cycles": 1, "actions": 3, "windUlts": 1, "danceUlts": 1, "vonwacq": True},
        )
        self.assertAlmostEqual(res["speedExact"], 140.67, places=2)

    def test_four_cycles_nine_actions_three_ults(self) -> None:
        # 4 轮 9 动，风套 + 叠五舞舞舞各触发 3 次：(90000−7200−7500)/450 = 167.33
        res = call("speed", "threshold", {"cycles": 4, "actions": 9, "windUlts": 3, "danceUlts": 3})
        self.assertAlmostEqual(res["speedExact"], 167.33, places=2)

    def test_advance_covers_distance(self) -> None:
        res = call("speed", "threshold", {"cycles": 1, "actions": 1, "extraAdvancePercent": 120})
        self.assertFalse(res["achievable"])


class TestSpeedSimulate(unittest.TestCase):
    def test_single_unit_cycles(self) -> None:
        res = call("speed", "simulate", {"units": [{"name": "A", "speed": 100}], "cycles": 3})
        times = [e["time"] for e in res["timeline"]]
        self.assertEqual([100.0, 200.0, 300.0], [round(t, 2) for t in times])
        self.assertEqual([1, 2, 3], [e["cycle"] for e in res["timeline"]])
        self.assertEqual(3, res["stats"][0]["actions"])

    def test_two_units_order(self) -> None:
        res = call(
            "speed",
            "simulate",
            {
                "units": [
                    {"name": "慢", "speed": 100},
                    {"name": "快", "speed": 200},
                ],
                "cycles": 1,
            },
        )
        order = [(e["unit"], round(e["time"], 1)) for e in res["timeline"]]
        self.assertEqual([("快", 50.0), ("快", 100.0), ("慢", 100.0), ("快", 150.0)], order)
        stats = {s["name"]: s["actions"] for s in res["stats"]}
        self.assertEqual({"快": 3, "慢": 1}, stats)

    def test_start_advance(self) -> None:
        # 进战拉条 40%：100 速的首次行动从 100 AV 提前到 60 AV
        res = call(
            "speed",
            "simulate",
            {"units": [{"name": "A", "speed": 100, "startAdvance": 40}], "cycles": 1},
        )
        self.assertAlmostEqual(res["timeline"][0]["time"], 60.0, places=2)


class TestGacha(unittest.TestCase):
    def pmf(self, pool_id: str, pity: int = 0) -> dict[int, float]:
        """在测试里独立按模型重算一遍分布，和 api.py 的实现交叉验证。"""
        data = call("gacha", "pools")["pools"]
        pool = next(p for p in data if p["id"] == pool_id)
        base = pool["baseRate"]
        hard = pool["hardPity"]
        start = pool["softPityStart"]
        step = pool["softPityStep"]
        out: dict[int, float] = {}
        survival = 1.0
        n = pity
        while n < hard and survival > 1e-15:
            n += 1
            if n >= hard:
                p = 1.0
            elif n < start:
                p = base
            else:
                p = min(1.0, base + step * (n - start + 1))
            out[n - pity] = survival * p
            survival *= 1.0 - p
        return out

    def test_pmf_normalised(self) -> None:
        for pool in ("character_event", "lightcone_event", "standard"):
            with self.subTest(pool=pool):
                self.assertAlmostEqual(sum(self.pmf(pool).values()), 1.0, places=9)

    def test_model_matches_official_overall_rate(self) -> None:
        res = call("gacha", "check")
        for row in res["rows"]:
            with self.subTest(pool=row["id"]):
                self.assertTrue(row["ok"], f"{row['name']} 综合概率偏差 {row['deviation']}")

    def test_character_hard_pity(self) -> None:
        dist = self.pmf("character_event")
        self.assertEqual(max(dist), 90)

    def test_lightcone_hard_pity(self) -> None:
        dist = self.pmf("lightcone_event")
        self.assertEqual(max(dist), 80)

    def test_guaranteed_costs_one_five_star(self) -> None:
        single = call("gacha", "single", {"pool": "character_event", "pity": 0})
        guaranteed = call(
            "gacha", "plan", {"pool": "character_event", "copies": 1, "guaranteed": True}
        )
        self.assertAlmostEqual(single["expectPulls"], guaranteed["expectPulls"], places=6)

    def test_fifty_fifty_costs_more(self) -> None:
        plan = call("gacha", "plan", {"pool": "character_event", "copies": 1})
        # 50/50：期望 = 单金期望 × 1.5 ≈ 93.7 抽
        self.assertGreater(plan["expectPulls"], 90)
        self.assertLess(plan["expectPulls"], 100)

    def test_lightcone_up_expectation(self) -> None:
        plan = call("gacha", "plan", {"pool": "lightcone_event", "copies": 1})
        # 75% UP：期望 = 单金期望 × 1.25 ≈ 66.9 抽
        self.assertGreater(plan["expectPulls"], 62)
        self.assertLess(plan["expectPulls"], 72)

    def test_pity_at_hard_pity(self) -> None:
        res = call("gacha", "single", {"pool": "character_event", "pity": 90})
        self.assertEqual(res["maxPulls"], 1)
        self.assertEqual(res["pityToHard"], 0)

    def test_have_pulls_probability(self) -> None:
        res = call(
            "gacha",
            "plan",
            {"pool": "character_event", "copies": 1, "guaranteed": True, "havePulls": 90},
        )
        self.assertGreater(res["probWithinHave"], 0.99)


class TestAhaOriginal(unittest.TestCase):
    """原版工具必须逐字节还原 —— 用户明确要求「原封不动」。

    这几个测试的作用：以后任何人（包括我自己）想顺手"优化"这个功能时，
    只要动了 original.html 就会立刻变红。
    """

    ORIGINAL = (
        ROOT / "modules" / "honkai-star-rail" / "features" / "aha-speed" / "original.html"
    )
    ORIGINAL_SHA256 = "9768d8592adce1fbcf73385d49bbe94d43c32501487aec722707ee423a26df60"
    ORIGINAL_BYTES = 24293

    def test_original_file_is_byte_identical(self) -> None:
        self.assertTrue(self.ORIGINAL.is_file(), "原版文件不见了")
        data = self.ORIGINAL.read_bytes()
        self.assertEqual(len(data), self.ORIGINAL_BYTES, "原版文件的字节数被改过")
        self.assertEqual(
            hashlib.sha256(data).hexdigest(),
            self.ORIGINAL_SHA256,
            "原版文件内容被改过（要求是逐字节还原）",
        )

    def test_original_keeps_its_own_cdn_reference(self) -> None:
        """磁盘上的原文件保持原样：CDN 那行还在，替换只发生在运行时。"""
        text = self.ORIGINAL.read_text(encoding="utf-8")
        self.assertIn('src="https://cdn.tailwindcss.com"', text)

    def test_tailwind_vendored_for_offline(self) -> None:
        vendor = self.ORIGINAL.parent / "vendor" / "tailwind.js"
        self.assertTrue(vendor.is_file(), "本地没备 Tailwind，断网打开会掉样式")
        self.assertGreater(vendor.stat().st_size, 10000)

    def test_ui_serves_the_original(self) -> None:
        ui = self.ORIGINAL.parent / "ui.js"
        self.assertTrue(ui.is_file())
        self.assertIn("original.html", ui.read_text(encoding="utf-8"))


class TestSpeedPlan(unittest.TestCase):
    """配速查询：速度合成规则、需求速度、命途限制、星魂档位。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = call("speed-plan", "catalog")
        cls.by_name = {item["name"]: item for item in cls.catalog["characters"]}

    def char(self, name: str) -> dict:
        self.assertIn(name, self.by_name, f"数据里没有 {name}")
        return self.by_name[name]

    def plan(self, name: str, **kwargs):
        payload = {
            "characterId": self.char(name)["id"],
            "relic": {},
            "advance": {},
            "target": {"t": 0, "actions": 2},
        }
        payload.update(kwargs)
        return call("speed-plan", "plan", payload)

    # ---------- 数据 ----------

    def test_catalog_is_complete(self) -> None:
        self.assertGreater(len(self.catalog["characters"]), 90)
        for item in self.catalog["characters"]:
            self.assertTrue(item["baseSpeed"] and item["baseSpeed"] > 0, item["name"])
            self.assertTrue(item["pathName"], item["name"])

    def test_known_base_speeds(self) -> None:
        """按 id 对拍基础速度（有同名角色，按名字查会撞车）。"""
        by_id = {str(item["id"]): item for item in self.catalog["characters"]}
        for char_id, name, speed in (
            ("1005", "卡芙卡", 100),
            ("1001", "三月七", 101),
            ("1002", "丹恒", 110),
            ("1006", "银狼", 107),
        ):
            with self.subTest(char_id=char_id):
                self.assertIn(char_id, by_id, f"数据里没有 {char_id}")
                self.assertEqual(by_id[char_id]["name"], name)
                self.assertEqual(by_id[char_id]["baseSpeed"], speed)

    def test_duplicate_names_are_distinguishable(self) -> None:
        """同名角色必须靠命途区分——界面上就是这么显示的。"""
        names: dict[str, list[dict]] = {}
        for item in self.catalog["characters"]:
            names.setdefault(item["name"], []).append(item)
        for name, items in names.items():
            if len(items) < 2:
                continue
            paths = {item["pathName"] for item in items}
            self.assertGreater(len(paths), 1, f"{name} 同名且命途相同，界面分不出来")

    def test_lightcones_are_path_filtered(self) -> None:
        for name in ("卡芙卡", "三月七", "花火"):
            character = self.char(name)
            cones = call("speed-plan", "lightcones", {"path": character["path"]})["lightcones"]
            with self.subTest(name=name):
                self.assertTrue(cones, name)
                for cone in cones:
                    self.assertEqual(cone["path"], character["path"])
                    self.assertNotEqual(cone["pathName"], "")

    def test_path_mismatch_is_rejected(self) -> None:
        kafka = self.char("卡芙卡")
        others = [
            cone
            for cone in call("speed-plan", "lightcones", {})["lightcones"]
            if cone["path"] != kafka["path"]
        ]
        with self.assertRaises(ValueError):
            self.plan("卡芙卡", lightconeId=others[0]["id"])

    # ---------- 速度合成 ----------

    def test_base_speed_alone(self) -> None:
        result = self.plan("卡芙卡")
        self.assertAlmostEqual(result["speed"]["final"], 100.0, places=6)
        self.assertAlmostEqual(result["speed"]["base"], 100.0, places=6)

    def test_speed_boots_are_flat(self) -> None:
        result = self.plan("卡芙卡", relic={"speedBoots": True})
        self.assertAlmostEqual(result["speed"]["final"], 125.0, places=6)

    def test_percent_applies_to_base_only(self) -> None:
        """速度% 只乘基础速度，固定速度加在最后：100 × 1.1 + 20 = 130。"""
        result = self.plan("卡芙卡", relic={"customPct": 10, "customFlat": 20})
        self.assertAlmostEqual(result["speed"]["final"], 100 * 1.1 + 20, places=6)
        # 如果实现成 (基础+固定)×(1+%) 会得到 132，这里专门挡住这种错法
        self.assertNotAlmostEqual(result["speed"]["final"], (100 + 20) * 1.1, places=3)

    # ---------- 需求速度 ----------

    def test_required_speed_matches_community_formula(self) -> None:
        result = self.plan("卡芙卡", target={"t": 0, "actions": 2})
        self.assertAlmostEqual(result["verdict"]["requiredSpeed"], 20000 / 150, places=6)

    def test_vonwacq_reduces_required_speed(self) -> None:
        # 裸速度 100 达不到翁瓦克的 120，拉条不计入。
        slow = self.plan("卡芙卡", advance={"vonwacq": True}, target={"t": 0, "actions": 2})
        self.assertAlmostEqual(slow["advance"]["total"], 0.0, places=6)
        self.assertAlmostEqual(slow["verdict"]["requiredSpeed"], 20000 / 150, places=6)
        self.assertTrue(slow["warnings"])
        # 速度鞋 +25 = 125，达到 120，40% 拉条才生效。
        fast = self.plan(
            "卡芙卡",
            relic={"speedBoots": True},
            advance={"vonwacq": True},
            target={"t": 0, "actions": 2},
        )
        self.assertAlmostEqual(fast["verdict"]["requiredSpeed"], 16000 / 150, places=6)
        self.assertAlmostEqual(fast["advance"]["distance"], 4000.0, places=6)
        self.assertEqual(fast["warnings"], [])

    def test_dance_dance_dance_by_superimpose(self) -> None:
        expected = {1: 16, 2: 18, 3: 20, 4: 22, 5: 24}
        for level, percent in expected.items():
            with self.subTest(superimpose=level):
                result = self.plan(
                    "卡芙卡",
                    advance={"danceUlts": 1, "danceSuperimpose": level},
                )
                self.assertAlmostEqual(result["advance"]["total"], float(percent), places=6)

    def test_wind_set_advance(self) -> None:
        result = self.plan("卡芙卡", advance={"windUlts": 2})
        self.assertAlmostEqual(result["advance"]["total"], 50.0, places=6)

    def test_every_table_cell_matches_formula(self) -> None:
        result = self.plan(
            "卡芙卡",
            relic={"speedBoots": True},
            advance={"vonwacq": True},
        )
        advance_distance = result["advance"]["distance"]
        final_speed = result["speed"]["final"]
        for table in result["tables"]:
            for row in table["rows"]:
                for cell in row["cells"]:
                    expected = max(0.0, (row["actions"] * 10000 - advance_distance) / cell["totalAV"])
                    with self.subTest(mode=table["id"], actions=row["actions"], t=cell["t"]):
                        self.assertAlmostEqual(cell["speed"], expected, places=6)
                        self.assertEqual(cell["reachable"], cell["speed"] <= final_speed + 1e-9)

    def test_vonwacq_warning_below_120_speed(self) -> None:
        slow = self.plan("卡芙卡", advance={"vonwacq": True})
        self.assertTrue(slow["warnings"], "速度不到 120 时应该提示翁瓦克不触发")
        self.assertAlmostEqual(slow["advance"]["total"], 0.0, places=6)
        fast = self.plan("卡芙卡", relic={"speedBoots": True, "substatSpeed": 30}, advance={"vonwacq": True})
        self.assertEqual(fast["warnings"], [])
        self.assertAlmostEqual(fast["advance"]["total"], 40.0, places=6)

    # ---------- 星魂 ----------

    def test_eidolon_gates_rank_effects(self) -> None:
        """星魂效果只在解锁对应档位后出现。"""
        target = None
        for character in self.catalog["characters"]:
            probe = call("speed-plan", "plan", {"characterId": character["id"], "eidolon": 6})
            gated = [
                effect
                for effect in probe["effects"]["speed"]
                if effect["origin"].endswith("星魂") and effect.get("rank")
            ]
            if gated:
                target = (character, gated[0]["rank"])
                break
        if target is None:
            self.skipTest("当前数据里没有带速度效果的星魂")

        character, rank = target
        locked = call("speed-plan", "plan", {"characterId": character["id"], "eidolon": rank - 1})
        unlocked = call("speed-plan", "plan", {"characterId": character["id"], "eidolon": rank})
        locked_ids = {effect["id"] for effect in locked["effects"]["speed"]}
        unlocked_ids = {effect["id"] for effect in unlocked["effects"]["speed"]}
        self.assertTrue(unlocked_ids - locked_ids, "解锁星魂后应该多出效果")


class TestSpeedPlanModesSplitAndSplash(unittest.TestCase):
    """异相仲裁拆成普通王棋 / 绝境王棋；立绘优先用不带角标的游戏内预览图。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = call("speed-plan", "catalog")
        cls.modes = {mode["id"]: mode for mode in cls.catalog["modes"]}

    def test_yixiang_split_into_normal_and_despair(self) -> None:
        self.assertIn("yixiang", self.modes)
        self.assertIn("yixiang_juejing", self.modes)
        self.assertIn("王棋", self.modes["yixiang"]["name"])
        self.assertIn("绝境", self.modes["yixiang_juejing"]["name"])
        # 两者各自带行动值，改一个不影响另一个
        self.assertEqual(self.modes["yixiang"]["firstCycleAV"], 300)
        self.assertIn("firstCycleAV", self.modes["yixiang_juejing"])

    def test_both_yixiang_modes_build_tables(self) -> None:
        result = call(
            "speed-plan",
            "plan",
            {"characterId": "1005", "target": {"mode": "yixiang_juejing", "t": 0, "actions": 2}},
        )
        table = next(item for item in result["tables"] if item["id"] == "yixiang_juejing")
        self.assertEqual(table["rows"][0]["cells"][0]["totalAV"], 300.0)
        self.assertIn("绝境", result["verdict"]["mode"]["name"])

    def test_splash_uses_game_preview(self) -> None:
        """立绘优先用**游戏内预览图**（StarRailRes 那张，没有「首发/复刻」角标）。

        本地化之后 `splash` 是 `/modules/.../assets/xxx.webp`，原始远程 URL 挪进了
        `data/characters.json` 的 `_remote.splash` 作为兜底 —— catalog 接口**不暴露**
        `_remote`（界面用不到），所以这里要回数据文件里验「优先哪张」。
        少数角色（克拉拉/素裳/停云）的 StarRailRes 图这里连不上，退而用了米游社那张。
        """
        raw_rows = {
            row["name"]: row
            for row in json.loads(
                (ROOT / "modules" / "honkai-star-rail" / "data" / "characters.json").read_text(
                    encoding="utf-8"
                )
            )
        }
        for char in self.catalog["characters"][:15]:
            with self.subTest(name=char["name"]):
                splash = char["splash"]
                self.assertTrue(splash)
                remote = (raw_rows.get(char["name"], {}).get("_remote") or {}).get("splash") or ""
                if splash.startswith("/modules/"):
                    self.assertTrue((ROOT / splash.lstrip("/")).is_file(), splash)
                    self.assertTrue(remote.startswith("http"), remote)
                    if "act-upload" not in remote:
                        self.assertIn("preview", remote)
                else:
                    self.assertIn("character_preview", splash)
                # 米游社那张（带「首发/复刻」角标）只作为兜底
                self.assertTrue(char.get("splashFallback"))

    def test_every_character_has_a_splash_source(self) -> None:
        for char in self.catalog["characters"]:
            with self.subTest(name=char["name"]):
                self.assertTrue(char.get("splash") or char.get("splashFallback"))


class TestSpeedPlanUltSwitchAndOrnament(unittest.TestCase):
    """「轴底开大」勾选、位面饰品只留一个栏位。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = call("speed-plan", "catalog")
        cls.four = {item["name"]: item for item in cls.catalog["fourPieceSets"]}
        cls.ornaments = {item["name"]: item for item in cls.catalog["ornamentSets"]}

    def plan(self, **kwargs):
        payload = {
            "characterId": "1005",
            "relic": {},
            "advance": {},
            "target": {"t": 0, "actions": 2},
        }
        payload.update(kwargs)
        return call("speed-plan", "plan", payload)

    # ---------- 轴底开大 ----------

    def test_exclude_last_ult_trims_one_ult(self) -> None:
        wind = self.four["晨昏交界的翔鹰"]
        normal = self.plan(relic={"fourPieceId": wind["id"], "fourPieceUlts": 3})
        trimmed = self.plan(
            relic={"fourPieceId": wind["id"], "fourPieceUlts": 3},
            advance={"excludeLastUlt": True},
        )
        self.assertAlmostEqual(normal["advance"]["total"], 75.0, places=6)
        self.assertAlmostEqual(trimmed["advance"]["total"], 50.0, places=6)
        self.assertIn("轴底", trimmed["advance"]["items"][0]["label"])
        self.assertTrue(trimmed["advance"]["excludeLastUlt"])

    def test_exclude_last_ult_with_single_ult_drops_to_zero(self) -> None:
        wind = self.four["晨昏交界的翔鹰"]
        result = self.plan(
            relic={"fourPieceId": wind["id"], "fourPieceUlts": 1},
            advance={"excludeLastUlt": True},
        )
        self.assertAlmostEqual(result["advance"]["total"], 0.0, places=6)

    def test_exclude_last_ult_affects_light_cone_advance(self) -> None:
        harmony = next(
            item for item in self.catalog["characters"] if item["pathName"] == "同谐"
        )
        cones = call("speed-plan", "lightcones", {"path": harmony["path"]})["lightcones"]
        dance = next(item for item in cones if item["name"] == "舞！舞！舞！")
        normal = self.plan(
            characterId=harmony["id"],
            lightconeId=dance["id"],
            superimpose=5,
            advance={"coneUlts": 2},
        )
        trimmed = self.plan(
            characterId=harmony["id"],
            lightconeId=dance["id"],
            superimpose=5,
            advance={"coneUlts": 2, "excludeLastUlt": True},
        )
        self.assertAlmostEqual(normal["advance"]["total"], 48.0, places=6)
        self.assertAlmostEqual(trimmed["advance"]["total"], 24.0, places=6)

    def test_exclude_last_ult_does_not_touch_on_enter_advance(self) -> None:
        vonwacq = self.ornaments["生命的翁瓦克"]
        result = self.plan(
            relic={"speedBoots": True, "ornamentIds": [vonwacq["id"], ""]},
            advance={"excludeLastUlt": True},
        )
        # 进战拉条是一次性的，不属于「开大触发」，不该被扣
        self.assertAlmostEqual(result["advance"]["total"], 40.0, places=6)

    def test_exclude_last_ult_raises_required_speed(self) -> None:
        wind = self.four["晨昏交界的翔鹰"]
        normal = self.plan(relic={"fourPieceId": wind["id"], "fourPieceUlts": 2})
        trimmed = self.plan(
            relic={"fourPieceId": wind["id"], "fourPieceUlts": 2},
            advance={"excludeLastUlt": True},
        )
        self.assertGreater(trimmed["verdict"]["requiredSpeed"], normal["verdict"]["requiredSpeed"])

    # ---------- 位面饰品只留一个 ----------

    def test_only_first_ornament_is_counted(self) -> None:
        vonwacq = self.ornaments["生命的翁瓦克"]
        other = next(
            item
            for name, item in self.ornaments.items()
            if name != "生命的翁瓦克" and item["hasSpeedEffect"] and any(
                effect["kind"] == "pct" for effect in item["effects"]
            )
        )
        one = self.plan(relic={"speedBoots": True, "ornamentIds": [vonwacq["id"], ""]})
        two = self.plan(
            relic={"speedBoots": True, "ornamentIds": [vonwacq["id"], other["id"]]}
        )
        # 第二个饰品不该参与计算
        self.assertAlmostEqual(one["speed"]["final"], two["speed"]["final"], places=6)
        self.assertAlmostEqual(one["advance"]["total"], two["advance"]["total"], places=6)


class TestSpeedPlanTracesAndPools(unittest.TestCase):
    """行迹自带速度要计入；遗器池要全量（含没有速度效果的套装）。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = call("speed-plan", "catalog")
        cls.by_id = {str(item["id"]): item for item in cls.catalog["characters"]}

    def plan(self, character_id: str, **kwargs):
        payload = {"characterId": character_id, "relic": {}, "advance": {}, "target": {"t": 0, "actions": 2}}
        payload.update(kwargs)
        return call("speed-plan", "plan", payload)

    # ---------- 行迹速度 ----------

    def test_trace_speed_is_in_effective_base(self) -> None:
        # 镜流：白值 96 + 行迹「速度强化」2/3/4 = 105
        mirror = self.by_id["1212"]
        self.assertEqual(mirror["baseSpeed"], 96)
        self.assertEqual(mirror["traceSpeed"], 9)
        self.assertEqual(mirror["effectiveBaseSpeed"], 105)

    def test_character_without_trace_keeps_base(self) -> None:
        kafka = self.by_id["1005"]
        self.assertEqual(kafka["traceSpeed"], 0)
        self.assertEqual(kafka["effectiveBaseSpeed"], kafka["baseSpeed"])

    def test_plan_uses_effective_base_speed(self) -> None:
        result = self.plan("1212")  # 镜流
        self.assertAlmostEqual(result["speed"]["base"], 105.0, places=6)
        self.assertAlmostEqual(result["speed"]["baseRaw"], 96.0, places=6)
        self.assertAlmostEqual(result["speed"]["traceSpeed"], 9.0, places=6)
        # 没有任何其它加成时，最终速度就等于含行迹的基础速度
        self.assertAlmostEqual(result["speed"]["final"], 105.0, places=6)
        self.assertIn("行迹", result["speed"]["formula"])

    def test_trace_is_listed_in_breakdown(self) -> None:
        result = self.plan("1212")
        labels = " ".join(item["label"] for item in result["speed"]["breakdown"])
        self.assertIn("行迹", labels)

    def test_recommend_uses_effective_base_speed(self) -> None:
        result = call(
            "speed-plan",
            "recommend",
            {"characterId": "1212", "target": {"t": 0, "actions": 2}, "relic": {"speedBoots": False}},
        )
        self.assertAlmostEqual(result["character"]["baseSpeed"], 105.0, places=6)

    # ---------- 遗器池 ----------

    def test_all_relic_sets_are_listed(self) -> None:
        # 4 件套遗器 34 个 + 位面饰品 28 个 = 62
        self.assertEqual(len(self.catalog["fourPieceSets"]), 34)
        self.assertEqual(len(self.catalog["ornamentSets"]), 28)

    def test_pools_include_sets_without_speed_effects(self) -> None:
        without = [item for item in self.catalog["fourPieceSets"] if not item["hasSpeedEffect"]]
        self.assertTrue(without, "4 件套池里应该也有不带速度效果的套装")
        for entry in without:
            self.assertEqual(entry["effects"], [])
            self.assertTrue(entry["summary"])

    def test_relic_sets_sorted_by_release_order(self) -> None:
        for key in ("fourPieceSets", "ornamentSets"):
            orders = [
                item["releaseOrder"]
                for item in self.catalog[key]
                if item.get("releaseOrder") is not None
            ]
            with self.subTest(pool=key):
                self.assertEqual(orders, sorted(orders), f"{key} 没有按推出顺序排")
                self.assertTrue(orders, f"{key} 缺少推出顺序")

    def test_set_without_speed_contributes_nothing(self) -> None:
        plain = next(
            item for item in self.catalog["fourPieceSets"] if not item["hasSpeedEffect"]
        )
        result = self.plan("1005", relic={"fourPieceId": plain["id"]})
        # 选了不带速度效果的套装，速度不该有任何变化，拉条也不该有
        self.assertAlmostEqual(result["speed"]["final"], 100.0, places=6)
        self.assertAlmostEqual(result["advance"]["total"], 0.0, places=6)
        self.assertEqual(result["relicSets"], [])


class TestSpeedPlanModesAndAssets(unittest.TestCase):
    """各模式自己的行动值口径、角色推出顺序、官方图。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = call("speed-plan", "catalog")
        cls.modes = {mode["id"]: mode for mode in cls.catalog["modes"]}

    def plan(self, **kwargs):
        payload = {"characterId": "1005"}
        payload.update(kwargs)
        return call("speed-plan", "plan", payload)

    # ---------- 模式行动值 ----------

    def test_each_mode_has_its_own_cycle_length(self) -> None:
        # 混沌回忆首轮 150；异相仲裁（王棋关同结构）首轮 300
        self.assertEqual(self.modes["moc"]["firstCycleAV"], 150)
        self.assertEqual(self.modes["yixiang"]["firstCycleAV"], 300)
        self.assertEqual(self.modes["yixiang"]["maxT"], 5)
        self.assertEqual(self.modes["xugou"]["firstCycleAV"], 150)

    def test_yixiang_nodes_match_wangqi_rule(self) -> None:
        """异相仲裁：首轮 300 AV，其后每轮 100（0T=300、1T=400、2T=500 …）。"""
        result = self.plan(target={"mode": "yixiang", "t": 0, "actions": 2})
        table = next(item for item in result["tables"] if item["id"] == "yixiang")
        avs = [cell["totalAV"] for cell in table["rows"][0]["cells"]]
        self.assertEqual(avs, [300.0, 400.0, 500.0, 600.0, 700.0, 800.0])

    def test_target_mode_decides_required_speed(self) -> None:
        moc = self.plan(target={"mode": "moc", "t": 0, "actions": 2})
        yixiang = self.plan(target={"mode": "yixiang", "t": 0, "actions": 2})
        self.assertAlmostEqual(moc["verdict"]["requiredSpeed"], 20000 / 150, places=6)
        self.assertAlmostEqual(yixiang["verdict"]["requiredSpeed"], 20000 / 300, places=6)
        self.assertIn("异相仲裁", yixiang["verdict"]["mode"]["name"])
        self.assertIn("异相仲裁", yixiang["verdict"]["text"])

    # ---------- 推出顺序 ----------

    def test_characters_sorted_newest_first(self) -> None:
        orders = [
            char["releaseOrder"]
            for char in self.catalog["characters"]
            if char.get("releaseOrder") is not None
        ]
        self.assertEqual(orders, sorted(orders), "角色没有按推出顺序排")
        self.assertLess(orders[0], orders[-1])
        # 米游社图鉴第一条就是最新的角色
        self.assertEqual(self.catalog["characters"][0]["releaseOrder"], 0)

    def test_characters_without_order_go_last(self) -> None:
        orders = [char.get("releaseOrder") for char in self.catalog["characters"]]
        seen_none = False
        for order in orders:
            if order is None:
                seen_none = True
            else:
                self.assertFalse(seen_none, "没有推出顺序的角色应该排在最后")

    # ---------- 官方图 ----------

    def test_every_character_has_icon_and_splash(self) -> None:
        for char in self.catalog["characters"]:
            with self.subTest(name=char["name"]):
                self.assertTrue(char.get("icon"), "角色缺少图标")
                self.assertTrue(char.get("splash"), "角色缺少立绘")

    def test_icons_are_resized_variants(self) -> None:
        """图标必须是**小图**：远程要用 OSS 缩略参数，本地要用压过的小 webp。

        单个 177KB 的原图会把下拉拖垮，所以这条盯住体积而不是只看「有没有 url」。
        """
        sample = self.catalog["characters"][0]["icon"]
        if sample.startswith("/modules/"):
            path = ROOT / sample.lstrip("/")
            self.assertTrue(path.is_file(), sample)
            self.assertLess(path.stat().st_size, 16 * 1024, f"{sample} 太大了")
        else:
            self.assertIn("x-oss-process", sample)
            self.assertIn("w_128", sample)

    def test_lightcones_and_sets_have_icons(self) -> None:
        cones = call("speed-plan", "lightcones", {"path": "Warlock"})["lightcones"]
        self.assertTrue(cones)
        for cone in cones:
            self.assertTrue(cone.get("icon"), cone["name"])
        for entry in self.catalog["fourPieceSets"] + self.catalog["ornamentSets"]:
            self.assertTrue(entry.get("icon"), entry["name"])


class TestSpeedPlanRecommend(unittest.TestCase):
    """自动推荐配装：同命途约束、排序、去重、120 条件。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = call("speed-plan", "catalog")
        cls.kafka = next(item for item in cls.catalog["characters"] if item["name"] == "卡芙卡")
        cls.cone_paths = {
            str(item["id"]): item["path"]
            for item in call("speed-plan", "lightcones", {})["lightcones"]
        }

    def recommend(self, **kwargs):
        payload = {
            "characterId": self.kafka["id"],
            "target": {"t": 0, "actions": 3},
            "relic": {"speedBoots": True},
        }
        payload.update(kwargs)
        return call("speed-plan", "recommend", payload)

    def test_only_same_path_cones(self) -> None:
        result = self.recommend()
        self.assertTrue(result["results"])
        for item in result["results"]:
            if not item["coneId"]:
                continue
            with self.subTest(cone=item["coneName"]):
                self.assertEqual(self.cone_paths[str(item["coneId"])], self.kafka["path"])

    def test_sorted_by_needed_substat_speed(self) -> None:
        result = self.recommend()
        needs = [item["neededSubstatSpeed"] for item in result["results"]]
        self.assertEqual(needs, sorted(needs))

    def test_outcomes_are_distinct(self) -> None:
        result = self.recommend()
        signatures = [
            (round(item["speed"], 1), round(item["advance"], 1), item["ok"])
            for item in result["results"]
        ]
        self.assertEqual(len(signatures), len(set(signatures)), "推荐结果里有等效重复项")

    def test_assumptions_and_target_are_reported(self) -> None:
        result = self.recommend(target={"t": 0, "actions": 3, "customAV": 0})
        self.assertEqual(result["assumptions"]["speedBoots"], True)
        self.assertEqual(result["assumptions"]["superimpose"], 5)
        self.assertAlmostEqual(result["target"]["totalAV"], 150.0, places=6)
        self.assertEqual(result["target"]["actions"], 3)
        self.assertGreater(result["evaluated"], 100)

    def test_custom_av_is_honoured(self) -> None:
        result = self.recommend(target={"actions": 3, "customAV": 300})
        self.assertAlmostEqual(result["target"]["totalAV"], 300.0, places=6)
        # 300 AV 内 3 动只要 100 速，必然有满足的方案
        self.assertTrue(any(item["ok"] for item in result["results"]))

    def test_120_note_only_when_not_satisfied(self) -> None:
        result = self.recommend()
        for item in result["results"]:
            if "120" not in " ".join(item["notes"]):
                continue
            with self.subTest(combo=item["coneName"]):
                # 只有在速度没到 120 时才会给出这条提示
                self.assertLess(item["speed"], 120)

    def test_recommendation_math_is_consistent(self) -> None:
        result = self.recommend()
        target_av = result["target"]["totalAV"]
        actions = result["target"]["actions"]
        for item in result["results"]:
            expected_required = max(0.0, (actions * 10000 - item["advance"] / 100 * 10000) / target_av)
            with self.subTest(combo=item["coneName"]):
                self.assertAlmostEqual(item["required"], expected_required, places=6)
                self.assertAlmostEqual(
                    item["neededSubstatSpeed"], max(0.0, item["required"] - item["speed"]), places=6
                )

    def test_speed_boots_off_changes_results(self) -> None:
        on = self.recommend(relic={"speedBoots": True})
        off = self.recommend(relic={"speedBoots": False})
        self.assertGreater(
            on["results"][0]["speed"], off["results"][0]["speed"]
        )


class TestSpeedPlanConeAndTarget(unittest.TestCase):
    """光锥拉条数据驱动、自定义行动值节点、补足建议、数据质量。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = call("speed-plan", "catalog")
        cls.harmony = next(
            item for item in cls.catalog["characters"] if item["pathName"] == "同谐"
        )
        cones = call("speed-plan", "lightcones", {"path": cls.harmony["path"]})["lightcones"]
        cls.dance = next(item for item in cones if item["name"] == "舞！舞！舞！")

    def plan(self, **kwargs):
        payload = {
            "characterId": "1005",
            "relic": {},
            "advance": {},
            "target": {"t": 0, "actions": 2},
        }
        payload.update(kwargs)
        return call("speed-plan", "plan", payload)

    def dance_plan(self, superimpose: int, ults: float):
        return self.plan(
            characterId=self.harmony["id"],
            lightconeId=self.dance["id"],
            superimpose=superimpose,
            advance={"coneUlts": ults},
        )

    # ---------- 光锥拉条 ----------

    def test_cone_advance_uses_superimpose_value(self) -> None:
        for level, per_ult in ((1, 16.0), (3, 20.0), (5, 24.0)):
            with self.subTest(superimpose=level):
                result = self.dance_plan(level, 2)
                self.assertAlmostEqual(result["advance"]["total"], per_ult * 2, places=6)

    def test_cone_advance_needs_ults(self) -> None:
        result = self.dance_plan(5, 0)
        self.assertAlmostEqual(result["advance"]["total"], 0.0, places=6)
        # 即使没填次数，也要把「这把光锥能给拉条」的信息摆出来
        self.assertTrue(result["effects"]["coneAdvance"])
        self.assertNotIn("counted", result["effects"]["coneAdvance"][0])

    def test_cone_advance_reported_as_counted(self) -> None:
        result = self.dance_plan(5, 1)
        entry = result["effects"]["coneAdvance"][0]
        self.assertEqual(entry["trigger"], "perUlt")
        self.assertAlmostEqual(entry["counted"], 24.0, places=6)

    # ---------- 自定义行动值 ----------

    def test_custom_av_overrides_cycle_math(self) -> None:
        result = self.plan(relic={"speedBoots": True}, target={"actions": 3, "customAV": 300})
        # 3 动 / 300 AV
        self.assertAlmostEqual(result["verdict"]["requiredSpeed"], 30000 / 300, places=6)
        self.assertEqual(result["verdict"]["totalAV"], 300.0)
        self.assertIn("300", result["verdict"]["text"])

    def test_zero_custom_av_falls_back_to_t(self) -> None:
        result = self.plan(target={"t": 1, "actions": 3, "customAV": 0})
        self.assertAlmostEqual(result["verdict"]["requiredSpeed"], 30000 / 250, places=6)

    # ---------- 补足建议 ----------

    def test_suggestions_appear_when_short(self) -> None:
        result = self.plan(target={"t": 0, "actions": 3})
        self.assertTrue(result["suggestions"])
        # 按「能达成的优先」排序
        flags = [item["ok"] for item in result["suggestions"]]
        self.assertEqual(flags, sorted(flags, reverse=True))
        for item in result["suggestions"]:
            self.assertIn("label", item)
            self.assertAlmostEqual(item["gap"], item["required"] - item["speed"], places=6)

    def test_suggestions_empty_when_comfortable(self) -> None:
        result = self.plan(relic={"speedBoots": True, "substatSpeed": 100})
        self.assertEqual(result["suggestions"], [])

    def test_speed_boot_suggestion_gains_25(self) -> None:
        result = self.plan(target={"t": 0, "actions": 3})
        boots = next(item for item in result["suggestions"] if "速度鞋" in item["label"])
        self.assertAlmostEqual(boots["speed"], result["speed"]["final"] + 25, places=6)

    def test_flat_suggestion_closes_the_gap(self) -> None:
        result = self.plan(target={"t": 0, "actions": 3})
        flat = next(
            item for item in result["suggestions"] if item["label"].startswith("副词条")
        )
        self.assertTrue(flat["ok"], "按建议堆到该数值时应该正好够")
        self.assertAlmostEqual(flat["speed"], flat["required"], places=6)

    # ---------- 数据质量 ----------

    def test_no_placeholder_names(self) -> None:
        for item in self.catalog["characters"]:
            self.assertNotIn("{", item["name"])
            self.assertNotIn("}", item["name"])

    def test_no_duplicate_character_rows(self) -> None:
        keys = [
            (item["name"], item["pathName"], item["elementName"], item["baseSpeed"])
            for item in self.catalog["characters"]
        ]
        self.assertEqual(len(keys), len(set(keys)), "角色列表里有完全重复的行")

    def test_trailblazer_forms_are_distinct(self) -> None:
        forms = [item for item in self.catalog["characters"] if item["name"] == "开拓者"]
        self.assertGreaterEqual(len(forms), 4)
        paths = {item["pathName"] for item in forms}
        self.assertGreater(len(paths), 1)


class TestSpeedPlanRelics(unittest.TestCase):
    """遗器套装的数据驱动：风套/翁瓦克/速度套自动带出，有条件的不乱算。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = call("speed-plan", "catalog")
        cls.four = {item["name"]: item for item in cls.catalog["fourPieceSets"]}
        cls.ornaments = {item["name"]: item for item in cls.catalog["ornamentSets"]}

    def plan(self, **kwargs):
        payload = {
            "characterId": "1005",  # 卡芙卡，基础速度 100，好算
            "relic": {},
            "advance": {},
            "target": {"t": 0, "actions": 2},
        }
        payload.update(kwargs)
        return call("speed-plan", "plan", payload)

    def test_sets_are_exposed_with_effects(self) -> None:
        self.assertTrue(self.four, "4 件套列表是空的")
        self.assertTrue(self.ornaments, "位面饰品列表是空的")
        for entry in list(self.four.values()) + list(self.ornaments.values()):
            self.assertTrue(entry["id"] and entry["name"], str(entry))
            # 池子里包含没有速度效果的套装（能选，但不参与配速计算）
            self.assertIn("hasSpeedEffect", entry)
            for effect in entry["effects"]:
                self.assertIn(effect["kind"], ("pct", "flat", "advance"))
                self.assertIn(effect["trigger"], ("passive", "perUlt", "allyUlt", "onEnter", "conditional"))

    def test_wind_set_advance_scales_with_ults(self) -> None:
        wind = self.four["晨昏交界的翔鹰"]
        for ults, expected in ((1, 25.0), (2, 50.0), (3, 75.0)):
            with self.subTest(ults=ults):
                result = self.plan(
                    relic={"fourPieceId": wind["id"], "fourPieceUlts": ults}
                )
                self.assertAlmostEqual(result["advance"]["total"], expected, places=6)

    def test_wind_set_without_ults_contributes_nothing(self) -> None:
        wind = self.four["晨昏交界的翔鹰"]
        result = self.plan(relic={"fourPieceId": wind["id"], "fourPieceUlts": 0})
        self.assertAlmostEqual(result["advance"]["total"], 0.0, places=6)

    def test_vonwacq_is_one_time_on_enter(self) -> None:
        vonwacq = self.ornaments["生命的翁瓦克"]
        result = self.plan(relic={"speedBoots": True, "ornamentIds": [vonwacq["id"], ""]})
        self.assertAlmostEqual(result["advance"]["total"], 40.0, places=6)
        self.assertAlmostEqual(result["speed"]["final"], 125.0, places=6)
        # (2×10000 − 4000) ÷ 150
        self.assertAlmostEqual(result["verdict"]["requiredSpeed"], 16000 / 150, places=6)

    def test_vonwacq_warns_below_120(self) -> None:
        vonwacq = self.ornaments["生命的翁瓦克"]
        slow = self.plan(relic={"ornamentIds": [vonwacq["id"], ""]})
        self.assertTrue(slow["warnings"])
        self.assertAlmostEqual(slow["advance"]["total"], 0.0, places=6)
        fast = self.plan(relic={"speedBoots": True, "ornamentIds": [vonwacq["id"], ""]})
        self.assertEqual(fast["warnings"], [])
        self.assertAlmostEqual(fast["advance"]["total"], 40.0, places=6)

    def test_passive_percent_set_applies_automatically(self) -> None:
        gunslinger = self.four["野穗伴行的快枪手"]
        result = self.plan(relic={"speedBoots": True, "fourPieceId": gunslinger["id"]})
        # 4 件套「速度提高6%」无条件 → 100 × 1.06 + 25
        self.assertAlmostEqual(result["speed"]["final"], 131.0, places=6)

    def test_conditional_effect_is_listed_not_counted(self) -> None:
        messenger = self.four["骇域漫游的信使"]
        result = self.plan(relic={"speedBoots": True, "fourPieceId": messenger["id"]})
        # 2 件套 +6% 自动；4 件套（开大给全队 +12%，按回合）不该自动计入
        self.assertAlmostEqual(result["speed"]["final"], 131.0, places=6)
        texts = " ".join(effect["text"] for effect in result["effects"]["conditional"])
        self.assertIn("我方全体速度提高12%", texts)

    def test_two_ornaments_stack(self) -> None:
        vonwacq = self.ornaments["生命的翁瓦克"]
        other = next(
            item for name, item in self.ornaments.items() if name != "生命的翁瓦克"
        )
        single = self.plan(relic={"speedBoots": True, "ornamentIds": [vonwacq["id"], ""]})
        double = self.plan(
            relic={"speedBoots": True, "ornamentIds": [vonwacq["id"], other["id"]]}
        )
        self.assertGreaterEqual(double["speed"]["final"], single["speed"]["final"])
        # 翁瓦克是唯一的进战拉条饰品，两个饰品不该把拉条翻倍
        self.assertAlmostEqual(double["advance"]["total"], single["advance"]["total"], places=6)

    def test_applied_sets_are_reported(self) -> None:
        wind = self.four["晨昏交界的翔鹰"]
        vonwacq = self.ornaments["生命的翁瓦克"]
        result = self.plan(
            relic={
                "speedBoots": True,
                "fourPieceId": wind["id"],
                "fourPieceUlts": 1,
                "ornamentIds": [vonwacq["id"], ""],
            }
        )
        names = {entry["setName"] for entry in result["relicSets"]}
        self.assertEqual(names, {"晨昏交界的翔鹰", "生命的翁瓦克"})


class TestImporter(unittest.TestCase):
    """导入器的文案解析：占位符换算与效果抽取（不联网）。"""

    @classmethod
    def setUpClass(cls) -> None:
        import importlib.util

        path = ROOT / "tools" / "import_hsr_data.py"
        spec = importlib.util.spec_from_file_location("hsr_importer_under_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.importer = module

    def test_placeholder_rendering(self) -> None:
        render = self.importer.render_description
        # 带 % 的原始值是比例，要 ×100
        self.assertEqual(render("行动提前#1[i]%。", [0.24]), "行动提前24%。")
        # 不带 % 的按原值
        self.assertEqual(render("速度提高#1[i]点。", [12]), "速度提高12点。")
        # f1 保留一位小数
        self.assertEqual(render("恢复#2[f1]点能量。", [1, 30.0]), "恢复30.0点能量。")
        # 多个占位符
        self.assertEqual(
            render("速度提高#1[i]%，持续#2[i]回合。", [0.18, 2]),
            "速度提高18%，持续2回合。",
        )

    def test_effect_extraction(self) -> None:
        extract = self.importer.extract_effects
        effects = extract("当装备者施放终结技后，我方全体行动提前24%。", source="光锥")
        self.assertEqual(len(effects), 1)
        self.assertEqual(effects[0]["kind"], "advance")
        self.assertEqual(effects[0]["value"], 24.0)
        self.assertEqual(effects[0]["apply"], "team")

        own = extract("使装备者的速度提高6%，普攻造成的伤害提高10%。", source="遗器·4件套")
        self.assertEqual(len(own), 1)
        self.assertEqual(own[0]["kind"], "pct")
        self.assertEqual(own[0]["value"], 6.0)
        self.assertEqual(own[0]["apply"], "self")

        flat = extract("进入战斗时，我方全体速度提高12点，持续1回合。", source="光锥")
        self.assertEqual(flat[0]["kind"], "flat")
        self.assertEqual(flat[0]["value"], 12.0)

        self.assertEqual(extract("暴击率提高12%。", source="遗器"), [])

    def test_apply_classification(self) -> None:
        """速度效果加在谁身上：self / team / ally。"""
        extract = self.importer.extract_effects

        def apply_of(text: str) -> str:
            return extract(text, source="测试")[0]["apply"]

        # 自身
        self.assertEqual(apply_of("使装备者的速度提高6%。"), "self")
        self.assertEqual(apply_of("发动时使自身速度提高8%，持续2回合。"), "self")
        # 我方全体 = 全队共享 → 算自己
        self.assertEqual(apply_of("我方全体速度提高12%。"), "team")
        self.assertEqual(apply_of("当装备者对我方目标施放终结技时，我方全体速度提高12%，持续1回合。"), "team")
        self.assertEqual(apply_of("进入战斗时，我方全体速度提高10%，持续2回合。"), "team")
        # 只给队友 → 不算自己
        self.assertEqual(apply_of("施放战技时，被指定的我方目标在行动后速度提高30%，持续1回合。"), "ally")
        self.assertEqual(apply_of("得到【赐福】的我方单体施放终结技后速度提高20%，持续1回合。"), "ally")
        # 用户口径：我方目标**包含角色自己**（风堇 2 魂），所以这条是 self；
        # 只有「被指定的我方目标」「得到【赐福】的我方单体」这种单个指定队友才是 ally。
        self.assertEqual(apply_of("我方目标生命值降低时，速度提高30%，持续2回合。"), "self")

    def test_duration_and_stacks_extraction(self) -> None:
        extract = self.importer.extract_effects

        def one(text: str) -> dict:
            return extract(text, source="测试")[0]

        # 「持续 N 回合」
        self.assertEqual(one("施放战技后，速度提高20%，持续1回合。")["durationTurns"], 1)
        self.assertEqual(one("使自身速度提高8%，持续2回合。")["durationTurns"], 2)
        self.assertEqual(one("速度提高6%。")["durationTurns"], 0)
        # 「最多叠加 N 层」
        stacked = one("装备者每次施放攻击后，速度提高8.0%，最多叠加3层。")
        self.assertEqual(stacked["maxStacks"], 3)
        self.assertEqual(stacked["apply"], "self")
        self.assertEqual(one("速度提高6%。")["maxStacks"], 0)
        # 真实数据：只需等待叠 3 层
        self.assertEqual(one("装备者每次施放攻击后，速度提高4.8%，最多叠加3层。")["maxStacks"], 3)
        # 真实数据：骇域漫游的信使 4 件套持续 1 回合
        self.assertEqual(
            one("当装备者对我方目标施放终结技时，我方全体速度提高12%，持续1回合，该效果无法叠加。")[
                "durationTurns"
            ],
            1,
        )


class TestSpeedPlanActionSimulation(unittest.TestCase):
    """行动模拟内核：加速按「自己第几次行动」生效，而不是永远按满值算。

    背景（用户需求）：静态公式默认加速从第 1 次行动就生效，但
    「施放终结技后速度提高 12%」这类要等开大之后才生效、
    「每次施放攻击后速度提高 8%，最多叠 3 层」这类是逐层叠上去的 ——
    必须真的把角色一次一次行动走出来，才知道窗口内到底能打几次。
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = call("speed-plan", "catalog")
        cls.four = {item["name"]: item for item in cls.catalog["fourPieceSets"]}
        cls.cones = {item["name"]: item for item in call("speed-plan", "lightcones")["lightcones"]}
        cls.characters = {item["name"]: item for item in cls.catalog["characters"]}

    def plan(self, **kwargs):
        payload = {
            "characterId": "1005",  # 卡芙卡：基础速度 100
            "relic": {"speedBoots": False},
            "advance": {},
            "target": {"mode": "moc", "t": 0, "actions": 2},
        }
        payload.update(kwargs)
        return call("speed-plan", "plan", payload)

    # ---------- 兼容性 ----------
    def test_no_timeline_effect_matches_static_formula(self) -> None:
        """没有任何随行动变化的加速时，模拟结果必须与静态公式完全一致。"""
        for relic in (
            {"speedBoots": True},
            {"speedBoots": True, "substatSpeed": 12, "customPct": 6, "customFlat": 4},
            {"speedBoots": True, "setSpeedPct": 6},
        ):
            with self.subTest(relic=relic):
                result = self.plan(relic=relic, target={"mode": "moc", "t": 0, "actions": 3})
                base = result["speed"]["base"]
                expected = base * (1 + result["speed"]["pct"] / 100.0) + result["speed"]["flat"]
                self.assertAlmostEqual(result["speed"]["final"], expected, places=9)
                self.assertFalse(result["speed"]["hasTimeline"])
                # 需求速度 = 闭式公式
                self.assertAlmostEqual(
                    result["verdict"]["requiredSpeed"],
                    (3 * 10000 - result["advance"]["distance"]) / result["verdict"]["totalAV"],
                    places=9,
                )
                # 可打次数 = 旧公式的 floor 口径
                self.assertEqual(
                    result["verdict"]["achievableActions"],
                    int(
                        math.floor(
                            (
                                result["speed"]["final"] * result["verdict"]["totalAV"]
                                + result["advance"]["distance"]
                            )
                            / 10000
                            + 1e-9
                        )
                    ),
                )
                # 时间线每一步同速
                speeds = {round(item["speed"], 9) for item in result["simulation"]["timeline"]}
                self.assertEqual(speeds, {round(result["speed"]["final"], 9)})

    # ---------- 开大触发 ----------
    def test_per_ult_speed_starts_after_first_ult_action(self) -> None:
        """开大加速从 firstUltAction+1 次行动起生效，持续 durationTurns 次。"""
        messenger = self.four["骇域漫游的信使"]
        result = self.plan(
            relic={"speedBoots": False, "fourPieceId": messenger["id"], "ultTargetsAlly": True, "fourPieceUlts": 2},
            target={"mode": "moc", "t": 2, "actions": 4},
            simulation={"firstUltAction": 2},
        )
        timeline = result["simulation"]["timeline"]
        s0 = result["speed"]["final"]
        boost = s0 + result["speed"]["base"] * 0.12
        # 第 1、2 次行动还没有开大
        self.assertAlmostEqual(timeline[0]["speed"], s0, places=6)
        self.assertAlmostEqual(timeline[1]["speed"], s0, places=6)
        # 第 3 次行动起生效
        self.assertAlmostEqual(timeline[2]["speed"], boost, places=6)
        # 「持续 1 回合」= 只有第 3 次行动那一下，第 4 次行动起回落
        self.assertAlmostEqual(timeline[3]["speed"], s0, places=6)
        self.assertEqual(result["simulation"]["firstUltAction"], 2)

    def test_first_ult_action_default_is_one(self) -> None:
        self.assertEqual(self.plan()["simulation"]["firstUltAction"], 1)

    def test_per_ult_speed_respects_duration_turns(self) -> None:
        """开大加速按 durationTurns 到期回落（谐乐静默之后：+16%，持续 2 回合）。"""
        cone = self.cones.get("谐乐静默之后")
        char = next(
            (
                item
                for item in self.catalog["characters"]
                if (cone or {}).get("path") and item["path"] == cone["path"]
            ),
            None,
        )
        if cone is None or char is None:
            self.skipTest("数据里没有「谐乐静默之后」或同命途角色")
        probe = call(
            "speed-plan",
            "plan",
            {
                "characterId": char["id"],
                "lightconeId": cone["id"],
                "superimpose": 5,
                "relic": {"speedBoots": False},
                "advance": {},
                "target": {"mode": "moc", "t": 1, "actions": 4},
            },
        )
        target_effect = next(
            (
                item
                for item in probe["effects"]["speed"]
                if item.get("trigger") == "perUlt" and item.get("durationTurns") == 2
            ),
            None,
        )
        if target_effect is None:
            self.skipTest("这条光锥当前没有「开大触发 + 持续 2 回合」的速度效果")
        result = call(
            "speed-plan",
            "plan",
            {
                "characterId": char["id"],
                "lightconeId": cone["id"],
                "superimpose": 5,
                "enabledEffects": [target_effect["id"]],
                "relic": {"speedBoots": False},
                "advance": {},
                "target": {"mode": "moc", "t": 1, "actions": 4},
                "simulation": {"firstUltAction": 0},
            },
        )
        timeline = result["simulation"]["timeline"]
        s0 = result["speed"]["final"]
        self.assertTrue(result["speed"]["hasTimeline"], result["speed"]["breakdown"])
        # firstUltAction=0 → 第 1 次行动起生效；持续 2 回合 → 第 3 次行动起失效
        self.assertGreater(timeline[0]["speed"], s0)
        self.assertGreater(timeline[1]["speed"], s0)
        self.assertAlmostEqual(timeline[2]["speed"], s0, places=6)

    # ---------- 叠层 ----------
    def _stack_plan(self, superimpose: int, target: dict | None = None):
        """只需等待（虚无光锥）：装备者每次施放攻击后速度提高 X%，最多叠 3 层。"""
        wait = self.cones.get("只需等待")
        if wait is None:
            self.skipTest("数据里没有「只需等待」")
        char = self.characters.get("卡芙卡")  # 虚无，基础速度 100
        result = call(
            "speed-plan",
            "plan",
            {
                "characterId": char["id"],
                "lightconeId": wait["id"],
                "superimpose": superimpose,
                "relic": {"speedBoots": False},
                "advance": {},
                "target": target or {"mode": "moc", "t": 2, "actions": 6},
            },
        )
        # 叠层效果是光锥效果，默认不勾（trigger=conditional）：显式勾上前先确认它在列表里
        stack_effect = next(
            (item for item in result["effects"]["speed"] if item.get("maxStacks")),
            None,
        )
        if stack_effect is None:
            self.skipTest("这条光锥当前没有叠层速度效果")
        return call(
            "speed-plan",
            "plan",
            {
                "characterId": char["id"],
                "lightconeId": wait["id"],
                "superimpose": superimpose,
                "enabledEffects": [stack_effect["id"]],
                "relic": {"speedBoots": False},
                "advance": {},
                "target": target or {"mode": "moc", "t": 2, "actions": 6},
            },
        ), stack_effect

    def test_stack_effect_grows_by_one_per_action(self) -> None:
        """「每次施放攻击后速度提高 X%，最多叠 N 层」→ 第 k 次行动前有 min(k-1, N) 层。"""
        result, stack_effect = self._stack_plan(5, {"mode": "moc", "t": 3, "actions": 6})
        self.assertTrue(result["speed"]["hasTimeline"], result["speed"]["breakdown"])
        self.assertEqual(stack_effect["maxStacks"], 3)
        per_stack = stack_effect["value"]
        timeline = result["simulation"]["timeline"]
        for index, item in enumerate(timeline[:4]):
            with self.subTest(action=item["action"]):
                stacks = min(index, stack_effect["maxStacks"])
                self.assertAlmostEqual(
                    item["speed"],
                    result["speed"]["base"]
                    * (1 + (result["speed"]["pct"] + per_stack * stacks) / 100.0)
                    + result["speed"]["flat"],
                    places=6,
                )
                if stacks == 0:
                    # 第 1 次行动时一层都没有 → 这条增益还没生效
                    self.assertEqual(item["active"], ["（无增益）"])
                else:
                    self.assertIn(f"层数 {stacks}/3", item["active"])
        # 到第 4 次行动就满层了，之后不再涨
        self.assertIn("层数 3/3", timeline[3]["active"])
        self.assertIn("层数 3/3", timeline[4]["active"])
        self.assertAlmostEqual(timeline[4]["speed"], timeline[3]["speed"], places=9)

    def test_stack_effect_notes_are_reported(self) -> None:
        result, stack_effect = self._stack_plan(1)
        self.assertTrue(
            any(f"最多 {stack_effect['maxStacks']} 层" in note for note in result["simulation"]["notes"]),
            result["simulation"]["notes"],
        )

    # ---------- 仅队友 ----------
    def test_ally_speed_is_not_counted_for_self(self) -> None:
        """「被指定的我方目标…」这类只给队友的提速，勾上也不算自己的速度。"""
        bronya = self.characters.get("布洛妮娅")
        if bronya is None:
            self.skipTest("数据里没有布洛妮娅")
        probe = call(
            "speed-plan",
            "plan",
            {
                "characterId": bronya["id"],
                "eidolon": 6,
                "relic": {"speedBoots": False},
                "advance": {},
                "target": {"t": 0, "actions": 2},
            },
        )
        ally = [item for item in probe["effects"]["speed"] if item["apply"] == "ally"]
        if not ally:
            self.skipTest("布洛妮娅当前数据里没有 ally 类效果")
        ids = [item["id"] for item in ally]
        plain = self.plan(characterId=bronya["id"], eidolon=6)
        with_ally = self.plan(characterId=bronya["id"], eidolon=6, enabledEffects=ids)
        # 速度一分不涨
        self.assertAlmostEqual(with_ally["speed"]["final"], plain["speed"]["final"], places=9)
        self.assertAlmostEqual(with_ally["speed"]["pct"], plain["speed"]["pct"], places=9)
        # 但效果照旧列出来，并且带上 apply，界面好标「仅队友」
        listed = [item for item in with_ally["effects"]["speed"] if item["id"] in ids]
        self.assertEqual(len(listed), len(ids))
        for item in listed:
            self.assertEqual(item["apply"], "ally")
        self.assertTrue(
            any("仅队友" in entry["label"] for entry in with_ally["speed"]["breakdown"])
        )

    # ---------- 时间线格式 ----------
    def test_timeline_shape_and_limit(self) -> None:
        result = self.plan(target={"mode": "moc", "t": 3, "actions": 8})
        timeline = result["simulation"]["timeline"]
        self.assertLessEqual(len(timeline), 12)
        self.assertGreaterEqual(len(timeline), 1)
        for index, item in enumerate(timeline):
            self.assertEqual(item["action"], index + 1)
            self.assertIn("speed", item)
            self.assertIn("av", item)
            self.assertIn("pct", item)
            self.assertIn("flat", item)
            self.assertIsInstance(item["active"], list)
        # 行动值单调不减，第 1 次行动是 0
        self.assertEqual(timeline[0]["av"], 0.0)
        avs = [item["av"] for item in timeline]
        self.assertEqual(avs, sorted(avs))

    def test_simulation_window_follows_target(self) -> None:
        result = self.plan(target={"mode": "moc", "t": 0, "actions": 2, "customAV": 300})
        self.assertAlmostEqual(result["simulation"]["windowAV"], 300.0, places=9)
        result = self.plan(target={"mode": "moc", "t": 2, "actions": 2})
        self.assertAlmostEqual(result["simulation"]["windowAV"], 350.0, places=9)


class TestSpeedPlanRecommendConsistency(unittest.TestCase):
    """推荐引擎必须和界面口径一致（单饰品栏位、轴底开大、不用显示顺序截断）。"""

    def recommend(self, **kwargs):
        payload = {"characterId": "1005", "target": {"mode": "moc", "t": 0, "actions": 3}}
        payload.update(kwargs)
        return call("speed-plan", "recommend", payload)

    def test_covers_whole_relic_pool(self) -> None:
        # 4 件套 34 个 + 位面饰品 28 个都要参与穷举，不能被显示顺序截断
        result = self.recommend()
        self.assertGreaterEqual(result["evaluated"], 34 * 28)

    def test_single_ornament_slot_matches_ui(self) -> None:
        result = self.recommend()
        for item in result["results"]:
            self.assertEqual(len(item["ornamentIds"]), 1, item)
            self.assertEqual(len(item["ornamentNames"]), 1, item)

    def test_recommend_respects_exclude_last_ult(self) -> None:
        normal = self.recommend(coneUlts=2, fourPieceUlts=2)
        trimmed = self.recommend(coneUlts=2, fourPieceUlts=2, excludeLastUlt=True)
        self.assertEqual(normal["assumptions"]["coneUlts"], 2)
        self.assertEqual(trimmed["assumptions"]["coneUlts"], 1)
        self.assertEqual(trimmed["assumptions"]["fourPieceUlts"], 1)
        # 少一次开大拉条，最省方案需要补的副词条速度不会更少
        self.assertGreaterEqual(
            trimmed["results"][0]["neededSubstatSpeed"],
            normal["results"][0]["neededSubstatSpeed"] - 1e-9,
        )

    def test_applying_top_recommendation_matches_plan(self) -> None:
        """套用推荐第一名后，用 plan 算出来的速度应该和推荐里写的一致。

        推荐按它自己的假设算（叠影、开大次数），套用时这些也要一起带过去——
        界面上的「套用」按钮就是这么做的（会同步叠影）。
        """
        result = self.recommend()
        best = result["results"][0]
        assumptions = result["assumptions"]
        plan = call(
            "speed-plan",
            "plan",
            {
                "characterId": "1005",
                "lightconeId": best["coneId"],
                "superimpose": assumptions["superimpose"],
                "relic": {
                    "speedBoots": True,
                    "fourPieceId": best["fourPieceId"],
                    "fourPieceUlts": assumptions["fourPieceUlts"],
                    "ornamentIds": best["ornamentIds"],
                },
                "advance": {"coneUlts": assumptions["coneUlts"]},
                "target": {"mode": "moc", "t": 0, "actions": 3},
            },
        )
        self.assertAlmostEqual(plan["speed"]["final"], best["speed"], places=1)
        self.assertAlmostEqual(plan["advance"]["total"], best["advance"], places=1)


class TestWebOracleIsCurrent(unittest.TestCase):
    """网页版对拍基准必须和当前 Python 实现一致。

    为什么需要这条：网页版是 JS 重写，它的正确性靠 tests/fixtures/web_oracle.json
    这份「Python 算出的标准答案」。如果数据更新了却没重新生成基准，
    网页版会拿着**过期**的答案"自检通过"，两边一起错。这条测试就是防这个。
    """

    @classmethod
    def setUpClass(cls) -> None:
        path = ROOT / "tests" / "fixtures" / "web_oracle.json"
        if not path.is_file():
            raise unittest.SkipTest("还没有生成网页版基准，先跑 tools/make_web_oracle.py")
        cls.oracle = json.loads(path.read_text(encoding="utf-8"))

    def test_plan_configs_match_python(self) -> None:
        for entry in self.oracle["plans"]:
            with self.subTest(label=entry["label"]):
                result = call("speed-plan", "plan", entry["payload"])
                self.assertAlmostEqual(result["speed"]["final"], entry["speed"]["final"], places=6)
                self.assertAlmostEqual(result["speed"]["pct"], entry["speed"]["pct"], places=6)
                self.assertAlmostEqual(result["speed"]["flat"], entry["speed"]["flat"], places=6)
                self.assertAlmostEqual(
                    result["advance"]["total"], entry["advance"]["total"], places=6
                )
                self.assertAlmostEqual(
                    result["verdict"]["requiredSpeed"],
                    entry["verdict"]["requiredSpeed"],
                    places=6,
                )
                self.assertEqual(
                    result["verdict"]["achievableActions"], entry["verdict"]["achievableActions"]
                )

    def test_tables_match_python(self) -> None:
        for entry in self.oracle["plans"]:
            for expected_table in entry.get("tables") or []:
                with self.subTest(label=entry["label"], mode=expected_table["id"]):
                    result = call("speed-plan", "plan", entry["payload"])
                    table = next(
                        item for item in result["tables"] if item["id"] == expected_table["id"]
                    )
                    for row, expected_row in zip(table["rows"], expected_table["cells"]):
                        for cell, expected_speed in zip(row["cells"], expected_row):
                            self.assertAlmostEqual(cell["speed"], expected_speed, places=6)

    def test_simulation_matches_python(self) -> None:
        """行动模拟的时间线也要对拍：网页版一旦漏同步内核，这条会立刻炸。

        （tools/check_web_port.mjs 的通用比较器会逐字段比 entry.simulation，
        所以基准里写了什么，网页版就必须原样给出来。）
        """
        checked = 0
        for entry in self.oracle["plans"]:
            expected = entry.get("simulation")
            if not expected:
                continue
            with self.subTest(label=entry["label"]):
                result = call("speed-plan", "plan", entry["payload"])
                actual = result["simulation"]
                self.assertEqual(actual["firstUltAction"], expected["firstUltAction"])
                self.assertAlmostEqual(actual["windowAV"], expected["windowAV"], places=6)
                self.assertEqual(actual["achievedActions"], expected["achievedActions"])
                self.assertEqual(actual["completedActions"], expected["completedActions"])
                self.assertEqual(actual["notes"], expected["notes"])
                self.assertEqual(len(actual["timeline"]), len(expected["timeline"]))
                for got, want in zip(actual["timeline"], expected["timeline"]):
                    self.assertEqual(got["action"], want["action"])
                    self.assertAlmostEqual(got["speed"], want["speed"], places=6)
                    self.assertAlmostEqual(got["av"], want["av"], places=6)
                    self.assertAlmostEqual(got["pct"], want["pct"], places=6)
                    self.assertAlmostEqual(got["flat"], want["flat"], places=6)
                    self.assertEqual(got["active"], want["active"])
                checked += 1
        self.assertGreater(checked, 0, "基准里一条 simulation 都没有，模拟内核没被测到")

    def test_recommend_assumptions_match_python(self) -> None:
        for entry in self.oracle["recommends"]:
            with self.subTest(label=entry["label"]):
                result = call("speed-plan", "recommend", entry["payload"])
                self.assertEqual(result["evaluated"], entry["evaluated"])
                self.assertEqual(result["assumptions"], entry["assumptions"])
                for item, expected in zip(result["results"][:5], entry["results"]):
                    self.assertAlmostEqual(item["speed"], expected["speed"], places=6)
                    self.assertAlmostEqual(item["advance"], expected["advance"], places=6)
                    self.assertAlmostEqual(
                        item["neededSubstatSpeed"], expected["neededSubstatSpeed"], places=6
                    )


class TestSpeedPlanTriggerAwareSpeed(unittest.TestCase):
    """「不是开局就生效」的速度效果要按条件处理。

    背景：遗器 4 件套里有「施放终结技后，我方全体速度提高 12%」这种，
    以前的算法只处理 passive 的 pct/flat，这条会被静默丢掉（会把速度算低）。
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = call("speed-plan", "catalog")
        cls.by_id = {str(item["id"]): item for item in cls.catalog["characters"]}
        cls.four = {item["name"]: item for item in cls.catalog["fourPieceSets"]}

    def plan(self, **kwargs):
        payload = {
            "characterId": "1005",  # 卡芙卡，白值 100
            "relic": {},
            "advance": {},
            "target": {"t": 0, "actions": 2},
        }
        payload.update(kwargs)
        return call("speed-plan", "plan", payload)

    def test_messenger_per_ult_speed_is_counted(self) -> None:
        messenger = self.four["骇域漫游的信使"]
        # 2 件套（常驻）+ 4 件套（开大触发）的数值从数据里读，别把数字写死
        passive = [
            effect["value"]
            for effect in messenger["effects"]
            if effect["slot"] == "2件套" and effect["kind"] == "pct"
        ]
        per_ult = [
            effect["value"]
            for effect in messenger["effects"]
            if effect["slot"] == "4件套" and effect["kind"] == "pct"
        ]
        self.assertTrue(passive and per_ult, messenger["effects"])
        # 4 件套那条是「开大触发」：**不是开局就生效**，默认第 1 次行动后才开大，
        # 所以未加速速度 S0 只含 2 件套；4 件套要等第 2 次行动才上。
        result = self.plan(relic={"speedBoots": False, "fourPieceId": messenger["id"], "ultTargetsAlly": True, "fourPieceUlts": 2})
        self.assertAlmostEqual(result["speed"]["pct"], passive[0], places=6)
        self.assertAlmostEqual(result["speed"]["final"], 100 * (1 + passive[0] / 100), places=6)
        labels = " ".join(item["label"] for item in result["speed"]["breakdown"])
        self.assertIn("开大触发", labels)
        # 第 2 次行动起速度 = 100 × (1 + 2 件套 + 4 件套)；持续 1 回合，第 3 次行动起回落
        boost = 100 * (1 + (passive[0] + per_ult[0]) / 100)
        # 窗口给大一点（1T = 250 AV），第 3 次行动才进得来，好验证「到期回落」
        result = self.plan(
            relic={"speedBoots": False, "fourPieceId": messenger["id"], "ultTargetsAlly": True, "fourPieceUlts": 2},
            target={"mode": "moc", "t": 1, "actions": 3},
        )
        timeline = result["simulation"]["timeline"]
        self.assertEqual(result["simulation"]["firstUltAction"], 1)
        self.assertAlmostEqual(timeline[0]["speed"], result["speed"]["final"], places=6)
        self.assertAlmostEqual(timeline[1]["speed"], boost, places=6)
        self.assertAlmostEqual(timeline[2]["speed"], result["speed"]["final"], places=6)
        self.assertTrue(any("从第 2 次行动起生效" in note for note in result["simulation"]["notes"]))

    def test_messenger_per_ult_speed_applies_immediately_when_ult_is_up(self) -> None:
        """firstUltAction=0（开局就有大）：开大触发的加速从第 1 次行动起生效。"""
        messenger = self.four["骇域漫游的信使"]
        pct = sum(
            effect["value"] for effect in messenger["effects"] if effect["kind"] == "pct"
        )
        result = self.plan(
            relic={"speedBoots": False, "fourPieceId": messenger["id"], "ultTargetsAlly": True, "fourPieceUlts": 2},
            target={"mode": "moc", "t": 1, "actions": 3},
            simulation={"firstUltAction": 0},
        )
        timeline = result["simulation"]["timeline"]
        self.assertAlmostEqual(timeline[0]["speed"], 100 * (1 + pct / 100), places=6)
        # 持续 1 回合：第 2 次行动时开大增益已经过期
        self.assertAlmostEqual(timeline[1]["speed"], result["speed"]["final"], places=6)

    def test_messenger_per_ult_speed_needs_an_ult(self) -> None:
        messenger = self.four["骇域漫游的信使"]
        result = self.plan(relic={"speedBoots": False, "fourPieceId": messenger["id"], "ultTargetsAlly": True, "fourPieceUlts": 0})
        # 不开大就只有 2 件套的 6%
        self.assertAlmostEqual(result["speed"]["pct"], 6.0, places=6)
        self.assertAlmostEqual(result["speed"]["final"], 106.0, places=6)
        conditional = " ".join(str(item.get("setName", "")) for item in result["effects"]["conditional"])
        self.assertIn("骇域漫游的信使", conditional)

    def test_messenger_ally_ult_is_not_counted_until_asked(self) -> None:
        """对敌人开大不触发信使 4 件套。没勾「开大目标是队友」时，即使填了开大次数也不计入。"""
        messenger = self.four["骇域漫游的信使"]
        result = self.plan(relic={"speedBoots": False, "fourPieceId": messenger["id"], "fourPieceUlts": 2})
        self.assertAlmostEqual(result["speed"]["final"], 106.0, places=6)
        self.assertFalse(result["speed"]["hasTimeline"])
        texts = " ".join(effect.get("text") or "" for effect in result["effects"]["conditional"])
        self.assertIn("对我方目标", texts)

    def test_percent_buff_uses_base_not_s0(self) -> None:
        """鞋子和常驻百分比已经在 S0 里时，开大百分比只乘基础速度。"""
        messenger = self.four["骇域漫游的信使"]
        result = self.plan(
            relic={
                "speedBoots": True,
                "substatSpeed": 10,
                "fourPieceId": messenger["id"],
                "ultTargetsAlly": True,
                "fourPieceUlts": 2,
            },
            target={"mode": "moc", "t": 1, "actions": 3},
        )
        base = result["speed"]["base"]
        flat = result["speed"]["flat"]
        true_boost = base * (1 + (result["speed"]["pct"] + 12) / 100.0) + flat
        wrong = result["speed"]["final"] * 1.12
        timeline = result["simulation"]["timeline"]
        self.assertAlmostEqual(timeline[1]["speed"], true_boost, places=6)
        self.assertNotAlmostEqual(timeline[1]["speed"], wrong, places=3)

        def actions_in_150(speed_of) -> int:
            av = 0.0
            done = 0
            for step in range(1, 8):
                av += 10000.0 / speed_of(step)
                if av <= 150 + 1e-6:
                    done += 1
                else:
                    break
            return done

        def search(speed_of) -> float:
            low, high = 0.0, 400.0
            for _ in range(50):
                mid = (low + high) / 2
                if actions_in_150(lambda step, mid=mid: speed_of(step, mid)) >= 2:
                    high = mid
                else:
                    low = mid
            return high

        # 正确：额外 12% 只加在基础速度上。错误：12% 再乘一遍已经含鞋的 S0。
        correct = search(lambda step, s0: s0 + (base * 0.12 if step == 2 else 0.0))
        inflated = search(lambda step, s0: s0 * (1.12 if step == 2 else 1.0))
        cell = next(
            item
            for table in result["tables"]
            if table["id"] == "moc"
            for row in table["rows"]
            if row["actions"] == 2
            for item in row["cells"]
            if item["t"] == 0
        )
        self.assertAlmostEqual(cell["speed"], correct, places=3)
        self.assertGreater(abs(cell["speed"] - inflated), 0.2)

    def test_per_ult_speed_counts_once_not_per_ult(self) -> None:
        """速度是「持续一段时间的增益」，不是每开一次大就叠一层，所以只算一次。"""
        messenger = self.four["骇域漫游的信使"]
        one = self.plan(relic={"fourPieceId": messenger["id"], "ultTargetsAlly": True, "fourPieceUlts": 1})
        five = self.plan(relic={"fourPieceId": messenger["id"], "ultTargetsAlly": True, "fourPieceUlts": 5})
        self.assertAlmostEqual(one["speed"]["final"], five["speed"]["final"], places=6)

    def test_on_enter_speed_is_counted(self) -> None:
        """进战触发的速度：开局就生效，应该算进去。"""
        # 找一条 onEnter 的遗器速度效果（当前数据里可能没有，就跳过）
        has_on_enter = any(
            effect.get("trigger") == "onEnter"
            for entry in self.catalog["fourPieceSets"] + self.catalog["ornamentSets"]
            for effect in entry["effects"]
            if effect["kind"] in ("pct", "flat")
        )
        if not has_on_enter:
            self.skipTest("当前数据里没有进战触发的遗器速度效果")

    def test_effects_carry_trigger(self) -> None:
        result = self.plan()
        for item in result["effects"]["speed"]:
            self.assertIn(item.get("trigger"), ("passive", "onEnter", "perUlt", "allyUlt", "conditional"))
            # 只有无条件常驻的才默认勾选
            if item["defaultEnabled"]:
                self.assertEqual(item["trigger"], "passive")

    def test_conditional_speed_is_not_auto_counted(self) -> None:
        """有条件的速度效果（例如「忆灵在场时」）不能自动计入，否则会高估速度。"""
        result = self.plan(relic={"speedBoots": False})
        self.assertAlmostEqual(result["speed"]["final"], 100.0, places=6)

    def test_enemy_debuff_and_overworld_speed_are_filtered_out(self) -> None:
        """杰帕德 2 魂是给敌人减速、赛飞儿是大地图移速，都不该出现在自己的速度列表里。"""
        for name, marker in (("杰帕德", "目标的速度降低"), ("赛飞儿", "移动速度")):
            character = next(
                (item for item in self.catalog["characters"] if item["name"] == name), None
            )
            if character is None:
                continue
            result = self.plan(characterId=character["id"], enabledEffects=[])
            texts = " ".join(item["text"] for item in result["effects"]["speed"])
            with self.subTest(character=name):
                self.assertNotIn(marker, texts)


def appearance(action: str, payload: dict | None = None):
    """外观功能在 interface 模块里（不是崩铁），所以单独一个调用助手。"""
    return feature_api.call("interface", "appearance", action, payload or {})


class TestInterfaceAppearance(unittest.TestCase):
    """外观主题：白名单清洗 + 存取。

    注意：这组测试会写 userdata/interface/theme.json，所以**测试前后都把用户原来的主题还原**，
    免得跑一次 self-check 就把人家调好的配色抹了。
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.original = appearance("load")["theme"]

    @classmethod
    def tearDownClass(cls) -> None:
        appearance("save", {"theme": cls.original})

    def test_load_returns_defaults_and_labels(self) -> None:
        data = appearance("load")
        self.assertIn("defaults", data)
        self.assertIn("colors", data["defaults"])
        self.assertIn("accent", data["defaults"]["colors"])
        self.assertTrue(data["labels"]["colors"])
        self.assertIn("baseSize", data["labels"]["numbersMeta"])
        self.assertTrue(data["fontChoices"])

    def test_save_accepts_valid_values(self) -> None:
        result = appearance(
            "save",
            {
                "theme": {
                    "colors": {"accent": "#FF0000", "bg": "#abc"},
                    "fonts": {"baseSize": 16, "lineHeight": 1.8},
                    "layout": {"radius": 12},
                    "text": {"brand": "我的工具箱"},
                }
            },
        )
        theme = result["theme"]
        self.assertEqual(theme["colors"]["accent"], "#ff0000")  # 统一小写
        self.assertEqual(theme["colors"]["bg"], "#aabbcc")      # 短写展开
        self.assertEqual(theme["fonts"]["baseSize"], 16)
        self.assertEqual(theme["layout"]["radius"], 12)
        self.assertEqual(theme["text"]["brand"], "我的工具箱")

    def test_save_rejects_bad_colors_and_unknown_keys(self) -> None:
        result = appearance(
            "save",
            {
                "theme": {
                    "colors": {"accent": "red; background: url(x)", "nope": "#fff"},
                    "layout": {"evil": 10},
                }
            },
        )
        theme = result["theme"]
        self.assertNotIn("colors", theme)  # 非法色值被丢掉
        self.assertNotIn("nope", theme)
        self.assertNotIn("evil", (theme.get("layout") or {}))

    def test_numbers_are_clamped(self) -> None:
        result = appearance(
            "save",
            {"theme": {"fonts": {"baseSize": 999, "lineHeight": -3}, "layout": {"radius": 999}}},
        )
        theme = result["theme"]
        self.assertEqual(theme["fonts"]["baseSize"], 22)
        self.assertEqual(theme["fonts"]["lineHeight"], 1.1)
        self.assertEqual(theme["layout"]["radius"], 24)

    def test_text_is_truncated_and_sanitized(self) -> None:
        result = appearance(
            "save",
            {"theme": {"text": {"brand": "很长" * 40, "searchPlaceholder": "   "}}},
        )
        theme = result["theme"]
        self.assertLessEqual(len(theme["text"]["brand"]), 40)
        self.assertNotIn("searchPlaceholder", theme["text"])  # 空字符串不收

    def test_reset_clears_theme(self) -> None:
        appearance("save", {"theme": {"colors": {"accent": "#123456"}}})
        appearance("reset", {})
        self.assertEqual(appearance("load")["theme"], {})


def nav_api(action: str, payload: dict | None = None):
    """「功能与文字」在 interface 模块里。"""
    return feature_api.call("interface", "nav", action, payload or {})


class TestInterfaceNav(unittest.TestCase):
    """功能改名/隐藏/排序：写入 userdata/shell-overrides.json 并作用到注册表。

    和外观测试一样，跑完要把作者原来的覆盖还原，不能把人家调好的导航冲掉。
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.original = nav_api("load")["overrides"]

    @classmethod
    def tearDownClass(cls) -> None:
        nav_api("save", {"overrides": cls.original})

    def test_rename_hide_and_order_take_effect(self) -> None:
        nav_api(
            "save",
            {
                "overrides": {
                    "labels": {
                        "honkai-star-rail/speed-plan": {"name": "配速测试名", "icon": "⚡"},
                    },
                    "hidden": ["honkai-star-rail/gacha"],
                    "order": {"honkai-star-rail/speed-plan": 1},
                }
            },
        )
        modules, _ = registry.scan()
        rail = registry.find(modules, "honkai-star-rail")
        self.assertIsNotNone(rail)
        names = [feature.name for feature in rail.features]
        self.assertIn("配速测试名", names)
        self.assertNotIn("抽卡规划", names)  # 被隐藏
        speed = next(feature for feature in rail.features if feature.id == "speed-plan")
        self.assertEqual(speed.icon, "⚡")
        self.assertEqual(speed.order, 1)
        self.assertEqual(rail.features[0].id, "speed-plan")  # order=1 排最前

    def test_unknown_ids_and_overlong_text_are_dropped(self) -> None:
        result = nav_api(
            "save",
            {
                "overrides": {
                    "labels": {"honkai-star-rail/不存在": {"name": "x" * 80}},
                    "hidden": ["不存在/也不存在"],
                    "order": {"honkai-star-rail/不存在": 3},
                }
            },
        )
        self.assertEqual(result["overrides"], {})

    def test_reset_restores_defaults(self) -> None:
        nav_api("save", {"overrides": {"hidden": ["honkai-star-rail/gacha"]}})
        nav_api("reset", {})
        modules, _ = registry.scan()
        rail = registry.find(modules, "honkai-star-rail")
        self.assertIn("抽卡规划", [feature.name for feature in rail.features])

    def test_broken_overrides_file_does_not_break_scan(self) -> None:
        path = config.OVERRIDES_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        backup = path.read_text(encoding="utf-8") if path.is_file() else None
        path.write_text("{ 这不是合法 JSON", encoding="utf-8")
        try:
            modules, _ = registry.scan()  # 不能抛异常
            self.assertTrue(modules)
        finally:
            if backup is None:
                path.unlink(missing_ok=True)
            else:
                path.write_text(backup, encoding="utf-8")


def texts_api(action: str, payload: dict | None = None):
    """「文字替换」也在 interface 模块里。"""
    return feature_api.call("interface", "texts", action, payload or {})


class TestInterfaceTexts(unittest.TestCase):
    """界面文字替换：白名单 key、只动 texts 段、reset 只清自己。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.original = config.load_overrides()

    @classmethod
    def tearDownClass(cls) -> None:
        config.save_overrides(cls.original)

    def test_catalog_has_speed_plan_cards(self) -> None:
        data = texts_api("load")
        keys = {item["key"] for group in data["groups"] for item in group["items"]}
        self.assertIn("speed-plan.card.pick", keys)
        self.assertIn("shell.guide", keys)
        self.assertEqual(len(keys), data["count"])

    def test_save_keeps_other_sections(self) -> None:
        config.save_overrides({"hidden": ["honkai-star-rail/gacha"], "labels": {}})
        texts_api("save", {"texts": {"speed-plan.card.pick": "我的标题"}})
        overrides = config.load_overrides()
        self.assertEqual(overrides["texts"], {"speed-plan.card.pick": "我的标题"})
        self.assertIn("honkai-star-rail/gacha", overrides["hidden"])  # 没被冲掉

    def test_unknown_keys_and_default_values_are_dropped(self) -> None:
        result = texts_api(
            "save",
            {"texts": {"不存在的.key": "x", "speed-plan.card.speed": "⚡ 实际速度"}},
        )
        self.assertEqual(result["texts"], {})  # 不认识的 key + 和默认一样的值都不存

    def test_reset_only_clears_texts(self) -> None:
        config.save_overrides({"hidden": ["honkai-star-rail/gacha"]})
        texts_api("save", {"texts": {"shell.guide": "说明书"}})
        texts_api("reset", {})
        overrides = config.load_overrides()
        self.assertNotIn("texts", overrides)
        self.assertIn("honkai-star-rail/gacha", overrides["hidden"])

    def test_overrides_endpoint_payload_shape(self) -> None:
        """/api/overrides 返回的就是外壳读的东西（这里只校验结构，不起服务）。"""
        texts_api("save", {"texts": {"shell.status": "状态"}})
        overrides = config.load_overrides()
        self.assertEqual(overrides["texts"]["shell.status"], "状态")


class TestSpeedPlanApplyClassification(unittest.TestCase):
    """速度效果的作用对象判定：「我方目标」包含角色自己，只有"单个被指定的队友"才是仅队友。

    这条是用户明确的口径：风堇 2 魂「我方目标生命值降低时，速度提高30%」，
    我方目标当然也包括风堇自己 → 必须计入。
    """

    def plan(self, character_id, **kwargs):
        payload = {
            "characterId": character_id,
            "relic": {},
            "advance": {},
            "target": {"t": 0, "actions": 2},
        }
        payload.update(kwargs)
        return call("speed-plan", "plan", payload)

    def character_id(self, name: str) -> str:
        catalog = call("speed-plan", "catalog")
        found = next((item for item in catalog["characters"] if item["name"] == name), None)
        self.assertIsNotNone(found, f"数据里没有 {name}")
        return found["id"]

    def find_effect(self, character_id: str, keyword: str) -> dict:
        probe = self.plan(character_id, eidolon=6)
        found = next(
            (item for item in probe["effects"]["speed"] if keyword in item["text"]), None
        )
        self.assertIsNotNone(found, f"没找到含「{keyword}」的速度效果")
        return found

    def test_wuliang_mubiao_counts_for_self(self):
        """风堇 2 魂：「我方目标生命值降低时速度提高30%」→ self，勾上要真的计入。"""
        char_id = self.character_id("风堇")
        effect = self.find_effect(char_id, "我方目标生命值降低时")
        self.assertEqual(effect["apply"], "self")
        self.assertEqual(effect.get("trigger"), "conditional")
        enabled = self.plan(
            char_id,
            eidolon=2,
            enabledEffects=[effect["id"]],
            target={"mode": "moc", "t": 2, "actions": 4},
        )
        duration = int(effect.get("durationTurns") or 0)
        if duration > 0:
            # 持续 N 回合：不并进整场速度，只覆盖前 N 次自己的行动。
            self.assertAlmostEqual(enabled["speed"]["pct"], 0.0, places=6)
            timeline = enabled["simulation"]["timeline"]
            boosted = enabled["speed"]["base"] * 1.30
            self.assertGreaterEqual(len(timeline), duration + 1)
            for step in timeline[:duration]:
                self.assertAlmostEqual(step["speed"], boosted, places=6)
            self.assertAlmostEqual(timeline[duration]["speed"], enabled["speed"]["final"], places=6)
        else:
            self.assertAlmostEqual(enabled["speed"]["pct"], 30.0, places=6)
        # 用户手动取消勾选后就不算。
        # 注意：接口把「空列表」当成「用默认勾选」（enabledEffects 没给 / 给空数组都走默认），
        # 所以要表达"我全部取消"必须给一个非空、但不含这条效果的列表。
        disabled = self.plan(char_id, eidolon=2, enabledEffects=["__none__"])
        self.assertAlmostEqual(disabled["speed"]["pct"], 0.0, places=6)
        # 2 魂时它默认就是勾上的（星魂是用户主动选的）
        defaulted = self.plan(char_id, eidolon=2, target={"mode": "moc", "t": 2, "actions": 4})
        if duration > 0:
            self.assertAlmostEqual(defaulted["speed"]["pct"], 0.0, places=6)
            self.assertAlmostEqual(defaulted["simulation"]["timeline"][0]["speed"], enabled["speed"]["base"] * 1.30, places=6)
        else:
            self.assertAlmostEqual(defaulted["speed"]["pct"], 30.0, places=6)

    def test_assigned_ally_stays_ally(self):
        """布洛妮娅 2 魂：「被指定的我方目标」是给队友的 → ally，不计入自己。"""
        char_id = self.character_id("布洛妮娅")
        effect = self.find_effect(char_id, "被指定的我方目标")
        self.assertEqual(effect["apply"], "ally")
        result = self.plan(char_id, eidolon=2, enabledEffects=[effect["id"]])
        self.assertAlmostEqual(result["speed"]["pct"], 0.0, places=6)

    def test_blessed_single_ally_stays_ally(self):
        """停云 1 魂：「得到【赐福】的我方单体」也是队友 → ally。"""
        char_id = self.character_id("停云")
        effect = self.find_effect(char_id, "赐福")
        self.assertEqual(effect["apply"], "ally")

    def test_team_wide_still_counts(self):
        """「我方全体」当然算自己。"""
        char_id = self.character_id("爻光")
        effect = self.find_effect(char_id, "我方全体目标速度提高")
        self.assertEqual(effect["apply"], "team")


class TestDataAudit(unittest.TestCase):
    """数据审计：nanoka 里带速度/拉条数字的条目，本地必须都有（只允许已知的几类排除）。

    这条守住的是「官方文案里有效果、工具里却勾不到」这类漏抽（花火 1 魂就是这种坑）。
    """

    def test_no_missing_speed_effects(self) -> None:
        sys.path.insert(0, str(ROOT / "tools"))
        import audit_data  # noqa: PLC0415

        self.assertEqual(audit_data.audit(), 0, "审计发现本地缺失的效果，见上面的报告")


class TestMergedV0166(unittest.TestCase):
    """v0.16.6 从 0.16.5 合入的部分：本地素材、MIME、本机限定接口、GT_USERDATA。"""

    def test_userdata_override_points_to_temp(self) -> None:
        if _TEMP_USERDATA is not None:
            self.assertEqual(Path(config.USERDATA_DIR).resolve(), _TEMP_USERDATA.resolve())

    def test_resolve_userdata_rules(self) -> None:
        old = os.environ.get("GT_USERDATA")
        try:
            os.environ["GT_USERDATA"] = "../evil"
            self.assertEqual(config._resolve_userdata(), config.ROOT / "userdata")
            os.environ["GT_USERDATA"] = ""
            self.assertEqual(config._resolve_userdata(), config.ROOT / "userdata")
            os.environ["GT_USERDATA"] = "tmp-ud"
            self.assertEqual(config._resolve_userdata(), config.ROOT / "tmp-ud")
        finally:
            if old is None:
                os.environ.pop("GT_USERDATA", None)
            else:
                os.environ["GT_USERDATA"] = old

    def test_webp_mime_registered(self) -> None:
        import mimetypes  # noqa: PLC0415
        from core import server  # noqa: F401, PLC0415

        self.assertEqual(mimetypes.guess_type("x.webp")[0], "image/webp")
        self.assertEqual(mimetypes.guess_type("x.js")[0], "text/javascript")

    def test_local_only_paths(self) -> None:
        from core import server  # noqa: PLC0415

        self.assertEqual(set(server.LOCAL_ONLY_PATHS), {"/api/call", "/api/reload", "/api/shutdown"})
        handler = server.make_handler(server.ToolboxState.__new__(server.ToolboxState))
        probe = handler.__new__(handler)
        for host, ok in (("127.0.0.1", True), ("::1", True), ("192.168.1.5", False)):
            probe.client_address = (host, 1234)
            self.assertIs(probe._is_local_client(), ok, host)

    def test_catalog_prefers_local_icons_and_files_exist(self) -> None:
        result = feature_api.call(MODULE_ID, "speed-plan", "catalog", {})
        local = 0
        groups = [result.get("characters") or []]
        for key in ("relicSets", "relics", "fourPieceSets", "ornamentSets"):
            if isinstance(result.get(key), list):
                groups.append(result[key])
        for group in groups:
            for item in group:
                icon = item.get("icon") or ""
                if icon.startswith("/modules/"):
                    local += 1
                    self.assertTrue((ROOT / icon.lstrip("/")).is_file(), icon)
        self.assertGreater(local, 0, "目录里应当优先给出本地素材路径")
        cones = feature_api.call(MODULE_ID, "speed-plan", "lightcones", {"path": result["characters"][0].get("path")})
        items = cones.get("lightcones") or cones.get("items") or []
        self.assertTrue(any(str(c.get("icon") or "").startswith("/modules/") for c in items))


if __name__ == "__main__":
    unittest.main(verbosity=2)
