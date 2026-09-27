"""Watch the savegame folders; when a match starts, print the opponent's civ.

This is also the live check for the handoff's first unknown -- is the header
readable the moment a match starts? Every new recording is appended to
%LOCALAPPDATA%\\aoe2-tools\\opponent-civ\\watch_log.jsonl with how many seconds
after game start it became readable.

    python watch.py                # watch, text from the game in 繁中
    python watch.py --lang en      # any folder under the game's resources/
    python watch.py --no-elo       # stay offline: skip the ladder ratings
"""
import argparse
import ctypes
import json
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

from civdata import load_civs
from ratings import RM_1V1, RM_TEAM, fetch_ratings
from rec_header import NotReady, Unsupported, read_match, split_sides
from savegames import RECORDING_GLOB, infer_my_profile_id, recordings, savegame_dirs

POLL_SECONDS = 0.25
GIVE_UP_SECONDS = 120
IN_PROGRESS_SECONDS = 15   # a recording written this recently is a match in progress
TITLE = 'AoE2 對手文明'
# Not next to the script: the packaged exe runs from a temp folder and lives on the desktop.
log_path = Path(os.environ['LOCALAPPDATA']) / 'aoe2-tools' / 'opponent-civ' / 'watch_log.jsonl'


class Pending:
    def __init__(self, path, joined_late=False):
        self.path = path
        self.joined_late = joined_late
        self.detected = time.time()
        self.attempts = 0
        self.errors = []

    def note(self, error):
        message = f'{type(error).__name__}: {error}'
        if message not in self.errors:
            self.errors.append(message)


def iso(timestamp):
    return datetime.fromtimestamp(timestamp).isoformat(timespec='milliseconds')


def list_files(dirs):
    return {Path(e.path) for d in dirs for e in os.scandir(d) if e.is_file()}


def log(entry):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, 'a', encoding='utf-8') as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + '\n')


def show(match, civs, my_id, readable_after):
    def civ_name(civ_id):
        return civs[civ_id].name if civ_id in civs else f'未知文明 #{civ_id}'

    kind = '排名' if match.rated else '多人' if match.multiplayer else '單機'
    print('\n' + '=' * 64)
    print(f'{datetime.now():%H:%M:%S}  新對局 · {kind} · {len(match.players)} 人  '
          f'（開局後 {readable_after:.1f} 秒讀到）')
    me, allies, enemies = split_sides(match, my_id)
    names_by_civ = {}
    for player in enemies:
        names_by_civ.setdefault(player.civ_id, []).append(player.name)
    label = '對手' if me else '玩家'
    for civ_id, names in names_by_civ.items():
        print(f'\n{label}  {"、".join(names)}  ──  {civ_name(civ_id)}\n')
        if civ_id in civs:
            print('    ' + civs[civ_id].description.replace('\n', '\n    '))
    if me:
        print(f'\n你    {me.name}  ──  {civ_name(me.civ_id)}')
    for player in allies:
        print(f'隊友  {player.name}  ──  {civ_name(player.civ_id)}')
    sys.stdout.flush()


def show_ratings(match, my_id):
    """Print every human's ladder ratings after the civ text; returns them for the log."""
    humans = {p.profile_id for p in match.players if p.is_human}
    if not humans:
        return {}
    try:
        ratings = fetch_ratings(humans)
    except Exception as e:  # best effort: never let the lookup stop the watcher
        print(f'\n（查不到積分：{e}）')
        return {}
    me, allies, enemies = split_sides(match, my_id)
    print('\n積分')
    for label, players in (('對手' if me else '玩家', enemies), ('你', [me] if me else []), ('隊友', allies)):
        for player in players:
            if player.is_human:
                board = ratings.get(player.profile_id, {})
                text = ' · '.join(f'{name} {board[lb]}' for lb, name in ((RM_1V1, '1v1'), (RM_TEAM, '團戰'))
                                  if lb in board)
                print(f'  {label} {player.name}：{text or "沒有排名紀錄"}')
    sys.stdout.flush()
    return ratings


