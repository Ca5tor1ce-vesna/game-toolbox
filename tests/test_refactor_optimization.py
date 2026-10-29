import sys
import unittest
from unittest.mock import patch

from test_toolbox import call
from core import feature_api


class TestSpeedTableReuse(unittest.TestCase):
    def test_dynamic_tables_reuse_equal_action_windows(self):
        catalog = call("speed-plan", "catalog")
        messenger = next(item for item in catalog["fourPieceSets"] if item["name"] == "骇域漫游的信使")
        payload = {"characterId": "1005", "relic": {"speedBoots": False, "fourPieceId": messenger["id"], "ultTargetsAlly": True, "fourPieceUlts": 2}}
        handler = feature_api.HANDLERS[("honkai-star-rail", "speed-plan")]["plan"]
        module = sys.modules[handler.__module__]
        original = module._required_speed
        with patch.object(module, "_required_speed", wraps=original) as measured:
            result = call("speed-plan", "plan", payload)
        cells = [(row["actions"], cell["totalAV"]) for table in result["tables"] for row in table["rows"] for cell in row["cells"]]
        self.assertLess(len(set(cells)), len(cells))
        self.assertLessEqual(measured.call_count, len(set(cells)) + 10)
        values = {}
        for table in result["tables"]:
            for row in table["rows"]:
                for cell in row["cells"]:
                    key = (row["actions"], cell["totalAV"])
                    actual = (cell["speed"], cell["reachable"])
                    if key in values:
                        self.assertEqual(values[key], actual)
                    values[key] = actual

    def test_recommend_computes_each_relic_contribution_once(self):
        catalog = call("speed-plan", "catalog")
        handler = feature_api.HANDLERS[("honkai-star-rail", "speed-plan")]["recommend"]
        module = sys.modules[handler.__module__]
        with patch.object(module, "_set_contribution", wraps=module._set_contribution) as measured:
            result = call("speed-plan", "recommend", {"characterId": "1005"})
        self.assertTrue(result["results"])
        self.assertLessEqual(measured.call_count, len(catalog["fourPieceSets"]) + len(catalog["ornamentSets"]) + 2)


class TestGachaDistributionReuse(unittest.TestCase):
    def test_multi_copy_reuses_fixed_probability_distribution(self):
        handler = feature_api.HANDLERS[("honkai-star-rail", "gacha")]["plan"]
        module = sys.modules[handler.__module__]
        with patch.object(module, "five_star_pmf", wraps=module.five_star_pmf) as pmf, \
             patch.object(module, "_convolve", wraps=module._convolve) as convolve:
            result = call("gacha", "plan", {"pool": "character_event", "copies": 6, "pity": 30})
        self.assertLessEqual(pmf.call_count, 2)
        self.assertLessEqual(convolve.call_count, 8)
        self.assertAlmostEqual(result["cdf"][-1]["cdf"], 1.0, places=9)

    def test_reuse_preserves_independently_computed_distribution(self):
        pool = next(p for p in call("gacha", "pools")["pools"] if p["id"] == "character_event")

        def single(start):
            remaining, out = 1.0, {}
            for pity in range(start + 1, pool["hardPity"] + 1):
                rate = 1.0 if pity >= pool["hardPity"] else min(1.0, pool["baseRate"] + pool["softPityStep"] * max(0, pity - pool["softPityStart"] + 1))
                out[pity - start] = remaining * rate
                remaining *= 1 - rate
                if remaining <= 1e-15:
                    break
            return out

        def product(a, b):
            result = {}
            for i, p in a.items():
                for j, q in b.items():
                    result[i + j] = result.get(i + j, 0.0) + p * q
            return result

        for guaranteed in (False, True):
            with self.subTest(guaranteed=guaranteed):
                dist = {0: 1.0}
                for index in range(3):
                    first = single(30 if index == 0 else 0)
                    if index == 0 and guaranteed:
                        need = first
                    else:
                        need = {k: v * pool["upChance"] for k, v in first.items()}
                        for k, v in product(first, single(0)).items():
                            need[k] = need.get(k, 0.0) + v * (1 - pool["upChance"])
                    dist = product(dist, need)
                expected_total = sum(dist.values())
                result = call("gacha", "plan", {"pool": "character_event", "copies": 3, "pity": 30, "guaranteed": guaranteed})
                actual = {row["pulls"]: row["prob"] for row in result["cdf"]}
                self.assertEqual(set(actual), set(dist))
                for pulls, probability in dist.items():
                    self.assertAlmostEqual(actual[pulls], probability / expected_total, places=12)
