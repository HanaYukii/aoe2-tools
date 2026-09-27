"""Civilization names and tech-tree descriptions, read from the installed game.

`civilizations.json` lists civs in id order (the id recordings store) with the
string ids of each civ's name and tech-tree description; the language folder's
key-value file holds the official text for those ids.
"""
import json
import os
import re
import winreg
from dataclasses import dataclass
from pathlib import Path

DEFAULT_GAME_DIR = Path(r'C:\Program Files (x86)\Steam\steamapps\common\AoE2DE')
STRING_LINE = re.compile(r'^(\d+)\s+"((?:[^"\\]|\\.)*)"')
ESCAPE = re.compile(r'\\(.)')


@dataclass(frozen=True)
class Civ:
    id: int
    key: str           # internal English name, e.g. "Britons"
    name: str          # localized name
    description: str   # localized tech-tree description, plain text


def find_game_dir():
    if os.environ.get('AOE2DE_DIR'):
        return Path(os.environ['AOE2DE_DIR'])
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam') as key:
            steam = Path(winreg.QueryValueEx(key, 'SteamPath')[0])
    except OSError:
        return DEFAULT_GAME_DIR
    libraries = [steam]
    try:
        vdf = (steam / 'steamapps' / 'libraryfolders.vdf').read_text(encoding='utf-8')
        libraries += [Path(p.replace('\\\\', '\\')) for p in re.findall(r'"path"\s+"([^"]+)"', vdf)]
    except OSError:
        pass
    for library in libraries:
        game_dir = library / 'steamapps' / 'common' / 'AoE2DE'
        if (game_dir / 'resources').is_dir():
            return game_dir
    return DEFAULT_GAME_DIR


def load_strings(game_dir, lang):
    path = game_dir / 'resources' / lang / 'strings' / 'key-value' / 'key-value-strings-utf8.txt'
    strings = {}
    with open(path, encoding='utf-8-sig') as handle:
        for line in handle:
            match = STRING_LINE.match(line)
            if match:
                text = ESCAPE.sub(lambda e: '\n' if e.group(1) == 'n' else e.group(1), match.group(2))
                strings[int(match.group(1))] = text
    return strings


def load_civs(game_dir=None, lang='tw'):
    """Map civ id -> Civ, text in `lang` (a folder under resources/, e.g. tw, en)."""
    game_dir = Path(game_dir) if game_dir else find_game_dir()
    listing = json.loads((game_dir / 'resources' / '_common' / 'dat' / 'civilizations.json')
                         .read_text(encoding='utf-8'))['civilization_list']
    strings = load_strings(game_dir, lang)
    english = strings if lang == 'en' else load_strings(game_dir, 'en')

    def text(string_id):
        return strings.get(string_id) or english.get(string_id, '')

    civs = {}
    for civ_id, entry in enumerate(listing):
        description_id = entry.get('tech_tree_description_string_id')
        if description_id is None:  # Gaia
            continue
        civs[civ_id] = Civ(
            id=civ_id,
            key=entry['internal_name'],
            name=text(entry['name_string_id']) or entry['internal_name'],
            description=text(description_id).replace('<b>', '').strip(),
        )
    return civs
