"""Build tabs beside the RP: 前期流程 reads one build, 戰術速查 shows the sheet that follows it,
and 流程庫 is where builds are chosen, ordered and searched."""
from i18n import tr, language
import os
import re
import sys
import subprocess
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from build_library import LibraryState, key, load_library, map_kind, opening_for, read_catalog, search_builds, sheets_for
from ui_icons import icon, sheet_icon, civilization_icon
from mapdata import map_label
from map_notes import load_map_notes, note_for_map
from rec_header import split_sides

BG, PANEL, FG, MUTED, ACCENT, SURFACE = '#10141e', '#1a2030', '#e8edf7', '#9caac2', '#65d9c2', '#242e42'
MARKED = '#24473f'
MAP_TYPES = {'open': '開放地圖', 'closed': '封閉地圖', 'fortress': '堡壘', 'water': '有魚可吃的地圖'}


def button(parent, text, command, accent=False):
    return ttk.Button(parent, text=text, command=command,
                      style='Accent.Build.TButton' if accent else 'Build.TButton', cursor='hand2', width=0)


def open_local(path):
    if not path or not path.is_file():
        messagebox.showinfo(tr('找不到教材'), tr('這份教材不在目前的資料夾中。'))
        return
    try:
        if sys.platform == 'win32':
            os.startfile(str(path))
        else:
            subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', str(path)])
    except OSError as exc:
        messagebox.showerror(tr('無法開啟'), str(exc))


def suitability(build, civ_key):
    if build.compatibility(civ_key) in {'ready', 'unknown'}:
        return tr('文明專屬') if build.civs else tr('通用')
    return {'adjust': tr('開局需調整'), 'other': tr('其他文明'), 'unavailable': tr('此文明不適用')}[build.compatibility(civ_key)]


WIDE_TOKEN = re.compile(r'[⺀-￿]| +|[^ ⺀-￿]+')
NO_LINE_START = set('，。、；：！？）」』】〕》％%…')


def wrap_text(text, measure, width):
    """Break lines Chinese-style, as Tk only breaks at spaces and leaves long CJK runs ragged.

    Any two wide characters may part; a Latin or number word ("30–35", "TC") stays whole; a
    space at the break is dropped. Closing punctuation never opens a line: when it does not fit,
    the word before it moves down with it, so no line runs past `width`.
    """
    lines = []
    for paragraph in text.split('\n'):
        line, used = [], 0
        for token in WIDE_TOKEN.findall(paragraph):
            size = measure(token)
            if not line or used + size <= width:
                line.append(token)
                used += size
            elif token.isspace():
                lines.append(''.join(line).rstrip())
                line, used = [], 0
            elif token[0] in NO_LINE_START and len(line) > 1 and not line[-1].isspace():
                carried = line.pop()
                lines.append(''.join(line).rstrip())
                line, used = [carried, token], measure(carried) + size
            else:
                lines.append(''.join(line).rstrip())
                line, used = [token], size
        lines.append(''.join(line).rstrip())
    return '\n'.join(lines)


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


REFERENCE_TECH = re.compile(
    r'精銳|二級箭|二級射|[一二三]級(?:步防|弓防|馬防|金|石)|'
    r'[一二三](?:木|農|防)|彈道(?:學)?|化學|織布|輪軸|手推車|'
    r'銀冠(?:葡萄園)?|金冠|徵兵(?:技術)?|步防|弓防|馬防|戟兵|長槍升級|'
    r'Elite Skirmisher|Bodkin Arrow|Fletching|Bracer|Ballistics|Chemistry|Loom|Wheelbarrow|Hand Cart|'
    r'Double-Bit Axe|Bow Saw|Horse Collar|Heavy Plow|Conscription|Halberdier|Pikeman|'
    r'(?:Scale|Chain|Plate) (?:Mail|Barding) Armor|(?:Padded|Leather|Ring) Archer Armor|Ballistas|Burgundian Vineyards')
REFERENCE_ECO = re.compile(r'\d+(?:[–—~～-]\d+)?\s*(?:木村|金村|石村|村|木|食|金|石|villagers?|wood|food|gold|stone)')


def reference_highlights(text):
    """Locate emphasis even when the CJK wrapper inserts a line break inside a phrase."""
    positions = [i for i, char in enumerate(text) if char != '\n']
    flat = ''.join(text[i] for i in positions)
    return [(tag, positions[m.start()], positions[m.end()-1] + 1)
            for tag, pattern in [('tech', REFERENCE_TECH), ('eco', REFERENCE_ECO)]
            for m in pattern.finditer(flat)]


