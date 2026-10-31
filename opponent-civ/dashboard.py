"""Second-screen desktop dashboard. Run with --no-elo for offline use."""
from i18n import tr, set_language, default_language, language
import argparse
import json
import sys
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

from ui_icons import CIVILIZATIONS, civilization_icon, ASSETS, icon, install_window_icon
from civdata import load_civs
from build_views import BuildLibraryUI, button
from settings import SetupDialog, read_settings, validate_settings
from collections import Counter
from history import recent_matches
from launcher import claim_single_instance, place, remember, start_game
from ratings import RM_1V1, RM_TEAM, fetch_ratings
from rec_header import read_match, split_sides
from savegames import infer_my_profile_id, recordings, savegame_dirs
from mapdata import load_map_names, map_label
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
        set_language(getattr(args, "lang", None) or "tw")
        self.events = queue.Queue()
        self.stop = threading.Event()
        self.pool = ThreadPoolExecutor(max_workers=2)
        self.generation = 0
        self.font_size = 12
        families = set(tkfont.families(root))
        self.font = next((f for f in ('Noto Sans TC', 'Microsoft JhengHei UI', 'PingFang TC') if f in families), 'TkDefaultFont')
        self.display_font = 'Noto Serif TC' if 'Noto Serif TC' in families else self.font
        self.civs, self.my_id = {}, None
        self.units = {}
        self.maps = {}
        self.match = None
        self.tabs = []
        self.counter_texts = []
        self.history_window = None
        self.history_request = 0
        self.history_rows = []
        root.title(tr('AoE2 · 對局筆記'))
        install_window_icon(root)
        place(root, 1220, 860)
        root.minsize(960, 650)
        root.configure(bg=BG)
        root.option_add('*Font', (self.font, 10))
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('Build.TButton', background=SURFACE, foreground=FG, padding=(10, 9), borderwidth=0, font=(self.font, 11))
        style.map('Build.TButton', background=[('active', '#344563')], foreground=[('disabled', MUTED)])
        style.configure('Accent.Build.TButton', foreground=ACCENT)
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
        bar.pack(fill='x', padx=28, pady=(10, 10))
        tk.Label(bar, image=icon(root, 'town-center', 64), bg=BG).pack(side='left', padx=(0, 14))
        brand = tk.Frame(bar, bg=BG)
        brand.pack(side='left')
        tk.Label(brand, text=tr('對局筆記'), font=(self.display_font, 20, 'bold'), bg=BG, fg=FG, anchor='w').pack(anchor='w')
        tk.Label(brand, text='AGE OF EMPIRES II   /   FIELD NOTES', font=('Segoe UI', 9), bg=BG, fg=MUTED).pack(anchor='w')
        self.pin = tk.BooleanVar()
        tk.Checkbutton(bar, text=tr('保持置頂'), variable=self.pin, command=lambda: root.attributes('-topmost', self.pin.get()), bg=BG, fg=MUTED, selectcolor=PANEL, activebackground=BG).pack(side='right', padx=(20, 0))
        for label, delta in [('＋', 1), ('－', -1)]:
            button(bar, label, lambda d=delta: self.resize(d)).pack(side='right')
        tk.Label(bar, text=tr('字級'), bg=BG, fg=MUTED).pack(side='right')
        self.sidebar_toggle = button(bar, tr('收起對局列表'), self.toggle_sidebar)
        self.sidebar_toggle.pack(side='right', padx=16)
        footer = tk.Frame(root, bg=BG)
        footer.pack(side='bottom', fill='x', padx=28, pady=12)
        tk.Label(footer, text=tr('●  展示對局 · 內建流程') if getattr(args, 'demo', False) else tr('●  本機錄影 · 自動監看'), bg=BG, fg=ACCENT).pack(side='left')
        tk.Label(footer, text=tr('離線模式') if args.no_elo else tr('排行榜顯示目前積分'), bg=BG, fg=MUTED).pack(side='right')
        workspace = tk.Frame(root, bg=BG)
        workspace.pack(fill='both', expand=True, padx=28)
        self.sidebar = tk.Frame(workspace, bg=BG, width=300)
        self.sidebar.pack(side='left', fill='y', padx=(0, 22))
        self.sidebar.pack_propagate(False)
        detail = self.detail = tk.Frame(workspace, bg=PANEL)
        detail.pack(side='left', fill='both', expand=True)
        ribbon = tk.Frame(detail, bg=PANEL, height=3)
        ribbon.pack(fill='x')
        for color in COLORS:
            tk.Frame(ribbon, bg=color, height=3).pack(side='left', fill='x', expand=True)
        info_row = tk.Frame(detail, bg=PANEL)
        info_row.pack(fill='x', padx=22, pady=(10, 4))
        self.status = tk.Label(info_row, text=tr('正在讀取遊戲資料…'), anchor='w', bg=PANEL, fg=ACCENT, font=(self.font, 11), wraplength=740, justify='left')
        self.status.pack(fill='x', expand=True)
        info_row.bind('<Configure>', lambda e: self.status.configure(wraplength=max(180, e.width)))
        # Outside the notebook and its scroll areas: visible on every page.
        self.reminder_bar = reminders = tk.Frame(detail, bg=SURFACE)
        reminders.pack(fill='x', padx=22, pady=(2, 6))
        self.reminders = []
        items = (
            (tr('記得蓋房子'), 'town-center'), (tr('注意 TC 閒置'), 'hourglass'), (tr('資源記得調配'), 'economy'),
            (tr('記得圍家'), 'wall'), (tr('看小地圖'), 'map'), (tr('記得挖堡'), 'stone-mining'),
            (tr('前後排分隊'), 'combat'), (tr('偵查對手轉兵'), 'scouting'), (tr('產兵建築充足'), 'barracks'),
        )
        for index, (text, artwork) in enumerate(items):
            reminder = tk.Label(reminders, text=text, image=icon(root, artwork, 24),
                compound='left', padx=6, font=(self.font, 14, 'bold'), bg=SURFACE,
                fg=(AMBER, BLUE, ACCENT)[index // 3], anchor='center')
            reminder.grid(row=index // 3, column=index % 3, sticky='ew', padx=6, pady=3)
            self.reminders.append(reminder)
            reminder.bind('<Configure>', lambda e, label=reminder: label.configure(wraplength=max(80, e.width - 48)))
        for column in range(3):
            reminders.columnconfigure(column, weight=1, uniform='reminders')
        self.house_reminder = self.reminders[0]
        meta_row = tk.Frame(detail, bg=PANEL)
        meta_row.pack(fill='x', padx=22, pady=(0, 12))
        self.map_shortcuts = tk.Frame(meta_row, bg=PANEL)
        self.meta = tk.Label(meta_row, text=tr('選一場對局，看看對手的文明。'), anchor='w', bg=PANEL, fg=MUTED, wraplength=740, justify='left')
        self.meta.pack(side='left', fill='x', expand=True)
        self.workspace_book = ttk.Notebook(detail)
        self.workspace_book.pack(fill='both', expand=True)
        self.rp_frame = tk.Frame(self.workspace_book, bg=PANEL)
        self.workspace_book.add(self.rp_frame, text=tr('對局 RP'), image=icon(root, 'map'), compound='left')
        root.bind('<Configure>', lambda event: self.reflow(event))
        self.book = ttk.Notebook(self.rp_frame)
        self.book.pack(fill='both', expand=True, padx=20, pady=(0, 16))
        self.empty = tk.Frame(self.book, bg=PANEL)
        self.book.add(self.empty, text=tr('文明情報'))
        tk.Label(self.empty, text=tr('下一場，知己知彼。'), bg=PANEL, fg=FG, font=(self.font, 23, 'bold')).pack(pady=(100, 20))
        tk.Label(self.empty, text=tr('左側回顧最近 10 場對局。\n新對局開始時，這裡會自動更新。'), bg=PANEL, fg=MUTED, font=(self.font, 13), justify='center').pack()
        self.preview = button(footer, tr('最近一場'), self.preview_latest)
        self.preview.configure(state='disabled')
        self.preview.pack(side='left', padx=20)
        button(footer, tr('設定'), self.configure_app, True).pack(side='right', padx=16)
        self.library = BuildLibraryUI(self)
        self.open_history()
        root.protocol('WM_DELETE_WINDOW', self.close)
        if not getattr(args, 'demo', False):
            threading.Thread(target=self.monitor, daemon=True).start()
        self.drain_timer = root.after(100, self.drain)

    def toggle_sidebar(self):
        if self.sidebar.winfo_manager():
            self.sidebar.pack_forget()
            self.sidebar_toggle.configure(text=tr('展開對局列表'))
        else:
            self.sidebar.pack(side='left', fill='y', padx=(0, 22), before=self.detail)
            self.sidebar_toggle.configure(text=tr('收起對局列表'))

    def configure_app(self):
        data = read_settings()
        SetupDialog(self.root, data)

    def close(self):
        self.stop.set()
        if self.drain_timer is not None:
            self.root.after_cancel(self.drain_timer)
            self.drain_timer = None
        self.pool.shutdown(wait=False, cancel_futures=True)
        if not getattr(self.args, 'demo', False):
            remember(self.root)
        self.root.destroy()

    def reflow(self, event):
        if event.widget is self.root:
            self.meta.configure(wraplength=max(300, event.width - 470))

    def resize(self, delta):
        self.font_size = max(11, min(24, self.font_size + delta))
        self.library.resize(self.font_size)
        for reminder in self.reminders:
            reminder.configure(font=(self.font, self.font_size + 2, 'bold'))
        for _, rating, _ in self.tabs:
            rating.configure(font=(self.font, self.font_size + 6, 'bold'))
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
        text.tag_configure('meta', foreground=MUTED, font=(self.font, max(9, self.font_size - 2)))
        text.tag_configure('group', foreground=BLUE, font=(self.font, self.font_size - 1, 'bold'), spacing1=18)

    def monitor(self):
        try:
            self.civs = load_civs(self.args.game_dir, self.args.lang)
            self.units = load_unique_units(self.args.game_dir, self.args.lang)
            self.maps = load_map_names(self.args.game_dir, self.args.lang)
            self.dirs =[Path(d) for d in self.args.dir] if self.args.dir else savegame_dirs()
            if any(not d.is_dir() for d in self.dirs):
                raise ValueError(tr('找不到錄影資料夾，請用 --dir 指定 savegame 資料夾。'))
            self.my_id = self.args.profile_id or infer_my_profile_id(self.dirs)
            seen = list_files(self.dirs)
            latest = next(iter(recordings(self.dirs)), None)
            pending = {}
            if latest and time.time() - latest.stat().st_mtime < IN_PROGRESS_SECONDS:
                pending[latest] = Pending(latest, joined_late=True)
            self.events.put(('ready', None))
            while not self.stop.is_set():
                if not self.args.dir and not self.dirs:
                    self.dirs = savegame_dirs()
                current = list_files(self.dirs)
                for path in sorted(current - seen):
                    if path.suffix.lower() == '.aoe2record':
                        pending[path] = Pending(path)
                        self.events.put(('status', tr('偵測到新對局，正在等待檔頭寫入…')))
                seen = current
                for path in list(pending):
                    shown = []
                    def present(match, source, delay):
                        shown.append(True)
                        self.events.put(('match', (match, source, delay, False)))
                    if try_parse(pending[path], self.civs, self.my_id, False, presenter=present):
                        del pending[path]
                        if not shown:
                            self.events.put(('status', tr('無法讀取新對局；監看仍持續，請檢查 watch_log.jsonl。')))
                self.stop.wait(POLL_SECONDS)
        except Exception as exc:
            self.events.put(('status', tr('監看停止：{0}' ,f'{exc}')))

    def preview_latest(self):
        self.preview.configure(state='disabled')
        generation = self.generation
        def work():
            try:
                latest = next(iter(recordings(self.dirs)), None)
                if latest is None:
                    raise ValueError(tr('目前沒有錄影檔，開一場對戰後再試。'))
                self.events.put(('preview_match', (generation, (read_match(latest), latest, None, True))))
            except Exception as exc:
                self.events.put(('status', tr('預覽失敗：{0}' ,f'{exc}')))
            finally:
                self.events.put(('preview_done', None))
        self.pool.submit(work)

    def open_history(self):
        window = self.history_window = self.sidebar
        bar = tk.Frame(window, bg=BG)
        bar.pack(fill='x', pady=(0, 12))
        tk.Label(bar, text=tr('最近對局'), bg=BG, fg=FG, font=(self.font, 14, 'bold')).pack(side='left')
        self.history_mode = tk.StringVar(value=tr('多人'))
        mode = ttk.Combobox(bar, textvariable=self.history_mode, values=(tr('多人'), tr('排名'), tr('全部')), state='readonly', width=11 if language() == 'en' else 6)
        mode.pack(side='right')
        mode.bind('<<ComboboxSelected>>', lambda event: self.refresh_history() if hasattr(self, 'dirs') else None)
        self.history_summary = tk.Label(window, text=tr('最近 10 場 · 依開局時間排序'), bg=BG, fg=MUTED, anchor='w', justify='left', wraplength=280)
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
        self.history_button = button(window, tr('重新整理對局'), self.refresh_history, True)
        self.history_button.configure(state='disabled')
        self.history_button.pack(fill='x', pady=(10, 0))
        tk.Label(window, text=tr('錄影檔頭未含勝敗與時長'), bg=BG, fg=MUTED, font=(self.font, 9)).pack(anchor='w', pady=8)

    def refresh_history(self):
        self.history_request += 1
        request = self.history_request
        mode = {tr('多人'): '多人', tr('排名'): '排名', tr('全部'): '全部'}[self.history_mode.get()]
        self.history_summary.configure(text=tr('正在讀取本機錄影…'))
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
            return civ.name if civ else tr('未知文明 #{0}' ,f'{player.civ_id}')
        for index, (path, match) in enumerate(rows):
            me, _, enemies = split_sides(match, self.my_id)
            if me:
                counts[civ_name(me)] += 1
            opponents = '、'.join(f'{p.name}（{civ_name(p)}）' for p in enemies)
            kind = tr('排名') if match.rated else tr('多人') if match.multiplayer else tr('單機')
            stamp = datetime.fromtimestamp(match.timestamp).strftime('%m/%d  %H:%M')
            opponent_label = opponents or tr('無對手')
            if len(opponent_label) > 22:
                opponent_label = opponent_label[:21] + '…'
            mine = civ_name(me) if me else tr('身分不明')
            place_name = map_label(match, self.maps)
            self.history_tree.insert('', 'end', iid=str(index), tags=('even' if index % 2 == 0 else 'odd',), values=(tr('{0}   ·   {1} {2} 人' ,f'{stamp}', f'{kind}', f'{len(match.players)}') + (f' · {place_name}' if place_name else '') + tr('\n{0}\n我的文明  /  {1}' ,f'{opponent_label}', f'{mine}'),))
        summary = tr('最近 {0} 場' ,f'{len(rows)}')
        if counts:
            summary += tr(' · 我的文明：') + '、'.join(tr('{0} {1} 場' ,f'{name}', f'{count}') for name, count in counts.most_common())
        if skipped:
            summary += tr(' · 略過 {0} 個暫時無法解析的錄影' ,f'{skipped}')
        if rows and self.generation == 0:
            self.history_tree.selection_set('0')
        self.history_summary.configure(text=tr('讀取失敗：{0}' ,f'{error}') if error else summary if rows else tr('沒有符合條件的錄影。') + (tr(' 略過 {0} 個無法解析的錄影。' ,f'{skipped}') if skipped else ''))

    def select_history(self):
        selected = self.history_tree.selection()
        if not selected:
            return
        source, match = self.history_rows[int(selected[0])]
        self.show(match, source, None, True)
        self.root.lift()

    def drain(self):
        if self.drain_timer is not None:
            self.root.after_cancel(self.drain_timer)
            self.drain_timer = None
        if self.stop.is_set():
            return
        try:
            while True:
                event, value = self.events.get_nowait()
                if event == 'ready':
                    identity = tr('你的 profile ID：{0}' ,f'{self.my_id}') if self.my_id else tr('無法確認你的身分，將列出所有玩家；可用 --profile-id 指定')
                    self.status.configure(text=tr('監看中 · {0} 個文明 · {1}' ,f'{len(self.civs)}', f'{identity}'))
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
                            summary = '  ·  '.join(f'{name}  {board[key]}' for key, name in ((RM_1V1, '1v1'), (RM_TEAM, tr('團戰'))) if key in board)
                            label.configure(text=tr('電腦玩家') if not player.is_human else error or (tr('目前積分 · ') + summary if summary else tr('沒有排名紀錄')))
        except queue.Empty:
            pass
        self.drain_timer = self.root.after(100, self.drain)

    def show(self, match, source, delay, preview):
        self.generation += 1
        generation = self.generation
        self.workspace_book.select(self.rp_frame)
        self.match = match
        self.library.set_match(match, live=not preview)
        for tab in self.book.tabs():
            self.book.nametowidget(tab).destroy()
        self.tabs = []
        self.counter_texts = []
        jumps = []
        me, allies, enemies = split_sides(match, self.my_id)
        kind = tr('排名') if match.rated else tr('多人') if match.multiplayer else tr('單機')
        place_name = map_label(match, self.maps)
        self.status.configure(text=(tr('歷史預覽') if preview else tr('已讀取新對局')) + f' · {kind}' + (f' · {place_name}' if place_name else '') + tr(' · {0} 人 · {1}' ,f'{len(match.players)}', f'{datetime.fromtimestamp(match.timestamp):%m/%d %H:%M}'))
        self.meta.configure(text=(tr('歷史對局 · 文明說明與積分為目前資料') if preview else tr('開局後 {0} 秒讀到' ,f'{delay:.1f}')) + tr(' · 新對局將自動顯示'))
        if getattr(self.args, 'demo', False):
            self.meta.configure(text=tr('展示用虛構對局 · {0} 套參考流程已內建' ,f'{len(self.library.builds)}'))
        for role, players in [(tr('對手') if me else tr('玩家'), enemies), (tr('你'), [me] if me else []), (tr('隊友'), allies)]:
            for player in players:
                civ = self.civs.get(player.civ_id)
                name = civ.name if civ else tr('未知文明 #{0}' ,f'{player.civ_id}')
                frame = tk.Frame(self.book, bg=PANEL)
                self.book.add(frame, text=f'{role} · {name}',
                              image=civilization_icon(self.root, civ.key if civ else '', 24), compound='left')
                color = COLORS[player.civ_id % len(COLORS)]
                hero = tk.Frame(frame, bg=PANEL)
                hero.pack(fill='x', padx=24, pady=(24, 16))
                tk.Label(hero, image=civilization_icon(self.root, civ.key if civ else '', 64),
                         bg=PANEL).pack(side='left', padx=(0, 18))
                heading = tk.Frame(hero, bg=PANEL)
                heading.pack(side='left', fill='x', expand=True)
                tk.Label(heading, text=(civ.key.upper() if civ else 'UNKNOWN') + '  /  ' + role, font=('Segoe UI', 9), fg=color, bg=PANEL, anchor='w').pack(fill='x')
                tk.Label(heading, text=name, font=(self.display_font, 28, 'bold'), fg=FG, bg=PANEL, anchor='w').pack(fill='x')
                tk.Label(heading, text=player.name, font=(self.font, 12), fg=MUTED, bg=PANEL, anchor='w').pack(fill='x')
                rating = tk.Label(frame, text=tr('積分查詢已關閉') if self.args.no_elo else tr('正在查詢積分…'), font=(self.font, self.font_size + 6, 'bold'), fg=BLUE, bg=SURFACE, anchor='w', justify='left', padx=14, pady=10)
                rating.pack(fill='x', padx=24, pady=(0, 20))
                rating.bind('<Configure>', lambda e, label=rating: label.configure(wraplength=max(120, e.width - 28)))
                body = tk.Frame(frame, bg=PANEL)
                body.pack(fill='both', expand=True, padx=24, pady=(0, 20))
                scrollbar = ttk.Scrollbar(body)
                scrollbar.pack(side='right', fill='y')
                text = tk.Text(body, bg=PANEL, fg=FG, relief='flat', wrap='word', padx=0, borderwidth=0, highlightthickness=0, yscrollcommand=scrollbar.set)
                text.pack(fill='both', expand=True)
                scrollbar.configure(command=text.yview)
                self.style_text(text)
                description = civ.description if civ else tr('此文明尚無官方說明，請確認遊戲資料版本。')
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
                    self.events.put(('ratings', (generation, {}, tr('暫時無法取得積分'))))
            self.pool.submit(lookup)

    def add_counters(self, jumps):
        """One tab with every enemy civ's unique units; each enemy's civ tab gets a button that jumps to its civ."""
        frame = tk.Frame(self.book, bg=PANEL)
        self.book.add(frame, text=tr('兵種應對'))
        tk.Label(frame, text=tr('特殊兵種怎麼打'), font=(self.display_font, 22, 'bold'), fg=FG, bg=PANEL, anchor='w').pack(fill='x', padx=24, pady=(24, 4))
        tk.Label(frame, text=tr('依對手文明列出各建築的特殊兵種與地區兵種，取自遊戲的科技樹與兵種說明；不代表對手已經出這些兵。'), font=(self.font, 10), fg=MUTED, bg=PANEL, anchor='w', wraplength=800, justify='left').pack(fill='x', padx=24, pady=(0, 14))
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
            text.insert('end', (civ.name if civ else tr('未知文明 #{0}' ,f'{civ_id}')) + '\n', 'heading')
            regional_started = False
            for unit in self.units[civ_id]:
                if unit.regional and not regional_started:
                    regional_started = True
                    text.insert('end', tr('地區兵種（少數文明共有）\n'), 'group')
                text.insert('end', unit.name + '\n', 'unit')
                where = ' · '.join(filter(None, (unit.building, unit.age)))
                if where:
                    text.insert('end', where + '\n', 'meta')
                if unit.summary:
                    text.insert('end', unit.summary + '\n')
                for label, items, tag in ((tr('用這些打'), unit.loses_to, 'good'), (tr('它特別克制'), unit.beats_hard, 'bad'), (tr('它克制'), unit.beats, 'bad')):
                    if items:
                        text.insert('end', label + (': ' if language() == 'en' else '　'), tag)
                        text.insert('end', (', ' if language() == 'en' else '、').join(items) + '\n')
                if unit.strong_in_numbers:
                    text.insert('end', tr('數量多時很強\n'), 'bad')
                if not (unit.loses_to or unit.beats_hard or unit.beats or unit.strong_in_numbers):
                    text.insert('end', tr('遊戲說明沒有列出克制關係\n'), 'intro')
                if unit.upgrades:
                    text.insert('end', unit.upgrades + '\n', 'intro')
        text.configure(state='disabled')
        self.counter_texts.append(text)
        for civ_id, civ_frame, civ_body in jumps:
            tk.Button(civ_frame, text=tr('看特殊兵種怎麼打\u3000→'), command=lambda c=civ_id: self.jump(frame, text, c),
                      bg=SURFACE, fg=VIOLET, activeforeground=VIOLET, relief='flat', borderwidth=0, anchor='w',
                      padx=14, pady=8, cursor='hand2', font=(self.font, 11, 'bold')).pack(fill='x', padx=24, pady=(0, 16), before=civ_body)

    def jump(self, frame, text, civ_id):
        self.book.select(frame)
        self.root.after_idle(lambda: text.yview(f'civ{civ_id}'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lang', choices=('tw', 'en', 'zh'), help='app, guides and game-data language')
    parser.add_argument('--game-dir')
    parser.add_argument('--dir', action='append')
    parser.add_argument('--profile-id', type=int)
    parser.add_argument('--no-elo', action='store_true', default=None)
    parser.add_argument('--with-game', action='store_true', help='also start the game through Steam')
    parser.add_argument('--setup', action='store_true', help='open settings before starting')
    parser.add_argument('--media-dir', '--library-dir', dest='media_dir', help='optional downloaded video/PDF directory')
    parser.add_argument('--demo-build', type=int, metavar='INDEX', help='open a build in the offline demo')
    parser.add_argument('--demo', action='store_true', help='synthetic example; no monitoring or network')
    parser.add_argument('--check-bundled-data', metavar='REPORT', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.check_bundled_data:
        set_language(args.lang or "tw")
        from map_notes import load_map_notes
        from build_library import load_library
        builds = load_library()
        report = dict(builds=len(builds), steps=sum(len(b.steps) for b in builds),
                      icons=len(list(ASSETS.rglob('*.png'))), civilizations=len(CIVILIZATIONS), map_notes=len(load_map_notes()), bundled=bool(getattr(sys, 'frozen', False)))
        Path(args.check_bundled_data).write_text(json.dumps(report), encoding='utf-8')
        return
    if not args.demo and not claim_single_instance() and args.with_game:  # dashboard already open: just start the game
        start_game()
        return
    root = tk.Tk()
    if not args.demo:
        root.withdraw()
        config = read_settings()
        set_language(args.lang or (config or {}).get("lang") or default_language())
        try:
            if config:
                validate_settings(config)
        except (OSError, ValueError, KeyError):
            config = None
        if config is None or args.setup:
            config = SetupDialog(root, config or {"lang": args.lang or default_language()}, first_run=True).result
            if config is None:
                root.destroy()
                return
        for field, key in (('game_dir', 'game_dir'), ('dir', 'dirs'), ('profile_id', 'profile_id'), ('lang', 'lang'), ('no_elo', 'no_elo')):
            if getattr(args, field) is None:
                setattr(args, field, config.get(key))
        root.deiconify()
    else:
        args.lang = args.lang or default_language()
        args.no_elo = True
    app = Dashboard(root, args)
    if args.demo:
        from demo import populate
        populate(app)
        if args.demo_build is not None:
            selected = next((b for b in app.library.builds if b.index == args.demo_build), None)
            if selected is None:
                app.close()
                parser.error(f'unknown build index: {args.demo_build}')
            root.after(200, lambda: app.library.pick(selected))
    if args.with_game and not args.demo:
        root.after(1000, start_game)  # after our window is up, so the game ends up in front
    root.mainloop()


if __name__ == '__main__':
    main()
