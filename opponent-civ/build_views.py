"""Local build picker and persistent, full-table reading views."""
import os
import sys
import subprocess
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from build_library import LibraryState, load_library, filter_builds, read_catalog

BG, PANEL, FG, MUTED, ACCENT, SURFACE = '#10141e', '#1a2030', '#e8edf7', '#9caac2', '#65d9c2', '#242e42'


def button(parent, text, command, accent=False):
    return ttk.Button(parent, text=text, command=command,
                      style='Accent.Build.TButton' if accent else 'Build.TButton', cursor='hand2', width=0)


def open_local(path):
    if not path or not path.is_file():
        messagebox.showinfo('找不到教材', '這份教材不在目前的資料夾中。')
        return
    try:
        if sys.platform == 'win32':
            os.startfile(str(path))
        else:
            subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', str(path)])
    except OSError as exc:
        messagebox.showerror('無法開啟', str(exc))


class ScrollArea(tk.Frame):
    def __init__(self, parent, background=PANEL):
        super().__init__(parent, bg=background)
        self.canvas = tk.Canvas(self, bg=background, highlightthickness=0)
        self.bar = ttk.Scrollbar(self, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.bar.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.body = tk.Frame(self.canvas, bg=background)
        self.window = self.canvas.create_window(0, 0, anchor='nw', window=self.body)
        self.body.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfigure(self.window, width=e.width))
        self.bind_wheel(self.canvas)

    def bind_wheel(self, widget):
        def wheel(event):
            if self.canvas.yview() == (0.0, 1.0):
                return 'break'
            amount = -event.delta if sys.platform == 'darwin' else -int(event.delta / 120)
            self.canvas.yview_scroll(amount, 'units')
            return 'break'
        widget.bind('<MouseWheel>', wheel)
        widget.bind('<Button-4>', lambda e: self.canvas.yview_scroll(-3, 'units'))
        widget.bind('<Button-5>', lambda e: self.canvas.yview_scroll(3, 'units'))
        for child in widget.winfo_children():
            self.bind_wheel(child)


