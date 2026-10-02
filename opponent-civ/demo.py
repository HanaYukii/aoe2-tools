"""Synthetic match examples for public screenshots; no personal replay data."""
from dataclasses import replace
from pathlib import Path
from civdata import load_civs
from units import load_unique_units
from rec_header import Match, Player


def populate(app):
    app.root.title('AoE2 · 對局筆記 — 範例資料')
    app.civs = load_civs(app.args.game_dir, app.args.lang)
    app.units = load_unique_units(app.args.game_dir, app.args.lang)
    app.my_id = 100
    base = Match(68.9, 1, 1780000000, True, True, False, (
        Player(1, 'Player One', 43, 2, 0, 100, 2),
        Player(2, 'Northern Scout', 11, 3, 1, 200, 2),
    ))
    rows = [(Path(f'example-{i}.aoe2record'), replace(base, timestamp=base.timestamp-i*3600,
             players=(base.players[0], replace(base.players[1], civ_id=[11,1,4,12,7,14,15,16,17,18][i], name=f'Opponent {i+1:02d}')))) for i in range(10)]
    app.show(rows[0][1], rows[0][0], None, True)
    app.render_history(app.history_request, rows, 0, None)
    app.history_tree.selection_set('0')
    app.meta.configure(text='展示用虛構玩家與對局 · 不讀取個人錄影、不連網')
    app.history_button.configure(state='disabled')
