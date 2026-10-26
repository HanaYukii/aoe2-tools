"""Open the dashboard with the game, on the screen the game does not cover.

AoE2 in full screen will not Alt+Tab back to the desktop, so the desktop game
icon runs the dashboard with --with-game: the window opens first, where it
was last closed (the first time: on a non-primary monitor, since the game
takes the primary one), then Steam starts the game as usual.
"""
import ctypes
import json
import os
import sys
import subprocess
import re
from ctypes import wintypes
from pathlib import Path
from app_paths import app_data_dir

GAME_URL = 'steam://rungameid/813780'
MUTEX_NAME = 'aoe2-tools-dashboard'
STATE_PATH = app_data_dir() / 'window.json'
ERROR_ALREADY_EXISTS = 183
MONITORINFOF_PRIMARY = 1
MARGIN = 40

user32 = ctypes.windll.user32 if sys.platform == 'win32' else None
kernel32 = ctypes.windll.kernel32 if sys.platform == 'win32' else None
_mutex = None


class MONITORINFO(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT),
                ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD)]


def claim_single_instance():
    """False if another dashboard already holds the mutex; ours lives until exit."""
    global _mutex
    if kernel32 is None:
        return True
    _mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    return kernel32.GetLastError() != ERROR_ALREADY_EXISTS


def start_game():
    if sys.platform == 'win32':
        os.startfile(GAME_URL)
    else:
        subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', GAME_URL])


def work_areas():
    """[(left, top, right, bottom, primary)] per monitor, in this process's coordinates."""
    areas = []
    if user32 is None:
        return areas
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
                                       ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

    def each(monitor, _dc, _rect, _data):
        info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
        user32.GetMonitorInfoW(monitor, ctypes.byref(info))
        work = info.rcWork
        areas.append((work.left, work.top, work.right, work.bottom, bool(info.dwFlags & MONITORINFOF_PRIMARY)))
        return True

    user32.EnumDisplayMonitors(None, None, callback_type(each), 0)
    return areas


def place(root, width, height, areas=None):
    """Keep off the primary screen whenever there is another one, since the game covers it.

    The last closed spot is reused if its screen is still there and is not the
    primary while a second screen exists: a spot saved during a laptop-only
    session would otherwise land under the game once the monitor is back.
    """
    areas = work_areas() if areas is None else areas
    if not areas:
        areas = [(0, 0, root.winfo_screenwidth(), root.winfo_screenheight(), True)]
    others = [area for area in areas if not area[4]]
    try:
        state = json.loads(STATE_PATH.read_text(encoding='utf-8'))
        x, y = state['x'], state['y']
        screen = next((a for a in areas if a[0] <= x + MARGIN < a[2] and a[1] <= y + MARGIN < a[3]), None)
        # Old versions saved small windows. Apply the new 90% default once.
        if screen and (not others or not screen[4]) and state.get('layout_version') == 2:
            left, top, right, bottom, _ = screen
            w = min(max(320, int(state['width'])), right-left-20)
            h = min(max(240, int(state['height'])), bottom-top-20)
            x = min(max(left, x), right-w)
            y = min(max(top, y), bottom-h)
            root.geometry(f"{w}x{h}+{x}+{y}")
            if state.get('zoomed') and sys.platform == 'win32':
                root.state('zoomed')
            return
    except (OSError, ValueError, KeyError, TypeError):
        pass
    left, top, right, bottom, _ = others[0] if others else areas[0]
    width, height = round((right-left)*.9), round((bottom-top)*.9)
    x, y = left + (right-left-width)//2, top + (bottom-top-height)//2
    root.geometry(f'{width}x{height}+{x}+{y}')


def remember(root):
    """Save where the window is; skipped for hidden windows (tests, previews)."""
    match = re.fullmatch(r'(\d+)x(\d+)\+(-?\d+)\+(-?\d+)', root.geometry())
    if not root.winfo_viewable() or not match:
        return
    width, height, x, y = map(int, match.groups())
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(dict(x=x, y=y, width=width, height=height,
                                              zoomed=root.state() == 'zoomed', layout_version=2)), encoding='utf-8')
    except OSError:
        pass
