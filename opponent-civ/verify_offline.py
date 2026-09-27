"""Offline check of the header parser against every recording on this PC.

1. Parse every recording, tallied by save version.
2. Sanity: the recorder is in every multiplayer match, every civ id is known.
3. How many bytes from the start of the file the player block needs.
4. The latest multiplayer matches, from the recorder's side.
"""
import sys
from collections import Counter, defaultdict
from datetime import datetime

from civdata import load_civs
from rec_header import NotReady, Unsupported, parse_match, read_match, split_sides
from savegames import infer_my_profile_id, recordings, savegame_dirs


def bytes_needed(path):
    """Smallest file prefix the player block parses from."""
    raw = path.read_bytes()
    low, high = 16, len(raw)
    while low < high:
        mid = (low + high) // 2
        try:
            parse_match(raw[:mid])
            high = mid
        except NotReady:
            low = mid + 1
    return low, int.from_bytes(raw[:4], 'little')


def main():
    if not sys.stdout.isatty():
        sys.stdout.reconfigure(encoding='utf-8')
    civs = load_civs()
    dirs = savegame_dirs()
    files = recordings(dirs)
    my_id = infer_my_profile_id(dirs)
    print(f'savegame 資料夾：{", ".join(str(d) for d in dirs)}')
    print(f'錄影檔 {len(files)} 個；推斷你的 profile ID = {my_id}\n')

    by_save = defaultdict(Counter)
    failures, problems, matches = [], [], []
    team_sizes, flags = Counter(), Counter()
    for path in files:
        try:
            match = read_match(path)
        except (NotReady, Unsupported) as e:
            failures.append((path.name, f'{type(e).__name__}: {e}'))
            by_save['?']['失敗'] += 1
            continue
        by_save[match.save_version]['成功'] += 1
        matches.append((path, match))
        unknown = [p.civ_id for p in match.players if p.civ_id not in civs]
        if unknown:
            problems.append((path.name, f'未知文明 id {unknown}'))
        if match.multiplayer and my_id not in {p.profile_id for p in match.players}:
            problems.append((path.name, '多人對局裡找不到你'))
        team_sizes[len(match.players)] += 1
        flags['排名'] += match.rated
        flags['隱藏文明'] += match.hidden_civs
        flags['多人'] += match.multiplayer

    print('1. 解析結果（依存檔版本）')
    for save, tally in sorted(by_save.items(), key=lambda kv: str(kv[0])):
        print(f'   save {save}: ' + '，'.join(f'{k} {v}' for k, v in tally.items()))
    for name, error in failures[:10]:
        print(f'   失敗 {name}: {error}')

    print('\n2. 合理性檢查')
    print(f'   人數分布：' + '，'.join(f'{n} 人 {c} 場' for n, c in sorted(team_sizes.items())))
    print(f'   旗標：' + '，'.join(f'{k} {v} 場' for k, v in flags.items()))
    print(f'   問題 {len(problems)} 個')
    for name, problem in problems[:10]:
        print(f'   {name}: {problem}')

    print('\n3. 讀到玩家區塊需要的檔案開頭長度')
    for path, _ in matches[:5]:
        needed, header_len = bytes_needed(path)
        print(f'   {needed:>6,} bytes（壓縮檔頭共 {header_len:,} bytes，整檔 {path.stat().st_size:,}）  {path.name}')

    print('\n4. 最近 5 場多人對局')
    shown = 0
    for path, match in matches:
        if not match.multiplayer:
            continue
        me, allies, enemies = split_sides(match, my_id)
        started = datetime.fromtimestamp(match.timestamp)
        mine = civs[me.civ_id].name if me else '?'
        theirs = '、'.join(f'{p.name}（{civs[p.civ_id].name}）' for p in enemies)
        print(f'   {started:%m-%d %H:%M}  {"排名" if match.rated else "大廳"}  你（{mine}） vs {theirs}')
        shown += 1
        if shown == 5:
            break


if __name__ == '__main__':
    main()
