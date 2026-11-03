#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""scene.py —— 「全量客户场景攻坚」解析。

## 源表形态

一张《全量客户场景攻坚成效图MM.DD.xlsx》，单 sheet，**两层表头**：

    A1       全量客户场景攻坚成效图            （标题，深红底）
    A2/A3    支行 | 养老代发场景(B2:C2 合并) | 薪管家代发场景(D2:E2) | …共 6 个场景
    B3/C3    已落地 | 推进中   （每个场景都是这两列，共 12 列内容列）
    A4:A11   颍州 颍泉 颍东 界首 临泉 阜南 颍上 太和   （8 家支行，顺序固定）
    A12      注释：标红为进度有变化项目

单元格里是**文字**，一条项目一行；多条时用 `1.` `2.` `3.` 编号（也可能混着换行）。

## 格式约定（对着成图核过）

* **红色字体 = 本期进度有变化**。成图里对应条目**标黄**，这是我们唯一要保留的样式信息。
* 部分单元格是**富文本**（同一格里一部分字红、一部分不红），所以要按 run 判断，
  不能只看单元格整体 `font.color`（那是兜底）。
* 数一个格子里有几个项目：按 `1. 2. 3.` / `1、2、` 切；没有编号就整格算 1 条；
  编号前如果还有正文（"已落地代发，其中…"），那段也单独算 1 条。
  这样切出来的总数与成图 KPI **完全一致**（落地 28 / 推进 23），改切法会让数字对不上。

## 日期

