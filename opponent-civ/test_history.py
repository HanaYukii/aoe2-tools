import io
import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from history import match_results, recent_matches
from ratings import fetch_results
from rec_header import Match, NotReady, Player

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

    def test_results_match_by_start_time_and_players(self):
        me, rival = 10, 20
        base = Match(68.9, 1, 1000, True, True, False, (Player(1, '我', 1, 2, 0, me, 2), Player(2, '對手', 2, 3, 1, rival, 2)))
        rows = [(Path(name), replace(base, timestamp=start, rated=rated))
                for name, start, rated in (('a', 1000, True), ('b', 5000, True), ('c', 9000, False), ('d', 13000, True), ('e', 17000, True))]
        games = [(1003, {me: (1, 1300, 1316), rival: (0, 1310, 1294)}),  # seconds apart: won, +16
                 (5000, {me: (0, 1316, 1299), 30: (1, 1300, 1317)}),     # someone else's game at that time
                 (9002, {me: (0, 975, 962), rival: (1, 980, 993)}),      # unranked: no rating change shown
                 (13500, {me: (1, 1299, 1315), rival: (0, 1, 1)}),       # too far from the recording
                 (17001, {me: (4, 1299, 1299), rival: (4, 1, 1)})]       # no clear outcome
        self.assertEqual(match_results(rows, games, me), [(True, 16), None, (False, None), None, None])
        self.assertEqual(match_results(rows, games, 99), [None] * 5)  # spectated: not my game

    def test_fetch_results_reads_each_member(self):
        body = {'result': {'code': 0}, 'matchHistoryStats': [{'startgametime': 100, 'matchhistorymember': [
            {'profile_id': 10, 'outcome': 1, 'oldrating': 1300, 'newrating': 1316},
            {'profile_id': 20, 'outcome': 0, 'oldrating': 1310, 'newrating': 1294}]}]}
        with patch('ratings.urllib.request.urlopen', return_value=io.BytesIO(json.dumps(body).encode())) as urlopen:
            self.assertEqual(fetch_results(10), [(100, {10: (1, 1300, 1316), 20: (0, 1310, 1294)})])
        self.assertIn('profile_ids=%5B10%5D', urlopen.call_args[0][0])
        with patch('ratings.urllib.request.urlopen', return_value=io.BytesIO(b'{"result": {"code": 2}}')):
            with self.assertRaises(ValueError):
                fetch_results(10)

if __name__ == '__main__':
    unittest.main()
