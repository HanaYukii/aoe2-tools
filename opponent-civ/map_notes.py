"""Compact map guidance, independent from civilization-specific build orders."""
import json
import re
from pathlib import Path
from urllib.parse import urlparse

DATA_PATH = Path(__file__).resolve().parent / 'data' / 'map-notes.zh-TW.json'


def normalized(value):
    return ''.join(c for c in re.sub(r'\.rms2?$', '', value, flags=re.I).casefold() if c.isalnum())


def load_map_notes(path=DATA_PATH):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('schema_version') != 1 or not isinstance(data.get('maps'), list):
        raise ValueError('invalid map notes catalog')
    seen_ids, seen_aliases, seen_maps = set(), set(), set()
    for note in data['maps']:
        if not all(isinstance(note.get(k), str) and note[k] for k in ('id', 'title', 'subtitle')):
            raise ValueError('invalid map note')
        if note['id'] in seen_ids:
            raise ValueError('duplicate map note')
        seen_ids.add(note['id'])
        if not isinstance(note.get('aliases'), list) or not note['aliases']:
            raise ValueError('missing map aliases')
        aliases = set()
        for alias in note['aliases']:
            if not isinstance(alias, str) or not normalized(alias):
                raise ValueError('invalid map alias')
            aliases.add(normalized(alias))
        if seen_aliases & aliases:
            raise ValueError('ambiguous map aliases')
        seen_aliases.update(aliases)
        if not isinstance(note.get('map_ids'), list) or any(type(i) is not int for i in note['map_ids']):
            raise ValueError('invalid map IDs')
        if seen_maps & set(note['map_ids']):
            raise ValueError('ambiguous map IDs')
        seen_maps.update(note['map_ids'])
        if not isinstance(note.get('cards'), list) or not note['cards']:
            raise ValueError('missing map cards')
        for card in note['cards']:
            if not all(isinstance(card.get(k), str) and card[k] for k in ('title', 'body')):
                raise ValueError('invalid map card')
        for source in note.get('sources', []):
            if not source.get('title') or urlparse(source.get('url', '')).scheme != 'https':
                raise ValueError('invalid map source')
    return data['maps']


def note_for_map(notes, label='', map_id=None, map_file=''):
    # Named custom maps take precedence over their often generic recorded map ID.
    # Exact normalized aliases prevent Nomad/Land Nomad and Arena/QS Arena overlap.
    if not map_file and map_id is not None:
        found = next((n for n in notes if map_id in n['map_ids']), None)
        if found:
            return found
    name = normalized(map_file or label)
    return next((n for n in notes if name and name in {normalized(a) for a in n['aliases']}), None)
