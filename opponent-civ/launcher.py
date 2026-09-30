"""Open the dashboard with the game, on the screen the game does not cover.

AoE2 in full screen will not Alt+Tab back to the desktop, so the desktop game
icon runs the dashboard with --with-game: the window opens first, where it
was last closed (the first time: on a non-primary monitor, since the game
takes the primary one), then Steam starts the game as usual.
"""
import ctypes
import json
import os
import re
from ctypes import wintypes
from pathlib import Path

GAME_URL = 'steam://rungameid/813780'
MUTEX_NAME = 'aoe2-tools-dashboard'
STATE_PATH = Path(os.environ['LOCALAPPDATA']) / 'aoe2-tools' / 'opponent-civ' / 'window.json'
ERROR_ALREADY_EXISTS = 183
MONITORINFOF_PRIMARY = 1
MARGIN = 40

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
_mutex = None


class MONITORINFO(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT),
                ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD)]


def claim_single_instance():
    """False if another dashboard already holds the mutex; ours lives until exit."""
    global _mutex
    _mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    return kernel32.GetLastError() != ERROR_ALREADY_EXISTS


def start_game():
    os.startfile(GAME_URL)


def work_areas():
    """[(left, top, right, bottom, primary)] per monitor, in this process's coordinates."""
    areas = []
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
    """Last closed spot if it is still on a screen, else a non-primary screen, else Tk's default."""
    areas = work_areas() if areas is None else areas
    try:
        state = json.loads(STATE_PATH.read_text(encoding='utf-8'))
        x, y = state['x'], state['y']
        if any(left <= x + MARGIN < right and top <= y + MARGIN < bottom for left, top, right, bottom, _ in areas):
            root.geometry(f"{state['width']}x{state['height']}+{x}+{y}")
            if state.get('zoomed'):
                root.state('zoomed')
            return
    except (OSError, ValueError, KeyError, TypeError):
        pass
    second = next((area for area in areas if not area[4]), None)
    if second:
        left, top, right, bottom, _ = second
        width, height = min(width, right - left - 2 * MARGIN), min(height, bottom - top - 2 * MARGIN)
        root.geometry(f'{width}x{height}+{left + MARGIN}+{top + MARGIN}')
    else:
        root.geometry(f'{width}x{height}')


def remember(root):
    """Save where the window is; skipped for hidden windows (tests, previews)."""
    match = re.fullmatch(r'(\d+)x(\d+)\+(-?\d+)\+(-?\d+)', root.geometry())
    if not root.winfo_viewable() or not match:
        return
    width, height, x, y = map(int, match.groups())
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(dict(x=x, y=y, width=width, height=height,
                                              zoomed=root.state() == 'zoomed')), encoding='utf-8')
    except OSError:
        pass
