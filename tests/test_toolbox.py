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
from urllib.parse import quote as urllib_quote

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


def _not_gbk(ch: str) -> bool:
    """这个字符在中文 Windows 的 GBK 控制台上打不出来吗？

    ASCII 一定可以；其余按 GBK 试编码 —— 顺便把无法编码的字符（emoji / 生僻符号）筛出来。
    """
    try:
        ch.encode("gbk")
    except UnicodeEncodeError:
        return True
    except Exception:  # noqa: BLE001 - 编码器异常不该让测试炸
        return True
    return False


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
        self.assertEqual(result["assumptions"]["superimpose"], 1)  # 0.17.0 起默认叠影 1
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


class TestFixesV0167SpeedPlan(unittest.TestCase):
    """0.16.7 配速修复的回归测试（A1/A4/A5/A6/A7/A8/A9/A21/A22）。"""

    KAFKA = "1005"
    COURIER = {"speedBoots": True, "fourPieceId": "114", "fourPieceUlts": 1, "ultTargetsAlly": True}

    def plan(self, **kwargs):
        payload = {"characterId": self.KAFKA, "relic": {}, "advance": {}, "target": {"t": 0, "actions": 2}}
        payload.update(kwargs)
        return call("speed-plan", "plan", payload)

    def test_a1_advance_counts_with_timeline_buff(self) -> None:
        no_buff = self.plan(relic={"speedBoots": True}, advance={"vonwacq": True})
        with_buff = self.plan(relic=dict(self.COURIER), advance={"vonwacq": True})
        no_adv = self.plan(relic=dict(self.COURIER))
        self.assertTrue(with_buff["speed"]["hasTimeline"])
        self.assertAlmostEqual(no_buff["verdict"]["requiredSpeed"], 106.6667, places=3)
        # 拉条必须让需求速度下降；多一个纯增益不能让需求反而升高
        self.assertLess(with_buff["verdict"]["requiredSpeed"], no_adv["verdict"]["requiredSpeed"] - 20)
        self.assertLessEqual(with_buff["verdict"]["requiredSpeed"], no_buff["verdict"]["requiredSpeed"])
        self.assertAlmostEqual(with_buff["verdict"]["requiredSpeed"], 99.49, places=2)

    def test_a1_constant_speed_simulation_matches_closed_form(self) -> None:
        """无随行动加速时，模拟（拉条抵扣路程）与闭式公式同一阈值。"""
        sp = next(m for name, m in sys.modules.items() if name.endswith("speed-plan") or "speed_plan" in name
                  if hasattr(m, "_simulate"))
        for speed in (95.0, 106.67, 133.34, 160.0):
            for adv in (0.0, 4000.0, 12000.0):
                run = sp._simulate(speed, [], window_av=150.0, advance_distance=adv)
                closed = max(0, math.floor((speed * 150.0 + adv) / 10000.0 + 1e-9))
                self.assertEqual(run["completed"], closed, (speed, adv))

    def test_a4_timeline_not_capped_at_12(self) -> None:
        r = self.plan(relic=dict(self.COURIER), target={"t": 0, "actions": 2, "customAV": 50000})
        self.assertGreater(r["verdict"]["achievableActions"], 600)
        self.assertEqual(len(r["simulation"]["timeline"]), 12)  # 时间线展示仍只给 12 条

    def test_a5_impossible_target_not_silently_capped(self) -> None:
        with self.assertRaisesRegex(ValueError, "目标动数最多"):
            self.plan(relic=dict(self.COURIER), target={"t": 0, "actions": 100000})
        # 上界不够时要翻倍找到真解，而不是返回初始上界
        r = self.plan(relic=dict(self.COURIER), target={"t": 0, "actions": 200, "customAV": 150})
        self.assertGreater(r["verdict"]["requiredSpeed"], 10000)
        self.assertTrue(math.isfinite(r["verdict"]["requiredSpeed"]))

    def test_a6_nonfinite_inputs_name_the_field(self) -> None:
        for relic, field in (({"customFlat": 1e308}, "customFlat"), ({"substatSpeed": "nan"}, "substatSpeed"),
                             ({"customPct": "inf"}, "customPct")):
            with self.assertRaisesRegex(ValueError, field):
                self.plan(relic=relic)
        with self.assertRaisesRegex(ValueError, "eidolon"):
            self.plan(eidolon="inf")

    def test_a7_response_is_strict_json(self) -> None:
        r = self.plan(relic=dict(self.COURIER), target={"t": 0, "actions": 8})
        json.dumps(r, allow_nan=False)

    def test_a8_empty_enabled_effects_is_honoured(self) -> None:
        march = "1224"  # 三月七：有默认勾选的常驻自身提速
        default = call("speed-plan", "plan", {"characterId": march, "target": {"t": 0, "actions": 2}})
        none = call("speed-plan", "plan", {"characterId": march, "enabledEffects": [], "target": {"t": 0, "actions": 2}})
        self.assertTrue(default["effects"]["enabled"])
        self.assertEqual(none["effects"]["enabled"], [])
        self.assertGreater(default["speed"]["final"], none["speed"]["final"])
        walter = "1004"
        with self.assertRaisesRegex(ValueError, "enabledEffects"):
            call("speed-plan", "plan", {"characterId": walter, "enabledEffects": "char1#1"})

    def test_a9_dance_not_double_counted(self) -> None:
        base = {"characterId": "1412", "lightconeId": "21018", "superimpose": 5, "target": {"t": 0, "actions": 2}}
        both = call("speed-plan", "plan", dict(base, advance={"danceUlts": 2, "coneUlts": 2}))
        cone = call("speed-plan", "plan", dict(base, advance={"coneUlts": 2}))
        self.assertEqual(both["advance"]["total"], 48)
        self.assertEqual(both["advance"]["total"], cone["advance"]["total"])
        # 没选舞舞舞时手填 danceUlts 照常计
        manual = call("speed-plan", "plan", {"characterId": "1412", "advance": {"danceUlts": 2}, "target": {"t": 0, "actions": 2}})
        self.assertEqual(manual["advance"]["total"], 48)

    def test_a21_negative_speed_never_negative_actions(self) -> None:
        r = self.plan(relic={"customPct": -200})
        self.assertEqual(r["verdict"]["achievableActions"], 0)

    def test_a22_parity_inputs(self) -> None:
        self.assertEqual(call("speed-plan", "plan", {"characterId": 1005.0})["character"]["id"], "1005")
        with self.assertRaisesRegex(ValueError, "rarity"):
            call("speed-plan", "lightcones", {"rarity": "abc"})
        with self.assertRaisesRegex(ValueError, "substatSpeed"):
            self.plan(relic={"substatSpeed": "１２"})
        r = call("speed-plan", "plan", {"characterId": "1004", "enabledEffects": ["char1#1", "char1#1"]})
        self.assertEqual(r["effects"]["enabled"], ["char1#1"])


