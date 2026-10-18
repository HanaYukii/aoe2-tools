"""Map names: a recording's map id looked up in the game's maps.json."""
import json
import re
from pathlib import Path

from civdata import find_game_dir, load_strings

SCENARIO = -3   # campaign and scenario games carry no random map


def load_map_names(game_dir=None, lang='tw'):
    """Map id -> localized name, for every map the installed game knows."""
    game_dir = Path(game_dir) if game_dir else find_game_dir()
    listing = json.loads((game_dir / 'resources' / '_common' / 'dat' / 'maps.json')
                         .read_text(encoding='utf-8'))['map_list']
    english = load_strings(game_dir, 'en')
    try:
        local = english if lang == 'en' else load_strings(game_dir, lang)
    except FileNotFoundError:
        local = english
    return {entry['storage_id']: (local.get(entry['name_string_id']) or english.get(entry['name_string_id'])
                                  or Path(entry.get('script_filename', '')).stem)
            for entry in listing if 'storage_id' in entry and 'name_string_id' in entry}


def map_label(match, names):
    """What to call the match's map; '' when the recording says nothing about it."""
    if match.map_file:
        return re.sub(r'\.rms2?$', '', match.map_file, flags=re.IGNORECASE)  # a mod's map script
    if match.map_id == SCENARIO:
        return '劇本／戰役'
    if match.map_id in names:
        return names[match.map_id]
    return f'未知地圖 #{match.map_id}' if match.map_id >= 0 else ''