class MapNotesView(tk.Frame):
    """Auto-follow a match's map, with a manual selector for pre-game study."""
    def __init__(self, parent, app):
        super().__init__(parent, bg=PANEL)
        self.app, self.view = app, None
        try:
            self.notes = load_map_notes()
            self.error = ''
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self.notes, self.error = [], tr('地圖注意資料無法載入：{0}' ,f'{exc}')
        self.current = None
        self.label = ''
        bar = tk.Frame(self, bg=PANEL)
        bar.pack(fill='x', padx=16, pady=10)
        self.status = tk.Label(bar, bg=PANEL, fg=MUTED, anchor='w')
        self.status.pack(side='left', fill='x', expand=True)
        button(bar, tr('回到本場地圖'), self.follow).pack(side='right', padx=6)
        self.selector = ttk.Combobox(bar, state='readonly', width=24,
                                    values=[n['title'].split(' · ')[0] for n in self.notes])
        self.selector.pack(side='right')
        self.selector.bind('<<ComboboxSelected>>', self.choose)
        self.body = tk.Frame(self, bg=PANEL)
        self.body.pack(fill='both', expand=True)
        self.message = tk.Label(self.body, bg=PANEL, fg=MUTED, font=(app.font, 14))

    def set_match(self, match, label):
        self.label = label
        self.current = note_for_map(self.notes, label, getattr(match, 'map_id', None),
                                    getattr(match, 'map_file', '') or '')
        self.follow()

    def follow(self):
        self.status.configure(text=self.error or (tr('本場：') + (self.label or tr('尚未載入對局'))))
        if self.current is None:
            self.selector.set(tr('選圖預習'))
            self.show(None)
        else:
            self.selector.current(self.notes.index(self.current))
            self.show(self.current)

    def choose(self, _event=None):
        index = self.selector.current()
        if index >= 0:
            note = self.notes[index]
            self.status.configure(text=tr('手動預習｜本場：') + (self.label or tr('尚未載入對局')))
            self.show(note)

    def show(self, note):
        if self.view is not None:
            self.view.destroy()
            self.view = None
        self.message.pack_forget()
        if note is None:
            self.message.configure(text=self.error or tr('這張地圖尚未整理（或為自訂／快速開局）。可從右上選圖預習。'))
            self.message.pack(expand=True)
            return
        self.view = ReferenceSheet(self.body, note, self.app.font, self.app.font_size, lambda _: None, [])
        self.view.pack(fill='both', expand=True)

    def resize(self, size):
        if self.view is not None:
            self.view.resize(size)


