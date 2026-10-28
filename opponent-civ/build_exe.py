"""Build a portable Windows executable without a game installation."""
import argparse
import ctypes
import hashlib
import json
import tempfile
import os
import shutil
import subprocess
import sys
from pathlib import Path
from build_library import load_library

HERE = Path(__file__).parent
BUILD = HERE / 'build'
EXE_NAME = 'aoe2-opponent-dashboard'
DESKTOP_NAME = 'AoE2 對局筆記.exe'


def desktop_dir():
    buffer = ctypes.create_unicode_buffer(260)
    ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buffer)
    return Path(buffer.value)



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--desktop', action='store_true', help='also copy to the local desktop')
    args = parser.parse_args()
    builds = load_library()
    expected = dict(builds=len(builds), steps=sum(len(b.steps) for b in builds), bundled=True)
    BUILD.mkdir(exist_ok=True)
    icon = HERE / 'assets' / 'app.ico'
    destination = BUILD / 'release'
    subprocess.run([
        sys.executable, '-m', 'PyInstaller', '--onefile', '--windowed', '--noconfirm', '--clean',
        '--name', EXE_NAME, '--icon', str(icon),
        '--add-data', f'{HERE / "data"}{os.pathsep}data',
        '--add-data', f'{HERE / "assets"}{os.pathsep}assets',
        '--distpath', str(destination), '--workpath', str(BUILD / 'work'), '--specpath', str(BUILD),
        str(HERE / 'dashboard.py'),
    ], check=True)
    exe = (destination / f'{EXE_NAME}.exe').resolve()
    # Run the actual one-file EXE from an empty directory, with no game or media.
    with tempfile.TemporaryDirectory() as folder:
        report = Path(folder) / 'catalog-check.json'
        subprocess.run([str(exe), '--check-bundled-data', str(report)], cwd=folder, check=True, timeout=60)
        summary = json.loads(report.read_text(encoding='utf-8'))
        if summary != expected:
            raise RuntimeError(f'Packaged catalog verification failed: {summary}')
        print(f'Packaged catalog verified: {summary}')
    (destination / 'SHA256SUMS.txt').write_text(f'{hashlib.sha256(exe.read_bytes()).hexdigest()}  {exe.name}\n', encoding='ascii')
    if args.desktop:
        shutil.copy2(exe, desktop_dir() / DESKTOP_NAME)
    print(f'Built: {exe}')


if __name__ == '__main__':
    main()
