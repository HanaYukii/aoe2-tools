import copy
import json
import tempfile
import unittest
from pathlib import Path
from map_notes import load_map_notes, note_for_map


class MapNotesTests(unittest.TestCase):
    def setUp(self):
        self.notes = load_map_notes()

    def test_every_map_matches_localized_names_and_ids(self):
        for note in self.notes:
            for alias in note['aliases']:
                self.assertEqual(note_for_map(self.notes, alias)['id'], note['id'])
            for mid in note['map_ids']:
                self.assertEqual(note_for_map(self.notes, '未知地圖', mid)['id'], note['id'])

    def test_titles_use_the_game_names_and_the_map_icon(self):
        from ui_icons import sheet_icon
        migration = note_for_map(self.notes, '遷徙')  # the game's name for map 21
        self.assertEqual(migration['id'], 'migration')
        self.assertTrue(migration['title'].startswith('遷徙'))
        self.assertTrue(all(sheet_icon(note) == 'map' for note in self.notes))

    def test_similar_names_do_not_overlap(self):
        self.assertEqual(note_for_map(self.notes, 'Nomad')['id'], 'nomad')
        self.assertEqual(note_for_map(self.notes, 'Land Nomad')['id'], 'land-nomad')
        for label in ['QS Arena', 'EM Arabia', 'Not Arabia', 'Water Nomad', '']:
            self.assertIsNone(note_for_map(self.notes, label))

    def test_custom_filename_takes_precedence_over_generic_map_id(self):
        self.assertEqual(note_for_map(self.notes, '', 9, 'Socotra.rms')['id'], 'socotra')
        self.assertIsNone(note_for_map(self.notes, '阿拉伯', 9, 'Tournament Arabia v5.rms'))
        self.assertIsNone(note_for_map(self.notes, '未知地圖 #999', 999))

    def test_ambiguous_aliases_are_rejected(self):
        notes = copy.deepcopy(self.notes)
        notes[1]['aliases'].append(notes[0]['aliases'][0])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'notes.json'
            path.write_text(json.dumps({'schema_version': 1, 'maps': notes}))
            with self.assertRaises(ValueError):
                load_map_notes(path)
