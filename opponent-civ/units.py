"""Each civ's unique units: what they are, what beats them, what they beat.

civilizations.json lists every civ's unique units as (name, description) string
ids. A description's second line says what the unit is and carries
"Strong vs. ..." / "Weak vs. ..." sentences. The counter lists are parsed from
the English text, whose phrasing is uniform (the Chinese phrasing varies unit
to unit), then mapped to the game's own Traditional Chinese unit names; the
rest is the localized text as the game shows it.

    python units.py          # every civ's units, plus any counter term not yet mapped
"""
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from civdata import find_game_dir, load_civs, load_strings

STRING_FILES = ('key-value-strings-utf8.txt', 'key-value-paphos-strings-utf8.txt')  # the second: Chronicles civs

# English counter terms -> the game's Traditional Chinese names: unit names as
# the game's strings spell them (Skirmisher = 矛兵, Spearman = 長槍兵), classes
# as its own unit descriptions most often translate them.
TERMS = {'tw': {
    'Infantry': '步兵',
    'Cavalry': '騎兵',
    'Mounted Units': '騎乘單位',
    'Mounted Archers': '騎乘弓兵',
    'Archery Units': '弓兵單位',
    'Foot Archers': '步弓兵',
    'Foot Archers at long range': '遠距離的步弓兵',
    'Ranged Soldiers': '遠程士兵',
    'Ranged Soldiers at long range': '遠距離的遠程士兵',
    'Gunners': '火槍兵',
    'Gunpowder Units': '火藥單位',
    'Skirmishers': '矛兵',
    'Skirmisher-line': '矛兵系',
    'Spearman-line': '長槍兵系',
    'Militia-line': '民兵系',
    'Scout Cavalry-line': '偵察騎兵系',
    'Camel Riders': '駱駝騎兵',
    'Eagle Warriors': '鷹勇士',
    'Monks': '僧侶',
    'Monastery Units': '修道院單位',
    'Priestesses': '女祭司',
    'Unique Units': '特殊單位',
    'Siege Weapons': '攻城武器',
    'Mangonel-line': '輕型投石車系',
    'buildings': '建築',
    'Galleys': '戰船',
    'Galley-line': '戰船系',
    'most Warships': '大多數戰艦',
    'Fire Ships': '火戰船',
    'Demolition Ships': '爆破船',
    'large groups of ships': '大群船隻',
    'large groups of units': '大群單位',
    'tight groups of units': '密集的單位群',
    'melee units': '近戰單位',
    'units at close range': '近戰單位',
    'units at range': '遠距離的單位',
    'units at medium and close range': '中近距離的單位',
    'slow, non-ranged units': '移動緩慢的非遠程單位',
    'especially Elephants': '尤其是大象單位',
    'especially with high armor': '尤其是高護甲單位',
}}

COUNTER = re.compile(r'(Exceptionally strong|Strong|Weak) vs\. ([^.]*)\.')
IN_NUMBERS = 'Strong in high numbers.'
SPLIT = re.compile(r',\s*(?:and\s+)?|\s+and\s+')
PHRASES = sorted((t for t in TERMS['tw'] if ',' in t or ' and ' in t), key=len, reverse=True)  # items SPLIT would cut
EN_COUNTER_SENTENCE = re.compile(r'\s*(?:(?:Exceptionally strong|Strong|Weak) vs\. [^.]*\.|Strong in high numbers\.)')
TW_COUNTER_CLAUSE = re.compile(
    r'擅|克制|剋制|不敵|較強|較弱|很強的攻擊|強勢|弱勢|克敵|反制|優勢|劣勢|不利|越多越強|對[^，]{1,10}(?:強大|特別強)'
    r'|^\s*尤其')  # "擅長對付騎乘單位，尤其是戰象" continues the clause before it


@dataclass(frozen=True)
class UniqueUnit:
    name: str
    summary: str             # the description without its counter sentences
    loses_to: tuple          # what to fight it with
    beats: tuple             # what not to send at it
    beats_hard: tuple        # ... and what it is exceptionally strong against
    strong_in_numbers: bool
    upgrades: str            # e.g. "升級：攻擊、射程、護甲 (兵工廠)；...", may be empty
    unmapped: tuple          # English terms with no translation yet, shown as-is


