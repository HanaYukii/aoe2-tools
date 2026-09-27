import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from history import recent_matches
from rec_header import Match, NotReady

class HistoryTests(unittest.TestCase):
    def test_sort_filter_limit_and_skip(self):
        base = Match(68.9, 1, 0, True, True, False, ())
        paths = [Path(str(i)) for i in range(16)]
        def parse(path):
            i = int(str(path))
            if i == 15:
                raise NotReady('incomplete')
            return replace(base, timestamp=i, multiplayer=i != 14, rated=i % 2 == 0)
        with patch('history.recordings', return_value=paths), patch('history.read_match', side_effect=parse):
            rows, skipped = recent_matches([])
            self.assertEqual([m.timestamp for _, m in rows], list(range(13, 3, -1)))
            self.assertEqual(skipped, 1)
            ranked, _ = recent_matches([], '排名')
            self.assertTrue(all(m.rated for _, m in ranked))
            all_rows, _ = recent_matches([], '全部')
            self.assertEqual(all_rows[0][1].timestamp, 14)

    def test_empty(self):
        with patch('history.recordings', return_value=[]):
            self.assertEqual(recent_matches([]), ([], 0))

if __name__ == '__main__':
    unittest.main()
