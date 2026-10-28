"""Synthetic match examples for public screenshots; no personal replay data."""
from dataclasses import replace
from pathlib import Path
from civdata import Civ, load_civs
from units import load_unique_units
from rec_header import Match, Player


def populate(app):
    app.root.title('AoE2 · 對局筆記 — 範例資料')
    if app.args.game_dir:
        app.civs = load_civs(app.args.game_dir, app.args.lang)
        app.units = load_unique_units(app.args.game_dir, app.args.lang)
    else:
        # Clearly labeled fixtures; actual play always reads the installed game.
        app.civs = {43: Civ(43, 'Romans', '羅馬', '展示用文明頁。\n\n實戰時會從遊戲安裝資料讀取文明加成與科技說明。'),
                    11: Civ(11, 'Vikings', '維京', '展示用對手文明頁。\n\n「前期流程」分頁會開啟自己文明的內建中文流程。'),
                    35: Civ(35, 'Burgundians', '勃根地', '展示用文明頁。')}
        app.units = {}
    app.maps = {9: '阿拉伯', 29: '競技場'}
    app.my_id = 100
    base = Match(68.9, 1, 1780000000, True, True, False, (
        Player(1, 'Player One', 43, 2, 0, 100, 2),
        Player(2, 'Northern Scout', 11, 3, 1, 200, 2),
    ), map_id=9)
    rows = [(Path(f'example-{i}.aoe2record'), replace(base, timestamp=base.timestamp-i*3600,
             players=(base.players[0], replace(base.players[1], civ_id=[11,35][i % 2], name=f'Opponent {i+1:02d}')))) for i in range(10)]
    app.show(rows[0][1], rows[0][0], None, True)
    app.render_history(app.history_request, rows, 0, None,
                       [(True, 15), (False, -14), (True, 12), (True, 16), (False, -15), (True, 13), (False, -12), (True, 14), (True, 11), (False, -16)])
    app.history_tree.selection_set('0')
    app.meta.configure(text='展示用虛構玩家與對局 · 不讀取個人錄影、不連網')
    app.history_button.configure(state='disabled')
    app.preview.configure(state='normal', command=lambda: (app.history_tree.selection_set('0'), app.select_history()))
