"""Package watch.py into one exe with PyInstaller and copy it to the desktop.

    python -m pip install pyinstaller
    python build_exe.py

The icon is the game's own tech-tree button, read from the install folder.
"""
import ctypes
import shutil
import struct
import subprocess
import sys
from pathlib import Path

from civdata import find_game_dir

HERE = Path(__file__).parent
BUILD = HERE / 'build'
EXE_NAME = 'aoe2-opponent-dashboard'
DESKTOP_NAME = 'AoE2 對局筆記.exe'
CSIDL_DESKTOPDIRECTORY = 0x10


def png_to_ico(png_path, ico_path):
    """Wrap a PNG in a single-image .ico (PNG entries are valid since Vista)."""
    png = png_path.read_bytes()
    width, height = struct.unpack('>II', png[16:24])
    entry = struct.pack('<BBBBHHII', width % 256, height % 256, 0, 0, 1, 32, len(png), 6 + 16)
    ico_path.write_bytes(struct.pack('<HHH', 0, 1, 1) + entry + png)


def desktop_dir():
    """The real desktop folder, following OneDrive redirection."""
    buffer = ctypes.create_unicode_buffer(260)
    ctypes.windll.shell32.SHGetFolderPathW(None, CSIDL_DESKTOPDIRECTORY, None, 0, buffer)
    return Path(buffer.value)


def main():
    BUILD.mkdir(exist_ok=True)
    icon = BUILD / 'icon.ico'
    png_to_ico(find_game_dir() / 'widgetui' / 'textures' / 'ingame' / 'icons' / 'menu_techtree_normal.png', icon)
    subprocess.run([
        sys.executable, '-m', 'PyInstaller', '--onefile', '--windowed', '--noconfirm',
        '--name', EXE_NAME, '--icon', str(icon),
        '--distpath', str(BUILD / 'dist'), '--workpath', str(BUILD / 'work'), '--specpath', str(BUILD),
        str(HERE / 'dashboard.py'),
    ], check=True)
    target = desktop_dir() / DESKTOP_NAME
    try:
        shutil.copy2(BUILD / 'dist' / f'{EXE_NAME}.exe', target)
    except PermissionError:
        sys.exit(f'{target} 正在執行，關掉它再重跑一次。')
    print(f'已放到 {target}')


if __name__ == '__main__':
    main()
