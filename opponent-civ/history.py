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


def match_results(rows, games, my_id, slack=120):
    """Per row, `my_id`'s (won, rating change or None) from `fetch_results` games; None when the game is not there.

    A game matches when it starts within `slack` seconds of the recording and has every recorded player."""
    results = []
    for _, match in rows:
        ids = {p.profile_id for p in match.players if p.profile_id > 0}
        members = next((m for start, m in games if abs(start - match.timestamp) <= slack and my_id in m and ids <= m.keys()), None)
        outcome, old, new = members[my_id] if members else (None, None, None)
        if outcome not in (0, 1):
            results.append(None)
        else:
            results.append((outcome == 1, new - old if match.rated and None not in (old, new) else None))
    return results
