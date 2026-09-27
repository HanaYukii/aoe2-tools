"""Unique-unit counters: parsing checks on game text, plus the installed game end to end."""
import unittest

from civdata import find_game_dir, load_civs
from units import build_unit, english_items, load_unique_units, summary

IDS = {'name': 1, 'description': 2}
# Strings as the game ships them (Longbowman).
EN = {1: 'Longbowman', 2: 'Create <b>Longbowman<b> (<cost>)\nBritish unique Foot Archer with exceptional range. '
                          'Strong vs. Infantry. Weak vs. Cavalry and Skirmishers. \n<GREY><i>Upgrades: attack, range, '
                          'armor (Blacksmith).<i><DEFAULT>\n<hp> <attack> <armor> <piercearmor> <range>'}
TW = {1: '長弓兵', 2: '生產<b>長弓兵<b> (<cost>)\n英國特殊步弓兵，擁有出色的射程。擅長對抗步兵。不擅長對抗騎兵和矛兵。\n'
                     '<GREY><i>升級：攻擊、射程、護甲 (兵工廠)。<i><DEFAULT>\n<hp> <attack> <armor> <piercearmor> <range>'}


class UnitTextTests(unittest.TestCase):
    def test_counters_from_english_in_game_names(self):
        unit = build_unit(IDS, TW, EN, 'tw')
        self.assertEqual(unit.name, '長弓兵')
        self.assertEqual(unit.summary, '英國特殊步弓兵，擁有出色的射程。')
        self.assertEqual(unit.loses_to, ('騎兵', '矛兵'))  # the Traditional Chinese game calls Skirmishers 矛兵
        self.assertEqual(unit.beats, ('步兵',))
        self.assertEqual(unit.beats_hard, ())
        self.assertEqual(unit.upgrades, '升級：攻擊、射程、護甲 (兵工廠)。')
        self.assertEqual(unit.unmapped, ())

    def test_english_items(self):
        self.assertEqual(english_items('buildings, Scout Cavalry- and Skirmisher-line'),
                         ['buildings', 'Scout Cavalry-line', 'Skirmisher-line'])
        self.assertEqual(english_items('Infantry, Monks, and Foot Archers'), ['Infantry', 'Monks', 'Foot Archers'])
        self.assertEqual(english_items('slow, non-ranged units'), ['slow, non-ranged units'])
        self.assertEqual(english_items('Cavalry and units at medium and close range'),
                         ['Cavalry', 'units at medium and close range'])

    def test_summary_drops_only_counter_clauses(self):
        self.assertEqual(summary('義大利獨特的步弓兵，特別擅長對抗騎兵。不擅長對抗弓兵單位和攻城武器。', 'tw'),
                         '義大利獨特的步弓兵。')
        self.assertEqual(summary('韃靼人的獨特爆破攻城騎兵。擅長對付騎乘單位，尤其是戰象。不擅長對付步弓兵和步兵。使用時會自爆。', 'tw'),
                         '韃靼人的獨特爆破攻城騎兵。使用時會自爆。')
        hero = '蜀國獨特的步兵英雄，能治療周圍的所有單位。非常強大。有一項限制，無法招降。'
        self.assertEqual(summary(hero, 'tw'), hero)
        self.assertEqual(summary('Italian unique Foot Archer. Exceptionally strong vs. Cavalry. Weak vs. Archery Units.', 'en'),
                         'Italian unique Foot Archer.')

    def test_exceptional_numbers_and_unknown_terms(self):
        english = {1: 'X', 2: 'Create X\nA unit. Exceptionally strong vs. Infantry. Strong in high numbers. Weak vs. Dragons.\n'}
        unit = build_unit(IDS, {}, english, 'tw')
        self.assertEqual(unit.beats_hard, ('步兵',))
        self.assertTrue(unit.strong_in_numbers)
        self.assertEqual(unit.loses_to, ('Dragons',))  # shown as-is rather than dropped
        self.assertEqual(unit.unmapped, ('Dragons',))
        self.assertEqual(unit.summary, 'A unit.')


@unittest.skipUnless((find_game_dir() / 'resources').is_dir(), 'AoE2 DE is not installed')
class InstalledGameTests(unittest.TestCase):
    def test_every_civ_has_mapped_unique_units(self):
        civs, units = load_civs(), load_unique_units()
        self.assertEqual(set(units), set(civs))
        self.assertEqual({t for found in units.values() for unit in found for t in unit.unmapped}, set())
        self.assertTrue(all(unit.summary for found in units.values() for unit in found))


if __name__ == '__main__':
    unittest.main()
