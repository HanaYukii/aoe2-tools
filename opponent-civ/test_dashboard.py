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


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


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
        pages = [str(self.app.workspace_book.tab(tab, 'image')) for tab in self.app.workspace_book.tabs()]
        self.assertEqual(len(set(pages)), len(pages))  # every page tab has its own icon

    def test_all_civilization_icons_load_with_fallback(self):
        from ui_icons import CIVILIZATIONS, civilization_icon, icon
        self.assertEqual(len(CIVILIZATIONS), 56)
        for key in CIVILIZATIONS:
            for size in (24, 32, 64, 128):
                image = civilization_icon(self.root, key, size)
                self.assertEqual((image.width(), image.height()), (size, size))
        self.assertIs(civilization_icon(self.root, 'Romans'), civilization_icon(self.root, 'romans'))
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
        next(w for w in descendants(enemy_tab) if isinstance(w, tk.Button)).invoke()
        self.root.update_idletasks()  # run jump's idle scroll now, not after this root is destroyed
        self.assertEqual(book.index('current'), 1)
        counters = self.app.counter_texts[0].get('1.0', 'end')
        self.assertIn('用這些打　騎兵、矛兵', counters)
        self.assertIn('它克制　步兵', counters)

    def team_match(self):
        self.app.civs[2] = Civ(2, 'Franks', '法蘭克人', '騎兵文明\n\n團隊加成：\n騎士視野 +2')
        self.app.civs[3] = Civ(3, 'Teutons', '條頓人', '步兵文明\n\n團隊成分：\n步兵抗轉化')
        return replace(self.match, players=(
            Player(1, '自己', 1, 2, 0, 10, 2), Player(2, '敵一', 2, 3, 1, 20, 2),
            Player(3, '盟友', 3, 2, 2, 30, 2), Player(4, '敵二', 1, 3, 3, 40, 2)))

    def test_team_game_opens_on_both_teams_side_by_side(self):
        team = self.team_match()
        self.app.show(team, Path('team.aoe2record'), 0.5, False)
        book = self.app.book
        self.assertEqual([book.tab(tab, 'text') for tab in book.tabs()],
                         ['團隊加成', '對手 · 法蘭克人', '對手 · 不列顛人', '你 · 不列顛人', '隊友 · 條頓人'])
        self.assertEqual(book.index('current'), 0)
        mine, theirs = (text.get('1.0', 'end') for text, _ in self.app.team_sides)
        for words in ('我方隊伍', '自己（你）', '盟友', '步兵抗轉化'):
            self.assertIn(words, mine)
        for words in ('對手隊伍', '敵一', '騎士視野 +2', '敵二', '射箭場工作速度 +10%'):
            self.assertIn(words, theirs)
        self.assertNotIn('積分', mine + theirs)  # rating lookup is off in these tests
        self.assertTrue(self.app.team_sides[0][0].tag_bind('player3', '<Button-1>', None))
        self.app.my_id = None
        self.app.show(team, Path('team.aoe2record'), 0.5, False)
        self.assertEqual(len(self.app.team_sides), 1)
        self.assertIn('所有玩家', self.app.team_sides[0][0].get('1.0', 'end'))
        self.app.show(self.match, Path('duel.aoe2record'), 0.5, False)
        self.assertNotIn('團隊加成', [book.tab(tab, 'text') for tab in book.tabs()])
        self.assertEqual(self.app.team_sides, [])

    def test_team_columns_show_each_side_average_rating(self):
        self.app.args.no_elo = False
        with patch.object(self.app.pool, 'submit'):  # no live lookup; the response is posted below
            self.app.show(self.team_match(), Path('team.aoe2record'), 0.5, False)
        mine, theirs = (text for text, _ in self.app.team_sides)
        self.assertIn('正在查詢積分', theirs.get('1.0', 'end'))
        self.app.events.put(('ratings', (self.app.generation, {10: {3: 1000, 4: 1100}, 30: {3: 1200},
                                                               20: {4: 1500}, 40: {4: 1700}}, None)))
        self.app.drain()
        self.assertIn('平均 1v1  1100  ·  團戰  1100 (1/2)', mine.get('1.0', 'end'))
        self.assertIn('平均 團戰  1600', theirs.get('1.0', 'end'))
        self.assertNotIn('正在查詢積分', theirs.get('1.0', 'end'))

    def test_team_columns_hide_idle_scrollbars_and_grow_emblems(self):
        from tkinter import ttk
        self.app.show(self.team_match(), Path('team.aoe2record'), 0.5, False)
        text, _ = self.app.team_sides[0]
        bar = next(w for w in text.master.winfo_children() if isinstance(w, ttk.Scrollbar))
        self.assertFalse(bar.winfo_manager())  # nothing to scroll
        Dashboard.toggle_scrollbar(bar, text, '0.0', '0.6')
        self.assertEqual(bar.winfo_manager(), 'pack')
        Dashboard.toggle_scrollbar(bar, text, '0.0', '1.0')
        self.assertFalse(bar.winfo_manager())
        self.app.fit_team_sides()  # off screen in tests: keeps the floor size without error
        self.app.style_team(text, 20)  # large text: 32 px emblems, bonus lines indented past them
        name, _ = self.app.team_icons[str(text)][0]
        self.assertEqual(text.tk.call('image', 'width', text.image_cget(name, 'image')), 32)
        self.assertEqual(int(str(text.tag_cget('bonus', 'lmargin1'))), 44)

if __name__ == '__main__':
    unittest.main()
