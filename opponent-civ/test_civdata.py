"""Civilization loading across old and current game metadata schemas."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from civdata import load_civs


class CivilizationTests(unittest.TestCase):
    def load(self, entries, tw, en=None):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / 'resources/_common/dat/civilizations.json'
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({'civilization_list': entries}), encoding='utf-8')
            def strings(_root, lang):
                return tw if lang == 'tw' else (en or {})
            with patch('civdata.load_strings', side_effect=strings):
                return load_civs(root, 'tw')

    def test_current_schema_preserves_recording_ids(self):
        entries = [{'internal_name': 'Gaia', 'name_string_id': 10102},
                   {'internal_name': 'Romans', 'name_string_id': 10313},
                   {'internal_name': 'Slavs', 'name_string_id': 10293}]
        civs = self.load(entries, {10313: '羅馬人', 120192: '<b>羅馬說明',
                                  10293: '斯拉夫人', 120172: '斯拉夫說明'})
        self.assertEqual(set(civs), {1, 2})
        self.assertEqual(civs[1].description, '羅馬說明')
        self.assertEqual(civs[2].description, '斯拉夫說明')
        self.assertEqual(civs[1].name, '羅馬人')

    def test_explicit_description_id_takes_precedence(self):
        civs = self.load([{'internal_name': 'Romans', 'name_string_id': 10313,
                           'tech_tree_description_string_id': 42}],
                         {10313: '羅馬人', 42: '指定說明', 120192: '備援說明'})
        self.assertEqual(civs[0].description, '指定說明')

    def test_missing_translation_falls_back_to_english(self):
        civs = self.load([{'internal_name': 'Romans', 'name_string_id': 10313}],
                         {10313: '羅馬人'}, {120192: 'Infantry civilization'})
        self.assertEqual(civs[0].description, 'Infantry civilization')

    def test_missing_description_keeps_civilization(self):
        civs = self.load([{'internal_name': 'Future', 'name_string_id': 19999}],
                         {19999: '新文明'})
        self.assertEqual(civs[0].name, '新文明')
        self.assertIn('確認遊戲資料版本', civs[0].description)
