"""Map labels from a recording's map id, and the installed game's map list."""
import unittest
from dataclasses import replace

from civdata import find_game_dir
from mapdata import load_map_names, map_label
from rec_header import Match, read_match
from savegames import recordings, savegame_dirs

BASE = Match(68.9, 1, 0, True, True, False, ())


class MapLabelTests(unittest.TestCase):
    def test_labels(self):
        names = {9: '阿拉伯'}
        self.assertEqual(map_label(replace(BASE, map_id=9), names), '阿拉伯')
        self.assertEqual(map_label(replace(BASE, map_id=-3), names), '劇本／戰役')
        self.assertEqual(map_label(replace(BASE, map_id=999), names), '未知地圖 #999')
        self.assertEqual(map_label(replace(BASE, map_id=77, map_file='ES@Arabia v1.2.rms'), names), 'ES@Arabia v1.2')
        self.assertEqual(map_label(BASE, names), '')  # built without a map, as in tests and the demo


@unittest.skipUnless((find_game_dir() / 'resources').is_dir(), 'AoE2 DE is not installed')
class InstalledGameTests(unittest.TestCase):
    def test_known_maps_and_recordings(self):
        names = load_map_names()
        self.assertEqual(names[9], '阿拉伯')
        multiplayer = [m for m in (read_match(p) for p in recordings(savegame_dirs())[:20]) if m.multiplayer]
        if not multiplayer:
            self.skipTest('no multiplayer recordings on this PC')
        self.assertTrue(all(map_label(m, names) and not map_label(m, names).startswith('未知') for m in multiplayer))


if __name__ == '__main__':
    unittest.main()
