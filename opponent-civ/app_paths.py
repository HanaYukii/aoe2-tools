"""Local configuration locations shared by Windows and offline desktop previews."""
import os
import sys
from pathlib import Path


def app_data_dir():
    if os.environ.get('LOCALAPPDATA'):
        return Path(os.environ['LOCALAPPDATA']) / 'aoe2-tools' / 'opponent-civ'
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / 'aoe2-tools'
    return Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'aoe2-tools'
