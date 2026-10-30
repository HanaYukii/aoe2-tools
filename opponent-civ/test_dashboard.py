"""Regression checks for match switching and the offline dashboard."""
import argparse
import gc
from dataclasses import replace
from pathlib import Path
import tkinter as tk
import unittest
from unittest.mock import patch

from civdata import Civ
from dashboard import Dashboard
from rec_header import Match, Player
from units import UniqueUnit


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
        self.app = self.root = None  # free the dashboard's Tk objects on this thread (see test_build_views)
        gc.collect()

    def test_bundled_icons_load_and_share_only_this_root(self):
        from ui_icons import icon
        for name in ('town-center', 'map', 'combat', 'sheep', 'scroll', 'economy', 'hourglass', 'ram'):
            image = icon(self.root, name)
            self.assertEqual((image.width(), image.height()), (24, 24))
            self.assertIs(image, icon(self.root, name))
        self.assertTrue(self.app.workspace_book.tab(self.app.rp_frame, 'image'))

    def test_all_civilization_icons_load_with_fallback(self):
        from ui_icons import CIVILIZATIONS, civilization_icon, icon
        self.assertEqual(len(CIVILIZATIONS), 56)
        for key in CIVILIZATIONS:
            for size in (24, 32, 64, 128):
                image = civilization_icon(self.root, key, size)
                self.assertEqual((image.width(), image.height()), (size, size))
        self.assertIs(civilization_icon(self.root, 'Romans'), civilization_icon(self.root, 'romans'))
        self.assertIsNot(civilization_icon(self.root, 'Indians'), icon(self.root, 'map', 32))  # Hindustanis' internal name
        self.assertIs(civilization_icon(self.root, 'future-civ'), icon(self.root, 'map', 32))
        self.assertIs(civilization_icon(self.root, None), icon(self.root, 'map', 32))

    def test_manual_drain_replaces_pending_timer(self):
        previous = self.app.drain_timer
        self.app.drain()
        pending = self.root.tk.call('after', 'info')
        self.assertNotIn(previous, pending)
        self.assertIn(self.app.drain_timer, pending)

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

    def test_status_names_the_map(self):
        self.app.maps = {29: '競技場'}
        self.app.show(replace(self.match, map_id=29), Path('live.aoe2record'), 0.5, False)
        self.assertIn('競技場', self.app.status.cget('text'))

    def test_counters_tab_and_jump(self):
        self.app.units = {1: (UniqueUnit('長弓兵', '英國特殊步弓兵，擁有出色的射程。', ('騎兵', '矛兵'), ('步兵',), (),
                                         False, '升級：攻擊 (兵工廠)。', ()),)}
        self.app.show(self.match, Path('live.aoe2record'), 0.5, False)
        book = self.app.book
        self.assertEqual([book.tab(tab, 'text') for tab in book.tabs()], ['對手 · 不列顛人', '兵種應對', '你 · 不列顛人'])
        enemy_tab = book.nametowidget(book.tabs()[0])
        next(w for w in enemy_tab.winfo_children() if isinstance(w, tk.Button)).invoke()
        self.assertEqual(book.index('current'), 1)
        counters = self.app.counter_texts[0].get('1.0', 'end')
        self.assertIn('用這些打　騎兵、矛兵', counters)
        self.assertIn('它克制　步兵', counters)


if __name__ == '__main__':
    unittest.main()