class ReferenceSheet(tk.Frame):
    """A compact reference tab, with scrolling retained for small displays."""
    def __init__(self, parent, sheet, font, size, close, open_build, builds):
        super().__init__(parent, bg=PANEL)
        self.sheet, self.font, self.size = sheet, font, size
        top = tk.Frame(self, bg=PANEL)
        top.pack(fill='x', padx=16, pady=(10, 4))
        button(top, '關閉速查', close).pack(side='right')
        tk.Label(top, text=sheet['title'], bg=PANEL, fg=FG, font=(font, 17, 'bold'),
                 anchor='w').pack(side='left')
        for build in builds:
            button(top, build.title, lambda b=build: open_build(b)).pack(side='right', padx=(0, 6))
        self.caption = tk.Label(self, text=sheet['subtitle'], bg=PANEL, fg=MUTED,
                               font=(font, 10), anchor='w', justify='left', wraplength=1000)
        self.caption.pack(fill='x', padx=16, pady=(0, 6))
        self.scroll = ScrollArea(self)
        self.scroll.pack(fill='both', expand=True, padx=10, pady=(0, 8))
        self.cards, self.texts = [], []
        for item in sheet['cards']:
            card = tk.Frame(self.scroll.body, bg=BG, padx=10, pady=7)
            tk.Label(card, text=item['title'], bg=BG, fg=ACCENT, anchor='w',
                     font=(font, 12, 'bold')).pack(fill='x', pady=(0, 4))
            label = tk.Label(card, text=item['body'], bg=BG, fg=FG, anchor='nw',
                             justify='left', font=(font, max(10, size-1)), wraplength=520)
            label.pack(fill='both', expand=True)
            self.cards.append(card)
            self.texts.append(label)
        footer = tk.Frame(self, bg=PANEL)
        footer.pack(fill='x', padx=16, pady=(0, 6))
        for source in sheet.get('sources', []):
            link = tk.Label(footer, text=source['title']+' ↗', bg=PANEL, fg=MUTED,
                            font=(font, 9), cursor='hand2')
            link.pack(side='left', padx=(0, 16))
            link.bind('<Button-1>', lambda e, url=source['url']: webbrowser.open(url))
        self.scroll.bind_wheel(self.scroll.body)
        self.scroll.canvas.bind('<Configure>', self.reflow, add='+')

    def reflow(self, event):
        columns = 3 if event.width >= 1150 else 2 if event.width >= 850 else 1
        for col in range(3):
            self.scroll.body.columnconfigure(col, weight=1 if col < columns else 0,
                                             uniform='cards' if col < columns else '')
        for i, (card, label) in enumerate(zip(self.cards, self.texts)):
            card.grid(row=i//columns, column=i%columns, sticky='nsew', padx=6, pady=4)
            label.configure(wraplength=max(240, event.width//columns-42))
        self.caption.configure(wraplength=max(240, event.width-24))

    def resize(self, size):
        self.size = size
        for label in self.texts:
            label.configure(font=(self.font, max(10, size-1)))


class BuildReader(tk.Frame):
    def __init__(self, parent, build, state, font, size, leave, leave_label='返回 RP', reference=None):
        super().__init__(parent, bg=PANEL)
        self.build, self.state, self.font, self.size = build, state, font, size
        saved = state.data['positions'].get(build.id, {})
        saved = saved if isinstance(saved, dict) else {}
        self.selected = saved.get('row', -1)
        self.rows, self.tasks, self.labels = [], [], []
        top = tk.Frame(self, bg=PANEL)
        top.pack(fill='x', padx=20, pady=(12, 6))
        button(top, leave_label, leave).pack(side='right')
        tk.Label(top, text=f'{build.population} 人口  ·  {build.title}', bg=PANEL, fg=FG,
                 font=(font, 19, 'bold'), anchor='w', wraplength=800).pack(side='left', fill='x', expand=True)
        tools = tk.Frame(self, bg=PANEL)
        tools.pack(fill='x', padx=20, pady=(0, 12))
        self.media_bar = tk.Frame(tools, bg=PANEL)
        self.media_bar.pack(side='right')
        self.update_media(build)
        self.position_label = tk.Label(tools, text=(build.arrival+'  ·  ' if build.arrival else '')+'點一下步驟，標記看到的位置', bg=PANEL, fg=ACCENT, anchor='w')
        self.position_label.pack(side='bottom', anchor='w', pady=(7, 0))
        self.scroll = ScrollArea(self)
        self.scroll.pack(fill='both', expand=True, padx=20, pady=(0, 12))
        grid = self.scroll.body
        grid.columnconfigure(1, weight=1)
        headings = ('人口', '操作', '木', '食', '金', '石')
        for col, heading in enumerate(headings):
            tk.Label(grid, text=heading, bg=SURFACE, fg=MUTED, padx=10, pady=9,
                     font=(font, 11, 'bold')).grid(row=0, column=col, sticky='nsew')
        previous, line = None, 1
        self.ages = {}
        for index, step in enumerate(build.steps):
            if step.age != previous:
                stage = tk.Label(grid, text=step.age, anchor='w', bg=PANEL, fg=ACCENT,
                                font=(font, 13, 'bold'), padx=10, pady=12)
                stage.grid(row=line, column=0, columnspan=6, sticky='ew')
                self.ages.setdefault(step.age, stage)
                previous, line = step.age, line + 1
            cells = []
            for col, value in enumerate((step.population or '·', step.task.replace('<br>', '\n'), step.wood, step.food, step.gold, step.stone)):
                cell = tk.Label(grid, text=value or '—', bg=BG if index % 2 == 0 else PANEL,
                                fg=FG if col in (0, 1) else MUTED, font=(font, size),
                                justify='left' if col == 1 else 'center', anchor='w' if col == 1 else 'center', padx=12, pady=6,
                                width=0 if col == 1 else 3, wraplength=580 if col == 1 else 0, cursor='hand2')
                cell.grid(row=line, column=col, sticky='nsew')
                cell.bind('<Button-1>', lambda e, n=index: self.mark(n))
                cells.append(cell)
                self.labels.append(cell)
                if col == 1:
                    self.tasks.append(cell)
            self.rows.append(cells)
            line += 1
        if build.notes:
            notes = build.notes.replace('### ', '').replace('\n- ', '\n• ').removeprefix('- ')
            self.notes = tk.Label(grid, text='打法與轉型\n\n'+notes, bg=PANEL, fg=MUTED,
                                 justify='left', anchor='w', font=(font, size), padx=12, pady=24, wraplength=850)
            self.notes.grid(row=line, column=0, columnspan=6, sticky='ew')
        jump = tk.Frame(tools, bg=PANEL)
        jump.pack(side='left')
        for age in self.ages:
            button(jump, age, lambda a=age: self.jump(a)).pack(side='left', padx=(0, 6))
        if reference:
            button(jump, '城堡期速查', reference, True).pack(side='left', padx=(0, 6))
        self.scroll.bind_wheel(grid)
        self.scroll.canvas.bind('<Configure>', self.reflow, add='+')
        if isinstance(self.selected, int) and 0 <= self.selected < len(self.rows):
            self.mark(self.selected, save=False)
        else:
            self.selected = -1
        fraction = saved.get('scroll', 0)
        self.restore_fraction = max(0, min(float(fraction), 1)) if isinstance(fraction, (float, int)) else 0
        self.bind('<Map>', self.restore)

    def update_media(self, build):
        self.build = build
        for child in self.media_bar.winfo_children():
            child.destroy()
        if build.video:
            button(self.media_bar, '本機影片 ↗', lambda: open_local(build.video), True).pack(side='right', padx=(8, 0))
        if build.video_url:
            button(self.media_bar, '會員影片 ↗', lambda: webbrowser.open(build.video_url), not bool(build.video)).pack(side='right', padx=(8, 0))
        if build.pdf:
            button(self.media_bar, f'PDF · 第 {build.page} 頁 ↗', lambda: open_local(build.pdf)).pack(side='right')

    def restore(self, event):
        if event.widget is self and self.restore_fraction is not None:
            fraction, self.restore_fraction = self.restore_fraction, None
            self.after_idle(lambda: self.scroll.canvas.yview_moveto(fraction) if self.winfo_exists() else None)

    def reflow(self, event):
        width = max(220, event.width - 330)
        for cell in self.tasks:
            cell.configure(wraplength=width)
        if hasattr(self, 'notes'):
            self.notes.configure(wraplength=max(240, event.width-40))

    def mark(self, index, save=True):
        self.selected = index
        for n, row in enumerate(self.rows):
            for cell in row:
                cell.configure(bg='#24473f' if n == index else BG if n % 2 == 0 else PANEL)
        self.position_label.configure(text=f'目前看到第 {index+1} 步 · {self.build.steps[index].age}')
        if save:
            self.persist()

    def jump(self, age):
        self.update_idletasks()
        height = max(1, self.scroll.body.winfo_height())
        self.scroll.canvas.yview_moveto(self.ages[age].winfo_y()/height)

    def resize(self, size):
        self.size = size
        for cell in self.labels:
            cell.configure(font=(self.font, size))
        if hasattr(self, 'notes'):
            self.notes.configure(font=(self.font, size))

    def persist(self):
        self.state.data['positions'][self.build.id] = {'row': self.selected, 'scroll': self.scroll.canvas.yview()[0]}
        try:
            self.state.save()
        except OSError:
            self.position_label.configure(text='位置保留於本次開啟；無法寫入設定檔')


class BuildLibraryUI:
    def __init__(self, app):
        self.app = app
        style = ttk.Style(app.root)
        style.configure('Build.TButton', background=SURFACE, foreground=FG, borderwidth=0,
                        padding=(16, 11), font=(app.font, 12), anchor='center')
        style.map('Build.TButton', background=[('active', '#344563')], foreground=[('disabled', MUTED)])
        style.configure('Accent.Build.TButton', foreground=ACCENT)
        self.state = LibraryState()
        self.builds, self.error, self.picker = [], '', None
        self.readers, self.direct, self.reader_frame = {}, None, None
        self.reference_tabs, self.reference_sheets = {}, {}
        self.opened_menu = tk.Menu(app.root, tearoff=False)
        self.opened_button = ttk.Menubutton(app.quickbar, text='已開流程 ▾', menu=self.opened_menu, style='Build.TButton')
        # Old folder settings become optional media locations; never a source of steps.
        selected = (getattr(app.args, 'media_dir', None) or getattr(app.args, 'library_dir', None)
                    or self.state.data.get('media_dir') or self.state.data.get('library_dir'))
        self.directory = Path(selected) if selected else None
        self.overview_tab = None
        self.reload()
        app.workspace_book.bind('<<NotebookTabChanged>>', lambda e: self.save_positions())

    def reload(self):
        try:
            self.builds = load_library(self.directory)
            self.reference_sheets = {s['id']: s for s in read_catalog().get('reference_sheets', [])}
            self.error = ''
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self.builds, self.error = [], str(exc)
            self.reference_sheets = {}

    def open_reference(self, sheet_id):
        self.save_positions()
        if sheet_id not in self.reference_tabs:
            sheet = self.reference_sheets[sheet_id]
            builds = [b for b in self.builds if b.id in sheet['build_ids']]
            tab = ReferenceSheet(self.app.workspace_book, sheet, self.app.font, self.app.font_size,
                                 lambda: self.close_reference(sheet_id), self.open_build, builds)
            self.reference_tabs[sheet_id] = tab
            self.app.workspace_book.add(tab, text=sheet['title'])
        self.app.workspace_book.select(self.reference_tabs[sheet_id])
        self.update_opened_menu()

    def close_reference(self, sheet_id):
        self.reference_tabs.pop(sheet_id).destroy()
        self.app.workspace_book.select(self.app.rp_frame)
        self.update_opened_menu()

    def reference_for(self, build):
        for sheet in self.reference_sheets.values():
            if build.id in sheet['build_ids']:
                return lambda sid=sheet['id']: self.open_reference(sid)
        return None

    def choose_folder(self):
        folder = filedialog.askdirectory(parent=self.app.root, title='選擇已下載的影片資料夾（選用）', initialdir=self.directory)
        if folder:
            self.directory = Path(folder)
            self.reload()
            self.state.data['media_dir'] = folder
            try:
                self.state.save()
            except OSError:
                messagebox.showinfo('無法儲存設定', '本次仍可播放，重新開啟後請再選影片資料夾。', parent=self.app.root)
            updated = {b.id: b for b in self.builds}
            for reader in self.readers.values():
                if reader.build.id in updated:
                    reader.update_media(updated[reader.build.id])
            self.refresh_picker()
            if self.builds and not any(b.video or b.pdf for b in self.builds):
                messagebox.showinfo('未找到本機影片', '這個資料夾沒有對應的影片或 PDF；內建流程與會員影片連結仍可照常使用。', parent=self.app.root)

    def open_overview(self):
        app = self.app
        if self.overview_tab is None:
            self.overview_tab = tk.Frame(app.workspace_book, bg=PANEL)
            app.workspace_book.add(self.overview_tab, text='開局調整')
            area = tk.Text(self.overview_tab, bg=PANEL, fg=FG, wrap='word', relief='flat',
                           font=(app.font, app.font_size), padx=24, pady=20, spacing3=8)
            scroll = ttk.Scrollbar(self.overview_tab, command=area.yview)
            area.configure(yscrollcommand=scroll.set)
            scroll.pack(side='right', fill='y')
            area.pack(fill='both', expand=True)
            # Render the short introduction as readable paragraphs, including animal variants.
            for line in read_catalog()['overview'].splitlines():
                if line.startswith('|---'):
                    continue
                if line.startswith('|'):
                    line = '：'.join(part.strip() for part in line.strip('|').split('|'))
                area.insert('end', line.lstrip('# ').replace('<br>', '\n')+'\n')
            area.configure(state='disabled')
        app.workspace_book.select(self.overview_tab)

    def open_picker(self):
        if self.picker and self.picker.winfo_exists():
            self.app.workspace_book.select(self.picker)
            return
        from rec_header import split_sides
        from mapdata import map_label
        app = self.app
        me = split_sides(app.match, app.my_id)[0] if app.match else None
        civ = app.civs.get(me.civ_id) if me else None
        self.context_map = map_label(app.match, app.maps) if app.match else ''
        window = self.picker = tk.Frame(app.workspace_book, bg=PANEL)
        app.workspace_book.add(window, text='流程選單')
        app.workspace_book.select(window)
        top = tk.Frame(window, bg=PANEL)
        top.pack(fill='x', padx=24, pady=(22, 12))
        tk.Label(top, text='我的文明流程', bg=PANEL, fg=FG, font=(app.font, 22, 'bold')).pack(side='left')
        button(top, '本機影片（選用）…', self.choose_folder).pack(side='right')
        button(top, '開局調整', self.open_overview).pack(side='right', padx=8)
        context = tk.Frame(window, bg=PANEL)
        context.pack(fill='x', padx=24, pady=8)
        self.civ_options = {'未指定文明': ''}
        self.civ_options.update({c.name: c.key for c in app.civs.values()})
        self.civ_name = tk.StringVar(value=civ.name if civ else '未指定文明')
        selector = ttk.Combobox(context, textvariable=self.civ_name, values=list(self.civ_options), state='readonly', width=15)
        selector.pack(side='left')
        selector.bind('<<ComboboxSelected>>', lambda e: self.refresh_picker())
        self.use_map = tk.BooleanVar(value=False)
        tk.Checkbutton(context, text=f'符合目前地圖：{self.context_map or "未知"}', variable=self.use_map,
                       command=self.refresh_picker, bg=PANEL, fg=MUTED, selectcolor=BG, activebackground=PANEL).pack(side='left', padx=16)
        self.search = tk.StringVar()
        entry = tk.Entry(window, textvariable=self.search, bg=BG, fg=FG, insertbackground=ACCENT,
                         relief='flat', font=(app.font, 14))
        entry.pack(fill='x', padx=24, ipady=10, pady=8)
        tk.Label(window, text='搜尋打法或人口，例如：裝甲、直城、23＋2', bg=PANEL, fg=MUTED).pack(anchor='w', padx=24)
        self.mode = tk.StringVar(value='recommended')
        modes = tk.Frame(window, bg=PANEL)
        modes.pack(fill='x', padx=24, pady=12)
        for label, value in [('文明常用', 'recommended'), ('我的收藏', 'favorites'), ('全部流程', 'all')]:
            tk.Radiobutton(modes, text=label, variable=self.mode, value=value, command=self.refresh_picker,
                           indicatoron=False, bg=BG, fg=FG, selectcolor='#24473f', activebackground=SURFACE,
                           padx=18, pady=10, relief='flat').pack(side='left', padx=(0, 6))
        self.count = tk.Label(window, bg=PANEL, fg=MUTED, anchor='w')
        self.count.pack(fill='x', padx=24, pady=(0, 8))
        self.reference_bar = tk.Frame(window, bg=PANEL)
        self.reference_bar.pack(fill='x', padx=24)
        self.results = ScrollArea(window)
        self.results.pack(fill='both', expand=True, padx=24, pady=(0, 20))
        self.search.trace_add('write', lambda *a: self.refresh_picker())
        self.refresh_picker()
        entry.focus_set()

    def refresh_picker(self):
        if not self.picker or not self.picker.winfo_exists():
            return
        for child in self.results.body.winfo_children():
            child.destroy()
        civ = self.civ_options[self.civ_name.get()]
        for child in self.reference_bar.winfo_children():
            child.destroy()
        for sheet in self.reference_sheets.values():
            if sheet['civ'] == civ.casefold():
                button(self.reference_bar, sheet['title'],
                       lambda sid=sheet['id']: self.open_reference(sid), True).pack(side='left', pady=(0, 8))
        favorites = self.state.favorites(civ)
        mode = 'all' if self.search.get().strip() else self.mode.get()
        builds = filter_builds(self.builds, civ, self.context_map, self.search.get(), mode, favorites, self.use_map.get())
        self.count.configure(text=self.error or f'{len(builds)} 套流程' + (' · 搜尋全部流程' if self.search.get().strip() else ''))
        if not builds:  # the count line already states the error; here say what to do about it
            hint = '請重新下載最新版程式，內建流程不需要另外選擇資料夾。' if self.error else '沒有符合的流程。試試「全部流程」或取消地圖篩選。'
            tk.Label(self.results.body, text=hint, bg=PANEL, fg=MUTED, wraplength=680, pady=35).pack(fill='x')
        for b in builds:
            row = tk.Frame(self.results.body, bg=BG, padx=16, pady=12)
            row.pack(fill='x', pady=(0, 8))
            title = tk.Frame(row, bg=BG)
            title.pack(fill='x')
            tk.Label(title, text=f'{b.population} 人口  ·  {b.title}', bg=BG, fg=FG, font=(self.app.font, 14, 'bold'), anchor='w').pack(side='left')
            tag = {'ready': '文明專屬' if b.civs else '通用', 'adjust': '開局需調整', 'other': '其他文明', 'unavailable': '此文明不適用', 'unknown': '先選文明確認適用性'}[b.compatibility(civ)]
            tk.Label(row, text=tag+'  ·  '+{'open':'開放地圖','closed':'封閉地圖','fortress':'堡壘','water':'有魚可吃的地圖'}[b.map_type]+('  ·  本機影片' if b.video else '  ·  會員影片' if b.video_url else ''), bg=BG, fg=MUTED, anchor='w').pack(fill='x', pady=(4, 10))
            actions = tk.Frame(row, bg=BG)
            actions.pack(fill='x')
            button(actions, '直接看', lambda item=b: self.open_build(item, False), True).pack(side='left', padx=(0, 8))
            button(actions, '另開分頁', lambda item=b: self.open_build(item, True)).pack(side='left')
            button(actions, '★ 常用' if b.id in favorites else '☆ 常用', lambda item=b: self.favorite(civ, item)).pack(side='right')
        self.results.bind_wheel(self.results.body)
        self.results.canvas.yview_moveto(0)

    def favorite(self, civ, build):
        self.state.toggle_favorite(civ, build.id)
        self.refresh_picker()

    def open_build(self, build, separate=False):
        self.save_positions()
        app = self.app
        existing_tab = self.readers.get(('tab', build.id))
        if existing_tab is not None:
            app.workspace_book.select(existing_tab)
            return
        if separate and ('direct', build.id) in self.readers:
            old = self.readers.pop(('direct', build.id))
            old.persist()
            if self.direct is old:
                self.direct = None
            old.destroy()
        if separate:
            token = ('tab', build.id)
            if token not in self.readers:
                reader = BuildReader(app.workspace_book, build, self.state, app.font, app.font_size,
                                     lambda: self.close_tab(token), '關閉分頁', self.reference_for(build))
                self.readers[token] = reader
                app.workspace_book.add(reader, text=build.title[:12] + ('…' if len(build.title) > 12 else ''))
            app.workspace_book.select(self.readers[token])
            self.update_opened_menu()
        else:
            token = ('direct', build.id)
            if self.direct:
                self.direct.pack_forget()
            if self.reader_frame is None:
                self.reader_frame = tk.Frame(app.workspace_book, bg=PANEL)
                app.workspace_book.add(self.reader_frame, text='流程閱讀')
            if token not in self.readers:
                self.readers[token] = BuildReader(self.reader_frame, build, self.state, app.font, app.font_size,
                                                 self.back, reference=self.reference_for(build))
            self.direct = self.readers[token]
            self.direct.pack(fill='both', expand=True)
            app.workspace_book.select(self.reader_frame)

    def back(self):
        if self.direct:
            self.direct.persist()
        # The RP tab always stays the RP; the reusable reader has its own tab.
        self.app.workspace_book.select(self.app.rp_frame)

    def close_tab(self, token):
        reader = self.readers.pop(token)
        reader.persist()
        reader.destroy()
        self.app.workspace_book.select(self.app.rp_frame)
        self.update_opened_menu()

    def update_opened_menu(self):
        self.opened_menu.delete(0, 'end')
        for (kind, _), reader in self.readers.items():
            if kind == 'tab':
                self.opened_menu.add_command(label=reader.build.title, command=lambda r=reader: self.app.workspace_book.select(r))
        for sheet in self.reference_tabs.values():
            self.opened_menu.add_command(label=sheet.sheet['title'], command=lambda s=sheet: self.app.workspace_book.select(s))
        if self.opened_menu.index('end') is not None:
            self.opened_button.pack(side='left', padx=10)
        else:
            self.opened_button.pack_forget()

    def reset_context(self):
        # A new RP invalidates only the picker, never open readers.
        if self.picker and self.picker.winfo_exists():
            self.picker.destroy()
        self.picker = None

    def save_positions(self):
        # Visible views win if the same build is open in both places.
        for reader in sorted(self.readers.values(), key=lambda r: r.winfo_ismapped()):
            reader.persist()