def try_parse(pending, civs, my_id, elo, presenter=None):
    """True once the recording is handled (shown or given up)."""
    pending.attempts += 1
    try:
        match = read_match(pending.path)
        stat = pending.path.stat()
    except (NotReady, Unsupported, OSError) as e:
        pending.note(e)
        if time.time() - pending.detected < GIVE_UP_SECONDS:
            return False
        if not presenter:
            print(f'\n放棄：{pending.path.name} 在 {GIVE_UP_SECONDS} 秒內都讀不到檔頭：{pending.errors}')
        log(dict(file=pending.path.name, ok=False, detected=iso(pending.detected),
                 attempts=pending.attempts, errors=pending.errors))
        return True

    parsed = time.time()
    created = getattr(stat, 'st_birthtime', stat.st_ctime)
    readable_after = parsed - match.timestamp
    if presenter:
        presenter(match, pending.path, readable_after)
    else:
        show(match, civs, my_id, readable_after)
    ratings = show_ratings(match, my_id) if elo else {}
    log(dict(
        file=pending.path.name, ok=True, joined_late=pending.joined_late,
        game_start=iso(match.timestamp), created=iso(created),
        detected=iso(pending.detected), parsed=iso(parsed),
        readable_after_start_s=round(readable_after, 3),
        readable_after_create_s=round(parsed - created, 3),
        attempts=pending.attempts, errors=pending.errors, size_at_parse=stat.st_size,
        save_version=match.save_version, rated=match.rated, hidden_civs=match.hidden_civs,
        players=[dict(name=p.name, civ_id=p.civ_id, team=p.team, profile_id=p.profile_id,
                      ratings=ratings.get(p.profile_id, {}))
                 for p in match.players],
    ))
    return True


def main():
    global log_path
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--lang', default='tw', help='text language folder, e.g. tw, en, zh')
    parser.add_argument('--game-dir', help='AoE2DE install folder (default: found via Steam)')
    parser.add_argument('--dir', action='append', help='folder to watch (default: every savegame folder)')
    parser.add_argument('--profile-id', type=int, help='your profile id (default: inferred from recordings)')
    parser.add_argument('--log', help=f'timing log (default: {log_path})')
    parser.add_argument('--no-elo', action='store_true', help='skip the ladder ratings (no network)')
    args = parser.parse_args()
    if sys.stdout.isatty():
        ctypes.windll.kernel32.SetConsoleTitleW(TITLE)
    else:
        sys.stdout.reconfigure(encoding='utf-8')
    if args.log:
        log_path = Path(args.log)

    civs = load_civs(args.game_dir, args.lang)
    dirs = [Path(d) for d in args.dir] if args.dir else savegame_dirs()
    my_id = args.profile_id or infer_my_profile_id(dirs)
    seen = list_files(dirs)
    pending = {}
    latest = next(iter(recordings(dirs)), None)
    if latest and time.time() - latest.stat().st_mtime < IN_PROGRESS_SECONDS:
        pending[latest] = Pending(latest, joined_late=True)
    print(f'監看中：{", ".join(str(d) for d in dirs)}')
    print(f'你的 profile ID：{my_id or "推斷不出來，會列出所有玩家"}；文明資料 {len(civs)} 個（{args.lang}）；'
          f'積分{"關閉" if args.no_elo else "向官方 API 查"}')
    print('開一場對戰就會自動顯示。Ctrl+C 結束。')
    sys.stdout.flush()

    try:
        while True:
            current = list_files(dirs)
            for path in sorted(current - seen):
                if path.match(RECORDING_GLOB):
                    pending[path] = Pending(path)
                else:
                    print(f'  （新檔案 {path.name}）')
            seen = current
            for path in list(pending):
                if try_parse(pending[path], civs, my_id, not args.no_elo):
                    del pending[path]
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    try:
        main()
    except Exception:
        traceback.print_exc()
        if getattr(sys, 'frozen', False):  # the exe's console closes on exit; keep the error readable
            input('\n出錯了，按 Enter 關閉視窗。')
        sys.exit(1)
