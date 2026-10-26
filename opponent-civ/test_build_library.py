"""Local library parsing, eligibility and persistence without membership assets."""
import json
import tempfile
import unittest
from pathlib import Path
from build_library import GUIDE_NAME, LibraryError, LibraryState, load_library, filter_builds


def write_fixture(directory):
    # Synthetic operations, not redistributed course content.
    body = []
    for index in range(1, 41):
        body.append(f'## {index:02} 20 人口｜測試流程 {index}\n\n| 階段 | 配村 | 操作 | 木 | 食 | 金 | 石 | 人口 |\n')
        body.extend(f'| {"黑暗" if n < 12 else "封建"} | 1 | 測試步驟 {n}。 | 4 | 10 | 2 | 0 | {n+1} |\n' for n in range(30))
    (directory / GUIDE_NAME).write_text(''.join(body), encoding='utf-8')


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        write_fixture(self.directory)
        self.builds = load_library(self.directory)

    def test_parse_complete_guide_and_reject_partial(self):
        self.assertEqual(len(self.builds), 40)
        self.assertEqual(self.builds[32].page, 69)
        self.assertEqual(self.builds[0].steps[0].wood, '4')
        path = self.directory / GUIDE_NAME
        path.write_text(path.read_text().split('## 40')[0], encoding='utf-8')
        with self.assertRaises(LibraryError):
            load_library(self.directory)

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

    def test_video_manifest_matches_page_and_rejects_path_traversal(self):
        folder = self.directory/'Hera-會員流程影片'
        folder.mkdir()
        ((folder/'sample.mp4').resolve()).touch()
        (self.directory/'outside.mp4').touch()
        (folder/'影片清單.json').write_text(json.dumps([{'pdf_page':5,'file':'sample.mp4'}, {'pdf_page':7,'file':'../outside.mp4'}]))
        builds = load_library(self.directory)
        self.assertEqual(builds[0].video, (folder/'sample.mp4').resolve())
        self.assertIsNone(builds[1].video)

    def test_missing_and_corrupt_state(self):
        path = self.directory/'state.json'
        path.write_text('{broken')
        self.assertEqual(LibraryState(path).favorites('Romans'), [])
        path.write_text('{"positions": [], "favorites": []}')
        self.assertEqual(LibraryState(path).data['positions'], {})


if __name__ == '__main__':
    unittest.main()
