"""Language parity and real English UI flow, independent from personal recordings."""
import argparse
import gc
import json
import re
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from i18n import DATA, set_language, tr, default_language
from build_library import load_library, read_catalog, search_builds, sheets_for, LibraryState
from build_views import reference_highlights
from map_notes import load_map_notes, note_for_map
from dashboard import Dashboard
from demo import populate


class TranslationTests(unittest.TestCase):
    def tearDown(self):
        set_language('tw')

    def test_catalog_parity_and_translated_display_fields(self):
        zh, en = read_catalog(lang='tw'), read_catalog(lang='en')
        self.assertEqual(len(en['builds']), 41)
        self.assertEqual(sum(len(b['steps']) for b in en['builds']), 953)
        for a, b in zip(zh['builds'], en['builds']):
            for field in ('id', 'index', 'population', 'civs', 'map_type', 'starter', 'advanced', 'video_filename'):
                self.assertEqual(a[field], b[field])
            for x, y in zip(a['steps'], b['steps']):
                for field in ('population', 'allocation', 'wood', 'food', 'gold', 'stone'):
                    self.assertEqual(x[field], y[field])
                self.assertNotRegex(y['task'] + y['age'], r'[\u4e00-\u9fff]')
            for field in ('title', 'notes', 'recommended_civs', 'arrival'):
                self.assertNotRegex(b[field], r'[\u4e00-\u9fff]')
        for a,b in zip(zh['reference_sheets'], en['reference_sheets']):
            for field in ('id', 'civ', 'build_ids', 'maps', 'era'):
                self.assertEqual(a.get(field), b.get(field))
            self.assertEqual(len(a['cards']), len(b['cards']))
            self.assertNotRegex(b['title'] + b['subtitle'], r'[\u4e00-\u9fff]')
            for c in b['cards']:
                self.assertNotRegex(c['title'] + c['body'], r'[\u4e00-\u9fff]')
        a,b=load_map_notes(lang='tw'),load_map_notes(lang='en')
        self.assertEqual(len(b),28)
        for x,y in zip(a,b):
            for field in ('id','aliases','map_ids'):
                self.assertEqual(x.get(field),y.get(field))
            self.assertNotRegex(y['title']+y['subtitle'],r'[\u4e00-\u9fff]')
            for c in y['cards']:
                self.assertNotRegex(c['title']+c['body'],r'[\u4e00-\u9fff]')

    def test_english_search_map_matching_and_highlights(self):
        set_language('en')
        builds=load_library()
        self.assertTrue(any(b.index==33 for b in search_builds(builds,'Romans','MAA')))
        self.assertTrue(any(b.index==15 for b in search_builds(builds,'Burgundians','FC')))
        self.assertTrue(search_builds(builds,query='23+2'))
        self.assertEqual(note_for_map(load_map_notes(),'競技場',29)['id'],'arena')
        roman=next(b for b in builds if b.index==33)
        self.assertTrue(sheets_for(read_catalog()['reference_sheets'],'Romans',roman,'Arabia'))
        spans=reference_highlights('Bodkin Arrow, Ballistics; 12–14 wood / 6 gold. Hand Cart.')
        self.assertEqual([s[0] for s in spans].count('tech'),3)
        self.assertEqual([s[0] for s in spans].count('eco'),2)

    def test_default_locale_and_formatting(self):
        with patch('i18n.locale.getlocale',return_value=('en_US','UTF-8')):
            self.assertEqual(default_language(),'en')
        with patch('i18n.locale.getlocale',return_value=('zh_TW','UTF-8')):
            self.assertEqual(default_language(),'tw')
        set_language('en')
        self.assertEqual(tr('最近 {0} 場',10),'Recent 10 games')
        set_language('tw')
        self.assertEqual(tr('最近 {0} 場',10),'最近 10 場')

    def test_english_dashboard_and_all_guides_render(self):
        root=tk.Tk(); root.withdraw()
        app=None
        try:
            with tempfile.TemporaryDirectory() as directory, patch('build_views.LibraryState',return_value=LibraryState(Path(directory)/'state.json')):
                args=argparse.Namespace(lang='en',demo=True,no_elo=True,game_dir=None)
                app=Dashboard(root,args);populate(app)
                self.assertEqual(app.workspace_book.tab(app.rp_frame,'text'),'Match')
                self.assertEqual(app.civs[43].name,'Romans')
                self.assertEqual(len({str(w.cget('image')) for w in app.reminders}),9)
                for b in app.library.builds:
                    app.library.pick(b)
                    self.assertEqual(len(app.library.readers[b.id].rows),len(b.steps))
                for sid in app.library.sheets:
                    app.library.open_sheet(sid)
                for note in app.library.map_tab.notes:
                    app.library.map_tab.show(note)
                app.library.pick(next(b for b in app.library.builds if b.index==33))
                root.update_idletasks()
                self.assertIn('Roman',app.library.title.cget('text'))
                self.assertIn('Click a step',app.library.readers[app.library.build.id].position_label.cget('text'))
                # UI state can be English, but the history query uses stable internal keys.
                app.dirs=[]
                with patch('dashboard.recent_matches',return_value=([],0)) as recent:
                    app.refresh_history()
                    app.pool.shutdown(wait=True)
                    recent.assert_called_once_with([], '多人')
        finally:
            if app: app.close()
            else: root.destroy()
            app=root=None
            gc.collect()
