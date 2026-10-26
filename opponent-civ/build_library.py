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
    video_url: str = ''
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
        return data
    except (OSError, ValueError, AttributeError) as exc:
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
            url = item.get('video_url', '')
            parsed = urlparse(url)
            if url and (parsed.scheme != 'https' or parsed.hostname not in {'www.patreon.com', 'patreon.com'}):
                raise ValueError('invalid video link')
            filename = item.get('video_filename', '')
            builds.append(Build(
                index=item['index'], id=item['id'], title=item['title'], population=item['population'],
                civs=tuple(item['civs']), map_type=item['map_type'], advanced=item['advanced'],
                steps=steps, notes=item['notes'], page=item['page'],
                video=media_file(media_dir, filename), pdf=media_file(media_dir, PDF_NAME),
                starter=item['starter'], requires_cavalry=item['requires_cavalry'],
                video_url=url, video_filename=filename,
                recommended_civs=item.get('recommended_civs', ''), arrival=item.get('arrival', '')))
        if not builds:
            raise ValueError('empty catalog')
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise LibraryError('內建流程資料不完整，請重新下載完整版本。') from exc
    return builds


def filter_builds(builds, civ_key='', map_label='', query='', mode='recommended', favorites=(), filter_map=True):
    """Separate applicable defaults from the full library; never imply automatic match strategy."""
    kind = map_kind(map_label) if filter_map else None
    terms = query.casefold().replace('maa', '裝甲').replace('fc', '直城').strip()
    result = []
    for b in builds:
        compatibility = b.compatibility(civ_key)
        if mode != 'all' and compatibility in {'other', 'unavailable'}:
            continue
        if kind and b.map_type != kind:
            continue
        if mode == 'favorites' and b.id not in favorites:
            continue
        if mode == 'recommended' and b.id not in favorites:
            if compatibility == 'adjust' or b.advanced or not (b.starter or (b.civs and civ_key)):
                continue
        if terms and terms not in (b.title+' '+b.population).casefold():
            continue
        result.append(b)
    return sorted(result, key=lambda b: (b.id not in favorites, not bool(b.civs), not b.starter, b.index))


class LibraryState:
    def __init__(self, path=STATE_PATH):
        self.path = Path(path)
        try:
            self.data = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(self.data, dict):
                self.data = {}
        except (OSError, ValueError):
            self.data = {}
        for field in ('favorites', 'positions'):
            if not isinstance(self.data.get(field), dict):
                self.data[field] = {}

    def favorites(self, civ_key):
        ids = self.data['favorites'].get(key(civ_key), [])
        return ids if isinstance(ids, list) else []

    def toggle_favorite(self, civ_key, build_id):
        ids = list(self.favorites(civ_key))
        ids.remove(build_id) if build_id in ids else ids.append(build_id)
        self.data['favorites'][key(civ_key)] = ids
        self.save()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(self.path)
