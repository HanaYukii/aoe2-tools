"""Where recordings live, and whose they are."""
import os
from collections import Counter
from pathlib import Path

from rec_header import NotReady, Unsupported, read_match

USER_ROOT = Path(os.path.expandvars(r'%USERPROFILE%\Games\Age of Empires 2 DE'))
RECORDING_GLOB = '*.aoe2record'


def savegame_dirs(root=USER_ROOT):
    """One savegame folder per account folder (the Steam id, plus "0")."""
    return sorted(p for p in Path(root).glob('*/savegame') if p.is_dir())


def recordings(dirs):
    """Every recording in `dirs`, newest first."""
    files = [f for d in dirs for f in Path(d).glob(RECORDING_GLOB)]
    return sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)


def infer_my_profile_id(dirs, sample=20):
    """The human profile present in nearly every recent recording: the recorder."""
    counts = Counter()
    parsed = 0
    for path in recordings(dirs)[:sample]:
        try:
            match = read_match(path)
        except (NotReady, Unsupported, OSError):
            continue
        parsed += 1
        counts.update({p.profile_id for p in match.players if p.is_human})
    top = counts.most_common(2)
    if not top or top[0][1] < 0.8 * parsed or (len(top) > 1 and top[1][1] == top[0][1]):
        return None
    return top[0][0]
