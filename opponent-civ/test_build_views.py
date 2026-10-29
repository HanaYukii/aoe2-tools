"""Exercise real Tk views with synthetic local material and match events."""
import argparse
import gc
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from tkinter import ttk
from unittest.mock import patch
from civdata import Civ
from dashboard import Dashboard
from build_library import LibraryState
from build_views import wrap_text, reference_highlights
from rec_header import Match, Player
from test_build_library import write_fixture

TABS = ['對局 RP', '前期流程', '中期速查', '地圖注意', '流程庫']


class BuildViewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        catalog = write_fixture(self.directory)
        patcher = patch('build_library.DATA_PATH', catalog)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.root = tk.Tk()
        self.root.withdraw()
        args = argparse.Namespace(no_elo=True, demo=True, library_dir=str(self.directory))
        with patch('build_views.LibraryState', return_value=LibraryState(self.directory/'state.json')):
            self.app = Dashboard(self.root, args)
        self.app.my_id = 10
        self.app.civs = {43: Civ(43, 'Romans', '羅馬', '展示'), 35: Civ(35, 'Burgundians', '勃根地', '展示'),
                         1: Civ(1, 'Britons', '不列顛', '展示')}
        self.app.maps = {9: '阿拉伯', 29: '競技場'}
        self.ui = self.app.library
        self.book = self.app.workspace_book

    def tearDown(self):
        self.app.close()
        self.temp.cleanup()
        # Dashboard and its library point at each other, so only the cycle collector frees them.
        # Collect here, on the Tk thread: run later on a worker thread, Tk aborts the whole suite.
        self.app = self.ui = self.book = self.root = None
        gc.collect()

    def game(self, civ_id, map_id=9, hour=0, live=False):
        """Show a match where I play `civ_id`: live as a new game, otherwise as browsed history."""
        match = Match(68.9, 1, 1700000000 + hour * 3600, True, True, False,
                      (Player(1, '自己', civ_id, 2, 0, 10, 2), Player(2, '對手', 1, 3, 1, 20, 2)), map_id=map_id)
        self.app.show(match, Path(f'{hour}.aoe2record'), .5 if live else None, not live)
        return match

    def build(self, index):
        return next(b for b in self.ui.builds if b.index == index)

    def row(self, index):
        """A build's row in the library, as {button text: button}."""
        for row in self.ui.library_tab.results.body.winfo_children():
            actions, text = row.winfo_children()
            if text.winfo_children()[0].cget('text').split('  ')[-1] == f'測試流程 {index}':
                return {b.cget('text'): b for b in actions.winfo_children()}
        raise AssertionError(f'build {index} is not listed')

    def texts(self, widget):
        for child in widget.winfo_children():
            try:
                yield str(child.cget('text'))
            except tk.TclError:
                pass
            yield from self.texts(child)

    def tabs(self):
        return [self.book.tab(tab, 'text').split(' · ')[0] for tab in self.book.tabs()]

    def test_tabs_stay_fixed_while_clicking_around(self):
        self.assertEqual(self.tabs(), TABS)
        self.game(35, 29)
        self.ui.pick(self.build(16))
        self.ui.open_sheet('romans-castle-push')
        self.ui.library_tab.mode.set('overview')
        self.ui.library_tab.refresh(top=True)
        self.ui.fill_switch()
        self.ui.switch_menu.invoke(0)
        self.game(43, hour=1, live=True)
        self.assertEqual(self.tabs(), TABS)
        self.assertEqual(self.book.select(), str(self.app.rp_frame))  # a new match opens on its RP
        self.assertEqual([r for r in self.ui.readers.values() if r.winfo_manager()], [self.ui.readers[self.ui.build.id]])

    def test_opening_is_the_first_recommended_build_that_suits_the_map(self):
        self.game(35, 29)
        self.assertEqual(self.ui.build.index, 15)
        self.assertEqual(self.book.tab(self.ui.plan_tab, 'text'), '前期流程 · 測試流程 15')
        self.assertEqual(self.ui.title.cget('text'), f'{self.build(15).population} 人口  ·  測試流程 15')
        self.game(35, 9, hour=1)
        self.assertEqual(self.ui.build.index, 1)
        self.game(43, 9, hour=2)
        self.assertEqual(self.ui.build.index, 33)
        self.assertIn('阿拉伯（開放地圖）', self.ui.library_tab.map_note.cget('text'))

    def test_map_notes_follow_match_without_switching_tabs(self):
        self.game(43, 9)
        view = self.ui.map_tab
        self.assertEqual(view.current['id'], 'arabia')
        self.assertEqual(self.book.select(), str(self.app.rp_frame))
        index = next(i for i, n in enumerate(view.notes) if n['id'] == 'nomad')
        view.selector.current(index)
        view.choose()
        self.assertEqual(view.view.sheet['id'], 'nomad')
        self.assertIn('手動預習', view.status.cget('text'))
        view.follow()
        self.assertEqual(view.view.sheet['id'], 'arabia')
        self.game(35, 29, hour=1)
        self.assertEqual(view.current['id'], 'arena')
        self.assertEqual(view.view.sheet['id'], 'arena')
        self.game(43, 999, hour=2)
        self.assertIsNone(view.current)
        self.assertIsNone(view.view)
        self.assertIn('尚未整理', view.message.cget('text'))

    def test_reordering_recommendations_moves_the_default_and_persists(self):
        self.game(35, 9)
        library = self.ui.library_tab
        self.assertIn('disabled', self.row(1)['▲'].state())
        self.assertIn('disabled', self.row(22)['▼'].state())
        for _ in range(3):
            self.row(22)['▲'].invoke()
        self.assertEqual([b.index for b in self.ui.recommended()], [22, 1, 2, 15])
        self.assertEqual(self.ui.build.index, 22)  # now the first that suits Arabia
        self.assertEqual(library.moved, self.build(22).id)
        saved = LibraryState(self.directory/'state.json').recommended(self.ui.builds, 'Burgundians')
        self.assertEqual([b.index for b in saved], [22, 1, 2, 15])
        self.game(35, 29, hour=1)
        self.assertEqual(self.ui.build.index, 15)  # Arena still opens the closed-map build
        with patch.object(LibraryState, 'save', side_effect=OSError('read-only')):
            self.row(2)['▲'].invoke()
        self.assertEqual([b.index for b in self.ui.recommended()], [22, 2, 1, 15])
        self.assertIn('無法寫入設定檔', library.note.cget('text'))

    def test_a_pick_belongs_to_its_match_and_a_new_game_starts_over(self):
        first = self.game(35, 9, live=True)
        self.assertEqual(self.ui.build.index, 1)
        self.ui.readers[self.build(1).id].mark(5)
        self.ui.fill_switch()
        menu = self.ui.switch_menu
        self.assertTrue(menu.entrycget(0, 'label').startswith('✓ 1. 測試流程 1'))
        self.assertEqual(menu.type(4), 'separator')
        menu.invoke(2)
        self.assertEqual(self.ui.build.index, 15)
        self.assertEqual(self.book.select(), str(self.ui.plan_tab))
        self.game(43, hour=1)  # browse an older match
        self.assertEqual(self.ui.build.index, 33)
        self.app.show(first, Path('0.aoe2record'), None, True)  # back to the game being played
        self.assertEqual(self.ui.build.index, 15)
        self.assertEqual(self.ui.readers[self.build(1).id].selected, 5)  # browsing keeps marks
        self.game(35, 9, hour=2, live=True)
        self.assertEqual(self.ui.build.index, 1)
        self.assertEqual(self.ui.readers[self.build(1).id].selected, -1)  # a new game starts from the top
        self.assertEqual(list(self.ui.readers), [self.build(1).id])

    def test_sheet_tab_follows_the_build_then_the_civilization(self):
        self.game(35, 29)
        self.assertEqual(self.ui.sheet, 'burgundians-arena-castle')
        self.assertEqual(str(self.book.tab(self.ui.sheet_tab, 'state')), 'normal')
        self.ui.next_button.invoke()
        self.assertEqual(self.book.select(), str(self.ui.sheet_tab))
        view = self.ui.sheet_views['burgundians-arena-castle']
        header = view.winfo_children()[0]
        next(w for w in header.winfo_children() if w.cget('text') == '測試流程 16').invoke()
        self.assertEqual(self.ui.build.index, 16)
        self.assertEqual(self.book.select(), str(self.ui.plan_tab))
        self.game(1, 9, hour=1)  # Britons on Arabia: no sheet of theirs and none for the map
        self.assertIsNone(self.ui.sheet)
        self.assertEqual(str(self.book.tab(self.ui.sheet_tab, 'state')), 'disabled')
        self.assertFalse(self.ui.next_button.winfo_manager())
        self.game(1, 29, hour=2)  # Britons fast castle on Arena: the Burgundian sheet for it is not theirs
        self.assertEqual(self.ui.build.index, 15)
        self.assertEqual(self.ui.sheet, 'arena-castle-drop')
        self.assertFalse(self.ui.sheet_bar.winfo_manager())  # one sheet: nothing to switch
        library = self.ui.library_tab
        library.civ_name.set('羅馬')
        library.refresh(top=True)
        sheet_buttons = [w for w in library.sheet_bar.winfo_children() if isinstance(w, ttk.Button)]
        self.assertEqual([b.cget('text') for b in sheet_buttons], ['羅馬・主線運營', '羅馬・對弓兵', '羅馬・對馬弓', '羅馬・對騎士', '競技場・壓堡應對'])
        sheet_buttons[0].invoke()
        self.assertEqual(self.ui.sheet, 'romans-castle-push')
        self.assertEqual(self.book.select(), str(self.ui.sheet_tab))
        self.assertEqual([b.cget('text') for b in self.ui.sheet_bar.winfo_children()],
                         ['競技場・壓堡應對', '羅馬・主線運營'])  # the pick joins what applies here
        self.game(43, 9, hour=3)
        self.assertEqual(self.ui.sheet, 'romans-castle-push')
        self.assertEqual(len(self.ui.sheet_views), 3)

    def test_roman_branches_switch_manually_and_keep_the_match_choice(self):
        self.game(43, 9, live=True)
        expected = ['羅馬・主線運營', '羅馬・對弓兵', '羅馬・對馬弓', '羅馬・對騎士']
        self.assertEqual([b.cget('text') for b in self.ui.sheet_bar.winfo_children()], expected)
        self.assertEqual(self.ui.sheet, 'romans-castle-push')
        for index, ident in enumerate(['romans-vs-archers', 'romans-vs-cavalry-archers', 'romans-vs-knights'], 1):
            self.ui.sheet_bar.winfo_children()[index].invoke()
            self.assertEqual(self.ui.sheet, ident)
            view = self.ui.sheet_views[ident]
            self.assertEqual(len(view.cards), 6)
            view.reflow(SimpleNamespace(width=1000, height=900))
            view.fit()
            self.assertTrue(any(body.tag_ranges('eco') for body in view.texts))
        self.ui.refresh()
        self.assertEqual(self.ui.sheet, 'romans-vs-knights')
        self.assertEqual(self.ui.sheet_bar.winfo_children()[3].grid_info()['row'], 1)
        self.game(43, 9, hour=1, live=True)
        self.assertEqual(self.ui.sheet, 'romans-castle-push')

    def test_arena_adds_the_castle_drop_sheet_beside_the_civilization_sheet(self):
        self.game(35, 29)
        self.assertEqual(self.ui.sheet, 'burgundians-arena-castle')
        self.assertEqual(self.ui.sheet_bar.winfo_manager(), 'pack')
        choices = self.ui.sheet_bar.winfo_children()
        self.assertEqual([c.cget('text') for c in choices], ['勃根地競技場・城堡期速查', '勃根地競技場・防壓堡速查', '勃根地競技場・防塔攻保直城', '競技場・壓堡應對'])
        choices[1].invoke()
        self.assertEqual(self.ui.sheet, 'burgundians-arena-defense')
        self.assertEqual(self.ui.sheet_views['burgundians-arena-defense'].winfo_manager(), 'pack')
        self.ui.sheet_bar.winfo_children()[3].invoke()
        self.assertEqual(self.ui.sheet, 'arena-castle-drop')
        view = self.ui.sheet_views['arena-castle-drop']
        self.assertEqual(view.winfo_manager(), 'pack')
        self.assertFalse(self.ui.sheet_views['burgundians-arena-castle'].winfo_manager())
        self.assertEqual(self.ui.sheet_choice.get(), 'arena-castle-drop')
        self.game(35, 29, hour=1, live=True)  # the next game starts from its own sheet again
        self.assertEqual(self.ui.sheet, 'burgundians-arena-castle')

    def test_map_shortcut_is_optional_and_never_auto_switches_tabs(self):
        self.game(35, 29, live=True)
        bar = self.app.map_shortcuts
        self.assertEqual(self.book.select(), str(self.app.rp_frame))
        self.assertEqual(len(bar.winfo_children()), 2)  # castle defense is deduplicated; tower defense is separate
        bar.winfo_children()[0].invoke()
        self.assertEqual(self.ui.sheet, 'burgundians-arena-defense')
        self.assertEqual(self.book.select(), str(self.ui.sheet_tab))
        bar.winfo_children()[1].invoke()
        self.assertEqual(self.ui.sheet, 'burgundians-arena-tower-defense')
        self.book.select(self.ui.plan_tab)
        self.ui.refresh()
        self.assertEqual(self.book.select(), str(self.ui.plan_tab))
        self.game(1, 29, hour=1, live=True)
        self.assertEqual(self.book.select(), str(self.app.rp_frame))
        bar.winfo_children()[0].invoke()
        self.assertEqual(self.ui.sheet, 'arena-castle-drop')
        for hour, map_id in enumerate((9, -1), 2):
            self.game(35, map_id, hour=hour)
            self.assertFalse(bar.winfo_children())
            self.assertFalse(bar.winfo_manager())
            self.ui.open_sheet('burgundians-arena-defense')  # manual library pick doesn't enable a map shortcut
            self.assertFalse(bar.winfo_children())
        self.game(35, 29, hour=4)  # history gets the same map-aware entry
        self.assertEqual(len(bar.winfo_children()), 2)
        self.assertEqual(self.book.select(), str(self.app.rp_frame))

    def test_library_search_add_remove_and_overview(self):
        self.game(35, 9)
        library = self.ui.library_tab
        library.search.set('流程 3')
        self.assertEqual(library.mode.get(), 'all')
        self.assertIn('11 套流程', library.note.cget('text'))
        self.row(31)['加入推薦'].invoke()
        self.assertEqual([b.index for b in self.ui.recommended()][-1], 31)
        self.assertIn('disabled', self.row(31)['已在推薦'].state())
        self.row(33)['看流程'].invoke()
        self.assertEqual(self.ui.build.index, 33)
        self.assertEqual(self.book.select(), str(self.ui.plan_tab))
        self.game(35, 9, hour=1)  # another match resets the library to its recommendations
        self.assertEqual((library.mode.get(), library.search.get()), ('recommended', ''))
        self.row(31)['移出'].invoke()
        self.assertNotIn(31, [b.index for b in self.ui.recommended()])
        library.mode.set('overview')
        library.refresh(top=True)
        self.assertFalse(library.results.winfo_manager())
        self.assertIn('動物配置', library.overview.winfo_children()[0].get('1.0', 'end'))
        library.mode.set('recommended')
        library.refresh(top=True)
        self.assertFalse(library.overview.winfo_manager())
        self.assertEqual(library.results.winfo_manager(), 'pack')

    def test_reader_marks_steps_and_has_no_member_video_links(self):
        self.game(43)
        reader = self.ui.readers[self.ui.build.id]
        self.assertEqual(len(reader.rows), 30)
        self.assertEqual(list(reader.ages), ['黑暗', '封建'])
        reader.mark(14)
        self.assertEqual(reader.rows[14][0].cget('bg'), '#24473f')
        self.assertIn('第 15 步', reader.position_label.cget('text'))
        self.ui.library_tab.search.set('流程')
        self.assertFalse([t for t in self.texts(self.root) if '會員影片' in t])
        self.app.resize(1)
        self.assertEqual(reader.size, self.app.font_size)

    def test_first_launch_and_an_unreadable_catalog(self):
        self.ui.directory = None
        self.ui.reload()
        self.game(43)
        self.assertEqual(len(self.ui.builds), 40)
        self.assertEqual(self.ui.build.index, 33)
        with patch('build_library.DATA_PATH', self.directory/'missing.json'):
            self.ui.reload()
        self.ui.refresh(top=True)
        self.assertIsNone(self.ui.build)
        self.assertIn('內建流程資料', self.ui.title.cget('text'))
        self.assertIn('內建流程資料', self.ui.library_tab.note.cget('text'))
        self.assertEqual(self.book.tab(self.ui.plan_tab, 'text'), '前期流程')

    def test_reference_cards_fill_the_area_and_scroll_only_below_the_floor(self):
        self.ui.open_sheet('burgundians-arena-castle')
        sheet = self.ui.sheet_views['burgundians-arena-castle']

        def lay_out(width, height):
            sheet.reflow(SimpleNamespace(width=width, height=height))
            sheet.fit()
            return float(sheet.scroll.canvas.itemcget(sheet.scroll.window, 'height'))

        self.assertEqual(lay_out(1600, 1400), 1400)         # 3 x 2 cards fill the whole height
        self.assertEqual([sheet.cards[i].grid_info()['column'] for i in (1, 2)], [1, 2])
        self.assertEqual(sheet.cards[3].grid_info()['row'], 1)
        for body in sheet.texts:
            self.assertEqual(str(body.cget('state')), 'disabled')
        self.assertTrue(any(body.tag_ranges('tech') for body in sheet.texts))
        self.assertTrue(any(body.tag_ranges('eco') for body in sheet.texts))
        self.assertEqual([label.cget('text') for label in self.app.reminders],
                         ['記得蓋房子', '注意 TC 閒置', '資源記得調配',
                          '記得圍家', '看小地圖', '記得挖堡',
                          '前後排分隊', '偵查對手轉兵', '產兵建築充足'])
        roomy = sheet.fitted_size
        self.assertGreater(roomy, sheet.size - 1)           # text grows past the floor to use the room
        lay_out(1600, 700)
        self.assertLessEqual(sheet.fitted_size, roomy)
        lay_out(1000, 1400)
        self.assertEqual(sheet.cards[2].grid_info()['column'], 0)
        self.assertGreater(lay_out(800, 300), 300)           # too small even at the floor: scroll
        self.assertEqual(sheet.cards[1].grid_info()['column'], 0)
        self.assertEqual(sheet.fitted_size, max(10, sheet.size - 1))
        self.app.resize(10)
        self.assertEqual(len(sheet.texts), 6)
        self.assertEqual(sheet.size, 22)


