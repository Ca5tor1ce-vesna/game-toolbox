"""角色目录扩充时提醒同步配速页配色。"""
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CharacterThemesTest(unittest.TestCase):
    def test_all_catalog_characters_have_one_theme(self):
        catalog = json.loads((ROOT / 'modules/honkai-star-rail/data/characters.json').read_text(encoding='utf-8'))
        source = (ROOT / 'modules/honkai-star-rail/features/speed-plan/ui.js').read_text(encoding='utf-8')
        groups = source.split('const CHARACTER_THEME_GROUPS = {', 1)[1].split('};', 1)[0]
        ids = re.findall(r'"(\d+)"', groups)
        self.assertEqual(len(ids), len(set(ids)), '角色配色不能重复配置')
        self.assertEqual(set(ids), {str(character['id']) for character in catalog})
