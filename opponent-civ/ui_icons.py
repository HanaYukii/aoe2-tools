"""Bundled transparent artwork, cached per Tk interpreter (no runtime Pillow)."""
from pathlib import Path
import tkinter as tk

ASSETS = Path(__file__).resolve().parent / 'assets'


def icon(widget, name, size=24):
    root = widget._root()
    if not hasattr(root, '_ui_icons'):
        root._ui_icons = {}
    key = (name, size)
    if key not in root._ui_icons:
        root._ui_icons[key] = tk.PhotoImage(master=root, file=str(ASSETS / f'{name}-{size}.png'))
    return root._ui_icons[key]


def install_window_icon(root):
    root.iconphoto(True, *(icon(root, 'town-center', size) for size in (32, 48, 64, 128, 256)))


def sheet_icon(sheet):
    ident = sheet.get('id', '')
    if 'romans' in ident:
        return 'ram'
    if 'drop' in ident or 'defense' in ident:
        return 'combat'
    return 'economy'