class WrapTextTests(unittest.TestCase):
    @staticmethod
    def measure(token):  # wide characters count 2, everything else 1
        return sum(2 if ord(c) >= 0x2e80 else 1 for c in token)

    def test_chinese_breaks_between_any_characters_and_fills_lines(self):
        self.assertEqual(wrap_text('看到投石車 →弩砲散開暫緩加衝車', self.measure, 12),
                         '看到投石車 →\n弩砲散開暫緩\n加衝車')

    def test_number_words_stay_whole_and_the_break_space_is_dropped(self):
        self.assertEqual(wrap_text('約 30–35 村', self.measure, 6), '約\n30–35\n村')

    def test_closing_punctuation_takes_the_word_before_it_down(self):
        wrapped = wrap_text('一二三四五六，七', self.measure, 12)
        self.assertEqual(wrapped, '一二三四五\n六，七')  # no line opens with "，" or runs past the width
        self.assertTrue(all(self.measure(line) <= 12 for line in wrapped.split('\n')))

    def test_reference_emphasis_survives_wrapping(self):
        text = '先補二級\n射、彈道學；配 22–26\n木，其他依情況調整。'
        spans = [(tag, text[start:end].replace('\n', ''))
                 for tag, start, end in reference_highlights(text)]
        self.assertEqual(spans, [('tech', '二級射'), ('tech', '彈道學'), ('eco', '22–26木')])

    def test_existing_line_breaks_are_kept(self):
        self.assertEqual(wrap_text('甲乙\n丙丁', self.measure, 100), '甲乙\n丙丁')


if __name__ == '__main__':
    unittest.main()