class ReferenceSheet(tk.Frame):
    """A glance-at-it reference tab: the cards fill the whole area and the text grows to fit.

    Rows share the height equally and the font is the largest that fits every card. The app's
    font size is the floor: below it the cards scroll instead of shrinking further.
    """
    MAX_SIZE = 30

    def __init__(self, parent, sheet, font, size, open_build, builds):
        super().__init__(parent, bg=PANEL)
        self.sheet, self.font, self.size = sheet, font, size
        self.fit_job, self.area, self.fitted_size, self.metrics = None, (0, 0), None, {}
        top = tk.Frame(self, bg=PANEL)
        top.pack(fill='x', padx=16, pady=(10, 4))
        tk.Label(top, text=sheet['title'], image=(civilization_icon(self, sheet['civ'], 32) if sheet.get('civ') else icon(self, sheet_icon(sheet), 32)), compound='left', padx=6, bg=PANEL, fg=FG, font=(font, 17, 'bold'),
                 anchor='w').pack(side='left')
        for build in reversed(builds):
            button(top, build.title, lambda b=build: open_build(b)).pack(side='right', padx=(6, 0))
        if builds:
            tk.Label(top, text=tr('搭配前期流程'), bg=PANEL, fg=MUTED).pack(side='right')
        self.caption = tk.Label(self, text=sheet['subtitle'], bg=PANEL, fg=MUTED,
                               font=(font, 10), anchor='w', justify='left', wraplength=1000)
        self.caption.pack(fill='x', padx=16, pady=(0, 6))
        self.scroll = ScrollArea(self)
        self.scroll.pack(fill='both', expand=True, padx=10, pady=(0, 8))
        self.cards, self.titles, self.texts = [], [], []
        for item in sheet['cards']:
            card = tk.Frame(self.scroll.body, bg=BG, padx=14, pady=10)
            title = tk.Label(card, text=item['title'], bg=BG, fg=ACCENT, anchor='w', justify='left',
                             font=(font, 12, 'bold'))
            title.pack(fill='x', pady=(0, 6))
            label = tk.Text(card, bg=BG, fg=FG, font=(font, max(10, size-1)),
                            width=1, height=1, wrap='none', borderwidth=0, highlightthickness=0,
                            padx=0, pady=0, takefocus=False, cursor='arrow', exportselection=False)
            label.insert('1.0', item['body'])
            label.configure(state='disabled')
            # Read like a label: without the Text class bindings a drag or wheel cannot scroll lines out of the card.
            label.bindtags((str(label), str(label.winfo_toplevel()), 'all'))
            label.pack(fill='both', expand=True)
            self.cards.append(card)
            self.titles.append(title)
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

    def destroy(self):
        if self.fit_job is not None:
            self.after_cancel(self.fit_job)
            self.fit_job = None
        super().destroy()

    def reflow(self, event):
        self.area = (event.width, event.height)
        if self.fit_job is not None:  # resizing fires many events; fit once it settles
            self.after_cancel(self.fit_job)
        self.fit_job = self.after(40, self.fit)

    def fit(self):
        if self.fit_job is not None:  # called directly (font size change) while a resize is pending
            self.after_cancel(self.fit_job)
            self.fit_job = None
        width, height = self.area
        if width < 50 or height < 50 or not self.cards:
            return
        count = len(self.cards)
        columns = min(count, 3 if width >= 1150 and count != 4 else 2 if width >= 850 else 1)
        rows = -(-count // columns)
        for col in range(3):
            self.scroll.body.columnconfigure(col, weight=1 if col < columns else 0,
                                             uniform='cards' if col < columns else '')
        for row in range(count):
            self.scroll.body.rowconfigure(row, weight=1 if row < rows else 0,
                                          uniform='rows' if row < rows else '')
        for i, card in enumerate(self.cards):
            card.grid(row=i//columns, column=i%columns, sticky='nsew', padx=6, pady=4)
        label = self.texts[0]
        inset = int(label.cget('borderwidth')) + int(label.cget('padx'))
        chrome = 2 * (2 * (int(label.cget('borderwidth')) + int(label.cget('pady'))))  # title + body
        wrap = max(200, width//columns - 12 - 28 - 2*inset - 4)   # grid padx, card padx, label inset, slack
        room = (height - rows*8) / rows - 20 - 6 - chrome         # grid pady, card pady, title gap
        floor = max(10, self.size - 1)
        best, low, high = floor, floor + 1, self.MAX_SIZE
        while low <= high:                                        # largest size whose tallest card fits
            mid = (low + high) // 2
            if self.layout(mid, wrap)[1] <= room:
                best, low = mid, mid + 1
            else:
                high = mid - 1
        wrapped, needed = self.layout(best, wrap)
        for (title_text, body_text), title, body in zip(wrapped, self.titles, self.texts):
            title.configure(text=title_text, font=(self.font, best + 1, 'bold'), wraplength=0)
            body.configure(state='normal', font=(self.font, best), height=body_text.count('\n') + 1)
            body.delete('1.0', 'end')
            body.insert('1.0', body_text)
            body.tag_configure('tech', foreground='#8bcaff', font=(self.font, best, 'bold'))
            body.tag_configure('eco', foreground='#f4cc78', font=(self.font, best, 'bold'))
            for tag, start, end in reference_highlights(body_text):
                body.tag_add(tag, f'1.0+{start}c', f'1.0+{end}c')
            body.configure(state='disabled')
        self.fitted_size = best
        # Fill the visible area; taller than it (scrolling) only when the floor size overflows.
        self.scroll.canvas.itemconfigure(self.scroll.window, height=max(height, rows * (needed + 34 + chrome)))
        self.caption.configure(wraplength=max(240, width-24))

    def layout(self, size, wrap):
        """Each card's title and body wrapped at `size`, and the tallest card's text height."""
        title_measure, title_line = self.measurer((self.font, size + 1, 'bold'))
        # Reserve bold widths so emphasized spans cannot overflow the fitted card.
        body_measure, body_line = self.measurer((self.font, size, 'bold'))
        wrapped = [(wrap_text(item['title'], title_measure, wrap), wrap_text(item['body'], body_measure, wrap))
                   for item in self.sheet['cards']]
        tallest = max((t.count('\n') + 1) * title_line + (b.count('\n') + 1) * body_line for t, b in wrapped)
        return wrapped, tallest

    def measurer(self, spec):
        """Cached text width and line height for a font spec, via Tcl (no Font objects to free)."""
        if spec not in self.metrics:
            cache = {}

            def measure(token):
                if token not in cache:
                    cache[token] = int(self.tk.call('font', 'measure', spec, token))
                return cache[token]
            self.metrics[spec] = (measure, int(self.tk.call('font', 'metrics', spec, '-linespace')))
        return self.metrics[spec]

    def resize(self, size):
        self.size = size
        self.fit()


class BuildReader(tk.Frame):
    """One build's whole table. Stage buttons jump; a click marks the step you are on."""
    def __init__(self, parent, build, font, size):
        super().__init__(parent, bg=PANEL)
        self.build, self.font, self.size = build, font, size
        self.selected = -1
        self.rows, self.tasks, self.labels = [], [], []
        tools = tk.Frame(self, bg=PANEL)
        tools.pack(fill='x', padx=20, pady=(0, 12))
        self.media_bar = tk.Frame(tools, bg=PANEL)
        self.media_bar.pack(side='right')
        self.update_media(build)
        self.position_label = tk.Label(tools, text=(build.arrival+'  ·  ' if build.arrival else '')+tr('點一下步驟，標記看到的位置'), bg=PANEL, fg=ACCENT, anchor='w')
        self.position_label.pack(side='bottom', anchor='w', pady=(7, 0))
        self.scroll = ScrollArea(self)
        self.scroll.pack(fill='both', expand=True, padx=20, pady=(0, 12))
        grid = self.scroll.body
        grid.columnconfigure(1, weight=1)
        headings = (tr('人口'), tr('操作'), tr('木'), tr('食'), tr('金'), tr('石'))
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
            self.notes = tk.Label(grid, text=tr('打法與轉型\n\n')+notes, bg=PANEL, fg=MUTED,
                                 justify='left', anchor='w', font=(font, size), padx=12, pady=24, wraplength=850)
            self.notes.grid(row=line, column=0, columnspan=6, sticky='ew')
        jump = tk.Frame(tools, bg=PANEL)
        jump.pack(side='left')
        for age in self.ages:
            button(jump, age.replace(' Age', '') if language() == 'en' else age, lambda a=age: self.jump(a)).pack(side='left', padx=(0, 6))
        self.scroll.bind_wheel(grid)
        self.scroll.canvas.bind('<Configure>', self.reflow, add='+')

    def update_media(self, build):
        self.build = build
        for child in self.media_bar.winfo_children():
            child.destroy()
        if build.video:
            button(self.media_bar, tr('本機影片 ↗'), lambda: open_local(build.video), True).pack(side='right', padx=(8, 0))
        if build.pdf:
            button(self.media_bar, tr('PDF · 第 {0} 頁 ↗' ,f'{build.page}'), lambda: open_local(build.pdf)).pack(side='right')

    def reflow(self, event):
        width = max(220, event.width - 330)
        for cell in self.tasks:
            cell.configure(wraplength=width)
        if hasattr(self, 'notes'):
            self.notes.configure(wraplength=max(240, event.width-40))

    def mark(self, index):
        self.selected = index
        for n, row in enumerate(self.rows):
            for cell in row:
                cell.configure(bg=MARKED if n == index else BG if n % 2 == 0 else PANEL)
        self.position_label.configure(text=tr('目前看到第 {0} 步 · {1}' ,f'{index + 1}', f'{self.build.steps[index].age}'))

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


class LibraryView(tk.Frame):
    """流程庫: a civilization's recommended builds in the user's order, every build, and opening advice."""
    MODES = ((tr('推薦順序'), 'recommended'), (tr('全部流程'), 'all'), (tr('開局調整'), 'overview'))

    def __init__(self, parent, ui):
        super().__init__(parent, bg=PANEL)
        self.ui, self.options, self.moved, self.searched_text, self.warning = ui, {tr('未指定文明'): ''}, None, '', ''
        self.overview = None
        font = ui.app.font
        top = tk.Frame(self, bg=PANEL)
        top.pack(fill='x', padx=24, pady=(18, 8))
        tk.Label(top, text=tr('流程庫'), image=icon(self, 'scroll', 32), compound='left', padx=6, bg=PANEL, fg=FG, font=(font, 20, 'bold')).pack(side='left')
        button(top, tr('本機影片（選用）…'), ui.choose_folder).pack(side='right')
        context = tk.Frame(self, bg=PANEL)
        context.pack(fill='x', padx=24, pady=4)
        self.civ_name = tk.StringVar(value=tr('未指定文明'))
        self.selector = ttk.Combobox(context, textvariable=self.civ_name, values=list(self.options), state='readonly', width=15)
        self.civ_badge = tk.Label(context, image=civilization_icon(self, ''), bg=PANEL)
        self.civ_badge.pack(side='left', padx=(0, 8))
        self.selector.pack(side='left')
        self.selector.bind('<<ComboboxSelected>>', lambda e: self.refresh(top=True))
        self.map_note = tk.Label(context, bg=PANEL, fg=MUTED, anchor='w')
        self.map_note.pack(side='left', padx=16)
        bar = tk.Frame(self, bg=PANEL)
        bar.pack(fill='x', padx=24, pady=(12, 6))
        self.mode = tk.StringVar(value='recommended')
        for label, value in self.MODES:
            tk.Radiobutton(bar, text=label, image=icon(self, 'sheep' if value == 'overview' else 'scroll'), compound='left', variable=self.mode, value=value, command=lambda: self.refresh(top=True),
                           indicatoron=False, bg=BG, fg=FG, selectcolor=MARKED, activebackground=SURFACE,
                           padx=18, pady=10, relief='flat').pack(side='left', padx=(0, 6))
        self.search = tk.StringVar()
        tk.Label(bar, text=tr('搜尋'), bg=PANEL, fg=MUTED).pack(side='left', padx=(18, 0))
        tk.Entry(bar, textvariable=self.search, bg=BG, fg=FG, insertbackground=ACCENT, relief='flat',
                 font=(font, 13)).pack(side='left', fill='x', expand=True, padx=(8, 0), ipady=8)
        self.search.trace_add('write', lambda *a: self.searched())
        self.sheet_bar = tk.Frame(self, bg=PANEL)
        self.sheet_bar.pack(fill='x', padx=24)
        self.note = tk.Label(self, bg=PANEL, fg=MUTED, anchor='w', justify='left')
        self.note.pack(fill='x', padx=24, pady=(6, 8))
        self.results = ScrollArea(self)
        self.results.pack(fill='both', expand=True, padx=24, pady=(0, 16))

    def civ(self):
        return self.options.get(self.civ_name.get(), '')

    def reset(self, civ):
        """Back to the match's civilization and its recommendations; the caller redraws."""
        self.options = {tr('未指定文明'): ''} | {c.name: c.key for c in self.ui.app.civs.values()}
        self.selector.configure(values=list(self.options))
        self.civ_name.set(next((name for name, value in self.options.items() if value == civ), tr('未指定文明')))
        self.mode.set('recommended')
        self.searched_text = ''
        self.search.set('')

    def searched(self):
        text = self.search.get().strip()
        if text == self.searched_text:
            return
        self.searched_text = text
        if text and self.mode.get() != 'all':
            self.mode.set('all')
        self.refresh(top=True)

    def refresh(self, top=False):
        ui, civ, mode = self.ui, self.civ(), self.mode.get()
        self.civ_badge.configure(image=civilization_icon(self, civ))
        position = 0 if top else self.results.canvas.yview()[0]
        if top:
            self.moved = None
        for child in (*self.results.body.winfo_children(), *self.sheet_bar.winfo_children()):
            child.destroy()
        sheets = sorted((s for s in ui.sheets.values() if s['civ'] in ('', key(civ))), key=lambda s: not s['civ'])
        if sheets:
            tk.Label(self.sheet_bar, text=tr('戰術速查'), bg=PANEL, fg=MUTED).grid(row=0, column=0, columnspan=2, sticky='w')
        for i, sheet in enumerate(sheets):
            button(self.sheet_bar, sheet['title'], lambda sid=sheet['id']: ui.open_sheet(sid), True).grid(
                row=1 + i // 2, column=i % 2, sticky='w', padx=(0, 6), pady=4)
        kind = map_kind(ui.map_label)
        self.map_note.configure(text=tr('本場地圖：{0}' ,f'{ui.map_label}') + (f'（{tr(MAP_TYPES[kind])}）' if kind else '') if ui.map_label else tr('本場地圖未知'))
        if mode == 'overview':
            self.results.pack_forget()
            self.note.configure(text=tr('動物配置與開局原則，可用來調整任何流程。'))
            self.show_overview()
            return
        if self.overview is not None:
            self.overview.pack_forget()
        self.results.pack(fill='both', expand=True, padx=24, pady=(0, 16))
        listed = ui.state.recommended(ui.builds, civ)
        listed_ids = {b.id for b in listed}
        if mode == 'recommended':
            builds = listed
            note = tr('「前期流程」會開清單中第一個適合本場地圖的流程；用 ▲▼ 調整順序。')
            empty = tr('清單是空的。到「全部流程」按「加入推薦」。')
        else:
            builds = search_builds(ui.builds, civ, self.search.get())
            note = tr('{0} 套流程 · 在上方搜尋打法或人口，例如：裝甲、直城、23＋2' ,f'{len(builds)}')
            empty = tr('沒有符合的流程。')
        self.note.configure(text=ui.error or self.warning or note)
        if not builds:
            tk.Label(self.results.body, text=tr('請重新下載最新版程式。') if ui.error else empty, bg=PANEL, fg=MUTED,
                     pady=35).pack(fill='x')
        for n, build in enumerate(builds):
            self.add_row(n, build, civ, mode == 'recommended', len(builds), build.id in listed_ids)
        self.results.bind_wheel(self.results.body)
        self.results.canvas.yview_moveto(position)

    def add_row(self, n, build, civ, ordered, count, listed):
        ui = self.ui
        background = MARKED if build.id == self.moved else BG
        row = tk.Frame(self.results.body, bg=background, padx=16, pady=10)
        row.pack(fill='x', pady=(0, 6))
        actions = tk.Frame(row, bg=background)
        actions.pack(side='right')
        button(actions, tr('看流程'), lambda: ui.pick(build), True).pack(side='left', padx=(0, 8))
        if ordered:
            for label, offset, enabled in (('▲', -1, n > 0), ('▼', 1, n < count - 1)):
                control = ttk.Button(actions, text=label, command=lambda o=offset: self.move(civ, build, o),
                                     style='Order.Build.TButton', cursor='hand2', width=0)
                control.state(['!disabled' if enabled else 'disabled'])
                control.pack(side='left', padx=(0, 4))
            button(actions, tr('移出'), lambda: self.change(ui.state.remove, civ, build)).pack(side='left', padx=(4, 0))
        elif listed:
            done = button(actions, tr('已在推薦'), None)
            done.state(['disabled'])
            done.pack(side='left')
        else:
            button(actions, tr('加入推薦'), lambda: self.change(ui.state.add, civ, build)).pack(side='left')
        text = tk.Frame(row, bg=background)
        text.pack(side='left', fill='x', expand=True)
        tk.Label(text, text=(f'{n+1}.  ' if ordered else '') + build.title, bg=background, fg=FG,
                 font=(ui.app.font, 14, 'bold'), anchor='w').pack(fill='x')
        current = ui.build is not None and build.id == ui.build.id
        tags = [tr('{0} 人口' ,f'{build.population}'), suitability(build, civ), tr(MAP_TYPES[build.map_type])]
        tags += [tr('本機影片')] * bool(build.video) + [tr('目前的前期流程')] * current
        tk.Label(text, text='  ·  '.join(tags), bg=background, fg=ACCENT if current else MUTED,
                 anchor='w').pack(fill='x', pady=(4, 0))

    def move(self, civ, build, offset):
        self.moved = build.id
        self.change(self.ui.state.move, civ, build, offset)

    def change(self, action, civ, build, *args):
        try:
            action(self.ui.builds, civ, build.id, *args)
        except OSError:
            self.warning = tr('無法寫入設定檔；新的順序只在這次開啟有效。')
        self.ui.refresh()  # the 前期流程 follows the new order unless one was picked for this match

    def show_overview(self):
        if self.overview is None:
            app = self.ui.app
            self.overview = tk.Frame(self, bg=PANEL)
            area = tk.Text(self.overview, bg=PANEL, fg=FG, wrap='word', relief='flat', borderwidth=0,
                           highlightthickness=0, font=(app.font, app.font_size), padx=4, pady=8, spacing3=8)
            scroll = ttk.Scrollbar(self.overview, command=area.yview)
            area.configure(yscrollcommand=scroll.set)
            scroll.pack(side='right', fill='y')
            area.pack(fill='both', expand=True)
            # Render the short introduction as readable paragraphs, including animal variants.
            for line in self.ui.overview.splitlines():
                if line.startswith('|---'):
                    continue
                if line.startswith('|'):
                    line = '：'.join(part.strip() for part in line.strip('|').split('|'))
                area.insert('end', line.lstrip('# ').replace('<br>', '\n')+'\n')
            area.configure(state='disabled')
        self.overview.pack(fill='both', expand=True, padx=24, pady=(0, 16))


class BuildLibraryUI:
    """Three fixed tabs after the RP that follow the match on screen.

    前期流程 shows the build picked for that match, else the first of the civilization's
    recommendations that suits the map. 戰術速查 shows the civilization's sheet, one linked to
    that build first, then any sheet for every civilization on this map; a bar switches between
    them. Marks belong to a game: a new live match starts every build from the top.
    """
    def __init__(self, app):
        self.app = app
        style = ttk.Style(app.root)
        style.configure('Build.TButton', background=SURFACE, foreground=FG, borderwidth=0,
                        padding=(16, 11), font=(app.font, 12), anchor='center')
        style.map('Build.TButton', background=[('active', '#344563')], foreground=[('disabled', MUTED)])
        style.configure('Accent.Build.TButton', foreground=ACCENT)
        # The first ▲ and last ▼ do nothing; dim them well below the usual disabled grey.
        style.map('Order.Build.TButton', background=[('active', '#344563')], foreground=[('disabled', '#4b5870')])
        self.state = LibraryState()
        # Old folder settings become optional media locations; never a source of steps.
        selected = (getattr(app.args, 'media_dir', None) or getattr(app.args, 'library_dir', None)
                    or self.state.data.get('media_dir') or self.state.data.get('library_dir'))
        self.directory = Path(selected) if selected else None
        self.reload()
        self.match, self.civ, self.map_label, self.build, self.sheet = None, '', '', None, None
        self.picks, self.sheet_picks, self.readers, self.sheet_views = {}, {}, {}, {}
        book = app.workspace_book
        self.plan_tab = tk.Frame(book, bg=PANEL)
        header = tk.Frame(self.plan_tab, bg=PANEL)
        header.pack(fill='x', padx=20, pady=(12, 8))
        self.switch = ttk.Menubutton(header, text=tr('換流程 ▾'), style='Build.TButton')
        self.switch_menu = tk.Menu(self.switch, tearoff=False, font=(app.font, 11), postcommand=self.fill_switch)
        self.switch.configure(menu=self.switch_menu)
        self.switch.pack(side='right')
        self.next_button = button(header, tr('戰術速查 →'), lambda: book.select(self.sheet_tab), True)
        self.title = tk.Label(header, bg=PANEL, fg=FG, font=(app.font, 19, 'bold'), anchor='w', justify='left')
        self.title.pack(side='left', fill='x', expand=True)
        self.sheet_tab = tk.Frame(book, bg=PANEL)
        self.sheet_choice = tk.StringVar()
        self.sheet_bar = tk.Frame(self.sheet_tab, bg=PANEL)  # shown when several sheets apply
        self.sheet_body = tk.Frame(self.sheet_tab, bg=PANEL)
        self.sheet_body.pack(fill='both', expand=True)
        self.map_tab = MapNotesView(book, app)
        self.library_tab = LibraryView(book, self)
        book.add(self.plan_tab, text=tr('前期流程'), image=icon(app.root, 'hourglass'), compound='left')
        book.add(self.sheet_tab, text=tr('戰術速查'), image=icon(app.root, 'combat'), compound='left')
        book.add(self.map_tab, text=tr('地圖注意'), image=icon(app.root, 'scroll'), compound='left')
        book.add(self.library_tab, text=tr('流程庫'), image=icon(app.root, 'scroll'), compound='left')
        self.set_match(None)

    def reload(self):
        try:
            self.builds = load_library(self.directory)
            catalog = read_catalog()
            self.sheets = {s['id']: s for s in catalog.get('reference_sheets', [])}
            self.overview, self.error = catalog['overview'], ''
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self.builds, self.sheets, self.overview, self.error = [], {}, '', str(exc)
        self.by_id = {b.id: b for b in self.builds}

    def recommended(self):
        return self.state.recommended(self.builds, self.civ)

    def set_match(self, match, live=False):
        """Follow the match on screen; a live one is a new game, so its builds start from the top."""
        me = split_sides(match, self.app.my_id)[0] if match else None
        civ = self.app.civs.get(me.civ_id) if me else None
        self.match, self.civ = match, civ.key if civ else ''
        self.map_label = map_label(match, self.app.maps) if match else ''
        self.map_tab.set_match(match, self.map_label)
        if live:
            for reader in self.readers.values():
                reader.destroy()
            self.readers = {}
        self.library_tab.reset(self.civ)
        self.refresh(top=True)

    def refresh(self, top=False):
        """Show the match's build and sheet, then redraw the library around them."""
        build = self.by_id.get(self.picks.get(self.match)) or opening_for(self.recommended(), self.map_label)
        self.build, reader = build, None
        if build is not None:
            reader = self.readers.get(build.id)
            if reader is None:
                reader = self.readers[build.id] = BuildReader(self.plan_tab, build, self.app.font, self.app.font_size)
        for other in self.readers.values():
            if other is not reader and other.winfo_manager():
                other.pack_forget()
        if reader is not None and not reader.winfo_manager():
            reader.pack(fill='both', expand=True)
        self.title.configure(text=tr('{0} 人口  ·  {1}' ,f'{build.population}', f'{build.title}') if build else
                             self.error or tr('推薦清單是空的：到「流程庫」加入流程'))
        tab = tr('前期流程')
        if build:
            tab += ' · ' + (build.title if len(build.title) <= (25 if language() == 'en' else 10) else build.title[:24 if language() == 'en' else 9] + '…')
        self.app.workspace_book.tab(self.plan_tab, text=tab)
        self.refresh_sheet()
        self.library_tab.refresh(top)

    def refresh_sheet(self):
        fitting = [s['id'] for s in sheets_for(self.sheets.values(), self.civ, self.build, self.map_label)]
        # Map/civilization eligibility also drives the right-hand shortcuts. A civilization's
        # version wins over the generic sheet with the same action id; no tab is auto-selected.
        bar = self.app.map_shortcuts
        for child in bar.winfo_children():
            child.destroy()
        actions = set()
        for sheet_id in fitting:
            action = self.sheets[sheet_id].get('shortcut')
            if action and action['id'] not in actions:
                actions.add(action['id'])
                button(bar, action['label'], lambda s=sheet_id: self.open_sheet(s), True).pack(side='left', padx=(6, 0))
        if actions:
            bar.pack(side='right', before=self.app.meta)
        else:
            bar.pack_forget()
        picked = self.sheet_picks.get(self.match)
        self.sheet = picked if picked in self.sheets else next(iter(fitting), None)
        view = None
        if self.sheet is not None:
            view = self.sheet_views.get(self.sheet)
            if view is None:
                sheet = self.sheets[self.sheet]
                view = self.sheet_views[self.sheet] = ReferenceSheet(
                    self.sheet_body, sheet, self.app.font, self.app.font_size, self.pick,
                    [b for b in self.builds if b.id in sheet['build_ids']])
        for other in self.sheet_views.values():
            if other is not view and other.winfo_manager():
                other.pack_forget()
        if view is not None and not view.winfo_manager():
            view.pack(fill='both', expand=True)
        choices = fitting + [self.sheet] * (self.sheet is not None and self.sheet not in fitting)
        for child in self.sheet_bar.winfo_children():
            child.destroy()
        self.sheet_choice.set(self.sheet or '')
        def choice(label, ident, row, col):
            tk.Radiobutton(self.sheet_bar, text=label, variable=self.sheet_choice, value=ident,
                           command=lambda: self.open_sheet(ident), indicatoron=False, bg=BG, fg=FG,
                           selectcolor=MARKED, activebackground=SURFACE, padx=10, pady=8, wraplength=150, relief='flat').grid(
                               row=row, column=col, sticky='ew', padx=(0, 6), pady=(0, 4))
        # Era sheets are grouped by civilization; map-specific defenses remain accessible.
        grouped = [i for i in choices if self.sheets[i].get('era')]
        if grouped:
            selected = self.sheets.get(self.sheet, {})
            current_era = selected.get('era')
            for col, (era, label) in enumerate((('feudal', tr('封建速查')), ('castle', tr('城堡速查')), ('imperial', tr('帝王速查')))):
                members = [i for i in grouped if self.sheets[i]['era'] == era]
                if members:
                    target = self.sheet if self.sheet in members else members[0]
                    choice(label, target, 0, col)
            branches = [i for i in grouped if self.sheets[i]['era'] == current_era]
            if len(branches) > 1:
                for col, ident in enumerate(branches):
                    choice(self.sheets[ident].get('nav_label', self.sheets[ident]['title']), ident, 1, col)
            for n, ident in enumerate(i for i in choices if i not in grouped):
                choice(self.sheets[ident]['title'], ident, 2 + n // 3, n % 3)
        else:
            for i, ident in enumerate(choices if len(choices) > 1 else ()):
                choice(self.sheets[ident]['title'], ident, i // 3, i % 3)
        if len(choices) > 1:
            self.sheet_bar.pack(fill='x', padx=16, pady=(10, 0), before=self.sheet_body)
        else:
            self.sheet_bar.pack_forget()
        self.app.workspace_book.tab(self.sheet_tab, state='normal' if view else 'disabled')
        if view is None:
            self.next_button.pack_forget()
        elif not self.next_button.winfo_manager():
            self.next_button.pack(side='right', padx=(0, 8))

    def pick(self, build):
        """The user's choice for this match; it stays while other matches are browsed."""
        self.picks[self.match] = build.id
        self.refresh()
        self.app.workspace_book.select(self.plan_tab)

    def open_sheet(self, sheet_id):
        self.sheet_picks[self.match] = sheet_id
        self.refresh_sheet()
        self.app.workspace_book.select(self.sheet_tab)

    def fill_switch(self):
        menu = self.switch_menu
        menu.delete(0, 'end')
        for n, build in enumerate(self.recommended(), 1):
            mark = '✓' if self.build and build.id == self.build.id else '　'
            menu.add_command(label=f'{mark} {n}. {build.title}  ·  {tr(MAP_TYPES[build.map_type])}',
                             command=lambda b=build: self.pick(b))
        menu.add_separator()
        menu.add_command(label=tr('\u3000 流程庫：排序、搜尋全部流程…'), command=lambda: self.app.workspace_book.select(self.library_tab))

    def resize(self, size):
        for view in (*self.readers.values(), *self.sheet_views.values(), self.map_tab):
            view.resize(size)

    def choose_folder(self):
        folder = filedialog.askdirectory(parent=self.app.root, title=tr('選擇已下載的影片資料夾（選用）'), initialdir=self.directory)
        if folder:
            self.directory = Path(folder)
            self.reload()
            self.state.data['media_dir'] = folder
            try:
                self.state.save()
            except OSError:
                messagebox.showinfo(tr('無法儲存設定'), tr('本次仍可播放，重新開啟後請再選影片資料夾。'), parent=self.app.root)
            for reader in self.readers.values():
                if reader.build.id in self.by_id:
                    reader.update_media(self.by_id[reader.build.id])
            self.refresh()
            if self.builds and not any(b.video or b.pdf for b in self.builds):
                messagebox.showinfo(tr('未找到本機影片'), tr('這個資料夾沒有對應的影片或 PDF；內建流程仍可照常使用。'), parent=self.app.root)
