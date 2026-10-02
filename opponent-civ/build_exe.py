"""Build a portable Windows executable without a game installation."""
import argparse
import ctypes
import hashlib
import shutil
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
BUILD = HERE / 'build'
EXE_NAME = 'aoe2-opponent-dashboard'
DESKTOP_NAME = 'AoE2 對局筆記.exe'


def desktop_dir():
    buffer = ctypes.create_unicode_buffer(260)
    ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buffer)
    return Path(buffer.value)


def create_icon(path):
    """Original geometric II mark; no game artwork or third-party assets."""
    size = 32
    pixels = bytearray()
    for y in reversed(range(size)):
        for x in range(size):
            ink = (x in range(9, 13) or x in range(19, 23)) and 7 <= y <= 24
            ink |= (y in (7, 8, 23, 24) and (7 <= x <= 14 or 17 <= x <= 24))
            red, green, blue = (101, 217, 194) if ink else (16, 20, 30)
            pixels.extend((blue, green, red, 255))
    bitmap = struct.pack('<IiiHHIIiiII', 40, size, size*2, 1, 32, 0, len(pixels), 0, 0, 0, 0)
    bitmap += pixels + bytes(size*4)
    path.write_bytes(struct.pack('<HHH', 0, 1, 1) + struct.pack('<BBBBHHII', size, size, 0, 0, 1, 32, len(bitmap), 22) + bitmap)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--desktop', action='store_true', help='also copy to the local desktop')
    args = parser.parse_args()
    BUILD.mkdir(exist_ok=True)
    icon = BUILD / 'app.ico'
    create_icon(icon)
    destination = BUILD / 'release'
    subprocess.run([
        sys.executable, '-m', 'PyInstaller', '--onefile', '--windowed', '--noconfirm', '--clean',
        '--name', EXE_NAME, '--icon', str(icon),
        '--distpath', str(destination), '--workpath', str(BUILD / 'work'), '--specpath', str(BUILD),
        str(HERE / 'dashboard.py'),
    ], check=True)
    exe = destination / f'{EXE_NAME}.exe'
    (destination / 'SHA256SUMS.txt').write_text(f'{hashlib.sha256(exe.read_bytes()).hexdigest()}  {exe.name}\n', encoding='ascii')
    if args.desktop:
        shutil.copy2(exe, desktop_dir() / DESKTOP_NAME)
    print(f'Built: {exe}')


if __name__ == '__main__':
    main()
