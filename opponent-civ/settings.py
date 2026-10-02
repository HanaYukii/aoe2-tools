"""Local first-run configuration; no account login or credentials required."""
import json
import os
from collections import Counter
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from civdata import find_game_dir, load_civs
from rec_header import NotReady, Unsupported, read_match
from savegames import infer_my_profile_id, recordings, savegame_dirs

SETTINGS_PATH = Path(os.environ['LOCALAPPDATA']) / 'aoe2-tools' / 'opponent-civ' / 'settings.json'


def read_settings(path=SETTINGS_PATH):
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            return None
        if not isinstance(data.get('game_dir'), str) or not isinstance(data.get('lang'), str):
            return None
        if not isinstance(data.get('dirs'), list) or not all(isinstance(p, str) for p in data['dirs']):
            return None
        profile = data.get('profile_id')
        if profile is not None and (type(profile) is not int or profile <= 0):
            return None
        if type(data.get('no_elo')) is not bool:
            return None
        return data
    except (OSError, ValueError):
        return None


def save_settings(data, path=SETTINGS_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def validate_settings(data):
    if data['lang'] not in ('tw', 'en', 'zh'):
        raise ValueError('請選擇支援的語言。')
    load_civs(data['game_dir'], data['lang'])
    for directory in data['dirs']:
        if not Path(directory).is_dir():
            raise ValueError(f'錄影資料夾不存在：{directory}')


def player_choices(dirs):
    names, counts = {}, Counter()
    for path in recordings(dirs)[:20]:
        try:
            match = read_match(path)
        except (NotReady, Unsupported, OSError):
            continue
        for p in match.players:
            if p.is_human and p.profile_id > 0:
                names[p.profile_id] = p.name
        counts.update({p.profile_id for p in match.players if p.is_human and p.profile_id > 0})
    return {f'{names[pid]} · ID {pid} · {count} 場': pid for pid, count in counts.most_common()}


class SetupDialog:
    def __init__(self, parent, initial=None, first_run=False):
        self.result = None
        initial = initial or {}
        self.window = window = tk.Toplevel(parent)
        window.title('AoE2 對局筆記 · 首次設定' if first_run else 'AoE2 對局筆記 · 設定')
        window.geometry('740x740')
        window.minsize(740, 740)
        window.configure(bg='#10141e')
        area = tk.Frame(window, bg='#10141e', padx=28, pady=24)
        area.pack(fill='both', expand=True)
        def label(text, size=11, color='#9caac2'):
            tk.Label(area, text=text, bg='#10141e', fg=color, font=('Microsoft JhengHei UI', size), anchor='w', justify='left', wraplength=660).pack(fill='x', pady=(5, 7))
        label('歡迎使用對局筆記' if first_run else '設定', 21, '#65d9c2')
        label('確認遊戲位置與玩家身分即可開始。設定只儲存在這台電腦，不需要登入。')
        label('01  遊戲安裝資料夾', color='#e8edf7')
        self.game = tk.StringVar(value=initial.get('game_dir') or str(find_game_dir()))
        row = tk.Frame(area, bg='#10141e'); row.pack(fill='x')
        ttk.Entry(row, textvariable=self.game).pack(side='left', fill='x', expand=True)
        ttk.Button(row, text='瀏覽…', command=self.browse_game).pack(side='right', padx=(8, 0))
        label('02  錄影資料夾（一行一個；留空為自動偵測）', color='#e8edf7')
        self.folders = tk.Text(area, height=2, bg='#242e42', fg='#e8edf7', insertbackground='white', relief='flat')
        self.folders.pack(fill='x')
        self.folders.insert('1.0', '\n'.join(initial.get('dirs', [])))
        ttk.Button(area, text='新增錄影資料夾…', command=self.browse_recordings).pack(anchor='w', pady=5)
        label('03  哪位玩家是你？', color='#e8edf7')
        self.profile = tk.StringVar(value=str(initial.get('profile_id') or '自動判斷'))
        self.players = ttk.Combobox(area, textvariable=self.profile)
        self.players.pack(fill='x')
        ttk.Button(area, text='重新偵測玩家', command=self.refresh_players).pack(anchor='w', pady=5)
        self.hint = tk.Label(area, bg='#10141e', fg='#9caac2', wraplength=650, justify='left', anchor='w')
        self.hint.pack(fill='x')
        label('04  語言與連線', color='#e8edf7')
        self.lang = tk.StringVar(value=initial.get('lang', 'tw'))
        ttk.Combobox(area, textvariable=self.lang, values=('tw', 'en', 'zh'), state='readonly', width=8).pack(anchor='w')
        label('tw 繁中 / en English / zh 簡中；介面與部分提示維持繁中。', 9)
        self.elo = tk.BooleanVar(value=not initial.get('no_elo', False))
        tk.Checkbutton(area, text='查詢目前積分（會將對局中玩家的 profile ID 傳給官方排行榜 API）', variable=self.elo, bg='#10141e', fg='#e8edf7', selectcolor='#242e42', activebackground='#10141e', activeforeground='white').pack(anchor='w')
        ttk.Button(area, text='儲存並開始' if first_run else '儲存（重新開啟程式後生效）', command=self.save).pack(anchor='e', pady=16)
        self.refresh_players()
        window.protocol('WM_DELETE_WINDOW', window.destroy)
        window.grab_set()
        parent.wait_window(window)

    def directories(self):
        return [line.strip() for line in self.folders.get('1.0', 'end').splitlines() if line.strip()]

    def browse_game(self):
        chosen = filedialog.askdirectory(parent=self.window, title='選擇 AoE2DE 安裝資料夾')
        if chosen:
            self.game.set(chosen)

    def browse_recordings(self):
        chosen = filedialog.askdirectory(parent=self.window, title='選擇 savegame 資料夾')
        if chosen:
            current = self.directories()
            if chosen not in current:
                self.folders.delete('1.0', 'end')
                self.folders.insert('1.0', '\n'.join(current + [chosen]))
            self.refresh_players()

    def refresh_players(self):
        try:
            dirs = [Path(d) for d in self.directories()] or savegame_dirs()
            self.choices = player_choices(dirs)
            self.players.configure(values=('自動判斷', *self.choices))
            inferred = infer_my_profile_id(dirs)
            chosen = self.profile.get()
            for name, pid in self.choices.items():
                if chosen == str(pid) or (chosen == '自動判斷' and pid == inferred):
                    self.profile.set(name)
                    break
            self.hint.configure(text='選擇你的暱稱；同名時請核對 ID。亦可直接輸入 profile ID。' if self.choices else '尚無可用錄影：可先用自動判斷開始，打一場有錄影的對局後回設定重新偵測。')
        except OSError as exc:
            self.choices = {}
            self.hint.configure(text=f'無法讀取錄影：{exc}')

    def save(self):
        try:
            value = self.profile.get().strip()
            profile = None if value in ('', '自動判斷') else self.choices.get(value)
            if profile is None and value not in ('', '自動判斷'):
                profile = int(value)
                if profile <= 0:
                    raise ValueError('profile ID 必須為正整數。')
            data = dict(game_dir=self.game.get().strip(), dirs=self.directories(), lang=self.lang.get(), profile_id=profile, no_elo=not self.elo.get())
            validate_settings(data)
            save_settings(data)
        except (OSError, ValueError, KeyError) as exc:
            messagebox.showerror('請確認設定', f'設定未儲存。\n{exc}', parent=self.window)
            return
        self.result = data
        self.window.destroy()
