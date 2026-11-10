"""Small offline translation layer for UI text and bundled guide selection."""
import json
import locale
from pathlib import Path

DATA = Path(__file__).resolve().parent / 'data'
CATALOGS = {'tw': 'zh-TW', 'zh': 'zh-CN', 'en': 'en'}  # language -> suffix of its bundled catalogs
_language = 'tw'
_english = json.loads((DATA / 'ui.en.json').read_text(encoding='utf-8'))
_simplified = json.loads((DATA / 'ui.zh-CN.json').read_text(encoding='utf-8'))  # written by make_zh_cn.py


def default_language():
    try:
        name = (locale.getlocale()[0] or '').lower()
    except (ValueError, TypeError):
        name = ''
    # POSIX names look like zh_CN; Windows ones like "Chinese (Simplified)_China".
    if name.startswith(('zh_cn', 'zh-cn', 'zh_sg', 'zh-sg', 'zh_hans', 'zh-hans', 'chinese_china')) or 'simplified' in name:
        return 'zh'
    return 'tw' if name.startswith(('zh', 'chinese')) else 'en'


def set_language(language):
    global _language
    _language = language if language in CATALOGS else 'tw'


def language():
    return _language


def tr(text, *args):
    translated = {'en': _english, 'zh': _simplified}.get(_language, {}).get(text, text)
    return translated.format(*args) if args else translated


def catalog_path(name, lang=None):
    return DATA / f'{name}.{CATALOGS.get(lang or _language, "zh-TW")}.json'
