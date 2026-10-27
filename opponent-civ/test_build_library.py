"""Local library parsing, eligibility and persistence without membership assets."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from build_library import DATA_PATH, LibraryError, LibraryState, load_library, filter_builds, media_file, read_catalog


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
        roman = [b.index for b in filter_builds(self.builds, 'Romans', filter_map=False)]
        self.assertEqual(roman, [33, 1, 2, 15, 22])
        maya = filter_builds(self.builds, 'Mayans', filter_map=False)
        self.assertNotIn(2, [b.index for b in maya])
        self.assertEqual(self.builds[0].compatibility('Mayans'), 'adjust')
        self.assertEqual([b.index for b in filter_builds(self.builds, '', filter_map=False)], [1, 2, 15, 22])

    def test_map_filter_and_full_search(self):
        rows = filter_builds(self.builds, 'Burgundians', '競技場')
        self.assertEqual([b.index for b in rows], [15])
        self.assertEqual(len(filter_builds(self.builds, mode='all', query='流程 33')), 1)
        self.assertEqual(len(filter_builds(self.builds, map_label='自訂地圖', mode='all')), 40)

    def test_favorites_are_per_civilization_and_restore(self):
        state = LibraryState(self.directory/'state.json')
        state.toggle_favorite('Romans', self.builds[30].id)
        loaded = LibraryState(state.path)
        self.assertEqual(loaded.favorites('romans'), [self.builds[30].id])
        self.assertFalse(loaded.favorites('Burgundians'))
        self.assertEqual(filter_builds(self.builds, 'Romans', favorites=loaded.favorites('Romans'), filter_map=False)[0].index, 31)
        loaded.toggle_favorite('Romans', self.builds[30].id)
        self.assertFalse(loaded.favorites('Romans'))

    def test_bundled_content_is_complete_without_media(self):
        builds = load_library(self.directory/'does-not-exist')
        self.assertEqual(len(builds), 40)
        self.assertEqual(sum(len(b.steps) for b in builds), 920)
        self.assertEqual(sum(bool(b.video_url) for b in builds), 38)
        self.assertTrue(all(b.video is None and b.pdf is None for b in builds))
        self.assertIn('動物配置', read_catalog()['overview'])

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
        self.assertTrue(builds[0].video_url.startswith('https://www.patreon.com/'))
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
        data['builds'][0]['video_url'] = 'file:///local-file'
        self.catalog.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaises(LibraryError):
            load_library(data_path=self.catalog)

    def test_missing_and_corrupt_state(self):
        path = self.directory/'state.json'
        path.write_text('{broken')
        self.assertEqual(LibraryState(path).favorites('Romans'), [])
        path.write_text('{"positions": [], "favorites": []}')
        self.assertEqual(LibraryState(path).data['positions'], {})


if __name__ == '__main__':
    unittest.main()
