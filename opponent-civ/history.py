"""Recent local recordings, ordered by the match start stored in the header."""
from rec_header import NotReady, Unsupported, read_match
from savegames import recordings


def recent_matches(dirs, mode='多人', limit=10):
    matches, skipped = [], 0
    for path in recordings(dirs):
        try:
            match = read_match(path)
        except (NotReady, Unsupported, OSError):
            skipped += 1
            continue
        if mode == '多人' and not match.multiplayer:
            continue
        if mode == '排名' and not match.rated:
            continue
        matches.append((path, match))
    matches.sort(key=lambda item: (item[1].timestamp, str(item[0])), reverse=True)
    return matches[:limit], skipped
