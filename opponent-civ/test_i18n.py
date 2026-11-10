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

import ast
from i18n import DATA, set_language, tr, default_language
from build_library import load_library, map_kind, read_catalog, search_builds, sheets_for, LibraryState
from build_views import reference_highlights
from map_notes import load_map_notes, note_for_map
from dashboard import Dashboard
from demo import populate
from units import COUNTER_CLAUSE, TERMS, summary


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


# Characters that exist only in Traditional script; none may survive in generated Simplified text.
TRADITIONAL = re.compile('[們個時當點對與這為無經裝騎劍戰馬術區應會從體學實際議圖產農礦鐵築隊開關]')
# Fields make_zh_cn.py copies as they are (ids, file names) or keeps alongside a Simplified copy.
COPIED = {'id', 'civs', 'civ', 'map_type', 'video_filename', 'build_ids', 'era', 'url', 'aliases', 'maps'}


def converted_text(value, key=None):
    if isinstance(value, dict):
        for k, v in value.items():
            yield from converted_text(v, k)
    elif isinstance(value, list) and key not in COPIED:
        for v in value:
            yield from converted_text(v, key)
    elif isinstance(value, str) and key not in COPIED:
        yield value


class SimplifiedChineseTests(unittest.TestCase):
    def tearDown(self):
        set_language('tw')

    def test_simplified_catalogs_mirror_traditional_ones(self):
        for name, items in (('builds', 'builds'), ('map-notes', 'maps')):
            tw = json.loads((DATA / f'{name}.zh-TW.json').read_text(encoding='utf-8'))
            cn = json.loads((DATA / f'{name}.zh-CN.json').read_text(encoding='utf-8'))
            self.assertEqual([x['id'] for x in tw[items]], [x['id'] for x in cn[items]], 'rerun make_zh_cn.py')
            for a, b in zip(tw[items], cn[items]):
                self.assertEqual(len(a.get('steps', a.get('cards', []))), len(b.get('steps', b.get('cards', []))))
                self.assertEqual(a.get('video_filename'), b.get('video_filename'))  # local videos keep their names
            for text in converted_text(cn):
                self.assertNotRegex(text, TRADITIONAL)
        tw, cn = read_catalog(lang='tw'), read_catalog(lang='zh')
        self.assertEqual([s['id'] for s in tw['reference_sheets']], [s['id'] for s in cn['reference_sheets']])
        for a, b in zip(tw['reference_sheets'], cn['reference_sheets']):
            self.assertEqual(len(a['cards']), len(b['cards']))
            self.assertTrue(set(a['maps']) <= set(b['maps']))  # map matching keeps the Traditional words

    def test_every_ui_string_has_a_simplified_translation(self):
        table = json.loads((DATA / 'ui.zh-CN.json').read_text(encoding='utf-8'))
        keys = set(json.loads((DATA / 'ui.en.json').read_text(encoding='utf-8')))
        for path in Path(__file__).resolve().parent.glob('*.py'):
            if path.name.startswith('test_') or path.name == 'make_zh_cn.py':
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'tr'
                        and node.args and isinstance(node.args[0], ast.Constant)):
                    keys.add(node.args[0].value)
        self.assertEqual(sorted(keys - set(table)), [], 'rerun make_zh_cn.py')
        for text in table.values():
            self.assertNotRegex(text, TRADITIONAL)

    def test_simplified_language_selection_and_terms(self):
        with patch('i18n.locale.getlocale', return_value=('zh_CN', 'UTF-8')):
            self.assertEqual(default_language(), 'zh')
        with patch('i18n.locale.getlocale', return_value=('Chinese (Simplified)_China', '936')):
            self.assertEqual(default_language(), 'zh')
        with patch('i18n.locale.getlocale', return_value=('Chinese (Traditional)_Taiwan', '950')):
            self.assertEqual(default_language(), 'tw')
        set_language('zh')
        self.assertEqual(tr('最近 {0} 場', 10), '最近 10 场')
        builds = load_library()
        self.assertTrue(search_builds(builds, '', 'MAA'))
        self.assertTrue(all('武士' in b.title for b in search_builds(builds, '', 'MAA')))
        roman = next(s for s in read_catalog()['reference_sheets'] if s['id'] == 'romans-vs-cavalry-archers')
        self.assertIn('掷矛手', roman['cards'][0]['body'])     # 矛兵 would read as a Spearman in Simplified
        self.assertNotIn('矛兵', roman['cards'][0]['body'])
        self.assertEqual([s[0] for s in reference_highlights('先精锐＋二级射，再点弹道学、手推车')].count('tech'), 4)
        self.assertEqual(note_for_map(load_map_notes(), '竞技场', 29)['id'], 'arena')

    def test_map_kinds_use_each_languages_official_names(self):
        for label, kind in (('竞技场', 'closed'), ('藏身之处', 'closed'), ('藏身之處', 'closed'),
                            ('阿拉伯半岛', 'open'), ('堡垒', 'fortress'), ('要塞', 'fortress')):
            self.assertEqual(map_kind(label), kind, label)

    def test_simplified_unit_text_drops_counter_sentences(self):
        self.assertEqual(set(TERMS['zh']), set(TERMS['tw']))
        self.assertIn('zh', COUNTER_CLAUSE)
        line = '罗马的独特重装骑兵，可提高附近民兵系单位的移动速度和攻击速度。适于攻击步兵和步弓手。不适于攻击长矛兵系和骆驼骑兵。'
        self.assertEqual(summary(line, 'zh'), '罗马的独特重装骑兵，可提高附近民兵系单位的移动速度和攻击速度。')
