"""Second-screen desktop dashboard. Run with --no-elo for offline use."""
import argparse
import queue
import re
import tkinter.font as tkfont
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
from launcher import claim_single_instance, place, remember, start_game
from ratings import RM_1V1, RM_TEAM, fetch_ratings
from rec_header import read_match, split_sides
from savegames import infer_my_profile_id, recordings, savegame_dirs
from units import load_unique_units
from watch import Pending, POLL_SECONDS, IN_PROGRESS_SECONDS, list_files, try_parse

BG = '#10141e'
PANEL = '#1a2030'
FG = '#e8edf7'
MUTED = '#9caac2'
ACCENT = '#65d9c2'
VIOLET = '#b9a0ff'
AMBER = '#f0bf79'
BLUE = '#80b9fa'
SURFACE = '#242e42'
COLORS = (ACCENT, VIOLET, AMBER, BLUE)


class Dashboard:
    def __init__(self, root, args):
        self.root, self.args = root, args
        self.events = queue.Queue()
        self.stop = threading.Event()
        self.pool = ThreadPoolExecutor(max_workers=2)
        self.generation = 0
        self.font_size = 14
        families = set(tkfont.families(root))
        self.font = 'Noto Sans TC' if 'Noto Sans TC' in families else 'Microsoft JhengHei UI'
        self.display_font = 'Noto Serif TC' if 'Noto Serif TC' in families else self.font
        self.civs, self.my_id = {}, None
        self.units = {}
        self.match = None
        self.tabs = []
        self.counter_texts = []
        self.history_window = None
        self.history_request = 0
        self.history_rows = []
        root.title('AoE2 · 對局筆記')
        place(root, 1220, 860)
        root.minsize(960, 650)
        root.configure(bg=BG)
        root.option_add('*Font', (self.font, 10))
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('TNotebook', background=PANEL, borderwidth=0, bordercolor=PANEL, lightcolor=PANEL, darkcolor=PANEL)
        style.layout('TNotebook', [('Notebook.client', {'sticky': 'nswe'})])
        style.configure('TNotebook.Tab', borderwidth=0, bordercolor=PANEL, lightcolor=PANEL, darkcolor=PANEL, background=BG, foreground=MUTED, padding=(12, 10), font=(self.font, 10))
        style.map('TNotebook.Tab', background=[('selected', SURFACE), ('active', SURFACE)], foreground=[('selected', ACCENT)])
        style.configure('TCombobox', fieldbackground=SURFACE, background=SURFACE, foreground=FG, arrowcolor=ACCENT, bordercolor=SURFACE, lightcolor=SURFACE, darkcolor=SURFACE, padding=6)
        style.map('TCombobox', fieldbackground=[('readonly', SURFACE)], foreground=[('readonly', FG)], selectbackground=[('readonly', SURFACE)], selectforeground=[('readonly', FG)])
        style.configure('Vertical.TScrollbar', background=SURFACE, troughcolor=PANEL, arrowcolor=MUTED, bordercolor=PANEL, lightcolor=PANEL, darkcolor=PANEL, width=10)
        style.map('Vertical.TScrollbar', background=[('active', '#3a4965')])
        root.option_add('*TCombobox*Listbox.background', SURFACE)
        root.option_add('*TCombobox*Listbox.foreground', FG)
        root.option_add('*TCombobox*Listbox.selectBackground', '#344563')
        root.option_add('*Button.activeBackground', SURFACE)
        root.option_add('*Button.activeForeground', FG)
        root.option_add('*Button.highlightThickness', 0)
        bar = tk.Frame(root, bg=BG)
        bar.pack(fill='x', padx=28, pady=(22, 18))
        tk.Label(bar, text='II', font=('Georgia', 30, 'bold'), bg=BG, fg=ACCENT).pack(side='left', padx=(0, 14))
        brand = tk.Frame(bar, bg=BG)
        brand.pack(side='left')
        tk.Label(brand, text='對局筆記', font=(self.display_font, 20, 'bold'), bg=BG, fg=FG, anchor='w').pack(anchor='w')
        tk.Label(brand, text='AGE OF EMPIRES II   /   FIELD NOTES', font=('Segoe UI', 9), bg=BG, fg=MUTED).pack(anchor='w')
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
        ribbon = tk.Frame(detail, bg=PANEL, height=3)
        ribbon.pack(fill='x')
        for color in COLORS:
            tk.Frame(ribbon, bg=color, height=3).pack(side='left', fill='x', expand=True)
        self.status = tk.Label(detail, text='正在讀取遊戲資料…', anchor='w', bg=PANEL, fg=ACCENT, font=(self.font, 11), wraplength=740, justify='left')
        self.status.pack(fill='x', padx=28, pady=(22, 8))
        self.meta = tk.Label(detail, text='選一場對局，看看對手的文明。', anchor='w', bg=PANEL, fg=MUTED, wraplength=740, justify='left')
        self.meta.pack(fill='x', padx=28, pady=(0, 20))
        root.bind('<Configure>', lambda event: self.reflow(event))
        self.book = ttk.Notebook(detail)
        self.book.pack(fill='both', expand=True, padx=20, pady=(0, 16))
        self.empty = tk.Frame(self.book, bg=PANEL)
        self.book.add(self.empty, text='文明情報')
        tk.Label(self.empty, text='下一場，知己知彼。', bg=PANEL, fg=FG, font=(self.font, 23, 'bold')).pack(pady=(100, 20))
        tk.Label(self.empty, text='左側回顧最近 10 場對局。\n新對局開始時，這裡會自動更新。', bg=PANEL, fg=MUTED, font=(self.font, 13), justify='center').pack()
        self.preview = tk.Button(footer, text='最近一場', command=self.preview_latest, state='disabled', bg=BG, fg=MUTED, relief='flat')
        self.preview.pack(side='left', padx=20)
        self.open_history()
        root.protocol('WM_DELETE_WINDOW', self.close)
        threading.Thread(target=self.monitor, daemon=True).start()
        root.after(100, self.drain)

    def close(self):
        self.stop.set()
        self.pool.shutdown(wait=False, cancel_futures=True)
        remember(self.root)
        self.root.destroy()

    def reflow(self, event):
        if event.widget is self.root:
            self.status.configure(wraplength=max(300, event.width - 470))
            self.meta.configure(wraplength=max(300, event.width - 470))

    def resize(self, delta):
        self.font_size = max(11, min(24, self.font_size + delta))
        for text in [text for _, _, text in self.tabs] + self.counter_texts:
            self.style_text(text)

    def style_text(self, text):
        text.configure(font=(self.font, self.font_size), spacing1=3, spacing3=5, selectbackground='#3c506a', selectforeground=FG)
        text.tag_configure('number', foreground=AMBER)
        text.tag_configure('unit', foreground=VIOLET, font=(self.font, self.font_size, 'bold'), spacing1=14)
        text.tag_configure('tech', foreground=BLUE, font=(self.font, self.font_size, 'bold'), spacing1=14)
        text.tag_configure('team', foreground=ACCENT, font=(self.font, self.font_size, 'bold'), spacing1=14)
        text.tag_configure('intro', foreground=MUTED, spacing3=16)
        text.tag_configure('heading', foreground=ACCENT, font=(self.font, self.font_size + 1, 'bold'), spacing1=16)
        text.tag_configure('good', foreground=ACCENT, font=(self.font, self.font_size, 'bold'))
        text.tag_configure('bad', foreground=AMBER, font=(self.font, self.font_size, 'bold'))

    def monitor(self):
        try:
            self.civs = load_civs(self.args.game_dir, self.args.lang)
            self.units = load_unique_units(self.args.game_dir, self.args.lang)
            self.dirs =[Path(d) for d in self.args.dir] if self.args.dir else savegame_dirs()
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
        tk.Label(bar, text='最近對局', bg=BG, fg=FG, font=(self.font, 14, 'bold')).pack(side='left')
        self.history_mode = tk.StringVar(value='多人')
        mode = ttk.Combobox(bar, textvariable=self.history_mode, values=('多人', '排名', '全部'), state='readonly', width=6)
        mode.pack(side='right')
        mode.bind('<<ComboboxSelected>>', lambda event: self.refresh_history() if hasattr(self, 'dirs') else None)
        self.history_summary = tk.Label(window, text='最近 10 場 · 依開局時間排序', bg=BG, fg=MUTED, anchor='w', justify='left', wraplength=330)
        self.history_summary.pack(fill='x', pady=(0, 14))
        body = tk.Frame(window, bg=BG)
        body.pack(fill='both', expand=True)
        style = ttk.Style(window)
        style.configure('History.Treeview', background=BG, fieldbackground=BG, foreground=FG, rowheight=84, borderwidth=0, bordercolor=BG, lightcolor=BG, darkcolor=BG, font=(self.font, 10))
        style.map('History.Treeview', background=[('selected', '#293d50')], foreground=[('selected', '#a5f2df')])
        self.history_tree = ttk.Treeview(body, columns=('match',), show='', selectmode='browse', height=7, style='History.Treeview')
        self.history_tree.tag_configure('even', background='#171e2d')
        self.history_tree.tag_configure('odd', background=BG)
        self.history_tree.column('match', width=312, minwidth=260)
        vertical = ttk.Scrollbar(body, command=self.history_tree.yview)
        vertical.pack(side='right', fill='y')
        self.history_tree.configure(yscrollcommand=vertical.set)
        self.history_tree.pack(fill='both', expand=True)
        self.history_tree.bind('<<TreeviewSelect>>', lambda event: self.select_history())
        self.history_tree.bind('<Return>', lambda event: self.select_history())
        self.history_button = tk.Button(window, text='重新整理對局', command=self.refresh_history, state='disabled', bg=BG, fg=ACCENT, relief='flat', cursor='hand2', pady=10)
        self.history_button.pack(fill='x', pady=(10, 0))
        tk.Label(window, text='錄影檔頭未含勝敗與時長', bg=BG, fg=MUTED, font=(self.font, 9)).pack(anchor='w', pady=8)

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
            self.history_tree.insert('', 'end', iid=str(index), tags=('even' if index % 2 == 0 else 'odd',), values=(f'{stamp}   ·   {kind} {len(match.players)} 人\n{opponent_label}\n我的文明  /  {mine}',))
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
        self.counter_texts = []
        jumps = []
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
                color = COLORS[player.civ_id % len(COLORS)]
                hero = tk.Frame(frame, bg=PANEL)
                hero.pack(fill='x', padx=24, pady=(24, 16))
                badge = tk.Canvas(hero, width=58, height=68, bg=PANEL, highlightthickness=0)
                badge.pack(side='left', padx=(0, 18))
                badge.create_polygon(4, 4, 54, 4, 54, 42, 29, 63, 4, 42, fill=SURFACE, outline=color, width=2)
                badge.create_text(29, 28, text='II', font=('Georgia', 23, 'bold'), fill=color)
                heading = tk.Frame(hero, bg=PANEL)
                heading.pack(side='left', fill='x', expand=True)
                tk.Label(heading, text=(civ.key.upper() if civ else 'UNKNOWN') + '  /  ' + role, font=('Segoe UI', 9), fg=color, bg=PANEL, anchor='w').pack(fill='x')
                tk.Label(heading, text=name, font=(self.display_font, 28, 'bold'), fg=FG, bg=PANEL, anchor='w').pack(fill='x')
                tk.Label(heading, text=player.name, font=(self.font, 12), fg=MUTED, bg=PANEL, anchor='w').pack(fill='x')
                rating = tk.Label(frame, text='積分查詢已關閉' if self.args.no_elo else '正在查詢積分…', font=('Segoe UI', 12), fg=BLUE, bg=SURFACE, anchor='w', padx=14, pady=10)
                rating.pack(fill='x', padx=24, pady=(0, 20))
                body = tk.Frame(frame, bg=PANEL)
                body.pack(fill='both', expand=True, padx=24, pady=(0, 20))
                scrollbar = ttk.Scrollbar(body)
                scrollbar.pack(side='right', fill='y')
                text = tk.Text(body, bg=PANEL, fg=FG, relief='flat', wrap='word', padx=0, borderwidth=0, highlightthickness=0, yscrollcommand=scrollbar.set)
                text.pack(fill='both', expand=True)
                scrollbar.configure(command=text.yview)
                self.style_text(text)
                description = civ.description if civ else '此文明尚無官方說明，請確認遊戲資料版本。'
                for index, line in enumerate(description.splitlines()):
                    tag = 'intro' if index == 0 else ''
                    if line.strip().endswith(('：', ':')):
                        tag = 'unit' if any(word in line for word in ('單位', 'Unit')) else 'tech' if any(word in line for word in ('科技', 'Tech')) else 'team'
                    start = text.index('end-1c')
                    text.insert('end', line + '\n', tag)
                    for number in re.finditer(r'[+−-]?\d+(?:[./]\d+)*(?:%|％)?', line):
                        text.tag_add('number', f'{start}+{number.start()}c', f'{start}+{number.end()}c')
                text.configure(state='disabled')
                self.tabs.append((player, rating, text))
                if players is enemies and player.civ_id in self.units:
                    jumps.append((player.civ_id, frame, body))
            if players is enemies and jumps:
                self.add_counters(jumps)
        if not self.args.no_elo:
            def lookup():
                try:
                    ids = {p.profile_id for p in match.players if p.is_human}
                    result = fetch_ratings(ids) if ids else {}
                    self.events.put(('ratings', (generation, result, None)))
                except Exception:
                    self.events.put(('ratings', (generation, {}, '暫時無法取得積分')))
            self.pool.submit(lookup)

    def add_counters(self, jumps):
        """One tab with every enemy civ's unique units; each enemy's civ tab gets a button that jumps to its civ."""
        frame = tk.Frame(self.book, bg=PANEL)
        self.book.add(frame, text='兵種應對')
        tk.Label(frame, text='特殊兵種怎麼打', font=(self.display_font, 22, 'bold'), fg=FG, bg=PANEL, anchor='w').pack(fill='x', padx=24, pady=(24, 4))
        tk.Label(frame, text='依對手文明列出，取自遊戲的兵種說明；不代表對手已經出這些兵。', font=(self.font, 10), fg=MUTED, bg=PANEL, anchor='w').pack(fill='x', padx=24, pady=(0, 14))
        body = tk.Frame(frame, bg=PANEL)
        body.pack(fill='both', expand=True, padx=24, pady=(0, 20))
        scrollbar = ttk.Scrollbar(body)
        scrollbar.pack(side='right', fill='y')
        text = tk.Text(body, bg=PANEL, fg=FG, relief='flat', wrap='word', padx=0, borderwidth=0, highlightthickness=0, yscrollcommand=scrollbar.set)
        text.pack(fill='both', expand=True)
        scrollbar.configure(command=text.yview)
        self.style_text(text)
        for civ_id in dict.fromkeys(civ_id for civ_id, _, _ in jumps):
            civ = self.civs.get(civ_id)
            text.mark_set(f'civ{civ_id}', 'end-1c')
            text.mark_gravity(f'civ{civ_id}', 'left')
            text.insert('end', (civ.name if civ else f'未知文明 #{civ_id}') + '\n', 'heading')
            for unit in self.units[civ_id]:
                text.insert('end', unit.name + '\n', 'unit')
                if unit.summary:
                    text.insert('end', unit.summary + '\n')
                for label, items, tag in (('用這些打', unit.loses_to, 'good'), ('它特別克制', unit.beats_hard, 'bad'), ('它克制', unit.beats, 'bad')):
                    if items:
                        text.insert('end', label + '　', tag)
                        text.insert('end', '、'.join(items) + '\n')
                if unit.strong_in_numbers:
                    text.insert('end', '數量多時很強\n', 'bad')
                if not (unit.loses_to or unit.beats_hard or unit.beats or unit.strong_in_numbers):
                    text.insert('end', '遊戲說明沒有列出克制關係\n', 'intro')
                if unit.upgrades:
                    text.insert('end', unit.upgrades + '\n', 'intro')
        text.configure(state='disabled')
        self.counter_texts.append(text)
        for civ_id, civ_frame, civ_body in jumps:
            tk.Button(civ_frame, text='看特殊兵種怎麼打　→', command=lambda c=civ_id: self.jump(frame, text, c),
                      bg=SURFACE, fg=VIOLET, activeforeground=VIOLET, relief='flat', borderwidth=0, anchor='w',
                      padx=14, pady=8, cursor='hand2', font=(self.font, 11, 'bold')).pack(fill='x', padx=24, pady=(0, 16), before=civ_body)

    def jump(self, frame, text, civ_id):
        self.book.select(frame)
        self.root.after_idle(lambda: text.yview(f'civ{civ_id}'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lang', default='tw')
    parser.add_argument('--game-dir')
    parser.add_argument('--dir', action='append')
    parser.add_argument('--profile-id', type=int)
    parser.add_argument('--no-elo', action='store_true')
    parser.add_argument('--with-game', action='store_true', help='also start the game through Steam')
    args = parser.parse_args()
    if not claim_single_instance() and args.with_game:  # dashboard already open: just start the game
        start_game()
        return
    root = tk.Tk()
    Dashboard(root, args)
    if args.with_game:
        root.after(1000, start_game)  # after our window is up, so the game ends up in front
    root.mainloop()


if __name__ == '__main__':
    main()
