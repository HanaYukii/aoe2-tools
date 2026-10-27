"""Exercise real Tk views with synthetic local material and match events."""
import argparse
import gc
import tempfile
import tkinter as tk
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from civdata import Civ
from dashboard import Dashboard
from build_library import LibraryState
from build_views import wrap_text
from rec_header import Match, Player
from test_build_library import write_fixture


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
        self.app.civs = {43: Civ(43, 'Romans', '羅馬', '展示'), 35: Civ(35, 'Burgundians', '勃根地', '展示')}
        self.match = Match(68.9, 1, 1700000000, True, True, False,
                           (Player(1, '自己', 43, 2, 0, 10, 2), Player(2, '對手', 35, 3, 1, 20, 2)))
        self.app.show(self.match, Path('fixture.aoe2record'), None, True)
        self.ui = self.app.library

    def tearDown(self):
        self.app.close()
        self.temp.cleanup()
        # Dashboard and its library point at each other, so only the cycle collector frees them.
        # Collect here, on the Tk thread: run later on a worker thread, Tk aborts the whole suite.
        self.app = self.ui = self.root = None
        gc.collect()

    def test_picker_reuses_an_embedded_tab_and_tracks_new_context(self):
        self.ui.open_picker()
        first = self.ui.picker
        self.assertNotIsInstance(first, tk.Toplevel)
        self.assertEqual(self.ui.civ_name.get(), '羅馬')
        self.ui.open_picker()
        self.assertIs(self.ui.picker, first)
        changed = replace(self.match, players=(replace(self.match.players[0], civ_id=35), self.match.players[1]))
        self.app.show(changed, Path('new.aoe2record'), .5, False)
        self.ui.open_picker()
        self.assertEqual(self.ui.civ_name.get(), '勃根地')

    def test_direct_reader_keeps_all_stages_and_mark_when_returning(self):
        build = self.ui.builds[32]
        self.ui.open_build(build)
        reader = self.ui.direct
        self.assertEqual(len(reader.rows), 30)
        self.assertEqual(list(reader.ages), ['黑暗', '封建'])
        reader.mark(14)
        self.ui.back()
        self.ui.open_build(build)
        self.assertIs(self.ui.direct, reader)
        self.assertEqual(reader.selected, 14)
        self.assertEqual(reader.rows[14][0].cget('bg'), '#24473f')

    def test_separate_tab_survives_new_match_and_does_not_duplicate(self):
        build = self.ui.builds[0]
        self.ui.open_build(build, True)
        self.ui.open_build(build, True)
        self.assertEqual(len(self.app.workspace_book.tabs()), 2)
        reader = self.ui.readers[('tab', build.id)]
        reader.mark(5)
        self.app.show(self.match, Path('live.aoe2record'), .5, False)
        self.assertTrue(reader.winfo_exists())
        self.assertEqual(reader.selected, 5)
        self.assertEqual(self.app.workspace_book.select(), str(self.app.rp_frame))
        self.ui.close_tab(('tab', build.id))
        self.assertEqual(len(self.app.workspace_book.tabs()), 1)
        self.ui.open_build(build, True)
        self.assertEqual(self.ui.readers[('tab', build.id)].selected, 5)

    def test_promoting_direct_reader_does_not_duplicate_or_lose_mark(self):
        build = self.ui.builds[32]
        self.ui.open_build(build)
        self.ui.direct.mark(9)
        self.ui.open_build(build, True)
        self.assertNotIn(('direct', build.id), self.ui.readers)
        reader = self.ui.readers[('tab', build.id)]
        self.assertEqual(reader.selected, 9)
        self.ui.open_build(build, False)
        self.assertEqual(self.app.workspace_book.select(), str(reader))
        self.assertEqual(len(self.ui.readers), 1)

    def test_scroll_position_survives_switching_and_reopening(self):
        self.root.attributes('-alpha', 0.0)
        self.root.geometry('1200x800+0+0')
        self.root.deiconify()
        build = self.ui.builds[0]
        self.ui.open_build(build, True)
        self.root.update()
        reader = self.ui.readers[('tab', build.id)]
        reader.jump('封建')
        self.root.update()
        position = reader.scroll.canvas.yview()[0]
        self.assertGreater(position, 0)
        self.ui.back()
        self.root.update()
        self.ui.open_build(build, True)
        self.root.update()
        self.assertAlmostEqual(reader.scroll.canvas.yview()[0], position, places=2)
        self.ui.close_tab(('tab', build.id))
        self.ui.open_build(build, True)
        self.root.update()
        restored = self.ui.readers[('tab', build.id)]
        self.assertAlmostEqual(restored.scroll.canvas.yview()[0], position, places=2)

    def test_member_video_is_available_without_local_files(self):
        build = self.ui.builds[32]
        self.assertIsNone(build.video)
        self.ui.open_build(build)
        reader = self.ui.direct
        media = next(w for w in reader.media_bar.winfo_children() if w.cget('text') == '會員影片 ↗')
        with patch('build_views.webbrowser.open') as open_page:
            media.invoke()
        open_page.assert_called_once_with(build.video_url)

    def test_first_launch_without_media_or_old_settings(self):
        self.ui.directory = None
        self.ui.reload()
        self.assertEqual(len(self.ui.builds), 40)
        self.ui.open_picker()
        self.assertEqual(self.ui.civ_name.get(), '羅馬')
        self.ui.open_overview()
        self.assertEqual(self.app.workspace_book.select(), str(self.ui.overview_tab))

    def test_sidebar_toggle_and_missing_library_recovery_view(self):
        self.app.toggle_sidebar()
        self.assertFalse(self.app.sidebar.winfo_manager())
        self.app.toggle_sidebar()
        self.assertEqual(self.app.sidebar.winfo_manager(), 'pack')
        self.ui.directory = self.directory/'missing'
        self.ui.reload()
        self.ui.open_picker()
        self.assertEqual(len(self.ui.builds), 40)
        self.assertFalse(self.ui.error)
        self.assertIn('5 套流程', self.ui.count.cget('text'))

    def test_roman_reference_routes_from_picker_and_reader(self):
        self.ui.open_picker()
        buttons = self.ui.reference_bar.winfo_children()
        self.assertEqual(len(buttons), 1)
        buttons[0].invoke()
        sid = 'romans-castle-push'
        sheet = self.ui.reference_tabs[sid]
        self.ui.open_build(self.ui.builds[32])
        self.ui.reference_for(self.ui.builds[32])()
        self.assertIs(self.ui.reference_tabs[sid], sheet)
        self.assertEqual(self.app.workspace_book.select(), str(sheet))
        self.assertNotIn('burgundians-arena-castle', self.ui.reference_tabs)

    def test_reference_tab_reuses_and_preserves_build_progress(self):
        self.ui.open_picker()
        self.ui.civ_name.set('勃根地')
        self.ui.refresh_picker()
        buttons = self.ui.reference_bar.winfo_children()
        self.assertEqual(len(buttons), 1)
        build = self.ui.builds[14]
        self.ui.open_build(build)
        self.ui.direct.mark(7)
        buttons[0].invoke()
        sid = 'burgundians-arena-castle'
        sheet = self.ui.reference_tabs[sid]
        self.assertNotIsInstance(sheet, tk.Toplevel)
        self.ui.open_reference(sid)
        self.assertIs(self.ui.reference_tabs[sid], sheet)
        self.app.resize(1)
        self.assertEqual(sheet.size, self.app.font_size)
        self.ui.open_build(build)
        self.assertEqual(self.ui.direct.selected, 7)
        self.app.show(self.match, Path('live.aoe2record'), .5, False)
        self.assertTrue(sheet.winfo_exists())
        self.ui.close_reference(sid)
        self.assertNotIn(sid, self.ui.reference_tabs)

    def test_reference_cards_fill_the_area_and_scroll_only_below_the_floor(self):
        from types import SimpleNamespace
        self.ui.open_reference('burgundians-arena-castle')
        sheet = self.ui.reference_tabs['burgundians-arena-castle']

        def lay_out(width, height):
            sheet.reflow(SimpleNamespace(width=width, height=height))
            sheet.fit()
            return float(sheet.scroll.canvas.itemcget(sheet.scroll.window, 'height'))

        self.assertEqual(lay_out(1600, 1400), 1400)         # 3 x 2 cards fill the whole height
        self.assertEqual([sheet.cards[i].grid_info()['column'] for i in (1, 2)], [1, 2])
        self.assertEqual(sheet.cards[3].grid_info()['row'], 1)
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

    def test_existing_line_breaks_are_kept(self):
        self.assertEqual(wrap_text('甲乙\n丙丁', self.measure, 100), '甲乙\n丙丁')


if __name__ == '__main__':
    unittest.main()
