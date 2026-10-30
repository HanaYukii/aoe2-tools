"""Small offline translation layer for UI text and bundled guide selection."""
import json
import locale
from pathlib import Path

DATA = Path(__file__).resolve().parent / 'data'
_language = 'tw'
_english = json.loads((DATA / 'ui.en.json').read_text(encoding='utf-8'))


def default_language():
    try:
        name = locale.getlocale()[0] or ''
    except (ValueError, TypeError):
        name = ''
    return 'tw' if name.lower().startswith('zh') else 'en'


def set_language(language):
    global _language
    _language = 'en' if language == 'en' else 'tw'


def language():
    return _language


def tr(text, *args):
    translated = _english.get(text, text) if _language == 'en' else text
    return translated.format(*args) if args else translated


def catalog_path(name, lang=None):
    return DATA / f'{name}.{"en" if (lang or _language) == "en" else "zh-TW"}.json'
