#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""jbl.py —— 「基保理」（基金 / 保险 / 理财）解析。

## 源表形态（用户直接给的是**成表**，不是明细）

一份《XX理财产品实时通报.xls》，里面通常有 5 张子表：

    支行通报    ← 要
    网点通报    ← 要
    支行草稿    ← 中间产物，忽略
    网点草稿    ← 中间产物，忽略
    40期        ← 个人明细产品指标查询表（按日），中间产物，忽略

**只读「支行通报」「网点通报」两张**，而且**照成表的数取，不自己重算**。
（成表里的 `合计` 列与我们按网点汇总的结果并不一致——源表自己就有对不上的地方，
 用户明确要求"导入的直接就是成表，直接用于做可视化"，所以不做二次汇总、不做校验修正。）

## 表头长这样（第 1 行标题、第 2 行字段，但行号不固定）

    支行通报：支行 | 39期销量 | 40期销量 | 本期销量 | 每期目标 | 达成率 | 重点基金 | 合计
    网点通报：（空）| 网点 | 39期销量 | 40期销量 | 本期销量 | 重点基金 | 合计

注意：
  * **期数不固定**：这期是 39/40/本期，下期就是 40/41/本期。所以列名要按
    `(\\d+)期销量` 动态解析，不能写死列号、也不能写死 39/40。
  * **「本期」是几期写在标题里**：`11.1第41期重点封闭式理财产品营销情况通报`。
    标题里认不出时才退回"列里最大期数 + 1"。
  * `合计` 列在两张表里口径不同（支行表有、网点表也有），都是源表给的，原样保留。
  * **单位是万元**（销量/目标/重点基金都是）。

## 识别规则（内容优先，名字只作兜底）

扫每张子表的**前 8 行**找"字段行"：同时出现「网点」或「支行」以及
`N期销量`/`本期销量` 之一 → 这是候选表。

  * 有「网点」列 → 网点表（首列无表头的"支行列"取第 0 列）
  * 否则 → 支行表（首列就是支行名）

同结构的多张表（`支行草稿` 与 `支行通报` 表头一模一样）→ 优先子表名带「通报」的，
并在 `_files` 里注明；只有草稿时用草稿。

## 多次导入会重叠

一次导入含 3 期（39/40/本期 41），下次导入可能是 41/42/本期 43 —— 期数会重叠。
所以快照里**按期数存**（不是按列位），上层按期数去重、后导入的覆盖先导入的。
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from . import readers
from .pbs import date_from_name

# 网点 → 支行：**不用源表里那一列**（源表网点通报的支行列是错的：
# 太和人民路被标成颍州、界首科创标成颍州、阜南三家标成阜南以外……按它聚合会和
# 「支行通报」完全不同）。统一用固定清单，与私银/一卡一户同一套 40 个实体网点。
NET_MAP_PATH = Path(__file__).resolve().parent.parent / 'report' / 'assets' / 'jbl_nets.json'

# 源表里的三种产品线，标题里认；认不出默认理财
KINDS = ('理财', '基金', '保险')
DEFAULT_KIND = '理财'

# 产品线 → 条线 id。三条线各存各的，互不覆盖（同一天三张表都能导进来）
KIND_LINE = {'理财': 'jbl_lc', '基金': 'jbl_fund', '保险': 'jbl_bx'}

# 表头字段（正则 → 内部键）
FIELD_RX = [
    ('branch_first', re.compile(r'^支行$')),
    ('net_first', re.compile(r'^网点$')),
    ('period', re.compile(r'^(\d{1,3})\s*期销量$')),
    ('current', re.compile(r'^本期销量$')),
    ('target', re.compile(r'^每期目标$')),
    ('rate', re.compile(r'^达成率$')),
    ('fund', re.compile(r'^重点基金$')),
    ('total', re.compile(r'^合计$')),
]

TITLE_PERIOD_RX = re.compile(r'第\s*(\d{1,3})\s*期')


# ---------------------------------------------------------------- 小工具
def _num(v):
    """数值列可能混字符串（'780.76' / '1,234' / 空），统一转 float；空返回 None。"""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(',', '').replace('％', '%')
    if not s or s in ('-', '—', '/', '--'):
        return None
    if s.endswith('%'):
        try:
            return float(s[:-1]) / 100.0
        except ValueError:
            return None
    try:
        return float(s)
    except ValueError:
        return None


def _text(v):
    return '' if v is None else str(v).strip()


def _norm(v):
    return re.sub(r'\s+', '', _text(v))


