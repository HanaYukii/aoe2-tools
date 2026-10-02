import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from settings import read_settings, save_settings, validate_settings, player_choices
from rec_header import Match, Player

class SettingsTests(unittest.TestCase):
    def test_roundtrip_and_corrupt_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            self.assertIsNone(read_settings(path))
            data = dict(game_dir='D:/遊戲', dirs=[], lang='tw', profile_id=123, no_elo=True)
            save_settings(data, path)
            self.assertEqual(read_settings(path), data)
            path.write_text('{broken', encoding='utf-8')
            self.assertIsNone(read_settings(path))
            save_settings(dict(data, profile_id='not-an-id'), path)
            self.assertIsNone(read_settings(path))

    def test_nonexistent_directory_rejected(self):
        with patch('settings.load_civs'):
            with self.assertRaises(ValueError):
                validate_settings(dict(game_dir='example', lang='tw', dirs=['Z:/missing-aoe2-test-folder']))

    def test_same_name_keeps_distinct_ids(self):
        match = Match(68.9, 1, 0, True, True, False, (
            Player(1, 'Same Name', 1, 2, 0, 10, 2), Player(2, 'Same Name', 1, 3, 1, 20, 2)))
        with patch('settings.recordings', return_value=[Path('example')]), patch('settings.read_match', return_value=match):
            self.assertEqual(set(player_choices([]).values()), {10, 20})

if __name__ == '__main__':
    unittest.main()
