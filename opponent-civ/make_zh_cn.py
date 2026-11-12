"""Regenerate the Simplified Chinese (zh) catalogs, UI strings and README from the Traditional ones.

    uv run --with opencc-python-reimplemented python opponent-civ/make_zh_cn.py

Run it after editing any *.zh-TW.json, a tr() string or README.zh-TW.md. OpenCC (tw2sp) converts
the script and Taiwan vocabulary; GLOSSARY first swaps the game terms whose mainland translation
differs, so the guides use the names the Simplified Chinese game shows. The app itself never needs
OpenCC: it only reads the generated files.
"""
import ast
import json
import re
from pathlib import Path

from opencc import OpenCC

HERE = Path(__file__).resolve().parent
DATA = HERE / 'data'
ROOT = HERE.parent

# Taiwan wording -> the mainland game's names (from its own string tables, matched by unit, building,
# civilization and map id). Player shorthand without an official name (肉馬, 銀冠, BK, 直城) stays.
# 矛兵 is a Skirmisher in the Traditional game but 长矛兵 is a Spearman in the Simplified one, hence
# every 矛 form below; 火矛兵 is already the mainland name of the Fire Lancer.
GLOSSARY = {
    '精銳矛兵': '精锐掷矛手', '精矛': '精锐掷矛手', '槍矛': '枪兵＋掷矛手', '矛兵': '掷矛手', '矛': '掷矛手',
    '火矛兵': '火矛兵', '火矛': '火矛',
    '裝甲': '武士', '長劍': '长剑士', '馬弓': '骑射手', '衝車': '攻城锤', '輪軸': '独轮推车',
    '重型弩砲': '重型弩炮', '重弩': '重型弩炮', '弩砲戰船': '战船', '弩砲象': '重弩战象', '弩砲': '弩炮',
    '強弩兵': '劲弩手', '弩兵': '弩手', '火弓兵': '火焰弓箭手', '弓兵': '步弓手',
    '輕騎兵': '轻型骑兵', '偵察騎兵': '斥候骑兵', '草原騎兵': '草原枪兵', '戟兵': '长戟兵',
    '土耳其火槍兵': '苏丹亲兵', '火槍兵': '火枪手', '火砲': '手推炮', '火箭車': '火箭推车',
    '炸藥桶': '爆破兵', '軍團兵': '罗马军', '戰鬥祭司': '牧师战士', '風琴砲': '风琴炮',
    '贊皮游擊兵': '蔷琵步兵', '贊皮戰士': '蔷琵战士', '贊皮斥候': '蔷琵斥候', '贊皮': '蔷琵',
    '佛萊明民兵': '弗拉芒民兵', '佛萊明': '弗拉芒',
    '軍營': '兵营', '射箭場': '靶场', '兵工廠': '铁匠铺', '攻城器製造所': '攻城武器厂', '市集': '市场',
    '採礦營地': '采矿场', '碼頭': '船坞', '漁船': '捕鱼船', '漁網': '养鱼场', '聚落': '定居点',
    '攻城工程師': '攻城技师',
    '中型戰艦': '中型战船', '躉船': '趸船',
    '勃根地': '勃艮第', '馬雅': '玛雅', '朝鮮': '高丽', '馬札爾': '马扎尔', '馬利': '马里',
    '柏柏爾': '柏柏尔', '柏柏': '柏柏尔', '曼帕契': '马普切', '匈牙利': '匈牙利', '匈奴': '匈奴', '匈': '匈奴',
    '阿拉伯沙漠': '阿拉伯沙漠', '阿拉伯': '阿拉伯半岛', '環形要塞': '环形要塞', '要塞': '堡垒', '猶加敦': '尤卡坦', '黃金谷': '金矿谷',
    '四座湖泊': '四片湖泊', '哈布風': '哈布风暴',
}
TERM = re.compile('|'.join(sorted(map(re.escape, GLOSSARY), key=len, reverse=True)))
# Values copied as they are: ids, file names, numbers and links the code or tests match exactly.
KEEP = {'id', 'index', 'civs', 'civ', 'recommended_for', 'map_type', 'video_filename', 'video_url', 'build_ids', 'era', 'url',
        'population', 'allocation', 'wood', 'food', 'gold', 'stone', 'edition', 'schema_version',
        'reviewed_on', 'map_ids', 'page'}
MATCHED = {'aliases', 'maps'}  # matched against map names: keep the original and add the Simplified one
CC = OpenCC('tw2sp')


OPEN, CLOSE = chr(0xE000), chr(0xE001)  # private-use marks around parked glossary terms
PARKED = re.compile(f'{OPEN}(\\d+){CLOSE}')


def convert(text):
    """Glossary terms first, parked between private-use marks so OpenCC cannot rewrite them."""
    parked = []

    def park(match):
        parked.append(GLOSSARY[match.group(0)])
        return f'{OPEN}{len(parked) - 1}{CLOSE}'
    return PARKED.sub(lambda m: parked[int(m.group(1))], CC.convert(TERM.sub(park, text)))


def convert_tree(value, key=None):
    if isinstance(value, dict):
        return {k: convert_tree(v, k) for k, v in value.items()}
    if isinstance(value, list):
        if key in MATCHED and all(isinstance(v, str) for v in value):
            return list(dict.fromkeys(value + [convert(v) for v in value]))
        return [convert_tree(v, key) for v in value]
    if isinstance(value, str) and key not in KEEP:
        return convert(value)
    return value


def ui_strings():
    """Every tr() literal in the app, plus the keys the English table already knows."""
    keys = set(json.loads((DATA / 'ui.en.json').read_text(encoding='utf-8')))
    for path in HERE.glob('*.py'):
        if path.name.startswith('test_') or path.name == Path(__file__).name:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'tr'
                    and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                keys.add(node.args[0].value)
    return {key: convert(key) for key in sorted(keys)}


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    for name in ('builds', 'map-notes'):
        source = json.loads((DATA / f'{name}.zh-TW.json').read_text(encoding='utf-8'))
        write_json(DATA / f'{name}.zh-CN.json', convert_tree(source))
    write_json(DATA / 'ui.zh-CN.json', ui_strings())
    readme = convert((ROOT / 'README.zh-TW.md').read_text(encoding='utf-8'))
    readme = re.sub(r'^\[English\]\(README\.md\) \| .*$', '[English](README.md) | [繁體中文](README.zh-TW.md) | 简体中文',
                    readme, count=1, flags=re.MULTILINE)
    (ROOT / 'README.zh-CN.md').write_text(readme, encoding='utf-8')
    print('wrote builds.zh-CN.json, map-notes.zh-CN.json, ui.zh-CN.json, README.zh-CN.md')


if __name__ == '__main__':
    main()