def _isnum(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _load_net_map():
    """网点 → 支行；文件缺失时退化成空表（那就用源表的支行列）。"""
    try:
        d = json.loads(NET_MAP_PATH.read_text('utf-8'))
        return {n['name']: n['branch'] for n in d.get('nets') or []}
    except (OSError, ValueError, KeyError):
        return {}


_NET2BR = _load_net_map()


def _cell(row, i):
    """越界取 None，省得到处判长度。"""
    if i is None or i < 0 or i >= len(row):
        return None
    return row[i]


# ---------------------------------------------------------------- 认表
def _find_header(rows):
    """在前 8 行里找字段行，返回 (行号, 列映射) 或 None。

    列映射：{'branch','net','periods':{39:2,40:3},'current','target','rate','fund','total'}
    """
    for r, row in enumerate(rows[:8]):
        cells = [_norm(c) for c in row]
        if not any(cells):
            continue
        hit = {'periods': {}}
        for i, c in enumerate(cells):
            if not c:
                continue
            for key, rx in FIELD_RX:
                if key == 'branch_first':
                    if rx.match(c) and 'branch' not in hit:
                        hit['branch'] = i
                        break
                elif key == 'net_first':
                    if rx.match(c) and 'net' not in hit:
                        hit['net'] = i
                        break
                else:
                    m = rx.match(c)
                    if not m:
                        continue
                    if key == 'period':
                        hit['periods'][int(m.group(1))] = i
                    elif key not in hit:
                        hit[key] = i
                    break
        has_name = ('net' in hit) or ('branch' in hit)
        has_sales = bool(hit['periods']) or ('current' in hit)
        if not (has_name and has_sales):
            continue
        # 网点表首列（表头是空的）是支行名
        if 'net' in hit and hit['net'] > 0 and 'branch' not in hit:
            hit['branch'] = 0
        return r, hit
    return None


def _role(header):
    """有「网点」列的当网点表，其余当支行表。"""
    return 'nets' if 'net' in header else 'branches'


def _title_of(rows, header_row):
    """标题：字段行上面最近的一行有文字的。"""
    for r in range(header_row - 1, -1, -1):
        for c in rows[r]:
            t = _text(c)
            if t and not _isnum(c):
                return t
    return ''


def _kind_of(text):
    for k in KINDS:
        if k in text:
            return k
    return DEFAULT_KIND


# ---------------------------------------------------------------- 读一张表
def _read_table(rows, header_row, header, role):
    """从字段行往下读数据行。

    返回 {'rows': [...], 'periods': [...], 'total': {...}, 'total_periods': {...}}
    `total_*` 是源表自带的「合计」行，原样保留（不自算）。
    """
    periods = sorted(header['periods'])
    name_idx = header['net'] if role == 'nets' else header['branch']
    branch_idx = header['branch'] if role == 'nets' else None

    recs = []
    total_row = None
    total_periods = {}
    for r in range(header_row + 1, len(rows)):
        row = rows[r]
        if not any(_text(c) for c in row):
            continue
        name = _text(_cell(row, name_idx))
        if not name:
            continue

        if name in ('合计', '总计', '小计'):
            total_row = _num(_cell(row, header.get('total')))
            total_periods = {str(p): _num(_cell(row, i)) for p, i in header['periods'].items()}
            if 'current' in header:
                total_periods['current'] = _num(_cell(row, header['current']))
            continue

        rec = {'name': name}
        if role == 'nets':
            rec['branch'] = _NET2BR.get(name) or _text(_cell(row, branch_idx))
        rec['metric'] = {str(p): _num(_cell(row, i)) for p, i in header['periods'].items()}
        if 'current' in header:
            rec['current'] = _num(_cell(row, header['current']))
        for key in ('target', 'rate', 'fund', 'total'):
            if key in header:
                rec[key] = _num(_cell(row, header[key]))
        recs.append(rec)

    return {'rows': recs, 'periods': periods,
            'total': total_row, 'total_periods': total_periods}


# ---------------------------------------------------------------- 入口
def parse_files(files, as_of=None, want_kind=None):
    """解析一个或多个工作簿，返回 (as_of, 快照)。

    `want_kind` = 这条线期望的产品线（理财/基金/保险）。源表标题里认出来的
    产品线与它不符时**直接报错**，避免把基金表传进理财条线。

    - 一次给多个文件也行；同一个工作簿里两种表都有最好
    - `as_of` 优先用手填的；其次标题里的日期（"11.1第41期…"）；再其次文件名
    """
    cands = {'branches': [], 'nets': []}
    used = []
    notes = []
    title = ''
    title_name = ''

    for name, blob in files:
        for sheet, rows in readers.sheets(blob, name):
            found = _find_header(rows)
            if not found:
                used.append({'name': name, 'role': f'忽略（{sheet}：不是通报表）'})
                continue
            header_row, header = found
            role = _role(header)
            t = _title_of(rows, header_row)
            # 标题优先取「通报」子表的：草稿表的标题可能带错别字
            # （实测「101.1第41期…」多打一个 0），用它认日期会认不出来
            if t and (not title or ('通报' in sheet and '通报' not in title_name)):
                title, title_name = t, sheet
            cands[role].append({'name': name, 'sheet': sheet, 'rows': rows,
                                'header_row': header_row, 'header': header})

    if not cands['branches'] and not cands['nets']:
        raise ValueError(
            '没认出「支行通报」「网点通报」。判断依据是表头：要有「支行」或「网点」列，'
            '并且有「N期销量」「本期销量」这类列。所有子表都读过了，没有符合的。')

    out = {}
    for role, hits in cands.items():
        if not hits:
            continue
        # 同结构多张表（草稿 vs 通报）：优先子表名带「通报」的；都没有就用最后一张
        named = [h for h in hits if '通报' in h['sheet'] or '通报' in h['name']]
        pick = (named or hits)[-1]
        body = _read_table(pick['rows'], pick['header_row'], pick['header'], role)
        if not body['rows']:
            continue
        out[role] = body
        label = '支行通报' if role == 'branches' else '网点通报'
        how = '表头' if len(hits) == 1 else '表头 + 子表名'
        used.append({'name': pick['name'],
                     'role': f'{label}（{len(body["rows"])} 行，{pick["sheet"]}，按{how}识别）'})
        if len(hits) > 1:
            skipped = '、'.join(h['sheet'] for h in hits if h is not pick)
            notes.append(f'{label}有 {len(hits)} 张同结构表，取了「{pick["sheet"]}」，'
                         f'忽略：{skipped}')

    if not out:
        raise ValueError('读到了表头但一行数据也没有，检查源表是否为空')

    # ---- 本期是第几期：标题里的「第N期」
    period = None
    m = TITLE_PERIOD_RX.search(title)
    if m:
        period = int(m.group(1))
    prev = set()
    for body in out.values():
        prev.update(body['periods'])
    if period is None and prev:
        period = max(prev) + 1
        notes.append(f'标题里没写「第几期」，按列里最大期数 +1 推为本期第 {period} 期')

    # ---- 日期：手填 > 标题 > 文件名
    dd = as_of or date_from_name(title) or None
    if not dd:
        for name, _blob in files:
            dd = date_from_name(name)
            if dd:
                notes.append('标题里认不出日期，用了文件名里的日期')
                break
    if not dd:
        raise ValueError('认不出数据日期：标题（如「11.1第41期…」）和文件名里都没有日期，'
                         '请手动填「本期」日期后再导入')

    # ---- 各期合计：优先支行表的「合计」行（源表口径），其次按网点求和
    totals = {}
    for role in ('branches', 'nets'):
        body = out.get(role)
        if not body:
            continue
        for p in body['periods']:
            key = str(p)
            if key in totals:
                continue
            v = body['total_periods'].get(key)
            if v is None:
                v = sum((r['metric'].get(key) or 0) for r in body['rows'])
            totals[key] = v
        if period is not None:
            key = str(period)
            if key not in totals:
                v = body['total_periods'].get('current')
                if v is None:
                    v = sum((r.get('current') or 0) for r in body['rows'])
                totals[key] = v

    kind = _kind_of(title)
    if want_kind and kind != want_kind:
        raise ValueError(
            f'这是「{kind}」的表（标题：{title}），当前模块是「{want_kind}」。'
            f'请到对应的产品线再导入。')

    snap = {
        'as_of': dd,
        'as_of_cn': f'{int(dd[5:7])}月{int(dd[8:10])}日',
        'kind': kind,
        'title': title,
        'period': period,
        'periods': sorted(int(k) for k in totals),
        'period_totals': totals,
        'branches': (out.get('branches') or {}).get('rows') or [],
        'branch_total_row': (out.get('branches') or {}).get('total'),
        'nets': (out.get('nets') or {}).get('rows') or [],
        '_files': used,
        '_notes': notes,
    }
    if not snap['branches'] or not snap['nets']:
        lack = '支行通报' if not snap['branches'] else '网点通报'
        snap['_notes'].append(f'本次没有「{lack}」，两张表都有的页面内容会更完整；'
                              f'同一天再导一次缺的那张会自动合并')
    return dd, snap


# ---------------------------------------------------------------- 同日合并
def merge(existing, fresh):
    """同一天分两次导入（先支行、后网点）时，把缺的那张从旧快照带过来。"""
    old = {}
    if existing:
        old = existing.get('payload') or existing or {}
    out = dict(fresh)
    notes = list(out.get('_notes') or [])
    carried = []
    for key, label in (('branches', '支行通报'), ('nets', '网点通报')):
        if out.get(key):
            continue
        if old.get(key):
            out[key] = old[key]
            carried.append(label)
    if carried:
        notes.append(f'本次没导 {"、".join(carried)}，已沿用同一天（{out.get("as_of")}）'
                     f'上次导入的数据')
        for key in ('period_totals', 'periods'):
            if not out.get(key) and old.get(key):
                out[key] = old[key]
        if not out.get('period') and old.get('period'):
            out['period'] = old['period']
    out['_notes'] = notes
    return out


if __name__ == '__main__':
    import json
    import sys
    from pathlib import Path
    src = sys.argv[1] if len(sys.argv) > 1 else \
        '/mnt/d/资料/ICBC/20261102基保理/1026理财产品实时通报.xls'
    blob = Path(src).read_bytes()
    _dd, snap = parse_files([(Path(src).name, blob)])
    slim = dict(snap)
    slim['branches'] = slim['branches'][:2] + (['…'] if len(snap['branches']) > 2 else [])
    slim['nets'] = slim['nets'][:2] + (['…'] if len(snap['nets']) > 2 else [])
    print(json.dumps(slim, ensure_ascii=False, indent=1))
    print('date_from_name sanity:', date_from_name('11.1第41期重点封闭式理财产品营销情况通报'),
          '| today', dt.date.today().isoformat())