源表里**没有日期**，从文件名认（`…11.02.xlsx`）；认不出就叫用户手填。
复用 `pbs.date_from_name`（认得 `20261024` / `2026-10-24` / `2026.10.24` / `10.24` / `1024` / `10月24日`…）。
"""
from __future__ import annotations

import datetime as dt
import re

from .pbs import date_from_name

# 8 家支行，顺序固定（与其余模块一致）
BRANCH_ORDER = ['颍州', '颍泉', '颍东', '界首', '临泉', '阜南', '颍上', '太和']

# 6 个场景，顺序与源表列序一致
SCENES = ['养老代发', '薪管家代发', '智慧校园', '支付即开票', '政务民生', '数币']

# 每个场景的两个状态列（表头第 3 行）
STATUS = ['已落地', '推进中']

# 项目编号切分：`1.` `2、` `3．`；数字前不能紧贴数字/小数点，后一位不能是数字
# （否则 "颍东4家加油站" 里的 4 会被当成编号）
ITEM_CUT = re.compile(r'(?<![\d.])([1-9])\s*[.、．]\s*(?!\d)')

RED = 'FFFF0000'
RED_LOOSE = ('FFFF0000', '00FF0000', 'FF0000', 'FFFF3333', 'FFC00000')


# ---------------------------------------------------------------- 单元格 → 带样式的文本段
def _runs(cell) -> list[tuple[str, bool]]:
    """把单元格拆成 [(文本, 是否红色), …]。

    富文本按 run 判定；普通字符串整格看 `font.color`。
    """
    v = cell.value
    if v is None:
        return []
    if isinstance(v, str):
        return [(v, _is_red(cell.font))]
    # CellRichText：可迭代出 str 或 TextBlock
    out: list[tuple[str, bool]] = []
    try:
        parts = list(v)
    except TypeError:
        return [(str(v), _is_red(cell.font))]
    for part in parts:
        if isinstance(part, str):
            out.append((part, _is_red(cell.font)))
        else:
            txt = getattr(part, 'text', '') or ''
            f = getattr(part, 'font', None)
            out.append((txt, _is_red(f) if f is not None else _is_red(cell.font)))
    return out


def _is_red(font) -> bool:
    if font is None:
        return False
    col = getattr(font, 'color', None)
    if col is None:
        return False
    rgb = getattr(col, 'rgb', None)
    if isinstance(rgb, str) and rgb.upper() in RED_LOOSE:
        return True
    # 主题色里的红（少数情况）：indexed 值 2 = 红
    idx = getattr(col, 'indexed', None)
    return idx == 2


# ---------------------------------------------------------------- 拆项目
def split_items(text: str) -> list[str]:
    """一格文字 → 若干条项目（按编号切；没编号整格算一条）。"""
    t = str(text or '')
    if not t.strip():
        return []
    out: list[str] = []
    for line in re.split(r'[\r\n]+', t):
        line = line.strip()
        if not line:
            continue
        cuts = [m.start() for m in ITEM_CUT.finditer(line)]
        if not cuts:
            out.append(_clean(line))
            continue
        if cuts[0] > 0:                      # 编号前的正文（"已落地代发，其中…"）
            head = line[:cuts[0]].strip(' 、,，;；')
            if head:
                out.append(_clean(head))
        for i, s in enumerate(cuts):
            e = cuts[i + 1] if i + 1 < len(cuts) else len(line)
            seg = ITEM_CUT.sub('', line[s:e], count=1).strip(' 、,，;；')
            if seg:
                out.append(_clean(seg))
    return [x for x in out if x]


def _clean(s: str) -> str:
    """去掉成表里为排版加的多余空格 / 全角空格 / 结尾逗号。"""
    s = s.replace('\u3000', ' ').replace('\xa0', ' ')
    s = re.sub(r'[ \t]{2,}', ' ', s)
    return s.strip(' 、,，;；')


def cell_items(cell) -> list[dict]:
    """一格 → [{'text', 'changed'(红), 'branch'…略}]；红只标记到"哪个 run 红"。"""
    runs = _runs(cell)
    if not runs:
        return []
    # 把 runs 拼起来，但记住每个字符是否红，这样切完项目还能按位置取红
    buf, flags = [], []
    for txt, red in runs:
        for ch in txt:
            buf.append(ch)
            flags.append(red)
    full = ''.join(buf)
    items = []
    pos = 0
    for piece in split_items(full):
        # 在原文里定位这一条（从上次位置往后找，避免重复文本错位）
        at = full.find(piece, pos)
        if at < 0:
            at = full.find(piece)
        if at < 0:
            items.append({'text': piece, 'changed': any(flags)})
            continue
        seg = flags[at:at + len(piece)]
        items.append({'text': piece, 'changed': bool(seg) and any(seg)})
        pos = at + len(piece)
    return items


# ---------------------------------------------------------------- 定位表头
def _find_header(rows: list[list]) -> int:
    """找"支行 + 若干场景列"那两行里的第一行（第 2 行，A 列写「支行」）。"""
    for i, row in enumerate(rows[:10]):
        head = ''.join(str(c or '') for c in row[:3])
        if '支行' in head and any('场景' in str(c or '') for c in row):
            return i
    return 1                                  # 兜底：第 2 行


def _scene_cols(header_top: list, header_sub: list) -> list[dict]:
    """从两层表头推出 6 个场景 × 2 状态列各自在第几列。

    返回 [{'scene': '养老代发', 'landed': 1, 'ongoing': 2}, …]，下标 0 基。
    """
    # 场景名在第 2 行，**只有合并区的左上格有值**，其余是 None。
    # 注意：不能先把值向右填满再找（填完每个下标都是真值，会把一个场景识别成两个）。
    # 直接用原始表头里非空的「XX场景」当起点，每个场景固定占 2 列（已落地 / 推进中）。
    starts = [i for i, c in enumerate(header_top) if '场景' in str(c or '')]
    if not starts:
        return []
    out = []
    for start in starts:
        pair = [start, start + 1]
        sub = [str(header_sub[i] or '').strip() if i < len(header_sub) else '' for i in pair]
        landed = ongoing = None
        for i, s in zip(pair, sub):
            if '落地' in s:
                landed = i
            elif '推进' in s:
                ongoing = i
        out.append({'scene': str(header_top[start] or '').replace('场景', '').strip(),
                    'landed': landed if landed is not None else pair[0],
                    'ongoing': ongoing if ongoing is not None else pair[1]})
    return out


# ---------------------------------------------------------------- 主解析
def parse(data_rows: list[list], cells=None, as_of: str | None = None) -> dict:
    """data_rows 只用于定位（值），cells 是可带样式的单元格二维表（getattr 取 .value / .font）。

    两者行列表头应当一致；cells 为空时退化成"全都不标红"。
    """
    hi = _find_header(data_rows)
    header_top = data_rows[hi] if hi < len(data_rows) else []
    header_sub = data_rows[hi + 1] if hi + 1 < len(data_rows) else []
    scenes = _scene_cols(header_top, header_sub)
    if not scenes:
        raise ValueError('认不出场景列（第 2 行应该有「XX场景」，第 3 行是「已落地 / 推进中」）')

    def cell_at(r, c):
        if cells is None or r >= len(cells) or c >= len(cells[r]):
            return None
        return cells[r][c]

    def val_at(r, c):
        if r >= len(data_rows) or c >= len(data_rows[r]):
            return None
        return data_rows[r][c]

    # 支行行：A 列是支行名，且落在 BRANCH_ORDER 或至少不是注释
    branches: dict[str, dict] = {}
    for r in range(hi + 2, len(data_rows)):
        name = str(val_at(r, 0) or '').strip()
        if not name or name.startswith('注释') or '注' == name[:1] and '标' in name:
            continue
        if name not in BRANCH_ORDER:
            # 允许写成 "颍州支行"
            name = name.replace('支行', '').strip()
        if name not in BRANCH_ORDER:
            continue
        rec = {'name': name, 'scenes': {}}
        for sc in scenes:
            key = sc['scene']
            landed_cell = cell_at(r, sc['landed'])
            ongoing_cell = cell_at(r, sc['ongoing'])
            landed = cell_items(landed_cell) if landed_cell is not None else \
                [{'text': x, 'changed': False} for x in split_items(val_at(r, sc['landed']))]
            ongoing = cell_items(ongoing_cell) if ongoing_cell is not None else \
                [{'text': x, 'changed': False} for x in split_items(val_at(r, sc['ongoing']))]
            rec['scenes'][key] = {'landed': landed, 'ongoing': ongoing}
        branches[name] = rec

    if not branches:
        raise ValueError('表里没认出支行行（A 列应是 颍州/颍泉/… 8 家）')

    # 汇总
    scene_list = []
    tot_l = tot_o = 0
    for sc in scenes:
        key = sc['scene']
        l = o = 0
        changed = 0
        for b in branches.values():
            items = b['scenes'].get(key) or {'landed': [], 'ongoing': []}
            l += len(items['landed'])
            o += len(items['ongoing'])
            changed += sum(1 for x in items['landed'] + items['ongoing'] if x['changed'])
        scene_list.append({'name': key, 'landed': l, 'ongoing': o,
                           'branches': sum(1 for b in branches.values()
                                           if (b['scenes'].get(key) or {}).get('landed')),
                           'changed': changed})
        tot_l += l
        tot_o += o

    covered = sum(1 for b in branches.values()
                  if any((b['scenes'].get(s['scene']) or {}).get('landed') for s in scenes))

    return {
        'as_of': as_of,
        'as_of_cn': f'{int(as_of[5:7])}月{int(as_of[8:10])}日' if as_of else '',
        'branches': [branches[b] for b in BRANCH_ORDER if b in branches],
        'scenes': scene_list,
        'total': {'landed': tot_l, 'ongoing': tot_o, 'scenes': len(scene_list),
                  'branches': covered,
                  'changed': sum(s['changed'] for s in scene_list)},
        'branch_order': BRANCH_ORDER,
    }


def parse_files(files, as_of: str | None = None) -> tuple[str, dict]:
    """只收一张成表。日期优先用手填的，其次文件名。"""
    import io
    import openpyxl

    if not files:
        raise ValueError('没有收到源表')
    name, blob = files[0]
    # 源表里的"标红"只有富文本读得出来，必须 rich_text=True
    wb = openpyxl.load_workbook(io.BytesIO(blob), data_only=True, rich_text=True)
    ws = wb.worksheets[0]

    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    cells = [[c for c in r] for r in ws.iter_rows()]

    dd = as_of or date_from_name(name)
    if not dd:
        raise ValueError('文件名里认不出数据日期（如「…11.02.xlsx」），请手动指定「数据日期」后再导入')

    snap = parse(rows, cells, as_of=dd)
    snap['files'] = [{'name': name, 'role': '场景攻坚成效表'}]
    snap['_notes'] = []
    if not as_of:
        snap['_notes'].append(f'数据日期取自文件名：{dd}')
    red = snap['total']['changed']
    if red:
        snap['_notes'].append(f'识别到 {red} 条标红项目（本期进度有变化），页面上会用黄色底标出')
    return dd, snap
