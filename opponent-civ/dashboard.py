"""Second-screen desktop dashboard. Run with --no-elo for offline use."""
import argparse
import queue
import threading
import time
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from tkinter import ttk

from civdata import load_civs
from collections import Counter
from history import recent_matches
from ratings import RM_1V1, RM_TEAM, fetch_ratings
from rec_header import read_match, split_sides
from savegames import infer_my_profile_id, recordings, savegame_dirs
from watch import Pending, POLL_SECONDS, IN_PROGRESS_SECONDS, list_files, try_parse

BG = '#f4f5f2'
PANEL = '#ffffff'
FG = '#202c29'
MUTED = '#687670'
ACCENT = '#24735b'


class Dashboard:
    def __init__(self, root, args):
        self.root, self.args = root, args
        self.events = queue.Queue()
        self.stop = threading.Event()
        self.pool = ThreadPoolExecutor(max_workers=2)
        self.generation = 0
        self.font_size = 15
        self.civs, self.my_id = {}, None
        self.match = None
        self.tabs = []
        self.history_window = None
        self.history_request = 0
        self.history_rows = []
        root.title('AoE2 · 對局筆記')
        root.geometry('1220x860')
        root.minsize(960, 650)
        root.configure(bg=BG)
        root.option_add('*Font', ('Microsoft JhengHei UI', 10))
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('TNotebook', background=PANEL, borderwidth=0)
        style.configure('TNotebook.Tab', background=BG, foreground=MUTED, padding=(12, 10), font=('Microsoft JhengHei UI', 10))
        style.map('TNotebook.Tab', background=[('selected', PANEL)], foreground=[('selected', ACCENT)])
        style.configure('TCombobox', fieldbackground=PANEL, padding=5)
        bar = tk.Frame(root, bg=BG)
        bar.pack(fill='x', padx=28, pady=(22, 18))
        tk.Label(bar, text='II', font=('Georgia', 30, 'bold'), bg=BG, fg=ACCENT).pack(side='left', padx=(0, 14))
        brand = tk.Frame(bar, bg=BG)
        brand.pack(side='left')
        tk.Label(brand, text='對局筆記', font=('Microsoft JhengHei UI', 19, 'bold'), bg=BG, fg=FG, anchor='w').pack(anchor='w')
        tk.Label(brand, text='AGE OF EMPIRES II   /   MATCH COMPANION', font=('Segoe UI', 8), bg=BG, fg=MUTED).pack(anchor='w')
        self.pin = tk.BooleanVar()
        tk.Checkbutton(bar, text='保持置頂', variable=self.pin, command=lambda: root.attributes('-topmost', self.pin.get()), bg=BG, fg=MUTED, selectcolor=PANEL, activebackground=BG).pack(side='right', padx=(20, 0))
        for label, delta in [('＋', 1), ('－', -1)]:
            tk.Button(bar, text=label, command=lambda d=delta: self.resize(d), bg=BG, fg=MUTED, relief='flat', borderwidth=0, padx=10, cursor='hand2').pack(side='right')
        tk.Label(bar, text='字級', bg=BG, fg=MUTED).pack(side='right')
        footer = tk.Frame(root, bg=BG)
        footer.pack(side='bottom', fill='x', padx=28, pady=12)
        tk.Label(footer, text='●  本機錄影 · 自動監看', bg=BG, fg=ACCENT).pack(side='left')
        tk.Label(footer, text='離線模式' if args.no_elo else '排行榜顯示目前積分', bg=BG, fg=MUTED).pack(side='right')
        workspace = tk.Frame(root, bg=BG)
        workspace.pack(fill='both', expand=True, padx=28)
        self.sidebar = tk.Frame(workspace, bg=BG, width=340)
        self.sidebar.pack(side='left', fill='y', padx=(0, 22))
        self.sidebar.pack_propagate(False)
        detail = tk.Frame(workspace, bg=PANEL)
        detail.pack(side='left', fill='both', expand=True)
        self.status = tk.Label(detail, text='正在讀取遊戲資料…', anchor='w', bg=PANEL, fg=ACCENT, font=('Microsoft JhengHei UI', 11), wraplength=740, justify='left')
        self.status.pack(fill='x', padx=28, pady=(22, 8))
        self.meta = tk.Label(detail, text='選一場對局，看看對手的文明。', anchor='w', bg=PANEL, fg=MUTED, wraplength=740, justify='left')
        self.meta.pack(fill='x', padx=28, pady=(0, 20))
        root.bind('<Configure>', lambda event: self.reflow(event))
        self.book = ttk.Notebook(detail)
        self.book.pack(fill='both', expand=True, padx=20, pady=(0, 16))
        self.empty = tk.Frame(self.book, bg=PANEL)
        self.book.add(self.empty, text='文明情報')
        tk.Label(self.empty, text='下一場，知己知彼。', bg=PANEL, fg=FG, font=('Microsoft JhengHei UI', 23, 'bold')).pack(pady=(100, 20))
        tk.Label(self.empty, text='左側回顧最近 10 場對局。\n新對局開始時，這裡會自動更新。', bg=PANEL, fg=MUTED, font=('Microsoft JhengHei UI', 13), justify='center').pack()
        self.preview = tk.Button(footer, text='最近一場', command=self.preview_latest, state='disabled', bg=BG, fg=MUTED, relief='flat')
        self.preview.pack(side='left', padx=20)
        self.open_history()
        root.protocol('WM_DELETE_WINDOW', self.close)
        threading.Thread(target=self.monitor, daemon=True).start()
        root.after(100, self.drain)

    def close(self):
        self.stop.set()
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()

    def reflow(self, event):
        if event.widget is self.root:
            self.status.configure(wraplength=max(300, event.width - 470))
            self.meta.configure(wraplength=max(300, event.width - 470))

    def resize(self, delta):
        self.font_size = max(11, min(24, self.font_size + delta))
        for _, _, text in self.tabs:
            self.style_text(text)

    def style_text(self, text):
        text.configure(font=('Microsoft JhengHei UI', self.font_size), spacing1=4, spacing3=7)
        text.tag_configure('heading', foreground=ACCENT, font=('Microsoft JhengHei UI', self.font_size + 1, 'bold'), spacing1=16)

    def monitor(self):
        try:
            self.civs = load_civs(self.args.game_dir, self.args.lang)
            self.dirs = [Path(d) for d in self.args.dir] if self.args.dir else savegame_dirs()
            if not self.dirs or any(not d.is_dir() for d in self.dirs):
                raise ValueError('找不到錄影資料夾，請用 --dir 指定 savegame 資料夾。')
            self.my_id = self.args.profile_id or infer_my_profile_id(self.dirs)
            seen = list_files(self.dirs)
            latest = next(iter(recordings(self.dirs)), None)
            pending = {}
            if latest and time.time() - latest.stat().st_mtime < IN_PROGRESS_SECONDS:
                pending[latest] = Pending(latest, joined_late=True)
            self.events.put(('ready', None))
            while not self.stop.is_set():
                current = list_files(self.dirs)
                for path in sorted(current - seen):
                    if path.suffix.lower() == '.aoe2record':
                        pending[path] = Pending(path)
                        self.events.put(('status', '偵測到新對局，正在等待檔頭寫入…'))
                seen = current
                for path in list(pending):
                    shown = []
                    def present(match, source, delay):
                        shown.append(True)
                        self.events.put(('match', (match, source, delay, False)))
                    if try_parse(pending[path], self.civs, self.my_id, False, presenter=present):
                        del pending[path]
                        if not shown:
                            self.events.put(('status', '無法讀取新對局；監看仍持續，請檢查 watch_log.jsonl。'))
                self.stop.wait(POLL_SECONDS)
        except Exception as exc:
            self.events.put(('status', f'監看停止：{exc}'))

    def preview_latest(self):
        self.preview.configure(state='disabled')
        generation = self.generation
        def work():
            try:
                latest = next(iter(recordings(self.dirs)), None)
                if latest is None:
                    raise ValueError('目前沒有錄影檔，開一場對戰後再試。')
                self.events.put(('preview_match', (generation, (read_match(latest), latest, None, True))))
            except Exception as exc:
                self.events.put(('status', f'預覽失敗：{exc}'))
            finally:
                self.events.put(('preview_done', None))
        self.pool.submit(work)

    def open_history(self):
        window = self.history_window = self.sidebar
        bar = tk.Frame(window, bg=BG)
        bar.pack(fill='x', pady=(0, 12))
        tk.Label(bar, text='最近對局', bg=BG, fg=FG, font=('Microsoft JhengHei UI', 14, 'bold')).pack(side='left')
        self.history_mode = tk.StringVar(value='多人')
        mode = ttk.Combobox(bar, textvariable=self.history_mode, values=('多人', '排名', '全部'), state='readonly', width=6)
        mode.pack(side='right')
        mode.bind('<<ComboboxSelected>>', lambda event: self.refresh_history() if hasattr(self, 'dirs') else None)
        self.history_summary = tk.Label(window, text='最近 10 場 · 依開局時間排序', bg=BG, fg=MUTED, anchor='w', justify='left', wraplength=330)
        self.history_summary.pack(fill='x', pady=(0, 14))
        body = tk.Frame(window, bg=BG)
        body.pack(fill='both', expand=True)
        style = ttk.Style(window)
        style.configure('History.Treeview', background=BG, fieldbackground=BG, foreground=FG, rowheight=84, borderwidth=0, font=('Microsoft JhengHei UI', 10))
        style.map('History.Treeview', background=[('selected', '#deebe3')], foreground=[('selected', '#174b3a')])
        self.history_tree = ttk.Treeview(body, columns=('match',), show='', selectmode='browse', height=7, style='History.Treeview')
        self.history_tree.column('match', width=312, minwidth=260)
        vertical = ttk.Scrollbar(body, command=self.history_tree.yview)
        vertical.pack(side='right', fill='y')
        self.history_tree.configure(yscrollcommand=vertical.set)
        self.history_tree.pack(fill='both', expand=True)
        self.history_tree.bind('<<TreeviewSelect>>', lambda event: self.select_history())
        self.history_tree.bind('<Return>', lambda event: self.select_history())
        self.history_button = tk.Button(window, text='重新整理對局', command=self.refresh_history, state='disabled', bg=BG, fg=ACCENT, relief='flat', cursor='hand2', pady=10)
        self.history_button.pack(fill='x', pady=(10, 0))
        tk.Label(window, text='錄影檔頭未含勝敗與時長', bg=BG, fg=MUTED, font=('Microsoft JhengHei UI', 9)).pack(anchor='w', pady=8)

    def refresh_history(self):
        self.history_request += 1
        request = self.history_request
        mode = self.history_mode.get()
        self.history_summary.configure(text='正在讀取本機錄影…')
        def work():
            try:
                rows, skipped = recent_matches(self.dirs, mode)
                self.events.put(('history', (request, rows, skipped, None)))
            except Exception as exc:
                self.events.put(('history', (request, [], 0, str(exc))))
        self.pool.submit(work)

    def render_history(self, request, rows, skipped, error):
        if request != self.history_request or self.history_window is None or not self.history_window.winfo_exists():
            return
        self.history_rows = rows
        self.history_tree.delete(*self.history_tree.get_children())
        counts = Counter()
        def civ_name(player):
            civ = self.civs.get(player.civ_id)
            return civ.name if civ else f'未知文明 #{player.civ_id}'
        for index, (path, match) in enumerate(rows):
            me, _, enemies = split_sides(match, self.my_id)
            if me:
                counts[civ_name(me)] += 1
            opponents = '、'.join(f'{p.name}（{civ_name(p)}）' for p in enemies)
            kind = '排名' if match.rated else '多人' if match.multiplayer else '單機'
            stamp = datetime.fromtimestamp(match.timestamp).strftime('%m/%d  %H:%M')
            opponent_label = opponents or '無對手'
            if len(opponent_label) > 22:
                opponent_label = opponent_label[:21] + '…'
            mine = civ_name(me) if me else '身分不明'
            self.history_tree.insert('', 'end', iid=str(index), values=(f'{stamp}   ·   {kind} {len(match.players)} 人\n{opponent_label}\n我的文明  /  {mine}',))
        summary = f'最近 {len(rows)} 場'
        if counts:
            summary += ' · 我的文明：' + '、'.join(f'{name} {count} 場' for name, count in counts.most_common())
        if skipped:
            summary += f' · 略過 {skipped} 個暫時無法解析的錄影'
        if rows and self.generation == 0:
            self.history_tree.selection_set('0')
        self.history_summary.configure(text=f'讀取失敗：{error}' if error else summary if rows else '沒有符合條件的錄影。' + (f' 略過 {skipped} 個無法解析的錄影。' if skipped else ''))

    def select_history(self):
        selected = self.history_tree.selection()
        if not selected:
            return
        source, match = self.history_rows[int(selected[0])]
        self.show(match, source, None, True)
        self.root.lift()

    def drain(self):
        try:
            while True:
                event, value = self.events.get_nowait()
                if event == 'ready':
                    identity = f'你的 profile ID：{self.my_id}' if self.my_id else '無法確認你的身分，將列出所有玩家；可用 --profile-id 指定'
                    self.status.configure(text=f'監看中 · {len(self.civs)} 個文明 · {identity}')
                    self.preview.configure(state='normal')
                    self.history_button.configure(state='normal')
                    self.refresh_history()
                elif event == 'status':
                    self.status.configure(text=value)
                elif event == 'preview_done':
                    self.preview.configure(state='normal')
                elif event == 'match':
                    self.show(*value)
                    if self.history_window is not None and self.history_window.winfo_exists():
                        self.refresh_history()
                elif event == 'history':
                    self.render_history(*value)
                elif event == 'preview_match':
                    generation, match_data = value
                    if generation == self.generation:
                        self.show(*match_data)
                elif event == 'ratings':
                    generation, ratings, error = value
                    if generation == self.generation:
                        for player, label, _ in self.tabs:
                            board = ratings.get(player.profile_id, {})
                            summary = '  ·  '.join(f'{name}  {board[key]}' for key, name in ((RM_1V1, '1v1'), (RM_TEAM, '團戰')) if key in board)
                            label.configure(text='電腦玩家' if not player.is_human else error or ('目前積分 · ' + summary if summary else '沒有排名紀錄'))
        except queue.Empty:
            pass
        self.root.after(100, self.drain)

    def show(self, match, source, delay, preview):
        self.generation += 1
        generation = self.generation
        self.match = match
        for tab in self.book.tabs():
            self.book.nametowidget(tab).destroy()
        self.tabs = []
        me, allies, enemies = split_sides(match, self.my_id)
        kind = '排名' if match.rated else '多人' if match.multiplayer else '單機'
        self.status.configure(text=('歷史預覽' if preview else '已讀取新對局') + f' · {kind} · {len(match.players)} 人 · {datetime.fromtimestamp(match.timestamp):%m/%d %H:%M}')
        self.meta.configure(text=('歷史對局 · 文明說明與積分為目前資料' if preview else f'開局後 {delay:.1f} 秒讀到') + ' · 新對局將自動顯示')
        for role, players in [('對手' if me else '玩家', enemies), ('你', [me] if me else []), ('隊友', allies)]:
            for player in players:
                civ = self.civs.get(player.civ_id)
                name = civ.name if civ else f'未知文明 #{player.civ_id}'
                frame = tk.Frame(self.book, bg=PANEL)
                self.book.add(frame, text=f'{role} · {name}')
                tk.Label(frame, text=name, font=('Microsoft JhengHei UI', 30, 'bold'), fg=FG, bg=PANEL, anchor='w').pack(fill='x', padx=24, pady=(20, 2))
                tk.Label(frame, text=player.name, font=('Microsoft JhengHei UI', 14), fg=FG, bg=PANEL, anchor='w').pack(fill='x', padx=24)
                rating = tk.Label(frame, text='積分查詢已關閉' if self.args.no_elo else '正在查詢積分…', fg=MUTED, bg=PANEL, anchor='w')
                rating.pack(fill='x', padx=24, pady=(8, 12))
                body = tk.Frame(frame, bg=PANEL)
                body.pack(fill='both', expand=True, padx=24, pady=(0, 20))
                scrollbar = ttk.Scrollbar(body)
                scrollbar.pack(side='right', fill='y')
                text = tk.Text(body, bg=PANEL, fg=FG, relief='flat', wrap='word', padx=0, borderwidth=0, highlightthickness=0, yscrollcommand=scrollbar.set)
                text.pack(fill='both', expand=True)
                scrollbar.configure(command=text.yview)
                self.style_text(text)
                description = civ.description if civ else '此文明尚無官方說明，請確認遊戲資料版本。'
                for line in description.splitlines():
                    text.insert('end', line + '\n', 'heading' if line.strip().endswith(('：', ':')) else ())
                text.configure(state='disabled')
                self.tabs.append((player, rating, text))
        if not self.args.no_elo:
            def lookup():
                try:
                    ids = {p.profile_id for p in match.players if p.is_human}
                    result = fetch_ratings(ids) if ids else {}
                    self.events.put(('ratings', (generation, result, None)))
                except Exception:
                    self.events.put(('ratings', (generation, {}, '暫時無法取得積分')))
            self.pool.submit(lookup)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lang', default='tw')
    parser.add_argument('--game-dir')
    parser.add_argument('--dir', action='append')
    parser.add_argument('--profile-id', type=int)
    parser.add_argument('--no-elo', action='store_true')
    args = parser.parse_args()
    root = tk.Tk()
    Dashboard(root, args)
    root.mainloop()


if __name__ == '__main__':
    main()