class TestFixesV0167Core(unittest.TestCase):
    """0.16.7 外壳/服务修复的回归测试（A2/A3/A7/A12-A16/A23-A26/A35）。"""

    @classmethod
    def setUpClass(cls) -> None:
        import threading
        from core import server
        cls.server_mod = server
        state = server.ToolboxState()
        state.rescan()
        cls.httpd = server._Server(("127.0.0.1", 0), server.make_handler(state))
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def request(self, method, path, body=None, headers=None):
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        data = json.dumps(body).encode() if body is not None else None
        hdrs = {"Content-Type": "application/json", **(headers or {})}
        conn.request(method, path, body=data, headers=hdrs)
        resp = conn.getresponse()
        raw = resp.read()
        conn.close()
        return resp.status, raw

    def setUp(self) -> None:
        self._overrides = config.OVERRIDES_PATH.read_bytes() if config.OVERRIDES_PATH.is_file() else None

    def tearDown(self) -> None:
        if self._overrides is None:
            config.OVERRIDES_PATH.unlink(missing_ok=True)
        else:
            config.OVERRIDES_PATH.write_bytes(self._overrides)

    # ---- A12 跨站 ----
    def test_a12_cross_site_post_rejected(self) -> None:
        call_body = {"module": MODULE_ID, "feature": "speed-plan", "action": "catalog", "payload": {}}
        status, _ = self.request("POST", "/api/call", call_body, {"Origin": "http://evil.example"})
        self.assertEqual(status, 403)
        status, _ = self.request("POST", "/api/shutdown", {}, {"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(status, 403)
        status, _ = self.request("POST", "/api/call", call_body, {"Origin": f"http://127.0.0.1:{self.port}"})
        self.assertEqual(status, 200)
        status, _ = self.request("POST", "/api/call", call_body)  # 没有 Origin（脚本/curl）照常
        self.assertEqual(status, 200)

    # ---- A16 HEAD ----
    def test_a16_head_supported(self) -> None:
        status, raw = self.request("HEAD", "/")
        self.assertEqual(status, 200)
        self.assertEqual(raw, b"")
        status, _ = self.request("HEAD", "/app/no-such-file.js")
        self.assertEqual(status, 404)

    # ---- A23 请求错位 ----
    def test_a23_bad_content_length_closes_connection(self) -> None:
        import socket
        smuggled = b"GET /api/health HTTP/1.1\r\nHost: x\r\n\r\n"
        raw = (b"POST /api/heartbeat HTTP/1.1\r\nHost: x\r\nContent-Length: -5\r\n\r\n" + smuggled)
        with socket.create_connection(("127.0.0.1", self.port), timeout=5) as sock:
            sock.sendall(raw)
            chunks = []
            while True:
                try:
                    chunk = sock.recv(65536)
                except socket.timeout:
                    break
                if not chunk:
                    break
                chunks.append(chunk)
        data = b"".join(chunks)
        self.assertEqual(data.count(b"HTTP/1.1 "), 1, data[:300])
        self.assertIn(b" 400 ", data.split(b"\r\n", 1)[0])

    # ---- A24 不泄漏 ----
    def test_a24_docs_null_byte_no_leak(self) -> None:
        status, raw = self.request("GET", "/api/docs/x%00.md")
        self.assertEqual(status, 403)
        self.assertNotIn("lstat", raw.decode("utf-8"))

    def test_a24_corrupt_module_data_error_has_no_absolute_path(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        (tmp / "data").mkdir()
        (tmp / "data" / "x.json").write_text("{bad", encoding="utf-8")
        ctx = feature_api.FeatureContext("m", "f", tmp, tmp)
        with self.assertRaises(ValueError) as cm:
            ctx.raw_data("x")
        self.assertNotIn(str(tmp), str(cm.exception))
        self.assertIn("data/x.json", str(cm.exception))
        shutil.rmtree(tmp, True)

    # ---- A25 端口 ----
    def test_a25_asset_port_checked(self) -> None:
        check = self.server_mod._check_asset_url
        with self.assertRaises(PermissionError):
            check("http://webstatic.mihoyo.com:9999/x.png")
        with self.assertRaises(PermissionError):
            check("http://webstatic.mihoyo.com:99999999/x.png")
        check("https://webstatic.mihoyo.com:443/x.png")
        check("https://webstatic.mihoyo.com/x.png")
        status, _ = self.request("GET", "/api/asset?url=" + urllib_quote("http://webstatic.mihoyo.com:9999/x.png"))
        self.assertEqual(status, 403)

    # ---- A7 严格 JSON ----
    def test_a7_non_finite_serialised_as_null(self) -> None:
        out = self.server_mod._finite({"a": float("inf"), "b": [float("nan"), 1.5], "c": "x"})
        self.assertEqual(json.dumps(out, allow_nan=False), '{"a": null, "b": [null, 1.5], "c": "x"}')

    # ---- A35 backlog ----
    def test_a35_backlog(self) -> None:
        self.assertGreaterEqual(self.server_mod._Server.request_queue_size, 64)
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(30) as pool:
            statuses = list(pool.map(lambda _: self.request("GET", "/api/health")[0], range(60)))
        self.assertEqual(statuses, [200] * 60)

    # ---- A2 并发保存 ----
    def test_a2_concurrent_preset_saves(self) -> None:
        import concurrent.futures
        ids = [c["id"] for c in call("speed-plan", "catalog")["characters"][:20]]
        for cid in ids:
            call("speed-plan", "delete_preset", {"characterId": cid})

        def save(cid):
            body = {"module": MODULE_ID, "feature": "speed-plan", "action": "save_preset",
                    "payload": {"characterId": cid, "config": {"x": cid}}}
            return self.request("POST", "/api/call", body)[0]

        with concurrent.futures.ThreadPoolExecutor(20) as pool:
            statuses = list(pool.map(save, ids))
        self.assertEqual(statuses, [200] * 20)
        stored = call("speed-plan", "presets")["presets"]
        self.assertLessEqual(set(ids), set(stored))
        for cid in ids:
            call("speed-plan", "delete_preset", {"characterId": cid})

    # ---- A3 nav 不清文字 ----
    def test_a3_nav_save_and_reset_keep_texts(self) -> None:
        config.save_overrides({"texts": {"shell.pick": "我的文字"}})
        call_iface = lambda feat, action, payload=None: feature_api.call("interface", feat, action, payload or {})
        call_iface("nav", "save", {"overrides": {"hidden": []}})
        self.assertEqual(config.load_overrides().get("texts"), {"shell.pick": "我的文字"})
        call_iface("nav", "reset")
        self.assertEqual(config.load_overrides(), {"texts": {"shell.pick": "我的文字"}})

    # ---- A13 BOM ----
    def test_a13_bom_json_accepted(self) -> None:
        config.OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)
        config.OVERRIDES_PATH.write_bytes(b"\xef\xbb\xbf" + json.dumps({"texts": {"a": "b"}}).encode())
        self.assertEqual(config.load_overrides(), {"texts": {"a": "b"}})
        tmp = Path(tempfile.mkdtemp())
        (tmp / "data").mkdir()
        (tmp / "data" / "x.json").write_bytes(b"\xef\xbb\xbf{\"k\": 1}")
        self.assertEqual(feature_api.FeatureContext("m", "f", tmp, tmp).raw_data("x"), {"k": 1})
        shutil.rmtree(tmp, True)

    # ---- A14 order ----
    def test_a14_bad_order_does_not_abort_scan(self) -> None:
        errors: list = []
        self.assertEqual(registry._order("top", errors, Path("feat")), 100)
        self.assertEqual(registry._order("7", errors, Path("feat")), 7)
        self.assertEqual(len(errors), 1)
        tmp = Path(tempfile.mkdtemp())
        fdir = tmp / "m" / "features" / "f"
        fdir.mkdir(parents=True)
        (tmp / "m" / "manifest.json").write_text(json.dumps({"id": "m", "name": "M"}), encoding="utf-8")
        (fdir / "feature.json").write_text(json.dumps({"id": "f", "name": "F", "order": "top"}), encoding="utf-8")
        (fdir / "ui.js").write_text("export function mount(){}", encoding="utf-8")
        saved = config.MODULES_DIR
        try:
            config.MODULES_DIR = tmp
            modules, errs = registry.scan()
        finally:
            config.MODULES_DIR = saved
            shutil.rmtree(tmp, True)
        self.assertEqual([f.order for m in modules for f in m.features], [100])
        self.assertTrue(any("order" in e.get("error", "") for e in errs))

    # ---- A15 坏掉的用户数据 ----
    def test_a15_corrupt_userdata_quarantined(self) -> None:
        ctx = feature_api.CONTEXTS[(MODULE_ID, "speed-plan")]
        path = ctx.user_path("speed-plan-presets")
        path.parent.mkdir(parents=True, exist_ok=True)
        backup = path.read_bytes() if path.is_file() else None
        path.write_text('{"1005": {"name": "x"', encoding="utf-8")
        try:
            self.assertEqual(call("speed-plan", "presets")["count"], 0)
            self.assertTrue(list(path.parent.glob("speed-plan-presets.corrupt-*.json")))
            call("speed-plan", "save_preset", {"characterId": "1005", "config": {}})
            self.assertEqual(call("speed-plan", "presets")["count"], 1)
        finally:
            for item in path.parent.glob("speed-plan-presets.corrupt-*.json"):
                item.unlink()
            if backup is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(backup)

    # ---- A26 config 类型 ----
    def test_a26_bad_config_types_fall_back(self) -> None:
        tmp = Path(tempfile.mkdtemp()) / "config.json"
        tmp.write_text(json.dumps({"port": "8765a", "watchdogSeconds": "x", "window": {"width": "w"},
                                   "autoPort": "yes", "host": 1}), encoding="utf-8")
        saved = config.CONFIG_PATH
        try:
            config.CONFIG_PATH = tmp
            cfg = config.load()
        finally:
            config.CONFIG_PATH = saved
            shutil.rmtree(tmp.parent, True)
        self.assertEqual(cfg["port"], 8765)
        self.assertEqual(cfg["watchdogSeconds"], 25)
        self.assertEqual(cfg["window"]["width"], 1360)
        self.assertIs(cfg["autoPort"], True)
        self.assertEqual(cfg["host"], "127.0.0.1")


class TestFixesV0167Frontend(unittest.TestCase):
    """0.16.7 前端修复的静态回归检查（A10/A11/A27/A28；浏览器里的复现见 修改记录.md）。"""

    FEAT = ROOT / "modules" / MODULE_ID / "features"

    def read(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def test_a10_escape_html_escapes_quotes(self) -> None:
        src = self.read(ROOT / "app" / "app.js")
        body = src[src.index("function escapeHtml"):][:300]
        self.assertIn("&quot;", body)
        self.assertIn("&#39;", body)

    def test_a11_speed_page_escapes_user_text(self) -> None:
        src = self.read(self.FEAT / "speed" / "ui.js")
        self.assertIn('value="${esc(u.name)}"', src)
        self.assertNotIn("${err.message}", src)
        self.assertNotIn("<td>${e.unit}</td>", src)
        self.assertNotIn("<td>${s.name}</td>", src)
        self.assertNotIn("${err.message}", self.read(self.FEAT / "gacha" / "ui.js"))

    def test_a27_no_html_string_into_text_content(self) -> None:
        # 0.17.0 新界面：「需要开大」提示走 innerHTML，并且名字经过 esc()；
        # 任何 textContent 赋值都不能是带标签的字符串
        import re
        src = self.read(self.FEAT / "speed-plan" / "ui.js")
        block = src[src.index('$("#relic-warn").innerHTML'):][:300]
        self.assertIn("esc(", block)
        for match in re.finditer(r"textContent\s*=\s*`([^`]*)`", src):
            self.assertNotRegex(match.group(1), r"<[a-z]", match.group(0))

    def test_a28_pool_hint_keeps_error(self) -> None:
        src = self.read(self.FEAT / "gacha" / "ui.js")
        body = src[src.index("function updatePoolHint"):][:300]
        self.assertIn("pool.baseRate === undefined) return;", body)


class TestFixesV0167Packaging(unittest.TestCase):
    """0.16.7 打包 / Windows 脚本修复的回归检查（A17-A20, A29-A34）。"""

    def test_a17_a33_bom_rules(self) -> None:
        for name in ("start.ps1", "tools/build_exe.ps1", "tools/install_exe.ps1", "tools/uninstall.ps1"):
            data = (ROOT / name).read_bytes()
            if any(b > 127 for b in data):
                self.assertTrue(data.startswith(b"\xef\xbb\xbf"), f"{name} 含中文必须带 BOM")
        for bat in list(ROOT.glob("*.bat")) + list((ROOT / "tools").glob("*.bat")):
            self.assertFalse(bat.read_bytes().startswith(b"\xef\xbb\xbf"), f"{bat.name} 不能带 BOM")

    def test_a18_no_machine_specific_paths(self) -> None:
        for name in ("tools/build_exe.ps1", "tools/打包回传.bat"):
            text = (ROOT / name).read_text(encoding="utf-8-sig")
            self.assertNotIn("Administrator", text)
            self.assertNotIn(".dsh", text)
        self.assertIn("$PSScriptRoot", (ROOT / "tools/build_exe.ps1").read_text(encoding="utf-8"))

    def test_a19_a20_install_exe_finds_exe_first_and_copies_only_exe(self) -> None:
        text = (ROOT / "tools/install_exe.ps1").read_text(encoding="utf-8-sig")
        self.assertNotIn("robocopy $source", text)
        self.assertIn("dist\\exe\\GameToolbox.exe", text)
        self.assertLess(text.index("找不到 GameToolbox.exe"), text.index("Copy-Item $sourceExe"))

    def test_a34_exe_bundles_docs(self) -> None:
        self.assertIn('--add-data "$root\\docs;docs"', (ROOT / "tools/build_exe.ps1").read_text(encoding="utf-8"))

    def test_a29_source_package_has_no_duplicate_entries(self) -> None:
        import subprocess
        import zipfile
        out = Path(tempfile.mkdtemp()) / "src.zip"
        subprocess.run([sys.executable, str(ROOT / "tools" / "make_source_package.py"), "--out", str(out)],
                       check=True, capture_output=True)
        names = zipfile.ZipFile(out).namelist()
        self.assertEqual(len(names), len(set(names)))
        shutil.rmtree(out.parent, True)

    def test_a30_a31_usage_text(self) -> None:
        sys.path.insert(0, str(ROOT))
        import make_package
        self.assertNotIn("\\\\", make_package.USAGE)
        self.assertIn("{test_count}", make_package.USAGE)
        self.assertGreaterEqual(make_package.count_tests(), 180)

    def test_a32_no_stale_version_fallback(self) -> None:
        self.assertNotIn('"0.16.2"', (ROOT / "tools/make_source_package.py").read_text(encoding="utf-8"))

    def test_a35_oracle_regeneration_keeps_line_endings(self) -> None:
        """重生成网页版基准**不能**顺手把行尾改成 CRLF。

        这个基准在仓库里是 LF；Windows 上若用 `write_text` 生成，Python 会把 `\\n` 翻成
        CRLF → 之后每跑一次重生成，git 里就多出 3826 行"改动"，而实测内容逐行完全相同
        （只差行尾，文件大小 68813 → 72639 B，特别像真的改了内容）。
        `make_web_oracle.target_eol()` 就是为这个加的，这里既钉函数、也钉基准文件本身。
        """
        # 注意：不能 import make_web_oracle —— 那是**顶层就写文件**的脚本，
        # 导入一次等于重生成一次基准。这里只把它源码里的 target_eol 取出来执行。
        import ast

        source = (ROOT / "tools" / "make_web_oracle.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        node = next(
            (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "target_eol"),
            None,
        )
        self.assertIsNotNone(node, "make_web_oracle.py 里应该有一个 target_eol() 函数")
        namespace: dict = {"Path": Path}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "<target_eol>", "exec"), namespace)
        target_eol = namespace["target_eol"]

        tmp = Path(tempfile.mkdtemp(prefix="gt-oracle-eol-"))
        try:
            self.assertEqual(target_eol(tmp / "none.json"), "\n", "没有原文件时应该用 LF")
            lf = tmp / "lf.json"
            lf.write_bytes(b'{\n "a": 1\n}\n')
            self.assertEqual(target_eol(lf), "\n", "原文件是 LF 时要保持 LF")
            crlf = tmp / "crlf.json"
            crlf.write_bytes(b'{\r\n "a": 1\r\n}\r\n')
            self.assertEqual(target_eol(crlf), "\r\n", "原文件是 CRLF 时要保持 CRLF")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

        oracle = ROOT / "tests" / "fixtures" / "web_oracle.json"
        raw = oracle.read_bytes()
        self.assertGreater(raw.count(b"\n"), 100, "基准文件应该有内容")
        self.assertNotIn(b"\r\n", raw, "基准文件被写成 CRLF 了（重生成时踩过）")

    def test_a36_console_scripts_are_gbk_printable(self) -> None:
        """会被直接跑的控制台脚本，print 的文字必须 **GBK 编得出**。

        中文 Windows 控制台默认 GBK：`🔄 ✅ ❌ ⚠ ✓ ✗` 一 print 就 UnicodeEncodeError，
        而且往往崩在最后几行 —— 包已经打完、脚本却报失败，后面的刷新/收尾全不执行
        （`make_package.py` 踩过）。这里按 `print(...)` 里的字面量逐个验证。

        只查**会被直接命令行跑**的脚本：这些崩了最难受。其余脚本经 `.bat`（`chcp 65001`）
        启动，或用 `PYTHONUTF8=1` 跑，不受这条约束。

        ⚠️ 这份名单本身就是当初的漏洞：`packaging/build_green.py` 没在里面，
        于是它 `print("③ ✅ …")` 一直没被发现 —— 本机裸控制台打绿色版时，包已经打完、
        脚本却以 1 退出（2026-10-15 实测复现）。`tools/audit_data.py` 同样漏网。
        加新脚本时**记得把它加进这份名单**。
        """
        import ast

        console_scripts = (
            "make_package.py",              # 打包.bat / 直接命令行
            "packaging/build_green.py",     # make_package.py --green 会 import 它
            "tools/audit_package.py",       # 发包前必跑
            "tools/audit_data.py",          # 数据审计
            "tools/make_web_standalone.py",  # 单独出单文件网页
            "tools/make_source_package.py",  # 出源码版
            "tools/make_web_oracle.py",     # 重生成对拍基准
        )
        all_bad: dict[str, list[str]] = {}
        for name in console_scripts:
            path = ROOT / name
            if not path.is_file():
                continue
            source = path.read_text(encoding="utf-8")
            if all(ord(ch) < 128 for ch in source):
                continue  # 纯 ASCII 一定没问题
            tree = ast.parse(source)
            literals: list[str] = []
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                    continue
                if node.func.id != "print":
                    continue
                for arg in node.args:
                    for sub in ast.walk(arg):
                        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                            literals.append(sub.value)
            if not literals:
                continue  # 这个脚本没有 print，跳过（别让名单变大就报错）
            bad = sorted({ch for text in literals for ch in text if _not_gbk(ch)})
            if bad:
                all_bad[name] = bad
        self.assertEqual(
            all_bad, {},
            "这些脚本的 print 里有 GBK 编不出的字符（中文 Windows 控制台会崩）："
            + repr(all_bad),
        )



class TestEnemyEffects(unittest.TestCase):
    """0.17.0：作用在敌方身上的速度效果（减速/缺陷/溃败）绝不计入本角色速度。"""

    def ids_and_speed(self, cid, enabled, **kw):
        r = call("speed-plan", "plan", {"characterId": cid, "enabledEffects": enabled, "eidolon": 6, **kw})
        return r, r["speed"]["final"]

    def test_enemy_effects_never_change_self_speed(self) -> None:
        for cid in ("1004", "1002", "1006"):  # 瓦尔特 / 丹恒 / 银狼
            probe = call("speed-plan", "plan", {"characterId": cid, "eidolon": 6})
            enemy = [e["id"] for e in probe["effects"]["speed"] if e["apply"] == "enemy"]
            self.assertTrue(enemy, cid)
            for e in probe["effects"]["speed"]:
                if e["apply"] == "enemy":
                    self.assertFalse(e["defaultEnabled"], e["text"])
            _, none = self.ids_and_speed(cid, [])
            r, ticked = self.ids_and_speed(cid, enemy)
            self.assertEqual(ticked, none, cid)
            self.assertTrue(any("作用于敌方" in b["label"] for b in r["speed"]["breakdown"]))

    def test_enemy_debuff_on_lightcone(self) -> None:
        cone = next(c for c in call("speed-plan", "lightcones")["lightcones"] if c["name"] == "梦应归于何处")
        char = next(c for c in call("speed-plan", "catalog")["characters"] if c["path"] == cone["path"])
        probe = call("speed-plan", "plan", {"characterId": char["id"], "lightconeId": cone["id"], "superimpose": 1})
        enemy = [e["id"] for e in probe["effects"]["speed"] if e["apply"] == "enemy"]
        self.assertTrue(enemy)
        _, none = self.ids_and_speed(char["id"], [], lightconeId=cone["id"], superimpose=1)
        _, ticked = self.ids_and_speed(char["id"], enemy, lightconeId=cone["id"], superimpose=1)
        self.assertEqual(none, ticked)

    def test_classifier(self) -> None:
        sys.path.insert(0, str(ROOT / "tools"))
        import import_hsr_data as imp
        cases = {
            "攻击命中时有65%的基础概率使受到攻击的敌方目标速度降低10%，持续2回合": "enemy",
            "禁锢状态下，敌方目标行动延后6.0%，速度降低10%": "enemy",
            "银狼能够制造：攻击力降低5.0%、防御力降低6.0%、速度降低3.0%3种【缺陷】": "enemy",
            "【溃败】状态下目标受到装备者造成的击破伤害提高24.0%，速度降低20%，同类效果无法叠加": "enemy",
            "使装备者的速度降低8%": "self",
            "使装备者在消灭敌方目标后，速度提高10%，持续2回合": "self",
            "我方目标为敌方目标添加弱点时，速度提高30%，持续2回合": "self",
            "使希儿的速度提高25%，并对指定敌方单体造成等同于希儿180%攻击力的量子属性伤害，速度提高效果持续3回合": "self",
            "我方全体速度提高12%。": "team",
        }
        for text, want in cases.items():
            self.assertEqual(imp.apply_of(text), want, text)

    def test_data_tags_match_classifier(self) -> None:
        sys.path.insert(0, str(ROOT / "tools"))
        import import_hsr_data as imp
        data = ROOT / "modules" / MODULE_ID / "data"
        for name in ("characters.json", "lightcones.json", "relic_sets.json"):
            for item in json.loads((data / name).read_text(encoding="utf-8")):
                for e in item.get("effects") or []:
                    self.assertEqual(e.get("apply") or "self", imp.apply_of(e.get("text") or ""), (item["name"], e["text"]))


class TestV0170Features(unittest.TestCase):
    """0.17.0：自定义角色 / 默认叠影 1 / 进战即开大。"""

    CUSTOM = {"characterId": "__custom__", "customCharacter": {"name": "测试", "baseSpeed": 100, "traceSpeed": 5}}

    def test_custom_character_plan(self) -> None:
        r = call("speed-plan", "plan", dict(self.CUSTOM, relic={"speedBoots": True}, target={"t": 0, "actions": 2}))
        self.assertEqual(r["character"]["id"], "__custom__")
        self.assertEqual(r["character"]["name"], "测试")
        self.assertAlmostEqual(r["speed"]["final"], 130.0)  # 100 + 5 + 鞋 25
        self.assertEqual(r["effects"]["speed"], [])  # 没有角色自带效果
        self.assertEqual(r["effects"]["advance"], [])

    def test_custom_character_any_path_cone(self) -> None:
        for cone in call("speed-plan", "lightcones")["lightcones"][:5]:
            call("speed-plan", "plan", dict(self.CUSTOM, lightconeId=cone["id"]))

    def test_custom_character_validation(self) -> None:
        bad = [
            ({}, "customCharacter"),
            ({"customCharacter": {"baseSpeed": 0}}, "1–1000"),
            ({"customCharacter": {"baseSpeed": 1000.5}}, "1–1000"),
            ({"customCharacter": {"baseSpeed": 100, "traceSpeed": -0.1}}, "0–200"),
            ({"customCharacter": {"baseSpeed": 100, "traceSpeed": 201}}, "0–200"),
            ({"customCharacter": {"baseSpeed": "nan"}}, "超出范围"),
            ({"customCharacter": {"baseSpeed": 100, "name": "字" * 21}}, "最多 20"),
        ]
        for extra, msg in bad:
            with self.assertRaisesRegex(ValueError, msg):
                call("speed-plan", "plan", {"characterId": "__custom__", **extra})
        ok = call("speed-plan", "plan", {"characterId": "__custom__", "customCharacter": {"baseSpeed": 1000, "traceSpeed": 200}})
        self.assertEqual(ok["character"]["name"], "自定义角色")

    def test_custom_character_recommend(self) -> None:
        r = call("speed-plan", "recommend", dict(self.CUSTOM, target={"t": 0, "actions": 2}))
        self.assertTrue(r["results"])
        self.assertEqual(r["character"]["id"], "__custom__")

    def test_custom_character_preset_roundtrip(self) -> None:
        cfg = {"characterId": "__custom__", "customCharacter": {"name": "存档", "baseSpeed": 111, "traceSpeed": 2}, "superimpose": 3}
        call("speed-plan", "save_preset", {"characterId": "__custom__", "name": "存档", "config": cfg})
        stored = call("speed-plan", "presets")["presets"]["__custom__"]
        self.assertEqual(stored["config"], cfg)  # 原样存，叠影保留存的值
        self.assertEqual(stored["name"], "存档")
        call("speed-plan", "delete_preset", {"characterId": "__custom__"})

    def test_superimpose_default_one(self) -> None:
        cone = next(c for c in call("speed-plan", "lightcones")["lightcones"] if c["name"] == "舞！舞！舞！")
        a = call("speed-plan", "plan", {"characterId": "1412", "lightconeId": cone["id"], "advance": {"coneUlts": 1}})
        b = call("speed-plan", "plan", {"characterId": "1412", "lightconeId": cone["id"], "superimpose": 1, "advance": {"coneUlts": 1}})
        self.assertEqual(a["advance"]["total"], b["advance"]["total"])
        rec = call("speed-plan", "recommend", {"characterId": "1005", "target": {"t": 0, "actions": 2}})
        self.assertEqual(rec["assumptions"]["superimpose"], 1)

    def test_first_ult_action_zero(self) -> None:
        relic = {"speedBoots": True, "fourPieceId": "114", "fourPieceUlts": 2, "ultTargetsAlly": True}
        zero = call("speed-plan", "plan", {"characterId": "1005", "relic": relic, "simulation": {"firstUltAction": 0},
                                           "target": {"t": 0, "actions": 3}})
        one = call("speed-plan", "plan", {"characterId": "1005", "relic": relic, "simulation": {"firstUltAction": 1},
                                          "target": {"t": 0, "actions": 3}})
        tl0, tl1 = zero["simulation"]["timeline"], one["simulation"]["timeline"]
        # 0 = 进战即开大：开大效果从第 1 次行动就生效
        self.assertGreater(tl0[0]["speed"], tl1[0]["speed"])
        self.assertAlmostEqual(tl0[0]["speed"], tl1[1]["speed"])
        notes = " ".join(zero["simulation"]["notes"])
        self.assertIn("进战即开大", notes)
        self.assertIn("从第 1 次行动起生效", notes)
        self.assertNotIn("第 0 次行动", notes)
        self.assertIn("第 1 次行动后开大", " ".join(one["simulation"]["notes"]))



class TestGreenPackage(unittest.TestCase):
    """0.17.0 绿色版打包的静态检查（exe 本身只能在 Windows 上打，见 .github/workflows/build.yml）。"""

    def test_icon_has_all_sizes(self) -> None:
        data = (ROOT / "packaging" / "toolbox.ico").read_bytes()
        self.assertEqual(data[:4], b"\x00\x00\x01\x00")  # ICO 头
        count = int.from_bytes(data[4:6], "little")
        sizes = sorted({(data[6 + 16 * i] or 256) for i in range(count)})
        self.assertEqual(sizes, [16, 24, 32, 48, 64, 128, 256])

    def test_spec_and_workflow(self) -> None:
        spec = (ROOT / "packaging" / "游戏工具箱.spec").read_text(encoding="utf-8")
        self.assertIn("exclude_binaries=True", spec)  # --onedir
        self.assertIn("console=False", spec)
        self.assertIn('name="游戏工具箱"', spec)
        self.assertIn("toolbox.ico", spec)
        workflow = (ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
        self.assertIn("windows-latest", workflow)
        self.assertIn("make_package.py --green", workflow)
        self.assertIn("upload-artifact", workflow)

    def test_workflow_creates_release_on_tag(self) -> None:
        """推 v* tag 时要自动建 Release 并把绿色版挂上去。

        README 让用户去 Releases 下「游戏工具箱-v版本号-绿色版.zip」，所以这条链路断了
        就等于发版流程断了。顺带钉住两个容易漏的点：
          * `permissions: contents: write` —— 新建仓库的 GITHUB_TOKEN 默认只读，少了就 403；
          * tag 与 `core/__init__.py` 的版本号必须一致，不一致要**报错停下**而不是发出名字对不上的包。
        """
        workflow = (ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
        self.assertIn("contents: write", workflow)
        self.assertIn("gh release create", workflow)
        self.assertIn("secrets.GITHUB_TOKEN", workflow)
        self.assertIn("startsWith(github.ref, 'refs/tags/v')", workflow)
        self.assertIn("core/__init__.py", workflow)
        self.assertIn("不一致", workflow)

    def test_version_with_suffix_still_packs(self) -> None:
        """版本号带后缀（如 0.20.0beta）时，绿色版的 Windows 版本资源也要能生成。

        踩过：`build_green.py` 直接 `int(x)` 拆版本号，`0beta` 崩在 PyInstaller 启动之前
        —— 资源已整理完、包还没开始打，报 `invalid literal for int() with base 10: '0beta'`。
        这里用 AST 把函数取出来单独执行（同 `round_of` / `target_eol` 的做法，
        不在加载器上下文里 import 打包脚本）。
        """
        import ast
        import re

        source = (ROOT / "packaging" / "build_green.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        node = next(
            (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "version_parts"),
            None,
        )
        self.assertIsNotNone(node, "build_green.py 里应该有一个 version_parts() 函数")

        cases = {
            "0.18.3": (0, 18, 3, 0),
            "0.20.0beta": (0, 20, 0, 0),
            "0.21.0-rc1": (0, 21, 0, 0),
            "1.2": (1, 2, 0, 0),
        }
        for version, expect in cases.items():
            namespace = {"__version__": version, "re": re}
            exec(compile(ast.Module(body=[node], type_ignores=[]), "<version_parts>", "exec"), namespace)
            self.assertEqual(namespace["version_parts"](), expect, f"{version} 应该解析成 {expect}")


class TestNoPrivateDataInPackages(unittest.TestCase):
    """发布产物里绝不能有 userdata / 浏览器记录（旧树 `pack_exe.py` 那次事故的回归）。

    0.16.x 的 exe 把浏览器配置写进 `_internal\\userdata`，整目录打包就把 History /
    Cookies / Login Data 一起发了出去；后来改成「userdata 写在 exe 旁边 + 白名单整理
    `_internal`」，但排除规则是手写的 —— 这里钉住它：真打一份用户包，
    用 `tools/audit_package.py` 过一遍。
    """

    @staticmethod
    def _audit():
        sys.path.insert(0, str(ROOT / "tools"))
        import audit_package

        return audit_package

    def test_user_package_has_no_private_data(self) -> None:
        import make_package

        audit = self._audit()
        tmp = Path(tempfile.mkdtemp(prefix="gt-pkg-audit-"))
        zip_path = tmp / "user.zip"
        try:
            files = make_package.collect_files(exclude_admin=True)
            make_package.write_zip(zip_path, files, None, "审计用，不发布", admin=False)
            findings = audit.audit_zip(zip_path)
            violations = [f for f in findings if f[1] == "violation"]
            self.assertEqual(violations, [], f"用户包里出现了私密条目：{violations[:5]}")
            # 占位说明是有意放进去的（zip 里那层 userdata/ 要保持存在），不算违规
            self.assertTrue(
                all(f[2] == "userdata 目录占位说明" for f in findings),
                f"用户包里出现了计划外的条目：{findings[:5]}",
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_return_package_keeps_theme_but_flags_browser_traces(self) -> None:
        """回传包：主题/预设算有意为之；浏览器记录必须被揪出来。"""
        import zipfile

        audit = self._audit()
        tmp = Path(tempfile.mkdtemp(prefix="gt-pkg-audit-"))
        try:
            zip_path = tmp / "回传-20261015-1630.zip"
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("userdata/interface/theme.json", "{}")
                zf.writestr("userdata/edge-profile/Default/Network/Cookies", "x")
            findings = dict((name, verdict) for name, verdict, _ in audit.audit_zip(zip_path))
            self.assertEqual(findings.get("userdata/interface/theme.json"), "expected")
            self.assertEqual(findings.get("userdata/edge-profile/Default/Network/Cookies"), "violation")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_classifier_catches_browser_config_shapes(self) -> None:
        audit = self._audit()
        for name in (
            "game-toolbox-v0.18.1/userdata/edge-profile/Default/History",
            "游戏工具箱-v0.18.1-绿色版/_internal/userdata/edge-profile/Default/Login Data",
            "src/userdata/BrowserMetrics/a.pma",
            "pack/User Data/Cookies",
            "pack/Default/Web Data",
        ):
            self.assertEqual(audit.classify(name)[0], "violation", name)
        for name in (
            "game-toolbox-v0.18.1/userdata/放你自己的数据在这里.txt",  # 占位说明 = expected
            "game-toolbox-v0.18.1/modules/herta/features/records/api.py",
            "game-toolbox-v0.18.1/tools/uninstall.ps1",
            "Screenshot 2026-10-15 161842.png",
        ):
            self.assertNotEqual(audit.classify(name)[0], "violation", name)

    def test_stage_is_user_flavour(self) -> None:
        sys.path.insert(0, str(ROOT / "packaging"))
        import build_green

        stage = Path(tempfile.mkdtemp(prefix="gt-green-"))
        old = build_green.STAGE
        build_green.STAGE = stage / "s"
        try:
            files = build_green.stage_resources()
        finally:
            build_green.STAGE = old
        tops = {f.split("/")[0] for f in files}
        self.assertEqual(tops, {"app", "modules", "docs"})
        self.assertFalse(any(f.startswith("modules/interface/") for f in files))  # 后门模块不进包
        self.assertFalse(any("/nanoka/" in f or "__pycache__" in f for f in files))
        cfg = json.loads((stage / "s" / "config.json").read_text(encoding="utf-8"))
        self.assertIs(cfg["admin"], False)
        shutil.rmtree(stage, ignore_errors=True)
        self.assertTrue(build_green.ZIP_NAME.startswith("游戏工具箱-v") and "绿色版" in build_green.ZIP_NAME)

    def test_usage_html_rendered(self) -> None:
        sys.path.insert(0, str(ROOT / "packaging"))
        import build_green

        html = build_green.usage_html()
        self.assertNotIn("{{", html)
        self.assertIn("游戏工具箱.exe", html)
        self.assertIn("userdata", html)

# ---------------- 角色顶分（herta/records） ----------------

HERTA_SAMPLE = {
    "source": "https://theherta.com/archive", "collected_at": "2026-10-15 16:28 UTC+8", "selection_rule": "x",
    "targets": [{"mode": "混沌回忆", "season": "4.5", "stage": "关卡", "category": "0轮次", "total_runs": 3,
                 "records": [{"group": "爻光", "runs_in_group": 1, "tag": "0轮次", "cycle": "0", "ltd": 1, "std": 0,
                              "date": "2026-10-01 00:00",
                              "lineup": [{"name": "爻光", "eidolon": 0, "superimposition": 5}]}]}],
}


class TestHertaRecords(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = feature_api.CONTEXTS[("herta", "records")]
        self.mod = sys.modules[feature_api.HANDLERS[("herta", "records")]["load"].__module__]
        path = self.ctx.user_path(self.mod.CACHE)
        if path.exists():
            path.unlink()
        self.body = json.dumps(HERTA_SAMPLE, ensure_ascii=False).encode("utf-8")
        self.sha = hashlib.sha256(self.body).hexdigest()

    def fake(self, good: set[str], bad_sha: set[str] = frozenset()):
        calls = []

        def fetch(url, timeout):
            calls.append(url)
            name = next(m["name"] for m in self.mod.MIRRORS if url.startswith(m["base"]))
            if name not in good:
                raise OSError("down")
            if url.endswith(".sha256"):
                return (("0" * 64) if name in bad_sha else self.sha).encode() + b"  latest.json\n"
            return self.body
        return fetch, calls

    def test_mirror_list_covers_required_hosts(self) -> None:
        bases = " ".join(m["base"] for m in self.mod.MIRRORS)
        for host in ("raw.githubusercontent.com", "cdn.jsdelivr.net/gh/Ca5tor1ce-vesna/herta-data@main",
                     "fastly.jsdelivr.net", "gcore.jsdelivr.net", "ghfast.top/https://", "gh-proxy.com/https://"):
            self.assertIn(host, bases)
        self.assertEqual(self.mod.MIRRORS[0]["name"], "GitHub Raw")

    def test_first_working_mirror_wins_and_checksum_mismatch_skipped(self) -> None:
        fetch, _ = self.fake({"jsDelivr", "ghfast.top"}, bad_sha={"jsDelivr"})
        result = self.mod.load({"refresh": True}, self.ctx, fetch)
        self.assertEqual(result["mirror"], "ghfast.top")
        self.assertFalse(result["offline"])
        self.assertEqual(result["sha256"], self.sha)
        self.assertEqual([a["ok"] for a in result["attempts"]], [False, False, False, False, True])
        self.assertIn("校验不一致", result["attempts"][1]["error"])

    def test_cache_then_offline_fallback(self) -> None:
        fetch, _ = self.fake({"GitHub Raw"})
        self.mod.load({"refresh": True}, self.ctx, fetch)
        fetch2, calls = self.fake(set())
        fresh = self.mod.load({}, self.ctx, fetch2)
        self.assertTrue(fresh["from_cache"])
        self.assertEqual(calls, [])  # 缓存新鲜不联网
        offline = self.mod.load({"refresh": True}, self.ctx, fetch2)
        self.assertTrue(offline["offline"])
        self.assertIn("离线", offline["note"])
        self.assertEqual(offline["data"]["targets"][0]["stage"], "关卡")

    def test_no_mirror_no_cache_raises(self) -> None:
        fetch, _ = self.fake(set())
        with self.assertRaises(ValueError):
            self.mod.load({"refresh": True}, self.ctx, fetch)

    def test_bad_structure_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.mod.validate({"targets": [{"mode": "未知", "records": []}]})

    def test_avatar_and_lightcone_mapping(self) -> None:
        fixture = json.loads((ROOT / "tests" / "fixtures" / "herta_lightcone_sample.json").read_text(encoding="utf-8"))
        result = self.mod.with_avatars({"data": fixture}, self.ctx)
        av = result["avatars"]
        self.assertEqual(av["三月七 (巡猎)"], "/modules/herta/assets/1224.webp")
        self.assertTrue((ROOT / "modules" / "herta" / "assets" / "1224.webp").is_file())
        chars = json.loads((ROOT / "modules" / MODULE_ID / "data" / "characters.json").read_text(encoding="utf-8"))
        by_id = {c["id"]: c["icon"] for c in chars}
        self.assertEqual(av["开拓者 (欢愉)"], by_id["8009"])
        self.assertEqual(av["开拓者 (记忆)"], by_id["8007"])
        for name in ("砂金•戏浪", "银狼LV.999", "Archer", "Saber"):
            self.assertTrue(av[name].startswith("/modules/honkai-star-rail/assets/"), name)
        self.assertEqual(result["unmapped"], ["不存在的角色"])
        lc = result["lightcone_icons"]
        self.assertIn("一场谎言的终幕", lc)
        self.assertIn("舞! 舞! 舞!", lc)  # 半角/空格写法也能对上
        self.assertIn("忍法帖·缭乱破魔", lc)  # · 与 • 等价
        self.assertEqual(result["unmapped_lightcones"], ["不存在的光锥"])

    def test_live_data_all_avatars_mapped(self) -> None:
        sample = ROOT / "tests" / "fixtures" / "herta_latest_snapshot.json"
        data = json.loads(sample.read_text(encoding="utf-8"))
        self.assertEqual(self.mod.with_avatars({"data": data}, self.ctx)["unmapped"], [])

    def test_web_port_matches(self) -> None:
        node = shutil.which("node")
        if not node:
            self.skipTest("没有 node")
        import subprocess
        proc = subprocess.run([node, str(ROOT / "tools" / "check_herta_web.mjs")], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


# ---------------- 行动值排轴（action-value/timeline） ----------------


class TestActionValueTimeline(unittest.TestCase):
    """行动值排轴模块：AV 公式、拉条口径、速度合成、回能、爻光机制。

    对照《行动值排轴 · 修改建议》第 6 节的 9 条验收逐条钉住；
    用爻光（1502，白值 101 + 行迹 9），不用基础速度 100 做合成验收。
    """

    MODULE = "action-value"
    FEATURE = "timeline"

    @classmethod
    def setUpClass(cls) -> None:
        assert cls.MODULE in [m.id for m in registry.scan()[0]], "新模块没被扫到"

    @classmethod
    def call(cls, action, payload=None):
        return feature_api.call(cls.MODULE, cls.FEATURE, action, payload or {})

    @classmethod
    def mod(cls):
        """api.py 装载后的模块对象。

        不能直接 import 那个 api.py（顶层 `@api(...)` 在加载器上下文外会 RuntimeError），
        但 `_load()` 已经把它装进 sys.modules，里面纯函数可以直接调。
        """
        return sys.modules[feature_api.HANDLERS[(cls.MODULE, cls.FEATURE)]["plan"].__module__]

    # ---- 行动值 ----

    def test_av_is_10000_over_speed(self) -> None:
        # 窗口会截掉窗口外的行动：3 轮 = 350 AV，装下 100/200/300 三动
        res = self.call("plan", {"baseSpeed": 100, "rounds": 3, "maxActions": 3})
        self.assertEqual(res["actions"][0]["gap"], 100.0)
        self.assertAlmostEqual(res["actions"][0]["av"], 100.0)
        self.assertAlmostEqual(res["actions"][2]["av"], 300.0)
        # 窗口外的行动不会出现在结果里（1 轮 = 150 AV，只剩第 1 动）
        short = self.call("plan", {"baseSpeed": 100, "rounds": 1, "maxActions": 3})
        self.assertEqual(short["actionCount"], 1)

    def test_advance_uses_full_distance_not_remaining_av(self) -> None:
        """拉条 20% 必须抵扣 2000 距离（= 10000 的 20%），不是拿剩余 AV 乘。"""
        res = self.call("plan", {"baseSpeed": 100, "advancePct": 20, "rounds": 3, "maxActions": 3})
        self.assertAlmostEqual(res["advance"]["distance"], 2000.0)
        # 第一动：(10000 − 2000) / 100 = 80，而不是 100 × 0.8 这种顺手写法
        self.assertAlmostEqual(res["actions"][0]["av"], 80.0)
        self.assertAlmostEqual(res["actions"][1]["av"], 180.0)

    def test_advance_clamped_per_action_no_overflow(self) -> None:
        """验收 4：拉条只减**当前这一动**的路程，减到 0 为止，多出来的不进入下一动。

        同一动上拉条 40% + 80%（= 120%）：这一动路程按 0 算，
        下一动仍是完整 10000（100 速 → gap 100），不剩那 20%。
        """
        res = self.call("plan", {"baseSpeed": 100, "advancePct": 120,
                                 "rounds": 3, "maxActions": 3})
        self.assertAlmostEqual(res["actions"][0]["gap"], 0.0)
        self.assertAlmostEqual(res["actions"][0]["av"], 0.0)
        self.assertAlmostEqual(res["actions"][1]["gap"], 100.0)  # 完整 10000
        self.assertAlmostEqual(res["actions"][1]["advanceUsed"], 0.0)

        # 同一动上的多次拉条先求和，再按同一个口径算
        summed = self.call("plan", {"baseSpeed": 100, "adv_percents": [40, 80],
                                    "rounds": 3, "maxActions": 3})
        self.assertAlmostEqual(summed["actions"][0]["gap"], 0.0)
        self.assertAlmostEqual(summed["actions"][1]["gap"], 100.0)

        sim = self.mod().simulate_actions(speed=100.0, adv_percents=[40.0, 80.0],
                                          max_actions=3)
        self.assertAlmostEqual(sim["actions"][0]["gap"], 0.0)
        self.assertAlmostEqual(sim["actions"][1]["gap"], 100.0)

    def test_advance_by_action_targets_only_its_action(self) -> None:
        """adv_by_action 给逐动拉条明细：只影响那一动，其它动照常 10000。"""
        sim = self.mod().simulate_actions(speed=100.0, adv_by_action={2: 50.0},
                                          max_actions=3)
        self.assertAlmostEqual(sim["actions"][0]["gap"], 100.0)
        self.assertAlmostEqual(sim["actions"][1]["gap"], 50.0)   # 10000 − 5000
        self.assertAlmostEqual(sim["actions"][2]["gap"], 100.0)

    def test_delay_adds_distance(self) -> None:
        """验收 5：延后 20%、速度 100 —— 第一动行动值 120，返回的距离是 **+2000**。

        延后（推条）用正数表示「往时间线后面推」，返回给界面的距离也是正数；
        写成 −2000 会被界面当拉条用。
        """
        res = self.call("plan", {"baseSpeed": 100, "delayPct": 20, "rounds": 1, "maxActions": 1})
        self.assertAlmostEqual(res["delay"]["distance"], 2000.0)  # 正数，不是 -2000
        self.assertAlmostEqual(res["delay"]["pct"], 20.0)
        self.assertAlmostEqual(res["actions"][0]["av"], 120.0)
        self.assertAlmostEqual(res["actions"][0]["delayUsed"], 2000.0)

    # ---- 速度合成（基础 / 光锥白字 / 百分比 / 固定 / 行迹） ----

    def test_speed_formula_pct_on_base_flat_last(self) -> None:
        res = self.call("plan", {"baseSpeed": 100, "speedPct": 10, "speedFlat": 50, "rounds": 1})
        # 100 × 1.10 + 50 = 160（不是 (100+50)×1.10 = 165）
        self.assertAlmostEqual(res["speed"]["final"], 160.0)
        self.assertAlmostEqual(res["actions"][0]["gap"], 10000 / 160.0)

    def test_speed_synthesis_trace_outside_pct(self) -> None:
        """验收 1/2：爻光白值 101、行迹 9 —— 行迹加在百分比**外面**。"""
        one = self.call("plan", {"characterId": "1502", "speedPct": 6, "speedFlat": 0,
                                 "rounds": 1, "maxActions": 1})
        self.assertAlmostEqual(one["speed"]["final"], 116.06)  # 101 × 1.06 + 9
        self.assertAlmostEqual(one["speed"]["base"], 101.0)    # 白值，不是 110
        self.assertAlmostEqual(one["speed"]["trace"], 9.0)
        self.assertFalse(one["speed"]["baseSource"]["useEffective"])

        two = self.call("plan", {"characterId": "1502", "speedPct": 6, "speedFlat": 25,
                                 "rounds": 1, "maxActions": 1})
        self.assertAlmostEqual(two["speed"]["final"], 141.06)  # 101 × 1.06 + 25 + 9

        # 只有显式传 useEffectiveBase=true 才走旧口径（行迹并进基础速度一起吃百分比）
        legacy = self.call("plan", {"characterId": "1502", "speedPct": 6,
                                    "useEffectiveBase": True, "rounds": 1, "maxActions": 1})
        self.assertAlmostEqual(legacy["speed"]["final"], 116.6)  # 110 × 1.06

    def test_speed_synthesis_lightcone_white_value(self) -> None:
        """验收 3：光锥白字进括号吃百分比 —— (101 + 12) × 1.06 + 9 = 128.78。"""
        res = self.call("plan", {"characterId": "1502", "lightconeBaseSpeed": 12,
                                 "speedPct": 6, "rounds": 1, "maxActions": 1})
        self.assertAlmostEqual(res["speed"]["final"], 128.78)
        self.assertAlmostEqual(res["speed"]["lightconeBase"], 12.0)

        # 没手填光锥白字时默认 0，不悄悄加
        plain = self.call("plan", {"characterId": "1502", "speedPct": 6,
                                   "rounds": 1, "maxActions": 1})
        self.assertAlmostEqual(plain["speed"]["final"], 116.06)

        final_speed = self.mod().final_speed
        self.assertAlmostEqual(final_speed(101, 6, 0, lightcone_base=12, trace=9), 128.78)
        self.assertAlmostEqual(final_speed(101, 6, 25, trace=9), 141.06)

    def test_speed_changes_add_to_base_not_final(self) -> None:
        """手填 speedChanges 是**增量**，只加在白字上：

            这一动 = (base + 光锥白字) × (1 + 常驻% + 这一动%) + 常驻固定 + 这一动固定 + 行迹

        拿已经算完的速度当基数再乘，会把鞋子和行迹再放大一遍。
        """
        res = self.call("plan", {
            "characterId": "1502", "speedPct": 6, "speedFlat": 0,
            "speedChanges": [{"fromAction": 2, "pct": 12, "flat": 0}],
            "rounds": 3, "maxActions": 2,
        })
        self.assertAlmostEqual(res["speed"]["final"], 116.06)
        self.assertAlmostEqual(res["speed"]["pct"], 6.0)   # 常驻值不被 speedChanges 覆盖
        self.assertAlmostEqual(res["actions"][0]["speed"], 116.06)
        self.assertAlmostEqual(res["actions"][1]["speed"], 128.18)  # 101 × 1.18 + 9
        # 错误口径是 116.06 × 1.12 = 129.99（把鞋子/行迹又乘了一遍）

    # ---- 中途变速 ----

    def test_mid_turn_speed_change_keeps_run_distance(self) -> None:
        """验收 6：剩余路程 5000 时速度 100 → 200 —— 已跑的 5000 不动，
        剩余行动值 50 → 25；这一动共 5000/100 + 5000/200 = 75 AV。
        """
        recalc = self.mod().recalc_remaining_av
        self.assertAlmostEqual(recalc(5000.0, 100.0, 200.0), 25.0)

        res = self.call("plan", {
            "baseSpeed": 100,
            "midTurnChanges": {"1": [{"atRemainingDistance": 5000, "speed": 200}]},
            "rounds": 3, "maxActions": 2,
        })
        self.assertAlmostEqual(res["actions"][0]["gap"], 75.0)
        self.assertAlmostEqual(res["actions"][0]["av"], 75.0)
        # 变速带「发生时刻」：变完之后按新速度继续跑（不退回 100、也不整段重跑）
        self.assertAlmostEqual(res["actions"][1]["speed"], 200.0)
        self.assertAlmostEqual(res["actions"][1]["gap"], 50.0)

    # ---- 轮次 ----

    def test_cycle_window_150_then_100(self) -> None:
        res = self.call("plan", {"baseSpeed": 100, "rounds": 4})
        self.assertEqual(res["window"]["av"], 450.0)
        self.assertEqual(self.call("plan", {"baseSpeed": 100, "rounds": 1})["window"]["av"], 150.0)

    def test_round_boundaries(self) -> None:
        # 第 1 轮 0–150、之后每轮 100：速度 100 时 AV 100/200/300/400 → 第 1/2/3/4 轮
        res = self.call("plan", {"baseSpeed": 100, "rounds": 5, "maxActions": 4})
        rounds = [r["round"] for r in res["actions"]]
        self.assertEqual(rounds, [1, 2, 3, 4])

    def test_round_of_boundaries(self) -> None:
        """轮次标签和配速查询对齐：打完时的累计行动值 ≤ 该轮窗口，仍算在这一轮。

        所以 150 是第 1 轮**末尾**、250 是第 2 轮末尾、350 是第 3 轮末尾、
        450 是第 4 轮末尾 —— 不是把边界当下一轮起点。
        """
        round_of = self.mod().round_of
        cases = {0.0: 1, 149.9: 1, 150.0: 1, 150.1: 2, 249.9: 2, 250.0: 2,
                 250.1: 3, 350.0: 3, 351.0: 4, 450.0: 4}
        for av, expect in cases.items():
            self.assertEqual(round_of(av), expect, f"AV {av} 应该在第 {expect} 轮")

    def test_required_speed_matches_open_formula(self) -> None:
        res = self.call("compare", {"baseSpeed": 100, "rounds": 4, "advancePct": 0})
        # 5 动 / 450 AV = 111.111
        self.assertAlmostEqual(res["requiredForActions"]["5"], 10000 * 5 / 450.0)

    # ---- 速度方案默认三行 ----

    def test_compare_default_plans_use_flat_speed_boots(self) -> None:
        """验收 9 + 「速度方案」默认三行：速度鞋是**固定 +25**，不是百分比 +25。

        爻光白值 101 + 行迹 9：第一行 101 + 25 + 9 = 135.0（不是 137.5）。
        副词条那 45 固定单独标来源（shoeFlat/extraFlat），不把 70 叫成速度鞋。
        """
        res = self.call("compare", {"characterId": "1502", "rounds": 4})
        self.assertEqual([r["label"] for r in res["rows"]],
                         ["速度鞋", "速度鞋 + 18%", "18% + 速度鞋 + 45 副词条"])

        one, two, three = res["rows"]
        self.assertAlmostEqual(one["pct"], 0.0)
        self.assertAlmostEqual(one["flat"], 25.0)
        self.assertAlmostEqual(one["speed"], 135.0)          # 101 + 25 + 9

        self.assertAlmostEqual(two["pct"], 18.0)
        self.assertAlmostEqual(two["flat"], 25.0)
        self.assertAlmostEqual(two["speed"], 101 * 1.18 + 25 + 9)

        self.assertAlmostEqual(three["pct"], 18.0)
        self.assertAlmostEqual(three["flat"], 70.0)          # 25（鞋）+ 45（副词条）
        self.assertAlmostEqual(three["shoeFlat"], 25.0)
        self.assertAlmostEqual(three["extraFlat"], 45.0)
        self.assertAlmostEqual(three["speed"], 101 * 1.18 + 70 + 9)

    # ---- 回能与数据来源 ----

    def test_yaoguang_energy_comes_from_skill_text_not_fallback(self) -> None:
        """爻光普攻的回能必须标成「文案」（30），不能是通用兜底 20。"""
        res = self.call("profile", {"characterId": "1502"})
        self.assertEqual(res["profile"]["name"], "爻光")
        self.assertEqual(res["profile"]["maxSp"], 180)
        normal = res["energyTable"]["普攻"]
        self.assertEqual(normal["value"], 30.0)
        self.assertEqual(normal["source"], "文案")

    def test_energy_gain_applies_err(self) -> None:
        base = self.call("energy", {"characterId": "1502", "rotation": ["普攻"],
                                    "actions": 1, "err": 0})
        buffed = self.call("energy", {"characterId": "1502", "rotation": ["普攻"],
                                      "actions": 1, "err": 50})
        self.assertAlmostEqual(base["rows"][0]["energy"], 30.0)
        self.assertAlmostEqual(buffed["rows"][0]["energy"], 45.0)

    def test_energy_caps_at_max_sp(self) -> None:
        res = self.call("energy", {"characterId": "1502", "maxSp": 180,
                                   "rotation": ["战技"], "actions": 20})
        self.assertLessEqual(max(r["energy"] for r in res["rows"]), 180.0)
        self.assertFalse(any(r["energy"] > 180.0 for r in res["rows"]))

    def test_first_full_action_is_6_without_extra_energy(self) -> None:
        # 180 ÷ 30 = 6 动（爻光普攻回能 30，能量上限 180）
        res = self.call("energy", {"characterId": "1502", "rotation": ["普攻"], "actions": 10})
        self.assertEqual(res["firstFullAction"], 6)

    def test_fixed_energy_ignores_err(self) -> None:
        """验收 8 + 「固定」护栏：标「固定」的回能**不乘 (1 + ERR)**。

        流萤战技是 144 点固定回能（不是通用 30）；停云终结技 50 点固定能量；
        阿哈愿力 +1 —— ERR 拉多高都不变。
        """
        f0 = self.call("energy", {"characterId": "1310", "rotation": ["战技"],
                                  "actions": 1, "err": 0})
        f50 = self.call("energy", {"characterId": "1310", "rotation": ["战技"],
                                   "actions": 1, "err": 50})
        self.assertAlmostEqual(f0["energyTable"]["战技"]["value"], 144.0)  # 不是 30
        self.assertEqual(f0["energyTable"]["战技"]["source"], "固定")
        self.assertTrue(f0["energyTable"]["战技"]["fixed"])
        self.assertAlmostEqual(f0["rows"][0]["energy"], 144.0)
        self.assertAlmostEqual(f50["rows"][0]["energy"], 144.0)  # 吃 ERR 就会变 216

        # 停云终结技 50 点固定能量：开大返还也不随 ERR 变（吃 ERR 会变 75）
        u0 = self.call("energy", {"characterId": "1202", "startEnergy": 130,
                                  "rotation": ["普攻"], "actions": 1,
                                  "actionsPerUlt": 1, "err": 0})
        u50 = self.call("energy", {"characterId": "1202", "startEnergy": 130,
                                   "rotation": ["普攻"], "actions": 1,
                                   "actionsPerUlt": 1, "err": 50})
        self.assertAlmostEqual(u0["energyTable"]["终结技"]["value"], 50.0)
        self.assertEqual(u0["energyTable"]["终结技"]["source"], "固定")
        self.assertAlmostEqual(u0["rows"][0]["energy"], 50.0)
        self.assertAlmostEqual(u50["rows"][0]["energy"], 50.0)

        # 星神★阿哈：愿力 +1 固定，不吃 ERR
        aha = self.call("energy", {"characterId": "1511", "rotation": ["普攻"],
                                   "actions": 1, "err": 100})
        self.assertAlmostEqual(aha["rows"][0]["energy"], 1.0)

    def test_excluded_characters_reject_energy_formula(self) -> None:
        """特殊能量角色（残梦/飞黄/新蕊/火种/追忆/隐藏分/绯英）不进这张表：

        调回能直接报「这套回能公式不适用」；查档案返回 excluded 标记。
        """
        for cid, name in [("1308", "黄泉"), ("1220", "飞霄"), ("1407", "遐蝶"),
                          ("1408", "白厄"), ("1415", "昔涟"), ("1506", "银狼LV.999"),
                          ("1505", "绯英")]:
            with self.assertRaises(ValueError) as err:
                self.call("energy", {"characterId": cid})
            msg = str(err.exception)
            self.assertIn(name, msg)
            self.assertIn("这套回能公式不适用", msg)

        res = self.call("profile", {"characterId": "1308"})
        self.assertTrue(res["excluded"])
        self.assertEqual(res["excludedReason"],
                         "特殊能量（负面状态叠层激活终结技，这套回能公式不适用）")
        self.assertEqual(res["message"], "这套回能公式不适用")

    def test_catalog_lists_speed_parts_and_excluded(self) -> None:
        """目录要把「基础 / 行迹 / 有效基础」拆开给界面，另列特殊能量隔离名单。"""
        res = self.call("catalog")
        by_id = {c["id"]: c for c in res["characters"]}
        yg = by_id["1502"]
        self.assertEqual(yg["baseSpeed"], 101)                # 白值
        self.assertAlmostEqual(yg["traceSpeed"], 9.0)          # 行迹单列
        self.assertAlmostEqual(yg["effectiveBaseSpeed"], 110.0)
        self.assertEqual(yg["pathName"], "欢愉")
        self.assertEqual(yg["elementName"], "物理")
        self.assertEqual(yg["energyType"], "standard")
        self.assertIn("结界", yg["mechanismNote"])

        excluded = {e["name"] for e in res["excludedCharacters"]}
        self.assertTrue({"黄泉", "飞霄", "遐蝶", "白厄", "昔涟", "银狼LV.999", "绯英"}
                        <= excluded)

    # ---- 爻光机制 ----

    def test_yaoguang_kit_numbers_match_starrailres(self) -> None:
        res = self.call("profile", {"characterId": "1502"})
        kit = res["kit"]
        self.assertEqual(kit["maxSp"], 180)
        self.assertEqual(kit["skill"]["fieldTurns"], 3)
        self.assertEqual(kit["skill"]["spunkPerAction"], 3)
        self.assertEqual(kit["ult"]["spunk"], 5)
        self.assertIn("开屏有礼", kit["extraTraces"])
        self.assertNotIn("速度强化", kit["extraTraces"])  # 数值升级项不算额外行迹

    def test_yaoguang_spunk_accumulates_3_per_own_action(self) -> None:
        """结界覆盖爻光自己的 3 次行动，只有这 3 动 +3；结界外不再加。"""
        res = self.call("yaoguang", {"actions": 4, "rotation": ["普攻"], "openingSkill": True})
        self.assertEqual([r["spunk"] for r in res["rows"]], [3, 6, 9, 9])
        self.assertEqual([r["fieldActive"] for r in res["rows"]],
                         [True, True, True, False])
        five = self.call("yaoguang", {"actions": 5, "rotation": ["普攻"], "openingSkill": True})
        self.assertEqual([r["spunk"] for r in five["rows"]], [3, 6, 9, 9, 9])
        self.assertEqual(five["totals"]["spunk"], 9)
        self.assertIn("结界外：不加笑点", five["rows"][3]["notes"])
        self.assertIn("结界外：不加笑点", five["rows"][4]["notes"])

    def test_yaoguang_field_decays_per_own_turn(self) -> None:
        """验收 7：结界覆盖爻光**自己的 3 次正常行动**。

        放战技那一次直接记满 3 回合、当回合**不**立刻减 1；
        从下一次自己的回合开始递减：fieldLeft [3, 2, 1, 0]，
        fieldActive [True, True, True, False]（不是旧的 2、1、0、0）。
        """
        res = self.call("yaoguang", {"actions": 4, "rotation": ["普攻"], "openingSkill": True})
        self.assertEqual([r["fieldLeft"] for r in res["rows"]], [3, 2, 1, 0])
        self.assertEqual([r["fieldActive"] for r in res["rows"]],
                         [True, True, True, False])

    def test_yaoguang_ult_gives_aha_extra_turn(self) -> None:
        res = self.call("yaoguang", {"actions": 10, "rotation": ["普攻"], "openingSkill": True,
                                     "err": 20, "actionsPerUlt": 5})
        self.assertEqual(res["totals"]["extraTurnsForAha"], res["totals"]["ults"])
        self.assertGreaterEqual(res["totals"]["extraTurnsForAha"], 1)
        # 1 魂把额外回合固定计入的笑点从 20 提到 40 —— 只影响说明文字，不改笑点累加
        e1 = self.call("yaoguang", {"actions": 10, "rotation": ["普攻"], "openingSkill": True,
                                    "err": 20, "actionsPerUlt": 5, "eidolon": 1})
        joined = " ".join(n for r in e1["rows"] for n in r["notes"])
        self.assertIn("40", joined)

    def test_yaoguang_ascension_trace_is_on_her_profile_not_a_switch(self) -> None:
        """升格不是排轴开关。笑点表不含 +12/+10；行迹写在爻光自己的档案里。"""
        base = {"actions": 1, "rotation": ["普攻"], "openingSkill": True,
                "startEnergy": 180, "actionsPerUlt": 1, "err": 0, "skillLevel": 10}
        off = self.call("yaoguang", base)
        sent = self.call("yaoguang", {**base, "pathAscension": True})
        self.assertEqual(off["rows"], sent["rows"])
        self.assertEqual(off["totals"], sent["totals"])
        self.assertNotIn("pathAscension", off["params"])
        self.assertAlmostEqual(off["kit"]["talent"]["elationDamage"], 0.2)
        self.assertAlmostEqual(off["kit"]["talent"]["ascensionBonus"], 0.0)
        trace = off["kit"]["inherentTrace"]
        self.assertEqual(trace["name"], "欢愉万相★心灵感应")
        self.assertEqual(trace["id"], "150229")
        self.assertFalse(trace["active"])
        self.assertAlmostEqual(trace["dajiBonus"], 0.2)
        self.assertEqual(trace["ultEnergy"], 12)
        self.assertEqual(trace["ultSpunk"], 10)
        self.assertNotIn("心灵感应", " ".join(n for r in off["rows"] for n in r["notes"]))
        text = " ".join(off["assumptions"])
        self.assertIn("欢愉万相", text)
        self.assertIn("阿哈", text)
        prof = self.call("profile", {"characterId": "1502"})["profile"]
        stored = next(t for t in prof["traces"] if t.get("name") == "欢愉万相★心灵感应")
        self.assertEqual(stored["kind"], "固有行迹")
        self.assertEqual(stored["params"][0], [0.2, 12, 0, 10])
        self.assertIn("hsr.nanoka.cc/character/1502", stored["sourceUrl"])

    def test_every_elation_character_keeps_its_ascension_trace(self) -> None:
        """每个欢愉角色的欢愉万相★行迹在自己的档案里，不在全局开关上。"""
        cat = self.call("catalog")
        by_id = {c["id"]: c for c in cat["characters"]}
        expect = {
            "1501": "欢愉万相★兔子戏法",
            "1502": "欢愉万相★心灵感应",
            "1503": "欢愉万相★跃然纸上",
            "1511": "欢愉万相★无中生有",
            "1513": "欢愉万相★三赌牌局",
            "8009": "欢愉万相★主角光环",
        }
        for cid, name in expect.items():
            with self.subTest(id=cid):
                got = by_id[cid]["ascensionTrace"]
                self.assertEqual(got["name"], name)
                self.assertEqual(got["kind"], "固有行迹")
                self.assertEqual(len(got["params"]), 2)
                self.assertIn(f"character/{cid}", got["sourceUrl"])
                self.assertIn("欢愉万相", got["activeWhen"])
        self.assertIsNone(by_id["1001"]["ascensionTrace"])
        self.assertEqual(by_id["8009"]["ascensionTrace"]["alsoRecordedAs"]["id"], "8010")
        excluded = {c["id"]: c for c in cat["excludedCharacters"]}
        self.assertEqual(excluded["1505"]["ascensionTrace"]["name"], "欢愉万相★书中折花")
        self.assertEqual(excluded["1505"]["ascensionTrace"]["params"][0], [0.75, 0.1, 60, 480])
        self.assertEqual(excluded["1506"]["ascensionTrace"]["name"], "欢愉万相★全息幻象")
        self.assertEqual(excluded["1506"]["ascensionTrace"]["params"][0], [360, 0.2, 0.4])
        self.assertIn("character/1506", excluded["1506"]["ascensionTrace"]["sourceUrl"])

    def test_yaoguang_declares_its_assumptions(self) -> None:
        """不确定的东西必须显式声明，不能悄悄假设。"""
        res = self.call("yaoguang", {"actions": 5})
        text = " ".join(res["assumptions"])
        self.assertIn("笑点", text)
        self.assertIn("阿哈", text)

    # ---- 模块骨架 ----

    def test_feature_json_matches_directory(self) -> None:
        feature_dir = ROOT / "modules" / self.MODULE / "features" / self.FEATURE
        meta = json.loads((feature_dir / "feature.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["id"], self.FEATURE)
        manifest = json.loads((ROOT / "modules" / self.MODULE / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["id"], self.MODULE)

    def test_profile_data_declares_its_sources(self) -> None:
        data = json.loads((ROOT / "modules" / self.MODULE / "data" / "profiles.json").read_text(encoding="utf-8"))
        names = " ".join(s["name"] for s in data["sources"])
        self.assertIn("StarRailRes", names)
        self.assertIn("通用", names)  # 兜底来源必须写出来


class TestActionValuePresetBridge(unittest.TestCase):
    """配速查询的预设 → 行动值排轴。**真的调 speed-plan**，不造假数据。"""

    # 每次跑都用独立的 userdata，不碰真 userdata
    MODULE = "action-value"
    FEATURE = "timeline"
    CONFIG = {
        "lightconeId": "23006",          # 卡芙卡的「只需等待」（虚无，能装）
        "superimpose": 5,
        "eidolon": 0,
        "relic": {"speedBoots": True, "customPct": 10, "substatSpeed": 12},
        "advance": {"custom": 25},
        "target": {"t": 0, "actions": 2},
    }

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.mkdtemp(prefix="gt-av-bridge-")
        cls._old = os.environ.get("GT_USERDATA")
        os.environ["GT_USERDATA"] = cls._tmp
        try:
            cls._errors = _load()
        finally:
            if cls._old is None:
                os.environ.pop("GT_USERDATA", None)
            else:
                os.environ["GT_USERDATA"] = cls._old

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def _with_temp_userdata(self, fn):
        """在临时 userdata 下跑一段（feature_api 是读环境变量决定目录的）。"""
        old = os.environ.get("GT_USERDATA")
        os.environ["GT_USERDATA"] = self._tmp
        try:
            return fn()
        finally:
            if old is None:
                os.environ.pop("GT_USERDATA", None)
            else:
                os.environ["GT_USERDATA"] = old

    def _sp(self, action, payload=None):
        return feature_api.call("honkai-star-rail", "speed-plan", action, payload or {})

    def _av(self, action, payload=None):
        return feature_api.call(self.MODULE, self.FEATURE, action, payload or {})

    def _save(self):
        return self._sp("save_preset", {"characterId": "1005", "config": self.CONFIG})

    def test_config_has_no_character_id_but_bridge_still_works(self) -> None:
        """预设的 config 里没有 characterId（角色 id 是外层键）—— 桥接必须自己补上。

        早期版本直接把 config 丢给 speed-plan，报「找不到角色 None」。
        """
        self.assertNotIn("characterId", self.CONFIG)
        self._with_temp_userdata(self._save)
        self.assertNotIn("characterId", self.CONFIG)  # 保存过程不该改动我们的字典
        got = self._with_temp_userdata(lambda: self._av("preset", {"characterId": "1005"}))
        self.assertEqual(got["characterId"], "1005")
        self.assertGreater(got["computed"]["speed"]["final"], 0)

    def test_preset_list_contains_saved_character(self) -> None:
        self._with_temp_userdata(self._save)
        lst = self._with_temp_userdata(lambda: self._av("preset"))
        ids = [p["characterId"] for p in lst["presets"]]
        self.assertIn("1005", ids)

    def test_missing_preset_raises_readable_error(self) -> None:
        self._with_temp_userdata(self._save)
        with self.assertRaises(ValueError) as ctx:
            self._with_temp_userdata(lambda: self._av("preset", {"characterId": "1999"}))
        self.assertIn("1999", str(ctx.exception))

    def test_timeline_uses_absolute_speed_not_delta(self) -> None:
        """timeline 每条是**绝对速度**；当增量叠加会把速度算爆（147 → 302）。

        这里对着 speed-plan 自己给的 final 速度钉住：每一动的速度必须等于它，
        不能是「S0 + 被动加成」那种重复计算。
        """
        self._with_temp_userdata(self._save)
        one = self._with_temp_userdata(lambda: self._av("preset", {"characterId": "1005"}))
        final = one["computed"]["speed"]["final"]
        res = self._with_temp_userdata(
            lambda: self._av("plan", {"presetCharacterId": "1005", "rounds": 4, "maxActions": 8})
        )
        for row in res["actions"]:
            self.assertAlmostEqual(row["speed"], final, places=6,
                                   msg="每动速度必须等于 speed-plan 的当前速度，不能叠成增量")

    def test_preset_plan_matches_manual_entry(self) -> None:
        """套预设 与 手填同样数字，必须逐动一致（同一条口径）。"""
        self._with_temp_userdata(self._save)
        one = self._with_temp_userdata(lambda: self._av("preset", {"characterId": "1005"}))
        comp = one["computed"]
        via_preset = self._with_temp_userdata(
            lambda: self._av("plan", {"presetCharacterId": "1005", "rounds": 4, "maxActions": 12})
        )
        manual = self._with_temp_userdata(lambda: self._av("plan", {
            "baseSpeed": comp["speed"]["base"],
            "speedPct": comp["speed"]["pct"],
            "speedFlat": comp["speed"]["flat"],
            "advancePct": comp["advance"]["total"],
            "rounds": 4, "maxActions": 12,
        }))
        self.assertAlmostEqual(via_preset["speed"]["final"], manual["speed"]["final"], places=6)
        self.assertEqual(via_preset["actionCount"], manual["actionCount"])
        for a, b in zip(via_preset["actions"], manual["actions"]):
            self.assertAlmostEqual(a["av"], b["av"], places=6)
            self.assertEqual(a["round"], b["round"])

    def test_preset_carries_speed_breakdown_and_advance_items(self) -> None:
        self._with_temp_userdata(self._save)
        res = self._with_temp_userdata(
            lambda: self._av("plan", {"presetCharacterId": "1005"})
        )
        labels = [b["label"] for b in res["appliedPreset"]["speedBreakdown"]]
        self.assertIn("遗器主词条·速度鞋", labels)
        self.assertAlmostEqual(res["advance"]["pct"], 25.0)
        self.assertEqual(res["source"], "preset")
        # 套用配装时**原样使用**配速查询的结果，并注明速度来自配速查询（排轴不重算）
        self.assertIn("配速查询", res["speed"]["baseSource"]["source"])

    def test_timeline_limit_does_not_change_action_count(self) -> None:
        """给 speed-plan 加 timelineLimit 只该多记几条时间线，**不能**改变能打几次。

        早期接错参数（把条数传进 action_cap）会让 completedActions 被截断。
        """
        base = {"characterId": "1005", "lightconeId": "23006",
                "relic": {"speedBoots": True, "customFlat": 200},
                "target": {"t": 9, "actions": 8}}
        default = self._sp("plan", dict(base))
        wide = self._sp("plan", {**base, "timelineLimit": 40})
        narrow = self._sp("plan", {**base, "timelineLimit": 5})
        self.assertEqual(default["simulation"]["completedActions"],
                         wide["simulation"]["completedActions"])
        self.assertEqual(default["verdict"]["achievableActions"],
                         narrow["verdict"]["achievableActions"])
        self.assertGreater(len(wide["simulation"]["timeline"]),
                           len(default["simulation"]["timeline"]))


class TestAhaEventRegressions(unittest.TestCase):
    """nanoka 4.6.53：资源转换与行动条时序的独立预期。"""

    @staticmethod
    def _engine(team: list[dict], **config):
        module = sys.modules[
            feature_api.HANDLERS[("honkai-star-rail", "aha-speed")]["simulate"].__module__
        ]
        return module.Sim({"maxAV": 1, "useTech": False, "trace3Advance": False,
                           "team": team, **config})

    def test_opening_ult_advance_is_not_overwritten(self) -> None:
        sim = self._engine([{"id": "1511", "baseSpd": 1, "traceSpd": 0,
                             "lcBaseSpd": 0, "eidolon": 1}],
                           e1Wishpower=8, maxAV=100, aeonAhaBaseSpd=100)
        res = sim.run()
        first = next(ev for ev in res["timeline"] if ev["type"] == "aha")
        self.assertAlmostEqual(first["av"], 8000 / 100.2)

    def test_opening_e6_advance_runs_at_zero(self) -> None:
        sim = self._engine([{"id": "1511", "eidolon": 6}], e1Wishpower=8)
        res = sim.run()
        first = next(ev for ev in res["timeline"] if ev["type"] == "aha")
        self.assertEqual(first["av"], 0)

    def test_advance_during_extra_aha_turn_applies_to_existing_distance(self) -> None:
        sim = self._engine([{"id": "1511"}])
        unit = sim.units[0]
        unit.energy = 7
        sim.aha["rem_dist"] = 6000
        sim.do_aha(is_extra=True, fixed=20)
        self.assertEqual(unit.ult_count, 1)
        self.assertEqual(sim.aha["rem_dist"], 4000)
        self.assertEqual(sim.aha["pending"], 0)

    def test_full_initial_energy_casts_before_first_action(self) -> None:
        sim = self._engine([{"id": "1505", "initialEnergy": 480}])
        res = sim.run()
        ults = [ev for ev in res["timeline"] if ev["type"] == "ultimate"]
        self.assertEqual(len(ults), 2)
        self.assertEqual([ev["av"] for ev in ults], [0, 0])
        self.assertEqual([ev["res"]["energyBefore"] for ev in ults], [480, 245])
        self.assertEqual(res["units"][0]["initialEnergy"], 480)
        self.assertEqual(res["units"][0]["finalEnergy"], 10)
        self.assertFalse(any(ev["type"] == "skill" for ev in res["timeline"]))

    def test_aha_moment_does_not_activate_ascension(self) -> None:
        for extra in (False, True):
            with self.subTest(extra=extra):
                sim = self._engine([{"id": "1505", "initialEnergy": 470},
                                     {"id": "1511"}])
                sim.do_aha(is_extra=extra, fixed=20 if extra else 0)
                self.assertFalse(sim.huanyu_active())
                self.assertEqual(sim.units[1].ult_count, 0)
                gains = [ev for ev in sim.timeline if ev["type"] == "energy_gain"]
                self.assertTrue(gains)
                self.assertTrue(all(ev["res"]["energyCap"] == 480 for ev in gains))

    def test_ascension_starts_at_aha_ult_and_ends_with_state(self) -> None:
        sim = self._engine([{"id": "1511", "initialEnergy": 8},
                             {"id": "1505", "initialEnergy": 0}])
        aha, fei = sim.units
        self.assertFalse(sim.huanyu_active())
        sim.maybe_ult(aha)
        self.assertTrue(sim.huanyu_active())
        sim.gain_energy(fei, 1, fixed=True)
        self.assertEqual(sim.timeline[-1]["res"]["energyCap"], 540)
        for _ in range(3):
            sim.do_turn(aha)
        self.assertFalse(sim.huanyu_active())
        sim.gain_energy(fei, 1, fixed=True)
        self.assertEqual(sim.timeline[-1]["res"]["energyCap"], 480)

    def test_feiying_casts_at_first_legal_gain_crossing_threshold(self) -> None:
        for ascended in (False, True):
            with self.subTest(ascended=ascended):
                sim = self._engine([{"id": "1511", "initialEnergy": 8},
                                     {"id": "1505", "initialEnergy": 230}])
                if ascended:
                    sim.maybe_ult(sim.units[0])
                sim.av = 12.5
                start = len(sim.timeline)
                sim.gain_energy(sim.units[1], 30, fixed=True, reason="test")
                events = sim.timeline[start:]
                self.assertEqual([ev["type"] for ev in events[:2]],
                                 ["energy_gain", "ultimate"])
                self.assertEqual(events[1]["av"], 12.5)
                self.assertEqual(events[1]["res"]["energyBefore"], 260)
                self.assertEqual(events[1]["res"]["energyCost"], 240)
                self.assertEqual(sim.units[1].ult_count, 1)

    def test_opening_aha_extra_finishes_before_any_ult(self) -> None:
        for team in (
            [{"id": "1505", "initialEnergy": 480}, {"id": "1511"}],
            [{"id": "1511"}, {"id": "1505", "initialEnergy": 480}],
            [{"id": "1502", "initialEnergy": 180}, {"id": "1505", "initialEnergy": 480},
             {"id": "1511"}],
        ):
            with self.subTest(team=team):
                res = self._engine(team, useTech=True).run()
                events = res["timeline"]
                extra = next(i for i, ev in enumerate(events) if ev["type"] == "aha_extra")
                ults = [i for i, ev in enumerate(events) if ev["type"] == "ultimate"]
                self.assertTrue(ults)
                self.assertGreater(min(ults), extra)
                first_ult = min(ults)
                skills = [i for i, ev in enumerate(events)
                          if i > extra and ev["type"] == "elation_skill"][:len(team)]
                self.assertEqual(len(skills), len(team))
                self.assertLess(max(skills), first_ult)
                settlement = [i for i, ev in enumerate(events)
                              if ev["label"] == "绯英回能·好活当赏·阿哈时刻额外回合"]
                self.assertTrue(settlement)
                self.assertLess(settlement[0], first_ult)  # 爻光开大后可另触发新的 0 AV 额外回合
                self.assertEqual(events[first_ult]["av"], 0)

    def test_full_energy_does_not_accumulate_phantom_gains(self) -> None:
        sim = self._engine([{"id": "1505", "initialEnergy": 480}])
        unit = sim.units[0]
        sim.extra_depth = 1
        sim.gain_energy(unit, 30)
        self.assertEqual(unit.energy, 480)
        self.assertEqual(unit.energy_total, 0)
        self.assertEqual(unit.feiy_total, 0)
        self.assertEqual(sim.haohuo_sum(unit), 0)
        sim.extra_depth = 0

    def test_partial_gain_only_credits_available_energy(self) -> None:
        sim = self._engine([{"id": "1505", "initialEnergy": 470}])
        unit = sim.units[0]
        sim.extra_depth = 1
        sim.gain_energy(unit, 30)
        self.assertEqual(unit.energy, 480)
        self.assertEqual(unit.energy_total, 10)
        self.assertEqual(unit.feiy_total, 10)
        self.assertEqual(sim.haohuo_sum(unit), 10)

    def test_feiying_ult_times_follow_real_energy_gains(self) -> None:
        # 100 速绯英与 100 速阿哈：每 100 AV 战技 +30，
        # 欢愉技基础 +5 / 附加好活当赏 +5 / 笑点结算 +10。
        # 240 即可开大；每 100 AV 共回 50，第 5 轮首次再达门槛。
        for initial, expected in ((240, [0, 500, 1000]),
                                  (480, [0, 0, 500, 1000]), (0, [500, 1000])):
            with self.subTest(initial=initial):
                sim = self._engine([{"id": "1505", "initialEnergy": initial,
                                     "baseSpd": 100, "traceSpd": 0}],
                                   useAeonAha=False, maxAV=1000)
                res = sim.run()
                ults = [ev for ev in res["timeline"] if ev["type"] == "ultimate"]
                self.assertEqual([ev["av"] for ev in ults], expected)
                for event in ults:
                    self.assertGreaterEqual(event["res"]["energyBefore"], 240)
                    self.assertEqual(event["res"]["energyCost"], 240)
                meter = initial
                for event in res["timeline"]:
                    if event["type"] == "energy_gain":
                        self.assertEqual(event["res"]["energyBefore"], meter)
                        meter += event["res"]["energyGain"]
                        self.assertEqual(event["res"]["energy"], meter)
                    elif event["type"] == "ultimate":
                        self.assertEqual(event["res"]["energyBefore"], meter)
                        meter -= 240
                self.assertEqual(res["units"][0]["finalEnergy"], meter)

    def test_initial_energy_is_validated(self) -> None:
        for value in (-1, 481, "invalid"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self._engine([{"id": "1505", "initialEnergy": value}])

    def test_feiying_energy_to_haohuo_does_not_feed_back(self) -> None:
        sim = self._engine([{"id": "1505", "initialEnergy": 0}])
        unit = sim.units[0]
        sim.gain_energy(unit, 30)
        self.assertEqual(unit.energy, 30)
        self.assertEqual(sim.haohuo_sum(unit), 30)
        self.assertEqual(unit.feiy_total, 30)
        self.assertEqual(unit.fua_count, 0)

    def test_feiying_haohuo_to_energy_does_not_duplicate_haohuo(self) -> None:
        sim = self._engine([{"id": "1505", "initialEnergy": 0}])
        unit = sim.units[0]
        sim.grant_haohuo([unit], 20, "test")
        self.assertEqual(unit.energy, 20)
        self.assertEqual(sim.haohuo_sum(unit), 20)
        self.assertEqual(unit.feiy_total, 20)

    def test_feiying_single_gain_milestone_cap(self) -> None:
        sim = self._engine([{"id": "1505", "initialEnergy": 0}])
        unit = sim.units[0]
        sim.gain_energy(unit, 1000, fixed=True)
        self.assertEqual(unit.fua_count, 1)
        self.assertAlmostEqual(unit.feiy_total, 10)  # 满能狐狸回能截掉，两次大招各返还 +5

    def test_feiying_copies_smaller_participation_number_not_team_slot(self) -> None:
        for eidolon, copied in ((0, 10), (2, 15)):
            with self.subTest(eidolon=eidolon):
                sim = self._engine([{"id": "1503"}, {"id": "1505", "eidolon": eidolon,
                                                     "initialEnergy": 0}])
                pearl, fei = sim.units
                sim.grant_haohuo([pearl], 20, "test")
                self.assertEqual(sim.haohuo_sum(fei), copied)
                self.assertEqual(fei.energy, copied)
        sim = self._engine([{"id": "1505", "initialEnergy": 0}, {"id": "1503"}])
        sim.grant_haohuo([sim.units[1]], 20, "test")
        self.assertEqual(sim.haohuo_sum(sim.units[0]), 10)
        sim = self._engine([{"id": "1513"}, {"id": "1505"}])
        sim.grant_haohuo([sim.units[0]], 20, "test")
        self.assertEqual(sim.haohuo_sum(sim.units[1]), 0)

    def test_elation_skills_follow_source_numbers_and_aha_is_last(self) -> None:
        sim = self._engine([{"id": "1505"}, {"id": "1511"}, {"id": "1502"},
                             {"id": "1503"}])
        self.assertEqual([unit.uid for unit in sim.elation_casters()],
                         ["1503", "1502", "1505", "1511"])

    def test_ascended_feiying_overflow_uses_aha_eidolon_level(self) -> None:
        for eidolon, cap in ((0, 540), (2, 720)):
            with self.subTest(eidolon=eidolon):
                sim = self._engine([{"id": "1511", "eidolon": eidolon},
                                     {"id": "1505", "initialEnergy": 470}])
                sim.units[0].huanyu = 3
                sim.extra_depth = 1
                sim.gain_energy(sim.units[1], 1000, fixed=True)
                self.assertEqual(sim.units[1].energy, cap)

    def test_overflow_restore_counts_for_fox_but_not_energy_to_haohuo(self) -> None:
        sim = self._engine([{"id": "1511", "eidolon": 2}, {"id": "1505"}])
        aha, fei = sim.units
        aha.huanyu = 3
        fei.energy = 600
        fei.feiy_total = 120
        fei.feiy_ult_bonus = 1
        sim.cast_ult(fei)
        self.assertEqual(fei.fua_count, 1)  # 120 累计 + 120 溢出恢复
        self.assertEqual(fei.energy, 375)  # 保留 240 + 恢复 120 + 狐狸 10 + 返还 5
        self.assertEqual(fei.feiy_total, 15)
        self.assertEqual(sim.haohuo_sum(fei), 15)  # 恢复的 120 不转好活当赏
        notes = [detail for ev in sim.timeline if ev["label"] == "欢愉万相★书中折花"
                 for detail in ev["details"]]
        self.assertTrue(any("150%" in detail for detail in notes))
        self.assertTrue(any("24%" in detail for detail in notes))

    def test_feiying_copies_expiring_ally_haohuo(self) -> None:
        for eidolon, copied in ((0, 10), (2, 20)):
            with self.subTest(eidolon=eidolon):
                sim = self._engine([{"id": "1505", "eidolon": eidolon, "initialEnergy": 0},
                                     {"id": "1503"}])
                fei, pearl = sim.units
                pearl.haohuo = [{"count": 20, "turns": 1, "label": "test"}]
                sim.turn_end(pearl)
                self.assertEqual(sim.haohuo_sum(fei), copied)
                self.assertEqual(pearl.haohuo, [])

    def test_feiying_technique_and_elation_grant_extra_haohuo(self) -> None:
        sim = self._engine([{"id": "1505", "initialEnergy": 0}], useTech=True)
        sim.battle_start()
        unit = sim.units[0]
        self.assertEqual(unit.energy, 20)
        self.assertEqual(sim.haohuo_sum(unit), 20)
        sim.cast_elation_skill(unit)
        self.assertEqual(unit.energy, 30)  # 5 基础能量 + 5 好活当赏转能量
        self.assertEqual(sim.haohuo_sum(unit), 30)

    def test_feiying_e1_followup_casts_elation_once(self) -> None:
        sim = self._engine([{"id": "1505", "eidolon": 1, "initialEnergy": 0}])
        unit = sim.units[0]
        sim.gain_energy(unit, 240, fixed=True)
        self.assertEqual(unit.fua_count, 1)
        self.assertEqual(sum(ev["type"] == "elation_skill" for ev in sim.timeline), 1)
        self.assertEqual(unit.energy, 35)  # 240 + 10 + 5 + 15 - 240 + 5
        self.assertEqual(unit.feiy_total, 35)

    def test_feiying_ult_waits_for_fox_and_e1_elation_settlement(self) -> None:
        sim = self._engine([{"id": "1505", "eidolon": 1, "initialEnergy": 230}])
        sim.gain_energy(sim.units[0], 250, fixed=True)
        events = sim.timeline
        ult = next(i for i, ev in enumerate(events) if ev["type"] == "ultimate")
        elation = next(i for i, ev in enumerate(events) if ev["type"] == "elation_skill")
        settlement = next(i for i, ev in enumerate(events)
                          if ev["label"] == "绯英回能·好活当赏·绯英欢愉技")
        self.assertLess(elation, settlement)
        self.assertLess(settlement, ult)
        self.assertEqual(sim.units[0].energy, 10)

    def test_damaging_ults_use_attack_hooks(self) -> None:
        for uid in ("1511", "1505"):
            with self.subTest(uid=uid):
                sim = self._engine([{"id": uid}, {"id": "1309"}])
                actor, robin = sim.units
                sim.cast_ult(actor)
                self.assertEqual(robin.energy, robin.max_sp * 0.5 + 2)

    def test_extra_turn_defers_ult_until_settlement(self) -> None:
        sim = self._engine([{"id": "1505", "maxSp": 30, "initialEnergy": 0}])
        sim.do_extra_turn(sim.units[0], "test", grant_punchline=60)
        labels = [ev["label"] for ev in sim.timeline]
        self.assertLess(labels.index("额外回合笑点结算"), labels.index("绯英 的终结技"))

    def test_custom_err_chain_is_bounded_and_reported(self) -> None:
        sim = self._engine([{"id": "1505", "err": 2400, "initialEnergy": 0,
                             "maxSp": 100000}])
        sim.gain_energy(sim.units[0], 240, fixed=True)
        self.assertTrue(sim.truncated)
        self.assertTrue(any("狐狸老师" in warning for warning in sim.warnings))


class TestAhaSpeedSimulation(unittest.TestCase):
    """【阿哈时刻】配速的模拟引擎：公式与机制全部钉在确定性排轴上。

    只走公开动作（catalog / simulate / threshold），每条机制都从
    timeline / units / notes 的账面上验证，改坏了立刻知道。
    """

    # ---- 小工具 ----

    @staticmethod
    def _sim(payload: dict) -> dict:
        return call("aha-speed", "simulate", payload)

    @staticmethod
    def _labels(res: dict, key: str) -> list[dict]:
        """timeline 里 label 含 key 的事件。"""
        return [ev for ev in res["timeline"] if key in ev["label"]]

    @staticmethod
    def _action_avs(res: dict, slot: int) -> list[float]:
        """某 slot 的常规行动时间点；额外回合不算（它不重置行动条距离）。"""
        return [ev["av"] for ev in res["timeline"]
                if ev["slot"] == slot and not ev["extra"]
                and ev["type"] in ("basic", "skill", "enhanced_basic")]

    @staticmethod
    def _fervor_steps(res: dict) -> list[float]:
        """热意快照的正向增量（每次队友攻击给多少热意）。"""
        vals = [ev["res"]["fervor"] for ev in res["timeline"] if ev["res"]["fervor"] is not None]
        return [round(b - a, 6) for a, b in zip(vals, vals[1:]) if b > a]

    # ---- 目录 ----

    def test_catalog_contains_core_elation_roster(self) -> None:
        """目录必须列出核心欢愉阵容（含对照组砂金(存护)）。"""
        res = call("aha-speed", "catalog")
        by_id = {row["id"]: row for row in res["roster"]}
        expect = {
            "1511": "星神★阿哈", "1503": "真珠", "1513": "砂金•戏浪", "1304": "砂金(存护)",
            "1502": "爻光", "1501": "火花", "8009": "开拓者•欢愉", "1505": "绯英",
            "1506": "银狼LV.999",
        }
        for cid, name in expect.items():
            with self.subTest(id=cid):
                self.assertIn(cid, by_id)
                self.assertEqual(by_id[cid]["name"], name)
        # 欢愉标记分对错：砂金(存护) 是对照组，不能算欢愉
        for cid in ("1511", "1503", "1513", "1502", "1501", "8009", "1505", "1506"):
            self.assertTrue(by_id[cid]["elation"], cid)
        self.assertFalse(by_id["1304"]["elation"])
        # 加权系数 0.2/0.1/0.05/0.025（除数 5/10/20/40）
        self.assertEqual([(w["weight"], w["divisor"]) for w in res["ahaWeights"]],
                         [(0.2, 5), (0.1, 10), (0.05, 20), (0.025, 40)])

    # ---- 【阿哈时刻】速度公式 ----

    def test_aha_instant_speed_formula_with_and_without_aeon_aha(self) -> None:
        """【阿哈时刻】速度 = 底速 + 0.2V1 + 0.1V2 + 0.05V3 + 0.025V4。

        useAeonAha=False 底速 80；True（或 1511 在队）底速 94 + 12（专武白值
        在百分比乘区内）。窗口压到 1 AV 且不吃秘技：没有任何事件改速度，
        测的就是纯公式。
        """
        base_cfg = {"useTech": False, "maxAV": 1}

        no_aeon = self._sim({"team": [{"id": "1503"}, {"id": "1513"},
                                      {"id": "1502"}, {"id": "1501"}],
                             "useAeonAha": False, **base_cfg})
        vs = sorted((u["initialSpd"] for u in no_aeon["units"] if u["elation"]), reverse=True)
        self.assertEqual([116.0, 110.0, 108.0, 107.0], vs)  # 砂金戏浪/爻光/真珠/火花
        self.assertFalse(no_aeon["aha"]["useAeonAha"])
        self.assertAlmostEqual(no_aeon["aha"]["base"], 80.0)
        self.assertAlmostEqual(no_aeon["aha"]["speed"],
                               80 + 0.2 * vs[0] + 0.1 * vs[1] + 0.05 * vs[2] + 0.025 * vs[3])
        self.assertAlmostEqual(no_aeon["aha"]["speed"], 122.275)

        with_aeon = self._sim({"team": [{"id": "1511"}, {"id": "1513"},
                                        {"id": "1502"}, {"id": "1503"}],
                               "useAeonAha": True, **base_cfg})
        vs = sorted((u["initialSpd"] for u in with_aeon["units"] if u["elation"]), reverse=True)
        self.assertEqual([116.0, 111.0, 110.0, 108.0], vs)  # 1511 带专武：94+12+5 行迹
        self.assertTrue(with_aeon["aha"]["useAeonAha"])
        self.assertAlmostEqual(with_aeon["aha"]["baseSpd"], 94.0)
        self.assertAlmostEqual(with_aeon["aha"]["lcBaseSpd"], 12.0)
        self.assertAlmostEqual(with_aeon["aha"]["base"], 106.0)  # 94 + 12（专武）
        self.assertAlmostEqual(with_aeon["aha"]["speed"],
                               106 + 0.2 * vs[0] + 0.1 * vs[1] + 0.05 * vs[2] + 0.025 * vs[3])
        self.assertAlmostEqual(with_aeon["aha"]["speed"], 148.5)
        for rank, weight, divisor in zip(with_aeon["aha"]["ranks"],
                                         (0.2, 0.1, 0.05, 0.025), (5, 10, 20, 40)):
            self.assertAlmostEqual(rank["weight"], weight)
            self.assertEqual(rank["divisor"], divisor)

    # ---- 真珠 ----

    def test_pearl_pull_scaling_1_2_3_4_elation_and_extra_turn(self) -> None:
        """真珠终结技：按欢愉人数拉【美学底本】10/15/30%，4 欢愉再给额外回合。

        拉条本身不打日志，但会改【美学底本】下一动的行动值：开局把真珠拉满
        （initAdv 100）让她在 av 0 开大，目标第一动 = (10000 − 100×拉条%) ÷ 目标速度，
        逐步对拍。真珠 err 500：战技 30×6 = 180 = 能量上限，第一动必定开大，
        之后靠【深度学习】强化普攻（20×6）压不满上限，窗口内不会有第二个大。
        """
        pearl = {"id": "1503", "initAdv": 100, "err": 500}

        # ---- 1 欢愉：拉 10% ----
        res = self._sim({"team": [{**pearl, "targetSlot": 1}, {"id": "1304"}],
                         "useTech": False, "maxAV": 150})
        details = self._labels(res, "鉴映灵魂的底色")[0]["details"]
        self.assertIn("欢愉 1 人 → 【美学底本】拉条 10%", details)
        self.assertAlmostEqual(self._action_avs(res, 1)[0], (10000 - 1000) / 106)

        # ---- 2 欢愉：拉 15% ----
        res = self._sim({"team": [{**pearl, "targetSlot": 2}, {"id": "1501"}, {"id": "1304"}],
                         "useTech": False, "maxAV": 150})
        details = self._labels(res, "鉴映灵魂的底色")[0]["details"]
        self.assertIn("欢愉 2 人 → 【美学底本】拉条 15%", details)
        self.assertAlmostEqual(self._action_avs(res, 2)[0], (10000 - 1500) / 106)

        # ---- 3 欢愉：拉 30%；E2 时其他欢愉队友一起拉 ----
        three = [{**pearl, "targetSlot": 3}, {"id": "1501"}, {"id": "1502"}, {"id": "1304"}]
        res = self._sim({"team": three, "useTech": False, "maxAV": 150})
        details = self._labels(res, "鉴映灵魂的底色")[0]["details"]
        self.assertIn("欢愉 3 人 → 【美学底本】拉条 30%", details)
        self.assertAlmostEqual(self._action_avs(res, 3)[0], (10000 - 3000) / 106)  # 砂金(存护)
        self.assertAlmostEqual(self._action_avs(res, 2)[0], 10000 / 110)           # 爻光没被拉

        res = self._sim({"team": [{**three[0], "eidolon": 2}, *three[1:]],
                         "useTech": False, "maxAV": 150})
        self.assertAlmostEqual(self._action_avs(res, 3)[0], (10000 - 3000) / 106)  # 美学底本照旧
        self.assertAlmostEqual(self._action_avs(res, 2)[0], (10000 - 3000) / 110)  # E2：爻光也拉
        self.assertAlmostEqual(self._action_avs(res, 1)[0], (10000 - 3000) / 107)  # 火花也是

        # ---- 4 欢愉：拉 30% + 【美学底本】1 个额外回合（+60 笑点）----
        res = self._sim({"team": [{**pearl, "targetSlot": 1}, {"id": "1501"},
                                  {"id": "1502"}, {"id": "8009"}],
                         "useTech": False, "maxAV": 80})
        details = self._labels(res, "鉴映灵魂的底色")[0]["details"]
        self.assertIn("欢愉 4 人 → 【美学底本】拉条 30%", details)
        self.assertIn("4 欢愉：【美学底本】额外回合（+60 笑点，E2 +120）", details)
        extra = self._labels(res, "真珠终结技·【美学底本】额外回合")
        self.assertEqual(1, len(extra))
        self.assertTrue(extra[0]["extra"])
        self.assertIn("笑点 +60（额外回合结束时结算）", extra[0]["details"])
        self.assertIn("好活当赏 +30", extra[0]["details"])
        self.assertIn("回收 60 笑点", self._labels(res, "额外回合笑点结算")[0]["details"])
        spark = next(u for u in res["units"] if u["id"] == "1501")
        self.assertEqual(1, spark["extraTurnCount"])
        # 额外回合不重置行动条：常规第一动照样按 30% 拉条后的距离跑
        self.assertAlmostEqual(self._action_avs(res, 1)[0], (10000 - 3000) / 107)

        # ---- 行迹3【艺术壁垒】：【美学底本】（欢愉）开大 → 真珠 +90 固定能量 ----
        res = self._sim({"team": [{**pearl, "targetSlot": 1}, {"id": "1501", "err": 500}],
                         "useTech": False, "maxAV": 90})
        barrier = self._labels(res, "艺术壁垒触发")
        self.assertEqual(1, len(barrier))
        self.assertEqual(["真珠 +90 固定能量（不吃 ERR）"], barrier[0]["details"])
        pearl_out = next(u for u in res["units"] if u["id"] == "1503")
        # 真珠 err 500：90 要是吃 ERR 就变 540。开局 50%（90）+ 开大返还 5×6=30 + 壁垒 90 = 210，
        # 由于上限 180 且中间会再补能量，最终停在 150（强化普攻 30×6=180 封顶后的溢出）
        self.assertAlmostEqual(pearl_out["finalEnergy"], 150.0)
        self.assertFalse(pearl_out["mechanics"]["barrierArmed"])  # 触发后解除武装

    # ---- 星神★阿哈 ----

    def test_aeon_aha_wishpower_and_ult_advances_aha_instant(self) -> None:
        """愿力来源、8 愿力开大、终结技拉条【阿哈时刻】、欢愉万相返还与 E6 首大。

        e1Wishpower 给 7（差 1 点）：第一动战技「愿力 +1」正好满 8 —— 开大必须
        发生在行动中而不是开局（开局触发的话会被 battle_start 末尾的行动条重置
        把拉条冲掉，测不到 rem_dist −= 2000）。
        """
        team = [
            {"id": "1511", "eidolon": 1, "initAdv": 30, "targetSlot": 1},
            {"id": "1503", "targetSlot": 2},
            {"id": "1513"},
            {"id": "1501"},
        ]
        cfg = {"team": team, "useTech": False, "e1Wishpower": 7, "maxAV": 200}
        res = self._sim(dict(cfg))

        # 愿力来源逐个对账：E1 开局 +7、自己出招 +1、欢愉技 +1、令使回合开始 +1、
        # 受治疗/护盾（行迹2）+1。这个 200 AV 窗口里，文档写明的笑点来源每轮都被
        # 【阿哈时刻】吃掉，堆不到 40；旧口径靠欢愉技 +20 才会在这里打出「笑点首达 40」。
        self.assertEqual(["愿力 +7"], self._labels(res, "E1 开局回能")[0]["details"])
        own = [ev for ev in res["timeline"]
               if ev["type"] == "skill" and ev["name"] == "星神★阿哈"]
        self.assertTrue(any("愿力 +1" in ev["details"] for ev in own))
        self.assertTrue(any("愿力 +1" in ev["details"]
                            for ev in self._labels(res, "自身动作回能")))
        self.assertEqual(["星神★阿哈愿力 +1"],
                         self._labels(res, "【「欢愉」令使】回合开始")[0]["details"])
        self.assertFalse(any("笑点首达 40" in n for n in res["notes"]))
        self.assertEqual(["真珠战技群疗 → 愿力 +1"],
                         self._labels(res, "戏中人的异想国")[0]["details"])
        aha_unit = next(u for u in res["units"] if u["id"] == "1511")
        self.assertGreaterEqual(aha_unit["mechanics"]["wishpowerTotal"], 12.0)

        # 8 愿力开大：消耗 8 愿力、拉条【阿哈时刻】20%、进【欢愉万相】3 回合
        ults = [ev for ev in res["timeline"]
                if ev["type"] == "ultimate" and ev["name"] == "星神★阿哈"]
        self.assertTrue(any("消耗 8 愿力" in ev["details"] for ev in ults))
        boom = self._labels(res, "啊哈！宇宙笑点大爆炸")[0]
        self.assertIn("【阿哈时刻】拉条 20%", boom["details"])
        self.assertTrue(any("星神★阿哈进入【欢愉万相】3 回合" in n for n in res["notes"]))
        settle = self._labels(res, "【阿哈时刻】笑点结算")[0]["details"]
        self.assertTrue(any(d.startswith("欢愉万相返还 10%") for d in settle))

        # 拉条 20% = rem_dist −= 2000：下一次【阿哈时刻】正好提前 2000/速度 的行动值
        def first_aha(r: dict) -> float:
            return [ev["av"] for ev in r["timeline"] if ev["type"] == "aha"][0]

        pulled = self._sim({**cfg, "ultAdvanceAha": 20})
        plain = self._sim({**cfg, "ultAdvanceAha": 0})
        self.assertAlmostEqual(first_aha(plain) - first_aha(pulled),
                               2000.0 / pulled["aha"]["speed"], places=6)

        # E6 首次终结技：拉条 100% → 【阿哈时刻】在同一行动值立刻接上，并 +100 笑点进池。
        # 旧参数 extra40 不再改行为。
        e6 = [{**team[0], "eidolon": 6}, *team[1:]]
        adv = self._sim({"team": e6, "useTech": False, "e1Wishpower": 7, "maxAV": 200,
                         "e6FirstUltMode": "extra40"})
        self.assertIn("E6 首次终结技：【阿哈时刻】拉条 100% + 笑点 +100",
                      self._labels(adv, "啊哈！宇宙笑点大爆炸")[0]["details"])
        self.assertNotIn("计入 40 笑点的额外回合",
                         " ".join(self._labels(adv, "啊哈！宇宙笑点大爆炸")[0]["details"]))
        ult_av = [ev["av"] for ev in adv["timeline"]
                  if ev["type"] == "ultimate" and ev["name"] == "星神★阿哈"][0]
        self.assertAlmostEqual([ev["av"] for ev in adv["timeline"]
                                if ev["type"] == "aha"][0], ult_av)
        self.assertGreaterEqual(adv["summary"]["punchlineGranted"], 100.0)

    # ---- 砂金•戏浪 ----

    def test_aventurine_sp_ult_speed_fervor_elation_skill_and_sandu(self) -> None:
        """终结技自提速 4 回合、热意阈值欢愉技、单欢愉/三赌牌局的速度口径。"""
        # ---- 终结技 +30% 速度（4 回合），【阿哈时刻】加权跟着变 ----
        team = [{"id": "1513", "err": 500}, {"id": "1503", "targetSlot": 3},
                {"id": "1502"}, {"id": "1501"}]
        res = self._sim({"team": team, "useTech": False, "maxAV": 120})
        self.assertEqual(["笑点 +6", "热意 +8", "自身速度 +30%（4 回合）",
                          "基础回能返还 +5 × (1+ERR)"],
                         self._labels(res, "胜局，凌越飓浪之上")[0]["details"])
        sp = next(u for u in res["units"] if u["id"] == "1513")
        self.assertAlmostEqual(sp["finalSpd"], 107 * 1.3 + 9)   # 148.1
        self.assertAlmostEqual(res["aha"]["speed"], 122.275)     # 开大前的加权
        # 提速后他是最快的欢愉，【阿哈时刻】速度动态跟着涨
        self.assertAlmostEqual(res["aha"]["finalSpeed"],
                               80 + 0.2 * 148.1 + 0.1 * 110 + 0.05 * 108 + 0.025 * 107)

        # 4 回合的落点：开局 50% 能量让第一动就能开大，开大后各行动间隔按 148.1 跑
        long = self._sim({"team": [{"id": "1513"}, {"id": "1503", "targetSlot": 3},
                                   {"id": "1502"}, {"id": "1501"}],
                          "useTech": False, "maxAV": 750})
        avs = self._action_avs(long, 0)
        self.assertGreaterEqual(len(avs), 4)
        self.assertAlmostEqual(avs[1] - avs[0], 10000 / 116, places=6)   # 开大前
        self.assertAlmostEqual(avs[2] - avs[1], 10000 / 148.1, places=6)  # 提速生效
        self.assertTrue(any("自身速度 +30%（4 回合）" in d
                            for ev in long["timeline"] for d in ev["details"]))

        # ---- 天赋 +1 / 行迹3【旧梦淘金】+2 热意；满 10 回合外放《举杯！敬炽烈一夏》----
        # 1513 压到 10 速：只有队友在打人，热意增量干净（1 / 2 / 一次攻击 3）
        slow = [{"id": "1513", "baseSpd": 1},
                {"id": "1309", "rotation": "basic"}, {"id": "1313", "rotation": "basic"}]
        res = self._sim({"team": slow, "useTech": False, "maxAV": 350})
        steps = self._fervor_steps(res)
        self.assertIn(1.0, steps)   # 天赋：队友攻击 +1
        self.assertIn(2.0, steps)   # 行迹3：再 +2
        self.assertIn(3.0, steps)   # 一次队友攻击同时给 1 + 2
        juban = self._labels(res, "举杯！敬炽烈一夏（回合外欢愉技）")
        self.assertEqual(1, len(juban))
        self.assertTrue(juban[0]["extra"])
        self.assertEqual(["好活当赏计入 20（不进笑点池）", "下一次【阿哈时刻】欢愉技升级为《All in！》",
                          "基础回能 5 × (1+ERR)"],
                         juban[0]["details"])
        self.assertAlmostEqual(juban[0]["res"]["fervor"], 10.0)  # 过 10 阈值立刻触发
        # 举杯记在好活当赏上，不往笑点池加 20
        juban_at = res["timeline"].index(juban[0])
        self.assertAlmostEqual(juban[0]["res"]["punchline"],
                               res["timeline"][juban_at - 1]["res"]["punchline"])
        sp = next(u for u in res["units"] if u["id"] == "1513")
        self.assertTrue(any(item["label"] == "举杯！敬炽烈一夏" and item["count"] == 20.0
                            for item in sp["mechanics"]["haohuo"]))
        allin = self._labels(res, "All in！敬炽烈一夏（欢愉技）")
        self.assertEqual(1, len(allin))
        self.assertIn("消耗全部热意", allin[0]["details"])
        self.assertIn("好活当赏计入 20（不进笑点池）", allin[0]["details"])
        # All in 记在好活当赏上，事件前后笑点池不变（不允许再 +20）
        allin_at = res["timeline"].index(allin[0])
        self.assertAlmostEqual(allin[0]["res"]["punchline"],
                               res["timeline"][allin_at - 1]["res"]["punchline"])

        # ---- 单欢愉（只有戏浪）：队友攻击 → 【阿哈时刻】固定速度 +25 ----
        solo = [{"id": "1513", "baseSpd": 1}, {"id": "1304", "rotation": "basic"}]
        res = self._sim({"team": solo, "useTech": False, "maxAV": 110})
        self.assertTrue(any("【纵享惊涛】触发" in n for n in res["notes"]))
        self.assertAlmostEqual(res["aha"]["flatBonus"], 25.0)
        self.assertAlmostEqual(res["aha"]["speed"], 82.0)        # 80 + 0.2×10
        self.assertAlmostEqual(res["aha"]["finalSpeed"], 107.0)  # 就是 +25
        self.assertFalse(res["resources"]["sanduActive"])
        self.assertAlmostEqual(next(u for u in res["units"]
                                    if u["id"] == "1304")["finalSpd"], 106.0)

        # ---- 三赌牌局（1513 + 1511 欢愉万相）：+25 固定速度 + 全队 15% ----
        duo = [{"id": "1511", "eidolon": 1, "e1Wishpower": 8, "targetSlot": 2},
               {"id": "1513"}, {"id": "1304", "rotation": "basic"}]
        res = self._sim({"team": duo, "useTech": False, "maxAV": 120})
        self.assertTrue(res["resources"]["sanduActive"])
        self.assertTrue(any("三赌牌局生效：全队速度 +15%" in n for n in res["notes"]))
        spd = {u["id"]: (u["initialSpd"], u["finalSpd"]) for u in res["units"]}
        self.assertAlmostEqual(spd["1513"][0], 116.0)                # 开局记账还没生效
        self.assertAlmostEqual(spd["1513"][1], 107 * 1.15 + 9)       # 132.05
        self.assertAlmostEqual(spd["1511"][1], (94 + 12) * 1.15 + 5)  # 126.9
        self.assertAlmostEqual(spd["1304"][1], 106 * 1.15)           # 121.9
        self.assertAlmostEqual(res["aha"]["flatBonus"], 25.0)
        self.assertAlmostEqual(res["aha"]["finalSpeed"],
                               106 + 0.2 * spd["1513"][1] + 0.1 * spd["1511"][1] + 25)

    # ---- 速度阈值反推 ----

    def test_threshold_formula(self) -> None:
        """需求速度 = 10000 × (动数 − 拉条%/100) ÷ 目标行动值。"""
        zero = call("aha-speed", "threshold", {"targetAV": 150, "actions": 2, "advancePct": 0})
        self.assertAlmostEqual(zero["requiredSpeed"], 10000 * 2 / 150, places=9)      # 133.33…
        self.assertAlmostEqual(zero["requiredSpeed"], 133.33, places=2)
        pulled = call("aha-speed", "threshold", {"targetAV": 150, "actions": 2, "advancePct": 40})
        self.assertAlmostEqual(pulled["requiredSpeed"], 10000 * 1.6 / 150, places=9)  # 106.66…
        self.assertAlmostEqual(pulled["requiredSpeed"], 106.67, places=2)
        # t 写法与 targetAV 写法同一条口径（150 AV 就是 0T）
        by_t = call("aha-speed", "threshold", {"t": 0, "actions": 2, "advancePct": 40})
        self.assertAlmostEqual(by_t["requiredSpeed"], pulled["requiredSpeed"], places=9)
        self.assertEqual(by_t["t"], 0)

    # ---- 0.20.1 欢愉口径 ----

    def test_spark_130_av_elation_skill_adds_no_punchline(self) -> None:
        """单火花、没人出招：第一次【阿哈时刻】消耗必须是 0，欢愉技不灌池。"""
        res = self._sim({
            "maxAV": 130, "useTech": False, "useAeonAha": False,
            "team": [{"id": "1501", "baseSpd": 1, "traceSpd": 0, "elation": True}],
        })
        spark = res["units"][0]
        self.assertEqual(0.0, res["summary"]["punchlineGranted"])
        self.assertEqual(0.0, res["summary"]["punchlineConsumed"])
        self.assertEqual(0.0, res["resources"]["punchline"])
        self.assertEqual(0, spark["actionCount"])
        self.assertEqual([], spark["mechanics"]["haohuo"])
        skills = [ev for ev in res["timeline"] if ev["type"] == "elation_skill"]
        self.assertEqual(["火花 的欢愉技"], [ev["label"] for ev in skills])
        self.assertEqual(["不产生笑点", "基础回能 5 × (1+ERR)"], skills[0]["details"])
        self.assertEqual(["消耗笑点 0"], self._labels(res, "【阿哈时刻】笑点结算")[0]["details"])
        self.assertNotIn("固定 +20 笑点", str(res["timeline"]))
        self.assertAlmostEqual(skills[0]["av"], 10000 / 80.2, places=4)

    def test_tech_and_e6_extra_aha_record_fixed_haohuo_without_pool(self) -> None:
        """秘技额外回合仍按 20 记账、不进池。E6 首大改为进池的 100 笑点，不再是额外回合 40。"""
        tech = self._sim({
            "maxAV": 1, "useTech": True, "useAeonAha": True,
            "team": [
                {"id": "1511"}, {"id": "1501"}, {"id": "8009"},
                {"id": "1503", "targetSlot": 1},
            ],
        })
        self.assertEqual(0.0, tech["summary"]["punchlineGranted"])
        self.assertEqual(0.0, tech["summary"]["punchlineConsumed"])
        self.assertEqual(0.0, tech["resources"]["punchline"])
        self.assertEqual(1, tech["aha"]["extraTriggerCount"])
        self.assertEqual(0, tech["aha"]["triggerCount"])
        self.assertFalse(any("笑点首达 40" in n for n in tech["notes"]))
        names = [ev["name"] for ev in tech["timeline"] if ev["type"] == "elation_skill"]
        self.assertEqual(["真珠", "开拓者•欢愉", "火花", "星神★阿哈"], names)
        aha = next(u for u in tech["units"] if u["id"] == "1511")
        self.assertEqual(1.0, aha["mechanics"]["wishpower"])
        for unit in tech["units"]:
            labels = [(item["label"], item["count"]) for item in unit["mechanics"]["haohuo"]]
            self.assertIn(("真珠秘技", 20.0), labels)
            self.assertIn(("阿哈时刻额外回合", 20.0), labels)

        extra = self._sim({
            "maxAV": 30, "useTech": False, "trace3Advance": False, "e1Wishpower": 8,
            "e6FirstUltMode": "extra40",
            "team": [{
                "id": "1511", "eidolon": 6, "baseSpd": 1, "traceSpd": 0, "initAdv": 0,
                "rotation": "basic", "lcBaseSpd": 0, "equipment": {"hasSigLc": False},
            }],
        })
        self.assertGreaterEqual(extra["summary"]["punchlineGranted"], 100.0)
        self.assertEqual(0, extra["aha"]["extraTriggerCount"])
        self.assertIn("E6 首次终结技：【阿哈时刻】拉条 100% + 笑点 +100",
                      self._labels(extra, "啊哈！宇宙笑点大爆炸")[0]["details"])
        self.assertNotIn("计入 40", str(extra["timeline"]))
        hits = [n for n in extra["notes"] if n.startswith("笑点首达 40")]
        self.assertEqual(1, len(hits))
        self.assertIn("全队暴伤 +40%", hits[0])

    def test_wolf_feiying_tech_extra_does_not_inflate_punchline(self) -> None:
        """欢愉技与绯英转移不凭空生成笑点，也不连触发两次首达 40。"""
        res = self._sim({
            "maxAV": 1, "useTech": True,
            "team": [{"id": "1511"}, {"id": "1506"}, {"id": "1505"}, {"id": "1501"}],
        })
        self.assertEqual(0.0, res["summary"]["punchlineGranted"])
        self.assertEqual(0.0, res["summary"]["punchlineConsumed"])
        self.assertFalse(any("笑点首达 40" in n for n in res["notes"]))
        wolf = next(u for u in res["units"] if u["id"] == "1506")
        fei = next(u for u in res["units"] if u["id"] == "1505")
        self.assertEqual(0, wolf["ultCount"])
        # 只有银狼自己的欢愉技 +15（队友欢愉技不给隐藏分）
        self.assertEqual(15.0, wolf["finalEnergy"])
        # 240 开局 + 20 秘技 + 5 欢愉技回能 + 5 附加好活当赏
        # + 20 阿哈额外回合好活当赏 + 阿哈/火花编号更小，各转移 10；银狼编号 999 不转移。
        self.assertEqual(75.0, fei["finalEnergy"])  # 310 - 240 + 5
        self.assertEqual(1.0, next(u for u in res["units"] if u["id"] == "1511")["mechanics"]["wishpower"])
        self.assertTrue(any(item["label"] == "阿哈时刻额外回合" and item["count"] == 20.0
                            for item in fei["mechanics"]["haohuo"]))
        self.assertNotIn("固定 +20 笑点", str(res["timeline"]))

    def test_punchline40_crit_note_and_reset_only_after_consuming_aha(self) -> None:
        """首达 40 的暴伤文案是 40%。额外回合也清标志，但池子仍 ≥40 时继续加笑点不会再触发。"""
        frozen = self._sim({
            "maxAV": 120, "useTech": False, "trace3Advance": False, "e1Wishpower": 0,
            "ahaSpdPct": -99, "sigLcPunchline": 100,
            "team": [
                {"id": "1511", "baseSpd": 200, "traceSpd": 0, "initAdv": 100, "rotation": "skill",
                 "equipment": {"hasSigLc": True}},
                {"id": "1502", "baseSpd": 180, "traceSpd": 0, "initAdv": 100, "err": 500,
                 "rotation": "skill"},
            ],
        })
        hits = [n for n in frozen["notes"] if n.startswith("笑点首达 40")]
        self.assertEqual(1, len(hits))
        self.assertIn("全队暴伤 +40%", hits[0])
        self.assertNotIn("24%", hits[0])
        self.assertEqual(0.0, frozen["summary"]["punchlineConsumed"])
        self.assertGreaterEqual(frozen["aha"]["extraTriggerCount"], 1)
        self.assertGreaterEqual(frozen["resources"]["punchline"], 40.0)
        self.assertNotIn("固定 +20 笑点", str(frozen["timeline"]))

        reset = self._sim({
            "maxAV": 160, "useTech": False, "trace3Advance": False, "e1Wishpower": 0,
            "sigLcPunchline": 100,
            "team": [{"id": "1511", "baseSpd": 200, "traceSpd": 0, "rotation": "skill",
                      "equipment": {"hasSigLc": True}}],
        })
        hits = [n for n in reset["notes"] if n.startswith("笑点首达 40")]
        self.assertEqual(2, len(hits))
        self.assertTrue(all("全队暴伤 +40%" in n for n in hits))
        self.assertGreaterEqual(reset["summary"]["punchlineConsumed"], 100.0)
        self.assertGreaterEqual(reset["aha"]["triggerCount"], 1)

    def test_yaoguang_mind_link_boosts_daji_only_while_ascended(self) -> None:
        """升格期间，持有好活当赏的攻击按 24% 记【大吉大利】；终结技带 +12 能量 +10 笑点。"""
        res = self._sim({
            "maxAV": 90, "useTech": False, "trace3Advance": False,
            "e1Wishpower": 8, "ahaAdvancePct": 100,
            "team": [
                {"id": "1511", "eidolon": 1, "baseSpd": 1, "traceSpd": 0, "lcBaseSpd": 0,
                 "rotation": "basic", "equipment": {"hasSigLc": False}},
                {"id": "1502", "baseSpd": 200, "traceSpd": 0, "err": 500,
                 "initAdv": 100, "rotation": "skill"},
            ],
        })
        ults = self._labels(res, "爻光终结技")
        self.assertTrue(ults)
        self.assertTrue(any("【大吉大利】倍率提高原倍率的 20%" in d
                            for ev in ults for d in ev["details"]))
        self.assertTrue(any("+12 固定能量 +10 笑点" in d
                            for ev in ults for d in ev["details"]))
        daji = self._labels(res, "大吉大利")
        self.assertTrue(daji)
        self.assertEqual(
            ["【大吉大利】欢愉伤害 24%（原倍率 20% × 1.20）",
             "固有行迹【欢愉万相★心灵感应】：倍率提高原倍率的 20%",
             "不视为 1 次攻击"],
            daji[0]["details"],
        )
        plain = self._sim({
            "maxAV": 40, "useTech": False, "useAeonAha": False,
            "team": [{"id": "1502", "baseSpd": 200, "traceSpd": 0, "err": 500,
                      "initAdv": 100, "rotation": "skill"}],
        })
        self.assertFalse(any("心灵感应" in d
                             for ev in plain["timeline"] for d in ev["details"]))
        self.assertFalse(self._labels(plain, "大吉大利"))

    def test_ascension_starts_when_aha_ults_and_lasts_three_of_his_turns(self) -> None:
        """升格跟着【欢愉万相】：开大置 3，阿哈自己每回合开始 -1，第三次行动开始时结束。"""
        slow = {
            "id": "1511", "eidolon": 1, "baseSpd": 100, "traceSpd": 0, "lcBaseSpd": 0,
            "rotation": "basic", "equipment": {"hasSigLc": False},
        }
        res = self._sim({
            "maxAV": 350, "useTech": False, "trace3Advance": False, "e1Wishpower": 8,
            "team": [slow],
        })
        self.assertTrue(any("星神★阿哈进入【欢愉万相】3 回合" in n for n in res["notes"]))
        self.assertTrue(any("固有行迹【欢愉万相★无中生有】1级" in n and "暴击率 +12%" in n
                            and "无视防御 30%" in n for n in res["notes"]))
        self.assertTrue(any("不另做强化" in n for n in res["notes"]))
        end = self._labels(res, "【欢愉万相】结束")
        self.assertEqual(1, len(end))
        self.assertAlmostEqual(end[0]["av"], self._action_avs(res, 0)[2])
        e2 = self._sim({
            "maxAV": 5, "useTech": False, "trace3Advance": False, "e1Wishpower": 8,
            "team": [{**slow, "eidolon": 2, "baseSpd": 1}],
        })
        self.assertTrue(any("固有行迹【欢愉万相★无中生有】2级" in n and "暴击率 +20%" in n
                            and "无视防御 60%" in n and "返还消耗笑点的 10%" in n
                            for n in e2["notes"]))

    def test_spark_rabbit_trick_is_a_note_only_after_aha_ults(self) -> None:
        """兔子戏法只在升格后写在欢愉技上，不额外加笑点。"""
        plain = self._sim({
            "maxAV": 130, "useTech": False, "useAeonAha": False,
            "team": [{"id": "1501", "baseSpd": 1, "traceSpd": 0}],
        })
        self.assertEqual(["不产生笑点", "基础回能 5 × (1+ERR)"],
                         [ev for ev in plain["timeline"] if ev["type"] == "elation_skill"][0]["details"])
        res = self._sim({
            "maxAV": 80, "useTech": False, "trace3Advance": False, "e1Wishpower": 8,
            "aeonAhaBaseSpd": 200, "aeonAhaLcBaseSpd": 0,
            "team": [
                {"id": "1511", "eidolon": 1, "baseSpd": 1, "traceSpd": 0, "lcBaseSpd": 0,
                 "rotation": "basic", "equipment": {"hasSigLc": False}},
                {"id": "1501", "baseSpd": 1, "traceSpd": 0},
            ],
        })
        skills = [ev for ev in res["timeline"] if ev["type"] == "elation_skill" and ev["name"] == "火花"]
        self.assertTrue(skills)
        self.assertEqual("不产生笑点", skills[0]["details"][0])
        self.assertTrue(any("兔子戏法" in d and "50%" in d for d in skills[0]["details"]))
        self.assertTrue(any("不加这份笑点" in n for n in res["notes"]))
        self.assertEqual(0.0, res["summary"]["punchlineGranted"])

    def test_trailblazer_halo_casts_own_skill_before_aha(self) -> None:
        """升格后，开拓者终结技打中阿哈时先放自己的欢愉技。"""
        res = self._sim({
            "maxAV": 20, "useTech": False, "trace3Advance": False, "e1Wishpower": 8,
            "team": [
                {"id": "1511", "eidolon": 1, "baseSpd": 1, "traceSpd": 0, "lcBaseSpd": 0,
                 "rotation": "basic", "equipment": {"hasSigLc": False}},
                {"id": "8009", "err": 500, "initAdv": 100, "baseSpd": 200, "traceSpd": 0,
                 "targetSlot": 0},
            ],
        })
        skills = [ev for ev in res["timeline"] if ev["type"] == "elation_skill"]
        self.assertGreaterEqual(len(skills), 2)
        self.assertEqual(["开拓者•欢愉", "星神★阿哈"], [ev["name"] for ev in skills[:2]])
        self.assertTrue(any("主角光环" in d for ev in res["timeline"] for d in ev["details"]))
        self.assertEqual(8.0, res["summary"]["punchlineGranted"])

    def test_pearl_keeps_ten_percent_of_extra_turn_haohuo_only_while_ascended(self) -> None:
        """跃然纸上：升格后额外回合结束，该次好活当赏收到 10%。笑点 10% 不重复加。"""
        pearl = {"id": "1503", "initAdv": 100, "err": 500, "targetSlot": 2}
        res = self._sim({
            "maxAV": 20, "useTech": False, "trace3Advance": False, "e1Wishpower": 8,
            "team": [
                {"id": "1511", "eidolon": 1, "baseSpd": 1, "traceSpd": 0, "lcBaseSpd": 0,
                 "rotation": "basic", "equipment": {"hasSigLc": False}},
                pearl,
                {"id": "1501", "baseSpd": 1, "traceSpd": 0},
                {"id": "1502", "baseSpd": 1, "traceSpd": 0},
            ],
        })
        spark = next(u for u in res["units"] if u["id"] == "1501")
        extra = [item for item in spark["mechanics"]["haohuo"]
                 if item["label"] == "真珠终结技·【美学底本】额外回合"]
        self.assertEqual([3.0], [item["count"] for item in extra])
        self.assertTrue(any(item["label"] == "真珠终结技" and item["count"] == 20.0
                            for item in spark["mechanics"]["haohuo"]))
        note = self._labels(res, "欢愉万相★跃然纸上")[0]
        self.assertIn("额外回合结束保留该次好活当赏的 10%（3.00）", note["details"])
        self.assertIn("回收 60 笑点（欢愉万相返还 10%）",
                      self._labels(res, "额外回合笑点结算")[0]["details"])

    def test_pearl_haohuo_cap_is_75_only_after_ascension(self) -> None:
        """升格后新获得的好活当赏把真珠自己夹到 75，队友不夹。"""
        res = self._sim({
            "maxAV": 80, "useTech": False, "trace3Advance": False, "e1Wishpower": 8,
            "aeonAhaBaseSpd": 200, "aeonAhaLcBaseSpd": 0,
            "team": [
                {"id": "1511", "eidolon": 6, "baseSpd": 1, "traceSpd": 0, "lcBaseSpd": 0,
                 "rotation": "basic", "equipment": {"hasSigLc": False}},
                {"id": "1503", "baseSpd": 1, "traceSpd": 0, "targetSlot": 2},
                {"id": "1501", "baseSpd": 1, "traceSpd": 0},
            ],
        })
        pearl = next(u for u in res["units"] if u["id"] == "1503")
        spark = next(u for u in res["units"] if u["id"] == "1501")
        self.assertAlmostEqual(sum(item["count"] for item in pearl["mechanics"]["haohuo"]), 75.0)
        # E6 首次拉条现保留：0 AV 消耗 100，后续自然阿哈再消耗返还的 10。
        self.assertAlmostEqual(sum(item["count"] for item in spark["mechanics"]["haohuo"]), 110.0)

    def test_wolf_hidden_score_gains_twenty_percent_of_haohuo_while_ascended(self) -> None:
        """全息幻象：升格后好活当赏的 20% 进隐藏分。没升格时不加。"""
        wolf_team = [
            {"id": "1511", "eidolon": 1, "baseSpd": 1, "traceSpd": 0, "lcBaseSpd": 0,
             "rotation": "basic", "equipment": {"hasSigLc": False}},
            {"id": "1503", "initAdv": 100, "err": 0, "baseSpd": 200, "traceSpd": 0,
             "targetSlot": 0},
            {"id": "1506", "baseSpd": 1, "traceSpd": 0},
        ]
        res = self._sim({
            "maxAV": 5, "useTech": False, "trace3Advance": False, "e1Wishpower": 8,
            "team": wolf_team,
        })
        wolf = next(u for u in res["units"] if u["id"] == "1506")
        self.assertAlmostEqual(wolf["finalEnergy"], 3.0)
        self.assertAlmostEqual(wolf["mechanics"]["hiddenOverflow"], 0.0)
        self.assertEqual(0, wolf["ultCount"])
        self.assertTrue(any("好活当赏 15 的 20% → 隐藏分 +3.00" in d
                            for ev in res["timeline"] for d in ev["details"]))
        plain = self._sim({
            "maxAV": 5, "useTech": False, "useAeonAha": False,
            "team": wolf_team[1:],
        })
        wolf = next(u for u in plain["units"] if u["id"] == "1506")
        self.assertEqual(0.0, wolf["finalEnergy"])
        self.assertFalse(any("全息幻象" in ev["label"] for ev in plain["timeline"]))

    def test_feiying_restores_overflow_energy_without_retriggering_talent(self) -> None:
        """书中折花：升格后能量可溢出最多 60，开大后把溢出写回来，不走好活当赏回能。"""
        team = [
            {"id": "1511", "eidolon": 1, "baseSpd": 1, "traceSpd": 0, "lcBaseSpd": 0,
             "rotation": "basic", "equipment": {"hasSigLc": False}},
            {"id": "1503", "initAdv": 100, "err": 0, "baseSpd": 200, "traceSpd": 0,
             "targetSlot": 0},
            {"id": "1505", "baseSpd": 1, "traceSpd": 0},
        ]
        res = self._sim({
            "maxAV": 5, "useTech": False, "trace3Advance": False, "e1Wishpower": 8,
            "feiyingHaohuoEnergyMode": "flat", "feiyingHaohuoEnergy": 500,
            "team": team,
        })
        fei = next(u for u in res["units"] if u["id"] == "1505")
        note = self._labels(res, "欢愉万相★书中折花")
        self.assertTrue(note)
        self.assertTrue(any("溢出能量 60.00" in d for ev in note for d in ev["details"]))
        self.assertTrue(any("不触发天赋好活当赏" in d for ev in note for d in ev["details"]))
        self.assertAlmostEqual(fei["finalEnergy"], 70.0)  # 540 - 2×240 + 2×5
        self.assertGreaterEqual(fei["ultCount"], 1)

    def test_aha_basic_gains_one_wishpower(self) -> None:
        """星神★阿哈普攻是 +1 愿力，不是把标准能量 +20 灌进愿力。"""
        res = self._sim({
            "maxAV": 5, "useTech": False, "trace3Advance": False, "e1Wishpower": 0,
            "team": [{
                "id": "1511", "baseSpd": 1, "traceSpd": 0, "initAdv": 100,
                "rotation": "basic", "lcBaseSpd": 0, "equipment": {"hasSigLc": False},
            }],
        })
        basic = [ev for ev in res["timeline"] if ev["type"] == "basic"]
        self.assertEqual(1, len(basic))
        self.assertEqual(["愿力 +1"], basic[0]["details"])
        unit = res["units"][0]
        self.assertEqual(1.0, unit["mechanics"]["wishpower"])
        self.assertEqual(1.0, unit["mechanics"]["wishpowerTotal"])
        self.assertEqual(0, unit["ultCount"])
        self.assertNotIn("基础回能 20", str(basic))

    def test_let_there_be_laughter_when_nobody_can_cast(self) -> None:
        """队里没有任何可施放欢愉技的角色时走保底，不伪造欢愉技、不加笑点。"""
        res = self._sim({
            "maxAV": 130, "useTech": False, "useAeonAha": False,
            "team": [{"id": "1304", "baseSpd": 1, "traceSpd": 0}],
        })
        laugh = self._labels(res, "Let There Be Laughter")
        self.assertEqual(1, len(laugh))
        self.assertEqual(
            ["场上没有可施放欢愉技的角色", "保底效果（文档未给数值，不产笑点、不改笑点池）"],
            laugh[0]["details"],
        )
        self.assertFalse(any(ev["type"] == "elation_skill" for ev in res["timeline"]))
        self.assertEqual(0.0, res["summary"]["punchlineGranted"])
        self.assertEqual(0.0, res["summary"]["punchlineConsumed"])
        self.assertEqual([], res["units"][0]["mechanics"]["haohuo"])
        self.assertNotIn("固定 +20 笑点", str(res["timeline"]))

    def test_aeon_aha_elation_skill_casts_last(self) -> None:
        """星神★阿哈无视站位，欢愉技始终最后放。"""
        res = self._sim({
            "maxAV": 60, "useTech": False, "trace3Advance": False, "e1Wishpower": 0,
            "aeonAhaBaseSpd": 200, "aeonAhaLcBaseSpd": 0,
            "team": [
                {"id": "1511", "baseSpd": 1, "traceSpd": 0, "lcBaseSpd": 0,
                 "equipment": {"hasSigLc": False}},
                {"id": "1501", "baseSpd": 1, "traceSpd": 0},
                {"id": "1503", "baseSpd": 1, "traceSpd": 0, "targetSlot": 1},
            ],
        })
        names = [ev["name"] for ev in res["timeline"] if ev["type"] == "elation_skill"]
        self.assertEqual(["真珠", "火花", "星神★阿哈"], names)

    def test_god_joy_does_not_advance_without_elation_degree(self) -> None:
        """神的瞬息欢愉只记 +6% 速度；没模拟欢愉度，不开局 40% 拉条。"""
        res = self._sim({
            "maxAV": 100, "useTech": False, "useAeonAha": False,
            "team": [{"id": "1304", "equipment": {"godJoy": True}}],
        })
        note = self._labels(res, "神的瞬息欢愉")[0]
        self.assertEqual(
            ["速度 +6% 已计入", "开局 40% 拉条需要欢愉度 ≥ 40%（本工具不模拟欢愉度，因此不拉条）"],
            note["details"],
        )
        unit = res["units"][0]
        self.assertAlmostEqual(unit["initialSpd"], 106 * 1.06)
        first = self._action_avs(res, 0)[0]
        self.assertAlmostEqual(first, 10000 / (106 * 1.06))
        self.assertGreater(first, 6000 / (106 * 1.06))

    def test_trailblazer_forced_skill_records_20_and_otherwise_advances(self) -> None:
        """开拓者终结技：目标有欢愉技则计入 20 且不进池；没有则只拉条 50%。"""
        forced = self._sim({
            "maxAV": 20, "useTech": False, "useAeonAha": False,
            "team": [
                {"id": "8009", "err": 500, "initAdv": 100, "baseSpd": 200, "traceSpd": 0,
                 "targetSlot": 1},
                {"id": "1501", "baseSpd": 1, "traceSpd": 0},
            ],
        })
        note = self._labels(forced, "开拓者•欢愉终结技")[0]
        skill = [ev for ev in forced["timeline"] if ev["type"] == "elation_skill"]
        self.assertEqual(1, len(skill))
        self.assertEqual(["不产生笑点", "基础回能 5 × (1+ERR)"], skill[0]["details"])
        # 终结技自己的 +5 是文档来源，发生在备注快照之后、欢愉技之前
        self.assertAlmostEqual(skill[0]["res"]["punchline"], note["res"]["punchline"] + 5.0)
        self.assertEqual(8.0, forced["summary"]["punchlineGranted"])
        self.assertEqual(0.0, forced["summary"]["punchlineConsumed"])
        spark = next(u for u in forced["units"] if u["id"] == "1501")
        self.assertTrue(any(item["label"] == "开拓者终结技·计入笑点" and item["count"] == 20.0
                            for item in spark["mechanics"]["haohuo"]))
        self.assertNotIn("固定 +20 笑点", str(forced["timeline"]))

        pulled = self._sim({
            "maxAV": 40, "useTech": False, "useAeonAha": False,
            "team": [
                {"id": "8009", "err": 500, "initAdv": 100, "baseSpd": 200, "traceSpd": 0,
                 "targetSlot": 1},
                {"id": "1304", "baseSpd": 100, "traceSpd": 0},
            ],
        })
        note = self._labels(pulled, "开拓者•欢愉终结技")[0]
        self.assertIn("砂金(存护) 拉条 50%", note["details"])
        self.assertFalse(any(ev["type"] == "elation_skill" for ev in pulled["timeline"]))
        self.assertTrue(all(item["label"] != "开拓者终结技·计入笑点"
                            for u in pulled["units"] for item in u["mechanics"]["haohuo"]))
        self.assertEqual(8.0, pulled["summary"]["punchlineGranted"])

    # ---- 0.20.2 能量修复 ----

    def test_standard_units_start_at_half_energy_special_stay_zero(self) -> None:
        """标准能量角色进战 = 上限 50%；愿力/隐藏分等特殊资源仍从 0 开始。"""
        res = self._sim({
            "maxAV": 1, "useTech": False,
            "team": [{"id": "1503"}, {"id": "1513"}, {"id": "1505"}, {"id": "1511"}],
        })
        by_id = {u["id"]: u for u in res["units"]}
        self.assertAlmostEqual(by_id["1503"]["finalEnergy"], 90.0)   # 180 的 50%
        self.assertAlmostEqual(by_id["1513"]["finalEnergy"], 65.0)   # 130 的 50%
        self.assertAlmostEqual(by_id["1505"]["initialEnergy"], 240.0)  # 480 的 50%
        self.assertAlmostEqual(by_id["1505"]["finalEnergy"], 5.0)  # 进战即可开大
        self.assertAlmostEqual(by_id["1511"]["finalEnergy"], 0.0)    # 愿力
        res = self._sim({"maxAV": 1, "useTech": False, "team": [{"id": "1506"}]})
        self.assertAlmostEqual(res["units"][0]["finalEnergy"], 0.0)  # 隐藏分

    def test_elation_skill_grants_five_times_err_except_aha(self) -> None:
        """欢愉技基础回能 5 × ERR（阿哈只 +1 愿力）。"""
        res = self._sim({
            "maxAV": 130, "useTech": False, "useAeonAha": True,
            "aeonAhaBaseSpd": 200, "aeonAhaLcBaseSpd": 0,
            "team": [{"id": "1503", "baseSpd": 1, "traceSpd": 0, "err": 100}],
        })
        skill = [ev for ev in res["timeline"] if ev["type"] == "elation_skill"][0]
        self.assertIn("基础回能 5 × (1+ERR)", skill["details"])
        # 开局 90 + 两次欢愉技各 10（5 × 2.0，err 100）= 110
        self.assertAlmostEqual(next(u for u in res["units"]
                                    if u["id"] == "1503")["finalEnergy"], 110.0)

    def test_pearl_enhanced_basic_grants_thirty(self) -> None:
        """真珠强化普攻基础回能 30（修复前 20）。"""
        res = self._sim({
            "maxAV": 1, "useTech": True, "useAeonAha": False,
            "team": [{"id": "1503", "baseSpd": 1, "traceSpd": 0, "initAdv": 100}],
        })
        ev = self._labels(res, "行笔，幻造星月")[0]
        self.assertIn("基础回能 30 × (1+ERR)", ev["details"])

    def test_spark_skill_turn_is_forty_times_err(self) -> None:
        """火花战技回合：战技 0 能量、同回合强化普攻 40 × ERR（修复前 30）。"""
        res = self._sim({
            "maxAV": 1, "useTech": False, "useAeonAha": False,
            "team": [{"id": "1501", "baseSpd": 1, "traceSpd": 0, "initAdv": 100, "err": 100}],
        })
        skill = [ev for ev in res["timeline"] if ev["type"] == "skill"][0]
        self.assertIn("战技本身 0 能量", skill["details"])
        extra = self._labels(res, "百花齐放，胜者独享！")[0]
        self.assertIn("基础回能 40 × (1+ERR)", extra["details"])
        # 开局 80 + 40×2 = 160 满能量立刻开大，返还 5×2 = 10
        self.assertAlmostEqual(res["units"][0]["finalEnergy"], 10.0)

    def test_feiying_skill_is_thirty_times_err_and_standard(self) -> None:
        """绯英按普通能量角色：战技 30 × ERR、吃 ERR、终结技返还 5 × ERR。"""
        res = self._sim({
            "maxAV": 1, "useTech": False, "useAeonAha": False,
            "team": [{"id": "1505", "baseSpd": 1, "traceSpd": 0, "initAdv": 100, "err": 100}],
        })
        fei = res["units"][0]
        self.assertEqual(fei["energyType"], "standard")
        skill = [ev for ev in res["timeline"] if ev["type"] == "skill"][0]
        self.assertIn("基础回能 30 × (1+ERR)", skill["details"])
        self.assertAlmostEqual(fei["finalEnergy"], 70.0)  # 240 - 240 + 5×2 + 30×2

    def test_feiying_haohuo_energy_capped_at_hundred(self) -> None:
        """好活当赏转能量单次不超过 100。"""
        res = self._sim({
            "maxAV": 1, "useTech": True, "useAeonAha": False,
            "team": [{"id": "1503", "baseSpd": 1, "traceSpd": 0, "initAdv": 100},
                     {"id": "1505", "baseSpd": 1, "traceSpd": 0}],
        })
        notes = [ev for ev in res["timeline"] if ev["label"].startswith("绯英回能·好活当赏")]
        self.assertTrue(notes)
        for ev in notes:
            self.assertLessEqual(ev["res"]["energyRequested"], 100.0)

    def test_wolf_only_gains_hidden_from_own_elation_skill(self) -> None:
        """银狼只吃自己的欢愉技 +15；队友欢愉技不给隐藏分。"""
        res = self._sim({
            "maxAV": 60, "useTech": False, "useAeonAha": True,
            "aeonAhaBaseSpd": 200, "aeonAhaLcBaseSpd": 0,
            "team": [{"id": "1506", "baseSpd": 1, "traceSpd": 0},
                     {"id": "1503", "baseSpd": 1, "traceSpd": 0}],
        })
        wolf = next(u for u in res["units"] if u["id"] == "1506")
        self.assertAlmostEqual(wolf["finalEnergy"], 15.0)
        self.assertNotIn(30.0, [ev["res"]["energy"] for ev in res["timeline"]
                                if ev["res"]["energy"] is not None])

    def test_wolf_base_overflow_and_invincible_blocks_second_ult(self) -> None:
        """基础天赋可溢出 240（合计 300）；【无敌玩家】期间不能再开大。"""
        res = self._sim({
            "maxAV": 1, "useTech": True, "useAeonAha": False,
            "team": [{"id": "1503", "baseSpd": 1, "traceSpd": 0, "initAdv": 100,
                      "targetSlot": 1},
                     {"id": "1506", "baseSpd": 1, "traceSpd": 0}],
        })
        wolf = next(u for u in res["units"] if u["id"] == "1506")
        self.assertLessEqual(wolf["finalEnergy"] + wolf["mechanics"]["hiddenOverflow"], 300.0)
        inv = self._sim({
            "maxAV": 250, "useTech": False, "useAeonAha": False, "sigLcPunchline": 100,
            "team": [{"id": "1511", "baseSpd": 200, "traceSpd": 0, "rotation": "skill",
                      "equipment": {"hasSigLc": True}},
                     {"id": "1506", "baseSpd": 200, "traceSpd": 0, "initAdv": 100,
                      "eidolon": 1}],
        })
        exits = [ev["av"] for ev in inv["timeline"] if "退出【无敌玩家】" in ev["label"]]
        self.assertTrue(exits)
        first_exit = exits[0]
        ults_in_window = [ev for ev in inv["timeline"]
                          if ev["type"] == "ultimate" and ev["name"] == "银狼LV.999"
                          and ev["av"] <= first_exit + 1e-9]
        self.assertEqual(1, len(ults_in_window))  # 无敌期间只有开大那一次
        basics = [ev for ev in inv["timeline"]
                  if ev["type"] == "enhanced_basic" and ev["name"] == "银狼LV.999"
                  and ev["av"] <= first_exit + 1e-9]
        self.assertEqual(3, len(basics))

    def test_robin_does_not_act_during_concerto(self) -> None:
        """【协奏】期间知更鸟本体不行动，倒计时归零后立即行动。"""
        res = self._sim({
            "maxAV": 250, "useTech": False, "useAeonAha": False,
            "team": [{"id": "1309", "baseSpd": 200, "traceSpd": 0, "initAdv": 100, "err": 500},
                     {"id": "1304", "baseSpd": 1, "traceSpd": 0}],
        })
        avs = self._action_avs(res, 0)
        self.assertAlmostEqual(avs[0], 0.0)          # 开局立即行动开大
        self.assertAlmostEqual(avs[1], 10000 / 90)   # 协奏倒计时归零后才再动
        self.assertFalse(any(0.0 < ev["av"] < 10000 / 90
                             for ev in res["timeline"]
                             if ev["slot"] == 0 and not ev["extra"]
                             and ev["type"] in ("basic", "skill", "enhanced_basic")))

    def test_robin_talent_and_skill_energy(self) -> None:
        """知更鸟天赋：我方每次攻击 +2（E2 +3）；战技 35（30 + 行迹 5）。"""
        res = self._sim({
            "maxAV": 60, "useTech": False, "useAeonAha": False,
            "team": [{"id": "1309", "baseSpd": 1, "traceSpd": 0, "initAdv": 100},
                     {"id": "1304", "baseSpd": 200, "traceSpd": 0}],
        })
        skill = [ev for ev in res["timeline"]
                 if ev["type"] == "skill" and ev["name"] == "知更鸟"][0]
        self.assertIn("基础回能 35（战技 30 + 行迹【模进乐段】5）× (1+ERR)", skill["details"])
        robin = next(u for u in res["units"] if u["id"] == "1309")
        self.assertGreater(robin["finalEnergy"], 0.0)

    def test_sunday_battle_start_and_e4_energy(self) -> None:
        """星期日行迹【崇高拂尘】开局 +25；E4 回合开始 +8。"""
        res = self._sim({
            "maxAV": 1, "useTech": False, "useAeonAha": False,
            "team": [{"id": "1313", "baseSpd": 1, "traceSpd": 0, "eidolon": 4}],
        })
        self.assertTrue(any(ev["label"] == "行迹【崇高拂尘】" for ev in res["timeline"]))
        self.assertAlmostEqual(res["units"][0]["finalEnergy"], 65.0 + 25.0)
        res = self._sim({
            "maxAV": 130, "useTech": False, "useAeonAha": False,
            "team": [{"id": "1313", "baseSpd": 200, "traceSpd": 0, "eidolon": 4}],
        })
        self.assertTrue(any(ev["label"] == "E4 雕塑的卷首语" for ev in res["timeline"]))

    def test_aventurine_e4_adds_three_fua_segments(self) -> None:
        """存护砂金 E4：追击 7 段 → 10 段（回能同步 +3）。"""
        def fua_label(eidolon: int) -> str:
            res = self._sim({
                "maxAV": 200, "useTech": False, "useAeonAha": False,
                "team": [{"id": "1304", "baseSpd": 1, "traceSpd": 0, "eidolon": eidolon},
                         {"id": "1501", "baseSpd": 200, "traceSpd": 0, "rotation": "basic"},
                         {"id": "1502", "baseSpd": 200, "traceSpd": 0, "rotation": "basic"}],
            })
            fuas = [ev for ev in res["timeline"]
                    if ev["type"] == "fua" and "砂金" in ev["label"] and "段追加" in ev["label"]]
            return fuas[0]["label"] if fuas else ""
        self.assertIn("7 段", fua_label(0))
        self.assertIn("10 段", fua_label(4))

    def test_pearl_lightcone_grants_ten_energy(self) -> None:
        """真珠专武：施放欢愉技固定 +10 能量（默认不勾）。"""
        def pearl_energy(equip: dict) -> float:
            res = self._sim({
                "maxAV": 130, "useTech": False, "useAeonAha": True,
                "aeonAhaBaseSpd": 200, "aeonAhaLcBaseSpd": 0,
                "team": [{"id": "1503", "baseSpd": 1, "traceSpd": 0, "equipment": equip}],
            })
            return next(u for u in res["units"] if u["id"] == "1503")["finalEnergy"]
        self.assertAlmostEqual(pearl_energy({}), 100.0)   # 开局 90 + 两次欢愉技各 +5
        self.assertAlmostEqual(pearl_energy({"hasPearlLc": True}), 120.0)  # 每次再固定 +10

    def test_yao_lightcone_err_and_wave_energy(self) -> None:
        """《当她决定看见》：ERR +12%、每波次固定 +15（本工具=战斗开始一次）。"""
        plain = self._sim({"maxAV": 1, "useTech": False, "useAeonAha": False,
                           "team": [{"id": "1502", "baseSpd": 1, "traceSpd": 0}]})
        lc = self._sim({"maxAV": 1, "useTech": False, "useAeonAha": False,
                        "team": [{"id": "1502", "baseSpd": 1, "traceSpd": 0,
                                  "equipment": {"hasYaoLc": True}}]})
        self.assertAlmostEqual(plain["units"][0]["err"], 0.0)
        self.assertAlmostEqual(lc["units"][0]["err"], 12.0)
        self.assertAlmostEqual(lc["units"][0]["finalEnergy"], 90.0 + 15.0)

    def test_feiying_lightcone_err_bonus(self) -> None:
        """绯英专武：ERR +10% + 上限超 120 部分每 10 点 +0.3%（480 上限共 +20.8%）。"""
        res = self._sim({"maxAV": 1, "useTech": False, "useAeonAha": False,
                         "team": [{"id": "1505", "baseSpd": 1, "traceSpd": 0,
                                   "equipment": {"hasFeiyLc": True}}]})
        self.assertAlmostEqual(res["units"][0]["err"], 20.8)

    def test_feiying_e6_first_ult_grants_120(self) -> None:
        """绯英 E6：首次终结技固定 +120 能量。"""
        res = self._sim({
            "maxAV": 1, "useTech": False, "useAeonAha": False,
            "team": [{"id": "1505", "baseSpd": 1, "traceSpd": 0, "initAdv": 100,
                      "err": 700, "eidolon": 6}],
        })
        self.assertTrue(any(ev["label"] == "E6 少女，见浮生入梦" for ev in res["timeline"]))

    def test_aventurine_sp_fervor_cap_is_thirty_at_e0(self) -> None:
        """砂金•戏浪【热意】E0 上限 30（修复前写死 50）。"""
        res = self._sim({
            "maxAV": 350, "useTech": False, "useAeonAha": False,
            "team": [{"id": "1513", "baseSpd": 1, "traceSpd": 0},
                     {"id": "1304", "baseSpd": 200, "traceSpd": 0, "rotation": "basic"},
                     {"id": "1309", "baseSpd": 200, "traceSpd": 0, "rotation": "basic"}],
        })
        peaks = [ev["res"]["fervor"] for ev in res["timeline"]
                 if ev["res"]["fervor"] is not None]
        self.assertTrue(peaks)
        self.assertLessEqual(max(peaks), 30.0)

    def test_aventurine_technique_triggers_aha_trace(self) -> None:
        """存护砂金【热手】开局护盾触发阿哈行迹2（+1 愿力）。"""
        res = self._sim({
            "maxAV": 1, "useTech": False, "useAeonAha": False,
            "team": [{"id": "1511"}, {"id": "1304"}],
        })
        self.assertTrue(any("砂金【热手】开局护盾 → 愿力 +1" in d
                            for ev in res["timeline"] for d in ev["details"]))

    def test_web_port_matches(self) -> None:
        """Python（api.py）与 JS（web_api.js）必须逐字段一致 —— 界面预设同一批数字。

        这是「工具箱算的和网页版算的一不一样」的那道闸：speed-plan 有
        tests/check_web_port.mjs，aha-speed 用 tools/check_aha_port.mjs。
        没有 node 就跳过（和 herta 的网页版对拍同一条规矩）。
        """
        node = shutil.which("node")
        if not node:
            self.skipTest("没有 node")
        import subprocess

        proc = subprocess.run(
            [node, str(ROOT / "tools" / "check_aha_port.mjs"), sys.executable],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        self.assertEqual(proc.returncode, 0, (proc.stdout or "") + (proc.stderr or ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