def english_items(clause):
    """'Infantry, Scout Cavalry- and Skirmisher-line' -> its items, in order."""
    for index, phrase in enumerate(PHRASES):
        clause = clause.replace(phrase, f'\0{index}\0')
    items = []
    for item in SPLIT.split(clause):
        item = item.strip()
        if item.startswith('\0'):
            item = PHRASES[int(item.strip('\0'))]
        if item:
            items.append(item + 'line' if item.endswith('-') else item)
    return items


def summary(line, lang):
    if lang == 'tw':  # clause by clause: "義大利獨特的步弓兵，特別擅長對抗騎兵。" keeps its first half
        sentences = []
        for sentence in line.split('。'):
            kept = [c for c in sentence.split('，') if c.strip() and not TW_COUNTER_CLAUSE.search(c)]
            if kept:
                sentences.append('，'.join(kept))
        return '。'.join(sentences) + '。' if sentences else ''
    if lang == 'en':
        return EN_COUNTER_SENTENCE.sub('', line).strip()
    return line


def described(text):
    lines = text.split('\n')
    return lines[1] if len(lines) > 1 else ''


def build_unit(ids, local, english, lang):
    localized = local.get(ids['description'])
    text = localized or english.get(ids['description'], '')
    english_line = described(english.get(ids['description'], ''))
    table = TERMS.get(lang)
    lists = {'Weak': [], 'Strong': [], 'Exceptionally strong': []}
    unmapped = []
    for kind, clause in COUNTER.findall(english_line):
        for item in english_items(clause):
            name = table.get(item) if table else item
            if name is None:
                unmapped.append(item)
                name = item
            if name not in lists[kind]:
                lists[kind].append(name)
    upgrades = next((line for line in text.split('\n') if '<GREY>' in line), '')
    return UniqueUnit(
        name=local.get(ids['name']) or english.get(ids['name'], '?'),
        summary=summary(described(text), lang if localized else 'en'),
        loses_to=tuple(lists['Weak']),
        beats=tuple(lists['Strong']),
        beats_hard=tuple(lists['Exceptionally strong']),
        strong_in_numbers=IN_NUMBERS in english_line,
        upgrades=re.sub(r'<[^>]+>', '', upgrades).strip(),
        unmapped=tuple(unmapped),
    )


def all_strings(game_dir, lang):
    strings = {}
    for filename in STRING_FILES:
        try:
            strings = {**load_strings(game_dir, lang, filename), **strings}  # earlier files win
        except FileNotFoundError:
            pass
    return strings


def load_unique_units(game_dir=None, lang='tw'):
    """Map civ id -> tuple of UniqueUnit, text in `lang`."""
    game_dir = Path(game_dir) if game_dir else find_game_dir()
    listing = json.loads((game_dir / 'resources' / '_common' / 'dat' / 'civilizations.json')
                         .read_text(encoding='utf-8'))['civilization_list']
    local = all_strings(game_dir, lang)
    english = local if lang == 'en' else all_strings(game_dir, 'en')
    units = {}
    for civ_id, entry in enumerate(listing):
        found = tuple(build_unit(ids, local, english, lang) for ids in entry.get('unique_unit_string_ids', []))
        if found:
            units[civ_id] = found
    return units


def main():
    if not sys.stdout.isatty():
        sys.stdout.reconfigure(encoding='utf-8')
    lang = sys.argv[1] if len(sys.argv) > 1 else 'tw'
    civs = load_civs(lang=lang)
    units = load_unique_units(lang=lang)
    unmapped = set()
    for civ_id, found in sorted(units.items()):
        print(f'== {civs[civ_id].name}')
        for unit in found:
            print(f'  {unit.name}：{unit.summary}')
            print(f'    用這些打：{"、".join(unit.loses_to) or "—"}')
            print(f'    特別克制：{"、".join(unit.beats_hard) or "—"}  克制：{"、".join(unit.beats) or "—"}'
                  + ('  數量多時很強' if unit.strong_in_numbers else ''))
            unmapped.update(unit.unmapped)
    print(f'\n{len(units)} 個文明、{sum(map(len, units.values()))} 個特殊兵種；未對應的英文詞：{sorted(unmapped) or "無"}')


if __name__ == '__main__':
    main()
