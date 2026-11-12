"""Opening coverage, population conventions and personalized-default regressions."""
import json
import tempfile
import unittest
from pathlib import Path

from build_library import (DATA_PATH, PDF_NAME, LibraryError, default_order,
                           load_library, opening_for, read_catalog, search_builds)
from i18n import set_language


ROOT = Path(__file__).resolve().parents[1]
NEW_OPENINGS = {'black-forest-fish-boom', 'romans-fast-castle-double-scorpions',
                'portuguese-fast-castle-organ-guns', 'lithuanians-four-lakes-fast-castle'}


class OpeningCatalogTests(unittest.TestCase):
    def tearDown(self):
        set_language('tw')

    def test_every_audited_guide_has_one_retained_destination(self):
        audit = json.loads((ROOT / 'docs/build-order-coverage.json').read_text())
        self.assertEqual(len(audit['entries']), 39)
        self.assertEqual(len({e['source_id'] for e in audit['entries']}), 39)
        added = {e['build_id'] for e in audit['entries'] if e['relation'] == 'new'}
        self.assertEqual(added, NEW_OPENINGS)
        for lang in ('tw', 'en', 'zh'):
            builds = {b.id: b for b in load_library(lang=lang)}
            self.assertTrue(all(e['build_id'] in builds for e in audit['entries']))
            self.assertEqual({b.id for b in builds.values() if b.index > 41}, NEW_OPENINGS)
            self.assertTrue(all(not builds[i].video_filename for i in NEW_OPENINGS))
            self.assertTrue(all(not builds[i].notes for i in NEW_OPENINGS))

    def test_search_finds_merged_openings_without_duplicate_variants(self):
        for lang, cases in (
            ('tw', {'雙靶場': 'hera-2026-10-14', '三肉馬': 'hera-2026-10-02',
                    '吃雞肉馬': 'hera-2026-10-19', '風琴炮': 'portuguese-fast-castle-organ-guns',
                    '四湖': 'lithuanians-four-lakes-fast-castle'}),
            ('en', {'three scouts': 'hera-2026-10-02', 'two range': 'hera-2026-10-14',
                    'YouPudding': 'romans-fast-castle-double-scorpions',
                    'Phosphoru': 'portuguese-fast-castle-organ-guns'}),
            ('zh', {'双靶场': 'hera-2026-10-14', '风琴炮': 'portuguese-fast-castle-organ-guns'}),
        ):
            set_language(lang)
            builds = load_library()
            for query, ident in cases.items():
                self.assertEqual([b.id for b in search_builds(builds, query=query)], [ident], (lang, query))

    def test_shared_flank_guide_is_playable_without_ethiopian_bonuses(self):
        builds = load_library(lang='tw')
        flank = next(b for b in builds if b.index == 14)
        self.assertEqual(flank.compatibility('Britons'), 'ready')
        self.assertEqual(flank.compatibility('Romans'), 'ready')
        self.assertIn(flank.id, [b.id for b in default_order(builds, 'Ethiopians')])
        self.assertIn(flank.id, [b.id for b in default_order(builds, 'Britons')])
        self.assertNotIn(flank.id, [b.id for b in default_order(builds, 'Romans')])

    def test_roman_three_maa_opening_delays_mill_and_preserves_default_id(self):
        for lang, dark, feudal, mill_word in (
            ('tw', '黑暗', '封建', '磨坊'), ('en', 'Dark Age', 'Feudal Age', 'mill'),
        ):
            builds = load_library(lang=lang)
            roman = next(b for b in builds if b.id == 'hera-2026-10-33')
            self.assertEqual(roman.population, '19')
            self.assertEqual(default_order(builds, 'Romans')[0].id, roman.id)
            self.assertTrue(roman.video_filename.startswith('24-'))
            self.assertEqual(roman.page, 47)
            dark_rows = [s for s in roman.steps if s.age == dark]
            self.assertEqual(dark_rows[-1].wood, '3')
            self.assertEqual(dark_rows[-1].population, '19')
            first_feudal = next(i for i,s in enumerate(roman.steps) if s.age == feudal)
            self.assertIn('裝甲' if lang == 'tw' else 'Man-at-Arms', roman.steps[first_feudal].task)
            # The mill is explicitly deferred rather than another Dark Age worker assignment.
            self.assertIn('不採果' if lang == 'tw' else 'delay berries', ' '.join(s.task for s in dark_rows).lower())
            mill_rows = [i for i,s in enumerate(roman.steps) if s.age == feudal and mill_word in s.task]
            self.assertTrue(mill_rows and min(mill_rows) > first_feudal)
            self.assertFalse(any('後兩隻' in s.task or 'reinforce with 2' in s.task for s in roman.steps))
            self.assertNotIn('romans-fast-castle-double-scorpions', [b.id for b in default_order(builds, 'Romans')])

    def test_burgundian_relic_default_stays_the_personalized_opening(self):
        for lang in ('tw', 'en', 'zh'):
            ordered = default_order(load_library(lang=lang), 'Burgundians')
            for label in ('Arena', '競技場', '竞技场'):
                self.assertEqual(opening_for(list(reversed(ordered)), label).id, 'burgundians-arena-relics')

    def test_simplified_search_and_compound_map_names(self):
        set_language('zh')
        self.assertEqual([b.index for b in search_builds(load_library(), query='蔷琵')], [6])
        maps = json.loads((DATA_PATH.parent/'map-notes.zh-CN.json').read_text())
        desert = next(n for n in maps['maps'] if n['id'] == 'arabian-desert')
        self.assertTrue(desert['title'].startswith('阿拉伯沙漠'))
        self.assertNotIn('阿拉伯半岛沙漠', desert['aliases'])

    def test_fishing_population_excludes_ships_and_gillnets_follows_castle(self):
        builds = {b.id:b for b in load_library(lang='en')}
        lith = builds['lithuanians-four-lakes-fast-castle']
        self.assertEqual(lith.population, '21＋2')
        self.assertIn('seven Dark Age Fishing Ships', ' '.join(s.task for s in lith.steps))
        for ident in ('black-forest-fish-boom', 'lithuanians-four-lakes-fast-castle'):
            build = builds[ident]
            gillnets = [s for s in build.steps if 'Gillnets' in s.task]
            self.assertTrue(gillnets)
            self.assertTrue(all(s.age == 'Castle Age' for s in gillnets))
            self.assertTrue(any('Fishing Lines' in s.task for s in build.steps))

    def test_new_openings_do_not_attach_an_unrelated_local_pdf(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/PDF_NAME).touch()
            builds = load_library(folder, lang='tw')
            self.assertTrue(next(b for b in builds if b.index == 1).pdf)
            self.assertTrue(all(b.pdf is None for b in builds if b.id in NEW_OPENINGS))

    def test_invalid_search_metadata_is_rejected(self):
        for field, value in (('aliases', 'not a list'), ('aliases', [None]),
                             ('recommended_for', {'Britons': True})):
            with tempfile.TemporaryDirectory() as folder:
                data = json.loads(DATA_PATH.read_text())
                data['builds'][0][field] = value
                path = Path(folder)/'builds.json'
                path.write_text(json.dumps(data))
                with self.assertRaises(LibraryError):
                    load_library(data_path=path)
