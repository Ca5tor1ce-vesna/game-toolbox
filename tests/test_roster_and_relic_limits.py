"""配速输入和队伍组成的独立边界。"""
import unittest
from test_toolbox import call


class TestRelicSpeedLimits(unittest.TestCase):
    def test_bounds_depend_on_speed_boots(self):
        for boots, limit in ((True, 78.0), (False, 93.6)):
            with self.subTest(boots=boots):
                base = {'characterId': '1502', 'relic': {'speedBoots': boots, 'substatSpeed': limit}}
                breakdown = call('speed-plan', 'plan', base)['speed']['breakdown']
                self.assertAlmostEqual(next(item['value'] for item in breakdown if item['label'] == '遗器副词条速度'), limit)
                base['relic']['substatSpeed'] = limit + 0.1
                with self.assertRaisesRegex(ValueError, '副词条'):
                    call('speed-plan', 'plan', base)

    def test_negative_substat_is_rejected(self):
        with self.assertRaisesRegex(ValueError, '副词条'):
            call('speed-plan', 'plan', {'characterId': '1502', 'relic': {'substatSpeed': -1}})


class TestDuplicateTeam(unittest.TestCase):
    def test_same_character_and_alias_are_rejected(self):
        for ids in (('1511', '1511'), ('1511', 'aeon_aha')):
            with self.subTest(ids=ids), self.assertRaisesRegex(ValueError, '重复'):
                call('aha-speed', 'simulate', {'team': [{'id': x} for x in ids]})
