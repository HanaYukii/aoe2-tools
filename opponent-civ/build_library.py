"""Bundled Chinese build orders with optional local media attachments."""
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from app_paths import app_data_dir

DATA_PATH = Path(__file__).resolve().parent / 'data' / 'builds.zh-TW.json'
PDF_NAME = 'Hera-2026-10-完整繁中攻略-台灣玩家用語.pdf'
STATE_PATH = app_data_dir() / 'builds.json'
MESO = {'aztecs', 'mayans', 'incas'}


def key(value):
    return re.sub(r'[^a-z]', '', value.lower())


def map_kind(label):
    label = label.lower()
    if any(s in label for s in ('競技場', 'arena', '黑森林', 'black forest', '避難所', 'hideout')):
        return 'closed'
    if any(s in label for s in ('阿拉伯', 'arabia', '陸地', 'land')):
        return 'open'
    if any(s in label for s in ('堡壘', 'fortress')):
        return 'fortress'
    return None  # Unknown/custom maps must not silently exclude builds.


@dataclass(frozen=True)
class Step:
    age: str
    allocation: str
    task: str
    wood: str
    food: str
    gold: str
    stone: str
    population: str


@dataclass(frozen=True)
class Build:
    index: int
    id: str
    title: str
    population: str
    civs: tuple
    map_type: str
    advanced: bool
    steps: tuple
    notes: str
    page: int
    video: Path | None
    pdf: Path | None

    starter: bool = False
    requires_cavalry: bool = False
    video_filename: str = ''
    recommended_civs: str = ''
    arrival: str = ''

    def compatibility(self, civ_key):
        civ_key = key(civ_key)
        if not civ_key:
            return 'unknown'
        if self.civs and civ_key not in self.civs:
            return 'other'
        if self.requires_cavalry and civ_key in MESO:
            return 'unavailable'
        if not self.civs and civ_key in {'chinese', 'mayans'}:
            return 'adjust'
        return 'ready'


class LibraryError(ValueError):
    pass


def read_catalog(data_path=None):
    try:
        data = json.loads(Path(data_path or DATA_PATH).read_text(encoding='utf-8'))
        if data.get('schema_version') != 1 or not isinstance(data.get('builds'), list):
            raise ValueError('unsupported catalog')
        sheet_ids = set()
        build_ids = {b['id'] for b in data['builds']}
        for sheet in data.get('reference_sheets', []):
            if not all(isinstance(sheet.get(k), str) and sheet[k] for k in ('id', 'title', 'subtitle')):
                raise ValueError('invalid reference sheet')
            maps = sheet.setdefault('maps', [])
            if not isinstance(sheet.get('civ'), str) or not isinstance(maps, list) or not all(isinstance(m, str) and m for m in maps):
                raise ValueError('invalid reference sheet')
            # A sheet for every civilization ('civ' empty) must name the maps it is for.
            if sheet['id'] in sheet_ids or not sheet.get('cards') or not isinstance(sheet.get('build_ids'), list) or not (sheet['civ'] or maps):
                raise ValueError('invalid reference sheet')
            sheet_ids.add(sheet['id'])
            if any(i not in build_ids for i in sheet['build_ids']):
                raise ValueError('unknown reference build')
            for card in sheet['cards']:
                if not all(isinstance(card.get(k), str) and card[k] for k in ('title', 'body')):
                    raise ValueError('invalid reference card')
            for source in sheet.get('sources', []):
                if not isinstance(source.get('title'), str) or urlparse(source.get('url', '')).scheme != 'https':
                    raise ValueError('invalid reference source')
        return data
    except (OSError, ValueError, AttributeError, KeyError, TypeError) as exc:
        raise LibraryError('內建流程資料無法讀取，請重新下載完整版本。') from exc


def media_file(directory, filename):
    """Resolve only the known file names inside the optional media directory."""
    if not directory or not filename or Path(filename).name != filename or '/' in filename or '\\' in filename:
        return None
    try:
        root = Path(directory).expanduser().resolve()
        for parent in (root, root / 'Hera-會員流程影片'):
            candidate = (parent / filename).resolve()
            if candidate.is_relative_to(root) and candidate.is_file():
                return candidate
    except (OSError, ValueError, RuntimeError):
        pass  # An unavailable optional drive cannot disable the bundled guide.
    return None


