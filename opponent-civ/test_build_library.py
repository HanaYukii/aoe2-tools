"""Local library parsing, eligibility and persistence without membership assets."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from build_library import (DATA_PATH, LibraryError, LibraryState, default_order, load_library, media_file, opening_for,
                           read_catalog, search_builds, sheets_for)


def write_fixture(directory):
    data = read_catalog()
    for item in data['builds']:
        item['title'] = f"測試流程 {item['index']}"
        item['notes'] = '測試筆記'
        item['steps'] = [dict(age='黑暗' if n < 12 else '封建', allocation='1', task=f'測試步驟 {n}',
                              wood='4', food='10', gold='2', stone='0', population=str(n+1)) for n in range(30)]
    path = directory / 'builds.json'
    path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    return path


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.catalog = write_fixture(self.directory)
        self.builds = load_library(data_path=self.catalog)

    def test_parse_complete_guide_and_reject_partial(self):
        self.assertEqual(len(self.builds), 40)
        self.assertEqual(self.builds[32].page, 69)
        self.assertEqual(self.builds[0].steps[0].wood, '4')
        data = read_catalog(self.catalog)
        data['builds'][0]['steps'] = []
        self.catalog.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaises(LibraryError):
            load_library(data_path=self.catalog)

    def test_civilization_defaults_and_unavailable_cavalry(self):
        self.assertEqual([b.index for b in default_order(self.builds, 'Romans')], [33, 1, 2, 15, 22])
        self.assertNotIn(2, [b.index for b in default_order(self.builds, 'Mayans')])
        self.assertEqual(self.builds[0].compatibility('Mayans'), 'adjust')
        self.assertEqual([b.index for b in default_order(self.builds, '')], [1, 2, 15, 22])

    def test_opening_suits_the_map_and_search_covers_everything(self):
        burgundian = default_order(self.builds, 'Burgundians')
        self.assertEqual(opening_for(burgundian, '競技場').index, 15)
        self.assertEqual(opening_for(burgundian, '阿拉伯').index, 1)
        self.assertEqual(opening_for(burgundian, '自訂地圖').index, 1)  # unknown map: simply the first
        self.assertEqual(opening_for(burgundian, '堡壘').index, 1)      # nothing suits: the first too
        self.assertIsNone(opening_for([], '阿拉伯'))
        self.assertEqual([b.index for b in search_builds(self.builds, query='流程 33')], [33])
        everything = search_builds(self.builds, 'Romans')
        self.assertEqual(len(everything), 40)
        other = [b.compatibility('Romans') in {'other', 'unavailable'} for b in everything]
        self.assertEqual(other, sorted(other))  # playable builds first

    def test_recommended_order_is_per_civilization_and_restores(self):
        state = LibraryState(self.directory/'state.json')
        def order(civ, source=state):
            return [b.index for b in source.recommended(self.builds, civ)]
        self.assertEqual(order('Burgundians'), [1, 2, 15, 22])
        for _ in range(2):
            state.move(self.builds, 'Burgundians', self.builds[21].id, -1)
        state.move(self.builds, 'Burgundians', self.builds[0].id, -1)  # already first: stays
        self.assertEqual(order('Burgundians'), [1, 22, 2, 15])
        state.remove(self.builds, 'Burgundians', self.builds[1].id)
        state.add(self.builds, 'Burgundians', self.builds[4].id)
        loaded = LibraryState(state.path)
        self.assertEqual(order('burgundians', loaded), [1, 22, 15, 5])  # a removed default stays out
        self.assertEqual(order('Romans', loaded), [33, 1, 2, 15, 22])
        state.add(self.builds, 'Burgundians', self.builds[1].id)
        self.assertEqual(order('Burgundians'), [1, 22, 15, 5, 2])
        state.data['order']['britons'] = [self.builds[21].id]  # saved before the other defaults existed
        self.assertEqual(order('Britons'), [22, 1, 2, 15])
        state.data['favorites']['romans'] = [self.builds[30].id]  # a star from an older version leads
        self.assertEqual(order('Romans')[0], 31)

    def test_bundled_content_is_complete_without_media(self):
        builds = load_library(self.directory/'does-not-exist')
        self.assertEqual(len(builds), 40)
        self.assertEqual(sum(len(b.steps) for b in builds), 920)
        self.assertFalse([b for b in read_catalog()['builds'] if 'video_url' in b])  # no member video links
        self.assertTrue(all(b.video is None and b.pdf is None for b in builds))
        self.assertIn('動物配置', read_catalog()['overview'])

    def test_sheets_for_a_match_by_civilization_build_and_map(self):
        sheets = read_catalog(self.catalog)['reference_sheets']
        def ids(civ, index=None, map_label=''):
            build = self.builds[index - 1] if index else None
            return [s['id'] for s in sheets_for(sheets, civ, build, map_label)]
        self.assertEqual(ids('Britons', 1, '競技場'), ['arena-castle-drop'])  # every civilization, on Arena only
        self.assertEqual(ids('Britons', 1, 'Arena 2'), ['arena-castle-drop'])
        self.assertEqual(ids('Britons', 15, '阿拉伯'), [])  # the Burgundian sheet for build 15 is not theirs
        self.assertEqual(ids('Burgundians', 15, '競技場'), ['burgundians-arena-castle', 'burgundians-arena-defense', 'arena-castle-drop'])
        self.assertEqual(ids('Romans', 1, ''), ['romans-castle-push'])
        self.assertEqual(ids('', 16, '阿拉伯'), ['burgundians-arena-castle'])  # no civilization: the build's own
        data = read_catalog(self.catalog)
        data['reference_sheets'][-1]['maps'] = []  # a sheet for every civilization must name its maps
        self.catalog.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaises(LibraryError):
            read_catalog(self.catalog)

    def test_reference_shortcuts_reject_malformed_actions(self):
        data = read_catalog(self.catalog)
        data['reference_sheets'][-1]['shortcut'] = {'id': 'castle-drop-defense', 'label': ''}
        self.catalog.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaises(LibraryError):
            read_catalog(self.catalog)

    def test_reference_sheets_reject_unknown_build_links(self):
        data = read_catalog(self.catalog)
        data['reference_sheets'][0]['build_ids'] = ['missing-build']
        self.catalog.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaises(LibraryError):
            read_catalog(self.catalog)

    def test_optional_media_uses_known_filename_without_a_manifest(self):
        folder = self.directory/'Hera-會員流程影片'
        folder.mkdir()
        filename = self.builds[0].video_filename
        (folder/filename).touch()
        builds = load_library(self.directory, data_path=self.catalog)
        self.assertEqual(builds[0].video, (folder/filename).resolve())
        self.assertIsNone(builds[1].video)
        self.assertIsNone(media_file(self.directory, '../outside.mp4'))
        self.assertIsNone(media_file(self.directory, r'..\outside.mp4'))

    def test_unreadable_optional_media_does_not_break_builtins(self):
        with patch('build_library.Path.resolve', side_effect=PermissionError('unavailable drive')):
            builds = load_library(self.directory)
        self.assertEqual(len(builds), 40)
        self.assertTrue(all(b.video is None for b in builds))

    def test_duplicate_ids_and_unsafe_links_are_rejected(self):
        data = read_catalog(self.catalog)
        data['builds'][1]['id'] = data['builds'][0]['id']
        self.catalog.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaises(LibraryError):
            load_library(data_path=self.catalog)
        self.catalog = write_fixture(self.directory)
        data = read_catalog(self.catalog)
        data['reference_sheets'][0]['sources'][0]['url'] = 'file:///local-file'
        self.catalog.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaises(LibraryError):
            load_library(data_path=self.catalog)

    def test_missing_and_corrupt_state(self):
        path = self.directory/'state.json'
        path.write_text('{broken')
        self.assertEqual(LibraryState(path).favorites('Romans'), [])
        path.write_text('{"positions": {"a": {"row": 3}}, "favorites": [], "order": {"romans": "broken"}}')
        state = LibraryState(path)
        self.assertNotIn('positions', state.data)  # marks no longer outlive a game
        self.assertEqual(state.favorites('Romans'), [])
        self.assertEqual([b.index for b in state.recommended(self.builds, 'Romans')], [33, 1, 2, 15, 22])


if __name__ == '__main__':
    unittest.main()
