"""Regression checks for match switching and the offline dashboard."""
import argparse
from pathlib import Path
import tkinter as tk
import unittest
from unittest.mock import patch

from civdata import Civ
from dashboard import Dashboard
from rec_header import Match, Player


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        args = argparse.Namespace(no_elo=True)
        with patch.object(Dashboard, 'monitor'):
            self.app = Dashboard(self.root, args)
        self.app.civs = {1: Civ(1, 'Britons', '不列顛人', '步弓兵文明\n\n團隊加分：\n射箭場工作速度 +10%')}
        self.app.my_id = 10
        self.match = Match(68.9, 1, 1700000000, True, True, False, (
            Player(1, '自己', 1, 2, 0, 10, 2),
            Player(2, '對手', 1, 3, 1, 20, 2),
        ))

    def tearDown(self):
        self.app.close()

    def test_offline_preview_and_match_switch(self):
        with patch('dashboard.fetch_ratings') as fetch:
            self.app.show(self.match, Path('preview.aoe2record'), None, True)
            self.assertIn('歷史預覽', self.app.status.cget('text'))
            self.assertEqual(self.app.tabs[0][0].name, '對手')
            self.assertEqual(len(self.app.book.tabs()), 2)
            self.app.show(self.match, Path('live.aoe2record'), 0.5, False)
            self.assertIn('新對局', self.app.status.cget('text'))
            self.assertEqual(len(self.app.book.tabs()), 2)
            fetch.assert_not_called()

    def test_old_rating_response_is_ignored(self):
        self.app.show(self.match, Path('old.aoe2record'), None, True)
        old_generation = self.app.generation
        self.app.show(self.match, Path('new.aoe2record'), None, True)
        self.app.events.put(('ratings', (old_generation, {20: {3: 9999}}, None)))
        self.app.drain()
        self.assertNotIn('9999', self.app.tabs[0][1].cget('text'))
        self.app.events.put(('ratings', (self.app.generation, {20: {3: 1200}}, None)))
        self.app.drain()
        self.assertIn('1200', self.app.tabs[0][1].cget('text'))

    def test_unknown_identity_labels_players(self):
        self.app.my_id = None
        self.app.show(self.match, Path('unknown.aoe2record'), None, True)
        self.assertTrue(all(self.app.book.tab(tab, 'text').startswith('玩家') for tab in self.app.book.tabs()))

    def test_delayed_preview_cannot_replace_new_match(self):
        generation = self.app.generation
        self.app.show(self.match, Path('live.aoe2record'), 0.5, False)
        self.app.events.put(('preview_match', (generation, (self.match, Path('old.aoe2record'), None, True))))
        self.app.drain()
        self.assertIn('新對局', self.app.status.cget('text'))


if __name__ == '__main__':
    unittest.main()