def load_library(media_dir=None, *, data_path=None):
    """Always read bundled steps. Missing optional videos/PDF never hide builds."""
    data = read_catalog(data_path)
    builds, ids, indices = [], set(), set()
    try:
        for item in data['builds']:
            if not isinstance(item['index'], int) or item['index'] <= 0:
                raise ValueError('invalid index')
            if item['id'] in ids or item['index'] in indices:
                raise ValueError('duplicate build')
            ids.add(item['id'])
            indices.add(item['index'])
            for field in ('id', 'title', 'population', 'notes'):
                if not isinstance(item[field], str) or not item[field]:
                    raise ValueError('missing text')
            if item['map_type'] not in {'open', 'closed', 'water', 'fortress'}:
                raise ValueError('invalid map')
            if not isinstance(item['civs'], list) or not all(isinstance(c, str) for c in item['civs']):
                raise ValueError('invalid civilizations')
            for field in ('starter', 'advanced', 'requires_cavalry'):
                if not isinstance(item[field], bool):
                    raise ValueError('invalid flag')
            steps = tuple(Step(**step) for step in item['steps'])
            if not steps or any(not step.task or not step.age or not all(isinstance(v, str) for v in vars(step).values()) for step in steps):
                raise ValueError('invalid steps')
            filename = item.get('video_filename', '')
            builds.append(Build(
                index=item['index'], id=item['id'], title=item['title'], population=item['population'],
                civs=tuple(item['civs']), map_type=item['map_type'], advanced=item['advanced'],
                steps=steps, notes=item['notes'], page=item['page'],
                video=media_file(media_dir, filename), pdf=media_file(media_dir, PDF_NAME),
                starter=item['starter'], requires_cavalry=item['requires_cavalry'], video_filename=filename,
                recommended_civs=item.get('recommended_civs', ''), arrival=item.get('arrival', '')))
        if not builds:
            raise ValueError('empty catalog')
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise LibraryError('內建流程資料不完整，請重新下載完整版本。') from exc
    return builds


def default_order(builds, civ_key='', favorites=()):
    """A civilization's recommendations before the user orders them: old favorites, its own
    builds, then the general starters. Advanced and adjusted openings wait in the full list."""
    result = []
    for b in builds:
        compatibility = b.compatibility(civ_key)
        if compatibility in {'other', 'unavailable'}:
            continue
        if b.id not in favorites and (compatibility == 'adjust' or b.advanced or not (b.starter or (b.civs and civ_key))):
            continue
        result.append(b)
    return sorted(result, key=lambda b: (b.id not in favorites, not bool(b.civs), not b.starter, b.index))


def search_builds(builds, civ_key='', query=''):
    """Every build whose title or population matches; ones the civilization can play come first."""
    terms = query.casefold().replace('maa', '裝甲').replace('fc', '直城').strip()
    found = [b for b in builds if terms in (b.title+' '+b.population).casefold()]
    return sorted(found, key=lambda b: (b.compatibility(civ_key) in {'other', 'unavailable'}, b.index))


def sheets_for(sheets, civ_key='', build=None, map_label=''):
    """The sheets for a match: the civilization's own, those for `build` first, then the ones for
    every civilization on this map. A sheet that lists maps applies only on them. Without a
    civilization, only a sheet for the build counts as its own."""
    civ, label = key(civ_key), map_label.casefold()

    def linked(sheet):
        return build is not None and build.id in sheet['build_ids']

    def on_map(sheet):
        return not sheet['maps'] or any(word.casefold() in label for word in sheet['maps'])
    own = [s for s in sheets if s['civ'] and (s['civ'] == civ if civ else linked(s)) and on_map(s)]
    return sorted(own, key=lambda s: not linked(s)) + [s for s in sheets if not s['civ'] and on_map(s)]


def opening_for(builds, map_label=''):
    """The first build that suits the map; simply the first when the map is unknown or none suits."""
    kind = map_kind(map_label)
    return next((b for b in builds if b.map_type == kind), builds[0] if builds else None)


class LibraryState:
    """Each civilization's recommended builds in the user's own order."""
    def __init__(self, path=STATE_PATH):
        self.path = Path(path)
        try:
            self.data = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(self.data, dict):
                self.data = {}
        except (OSError, ValueError):
            self.data = {}
        for field in ('favorites', 'order', 'removed'):
            if not isinstance(self.data.get(field), dict):
                self.data[field] = {}
        self.data.pop('positions', None)  # reading marks now last one game, not across launches

    def ids(self, field, civ_key):
        ids = self.data[field].get(key(civ_key), [])
        return [i for i in ids if isinstance(i, str)] if isinstance(ids, list) else []

    def favorites(self, civ_key):
        """Stars from older versions; they only lead the default order now."""
        return self.ids('favorites', civ_key)

    def recommended(self, builds, civ_key):
        """The user's order, then any default they never removed (such as a newly bundled build)."""
        by_id = {b.id: b for b in builds}
        removed = set(self.ids('removed', civ_key))
        defaults = [b.id for b in default_order(builds, key(civ_key), self.favorites(civ_key)) if b.id not in removed]
        return [by_id[i] for i in dict.fromkeys(self.ids('order', civ_key) + defaults) if i in by_id]

    def move(self, builds, civ_key, build_id, offset):
        ids = [b.id for b in self.recommended(builds, civ_key)]
        if build_id in ids:
            here = ids.index(build_id)
            ids.insert(max(0, min(len(ids) - 1, here + offset)), ids.pop(here))
            self.store(builds, civ_key, ids)

    def add(self, builds, civ_key, build_id):
        ids = [b.id for b in self.recommended(builds, civ_key)]
        self.store(builds, civ_key, ids if build_id in ids else ids + [build_id])

    def remove(self, builds, civ_key, build_id):
        self.store(builds, civ_key, [b.id for b in self.recommended(builds, civ_key) if b.id != build_id])

    def store(self, builds, civ_key, ids):
        """Keep the whole list; a default left out of it stays out."""
        defaults = [b.id for b in default_order(builds, key(civ_key), self.favorites(civ_key))]
        self.data['order'][key(civ_key)] = ids
        self.data['removed'][key(civ_key)] = [i for i in defaults if i not in ids]
        self.save()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(self.path)
