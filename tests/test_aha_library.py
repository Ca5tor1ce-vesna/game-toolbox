"""角色存档共享与队伍快照；测试夹具沿用隔离 userdata。"""
import copy
import unittest

from test_toolbox import call


class TestAhaLibrary(unittest.TestCase):
    def setUp(self):
        self.cid = "1502"
        self.config = {
            "eidolon": 2, "superimpose": 1,
            "relic": {"speedBoots": True, "substatSpeed": 33, "ornamentIds": ["308"]},
            "simulation": {"firstUltAction": 3},
            "aha": {"err": 19.4, "initialEnergy": 80, "rotation": "basic"},
        }
        call("speed-plan", "save_preset", {"characterId": self.cid, "config": self.config})
        self.created = []

    def tearDown(self):
        call("speed-plan", "delete_preset", {"characterId": self.cid})
        for key in self.created:
            call("aha-speed", "delete_team", {"id": key})

    def test_shared_build_uses_original_calculation(self):
        resolved = call("aha-speed", "resolve_build", {"characterId": self.cid})
        expected = call("speed-plan", "plan", {**self.config, "characterId": self.cid})
        self.assertEqual(resolved["result"], expected)
        library = call("aha-speed", "library")
        self.assertEqual(library["presets"][self.cid]["config"], self.config)
        self.assertTrue(next(c for c in library["characters"] if c["id"] == self.cid)["icon"])

    def test_missing_or_unsupported_build_has_readable_error(self):
        with self.assertRaisesRegex(ValueError, "尚未保存"):
            call("aha-speed", "resolve_build", {"characterId": "missing"})
        call("speed-plan", "save_preset", {"characterId": "__custom__", "config": {}})
        try:
            with self.assertRaisesRegex(ValueError, "尚未支持"):
                call("aha-speed", "resolve_build", {"characterId": "__custom__"})
        finally:
            call("speed-plan", "delete_preset", {"characterId": "__custom__"})

    def test_team_snapshot_roundtrip_overwrite_and_delete(self):
        payload = {"name": "我的队伍", "team": [{"id": self.cid, "err": 19.4, "initialEnergy": 80}], "config": {"maxAV": 250, "useTech": False}}
        original = copy.deepcopy(payload)
        result = call("aha-speed", "save_team", payload)
        key = result["id"]
        self.created.append(key)
        saved = call("aha-speed", "library")["teams"][key]
        self.assertEqual(saved["team"], original["team"])
        self.assertEqual(saved["config"], original["config"])
        self.assertEqual(call("aha-speed", "simulate", {**saved["config"], "team": saved["team"]}),
                         call("aha-speed", "simulate", {**original["config"], "team": original["team"]}))
        call("aha-speed", "save_team", {**payload, "id": key, "name": "修改后的队伍"})
        self.assertEqual(call("aha-speed", "library")["teams"][key]["name"], "修改后的队伍")
        call("aha-speed", "delete_team", {"id": key})
        self.created.remove(key)
        self.assertNotIn(key, call("aha-speed", "library")["teams"])
        self.assertEqual(call("speed-plan", "presets")["presets"][self.cid]["config"], self.config)

    def test_invalid_save_does_not_change_existing_data(self):
        before = call("aha-speed", "library")["teams"]
        for invalid in ({"name": "", "team": [{"id": self.cid}], "config": {}},
                        {"name": "空队", "team": [], "config": {}},
                        {"name": "未知角色", "team": [{"id": "bad"}], "config": {}},
                        {"name": "非法速度", "team": [{"id": self.cid, "baseSpd": "bad"}], "config": {}}):
            with self.assertRaises(ValueError):
                call("aha-speed", "save_team", invalid)
        self.assertEqual(call("aha-speed", "library")["teams"], before)


if __name__ == "__main__":
    unittest.main()
