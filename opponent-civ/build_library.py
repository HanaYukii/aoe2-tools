"""Read a user's local Chinese guide; never bundle membership materials in the app."""
import json
import re
from dataclasses import dataclass
from pathlib import Path
from app_paths import app_data_dir

GUIDE_NAME = 'Hera-2026-10-完整繁中攻略-可編輯文字.md'
PDF_NAME = 'Hera-2026-10-完整繁中攻略-台灣玩家用語.pdf'
STATE_PATH = app_data_dir() / 'builds.json'
# Guide indices are specific to this local 2026-10, 40-build edition.
STARTERS = {1, 2, 15, 22}
SPECIAL = {4: ('armenians',), 5: ('burgundians',), 6: ('incas', 'mapuche', 'muisca', 'tupi'),
           7: ('chinese',), 8: ('cumans',), 9: ('danes',), 10: ('aztecs', 'incas', 'mayans'),
           13: ('aztecs', 'incas', 'mayans'), 14: ('ethiopians',), 23: ('georgians',),
           24: ('japanese',), 25: ('jurchens', 'koreans', 'vietnamese', 'chinese', 'khitans'),
           26: ('khmer',), 27: ('khmer',), 29: ('koreans', 'byzantines', 'lithuanians'),
           30: ('malay',), 32: ('portuguese',), 33: ('romans',), 34: ('saxons',),
           38: ('teutons',), 39: ('turks',), 40: ('varangians',)}
CLOSED = {15, 16, 17, 39}
ADVANCED = {3, 4, 5, 6, 8, 25, 26, 27, 32, 34, 38, 39, 40}
CAVALRY = {2, 11, 16, 28, 35, 36, 37}
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

    @property
    def starter(self):
        return self.index in STARTERS

    def compatibility(self, civ_key):
        civ_key = key(civ_key)
        if not civ_key:
            return 'unknown'
        if self.civs and civ_key not in self.civs:
            return 'other'
        if self.index in CAVALRY and civ_key in MESO:
            return 'unavailable'
        if not self.civs and civ_key in {'chinese', 'mayans'}:
            return 'adjust'
        return 'ready'


class LibraryError(ValueError):
    pass


def load_library(directory):
    """Parse the local editable guide and optional verified video manifest."""
    directory = Path(directory).expanduser().resolve()
    guide = directory / GUIDE_NAME
    if not guide.is_file():
        raise LibraryError('這個資料夾沒有中文版流程文字檔，請選 Hera 教材資料夾。')
    parts = re.split(r'(?m)^## (\d+) ([^\n]+)\n', guide.read_text(encoding='utf-8'))
    videos = {}
    manifest = directory / 'Hera-會員流程影片' / '影片清單.json'
    if manifest.is_file():
        for item in json.loads(manifest.read_text(encoding='utf-8')):
            # Only match files inside the chosen library, never arbitrary paths.
            filename = item.get('file', '')
            if Path(filename).name == filename:
                path = directory / 'Hera-會員流程影片' / filename
                if path.is_file():
                    videos[item['pdf_page']] = path
    pdf = directory / PDF_NAME
    builds = []
    for pos in range(1, len(parts), 3):
        number, heading, body = parts[pos:pos+3]
        index = int(number)
        match = re.fullmatch(r'(.+?) 人口(?:＋3 漁船)?｜(.+)', heading.strip())
        if not match:
            raise LibraryError(f'第 {index} 套流程標題格式無法辨識。')
        population, title = match.groups()
        if '＋3 漁船' in heading:
            title += '（＋3 漁船）'
        steps = []
        for line in body.splitlines():
            if re.match(r'\| (黑暗|升封途中|封建|升城途中|城堡|升帝途中|帝王) \|', line):
                fields = [v.strip() for v in line.strip('|').split('|')]
                if len(fields) != 8:
                    raise LibraryError(f'第 {index} 套流程的配工表欄位不完整。')
                steps.append(Step(*fields))
        if not steps:
            raise LibraryError(f'第 {index} 套流程沒有配工表。')
        page = 5+(index-1)*2
        notes = body.split('### 打法目的', 1)[-1].strip() if '### 打法目的' in body else ''
        kind = 'fortress' if index == 18 else 'water' if index == 21 else 'closed' if index in CLOSED else 'open'
        builds.append(Build(index, f'hera-2026-10-{index:02}', title, population, SPECIAL.get(index, ()),
                            kind, index in ADVANCED, tuple(steps), notes, page,
                            videos.get(page), pdf if pdf.is_file() else None))
    if len(builds) != 40 or {b.index for b in builds} != set(range(1, 41)):
        raise LibraryError('目前支援 2026 年 10 月的 40 套中文版流程，這份內容不完整或版本不同。')
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
