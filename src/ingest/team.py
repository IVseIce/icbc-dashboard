#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""team.py —— 「经理队伍」解析：财客 / 远维 两块，各自一张明细表。

## 源表（两个官方文件，各一张明细子表）

    2026年财富客户经理经营业绩通报（….xlsx）  → 子表 `财客明细`（88 列，3 行表头）
    2026年远维经理营销PK赛通报（….xlsx）      → 子表 `远维明细`（83 列，3 行表头）

两份可以一次导，也可以分两次导（导哪个更新哪个，另一块沿用同一天已有的数据）。

⚠️ 同一份工作簿里的 `计算１` / `ＶＬＯＯＫ`（远维是 `计算` / `VLOOK`）都是**中间表**：
`计算１` 只是把 `财客明细` 的三行表头改成一行的同一份数据（49×88 逐格一致），
`ＶＬＯＯＫ` 是按支行聚合的透视结果。**我们只读明细表**，不读这两张。

## 口径（对着成表逐格验算过，见 HANDOFF 8.13）

- 按支行聚合：`总得分`、`营销通两个执行率` 取**平均**，其余一律**求和**
- 存款 / 非存 / 理财：明细是**万元**。财客成表把理财也换成**亿元**；远维成表里
  理财仍按**万元**展示
- 50 万以上客户：表头写「万户」，值其实是**户**（成表照抄，不换算）
- 财客有 `网点` 列（40 个实体网点），远维**没有网点**（只有支行 + 经理）

## 列位置

两块的表头分组不同、列数不同，所以各有一份 `关键字段 → 列号` 映射，
导入时会用表头路径（三行表头合并后的文本）**逐列校验**，对不上直接报错，
避免哪天源表加了列还静默取错。
"""
from __future__ import annotations

import datetime as dt
import re
from collections import defaultdict

from . import readers

# ---------------------------------------------------------------- 列映射
# 关键字段 → 明细表里的列号（1 起）。校验串 = 三行表头合并后的「分组/子项/字段」。
CK_COLS = {
    'branch': 2, 'net': 3, 'mgr': 4, 'empno': 5, 'hu': 6, 'prov_rank': 7, 'score': 8,
    'dep_stock': 9, 'dep_inc': 10, 'dep_rate': 11, 'dep_score': 12,
    'nstock_stock': 13, 'nstock_inc': 14, 'nstock_rate': 15, 'nstock_score': 16,
    'c50_stock': 17, 'c50_inc': 18, 'c50_rate': 19, 'c50_score': 20,
    'rev_cur': 21, 'rev_score': 22, 'rev_yoy': 23, 'rev_yoy_score': 24,
    'rej_stock': 25, 'rej_inc': 26, 'rej_rate': 27, 'rej_score': 28,
    'kp_stock': 29, 'kp_inc': 30, 'kp_rate': 31, 'kp_score': 32,
    'mobile_stock': 33, 'mobile_pen': 34, 'mobile_inc': 35, 'mobile_rate': 36,
    'sb_stock': 37, 'sb_pen': 38, 'sb_inc': 39, 'sb_rate': 40,
    'yl_stock': 41, 'yl_pen': 42, 'yl_inc': 43, 'yl_rate': 44,
    'debit_stock': 45, 'debit_pen': 46, 'debit_inc': 47, 'debit_rate': 48,
    'cc_stock': 49, 'cc_pen': 50, 'cc_inc': 51, 'cc_rate': 52,
    'cp_stock': 53, 'cp_pen': 54, 'cp_inc': 55, 'cp_rate': 56,
    'prod_rate': 57, 'prod_score': 58, 'c50_in_hand': 59,
    'up_cust': 60, 'up_share': 61, 'up_amt': 62,
    'down_cust': 63, 'down_share': 64, 'down_amt': 65,
    'recov_base': 66, 'recov_cur': 67, 'recov_amt': 68, 'recov_rate': 69,
    'unp5_cnt': 70, 'unp5_amt': 71, 'fut5_cnt': 72, 'fut5_amt': 73,
    'term_end': 74, 'term_begin': 75, 'term_due': 76, 'term_rate': 77,
    'ins_year': 78, 'ins_month': 79, 'fund_year': 80, 'fund_month': 81,
    'licai_year': 82, 'licai_month': 83,
    'wx_friends': 84, 'wx_net': 85, 'wx_read': 86,
    'mkt_norm': 87, 'mkt_time': 88,
}
CK_NCOLS = 88

YW_COLS = {
    'branch': 1, 'mgr': 2, 'empno': 3, 'hu': 4, 'prov_rank': 5, 'score': 6,
    'dep_stock': 7, 'dep_inc': 8, 'dep_rate': 9, 'dep_score': 10,
    'nstock_stock': 11, 'nstock_inc': 12, 'nstock_rate': 13, 'nstock_score': 14,
    'c50_stock': 15, 'c50_inc': 16, 'c50_rate': 17, 'c50_score': 18,
    'rev_cur': 19, 'rev_score': 20, 'rev_yoy': 21, 'rev_yoy_score': 22,
    'rej_stock': 23, 'rej_inc': 24, 'rej_rate': 25, 'rej_score': 26,
    'kp_stock': 27, 'kp_inc': 28, 'kp_rate': 29, 'kp_score': 30,
    'mobile_stock': 31, 'mobile_pen': 32, 'mobile_inc': 33, 'mobile_rate': 34,
    'sb_stock': 35, 'sb_pen': 36, 'sb_inc': 37, 'sb_rate': 38,
    'yl_stock': 39, 'yl_pen': 40, 'yl_inc': 41, 'yl_rate': 42,
    'debit_stock': 43, 'debit_pen': 44, 'debit_inc': 45, 'debit_rate': 46,
    'cc_stock': 47, 'cc_pen': 48, 'cc_inc': 49, 'cc_rate': 50,
    'cp_stock': 51, 'cp_pen': 52, 'cp_inc': 53, 'cp_rate': 54,
    'prod_rate': 55, 'prod_score': 56,
    'up_cust': 57, 'up_share': 58, 'up_amt': 59,
    'down_cust': 60, 'down_share': 61, 'down_amt': 62,
    'recov_base': 63, 'recov_cur': 64, 'recov_amt': 65, 'recov_rate': 66,
    'unp5_cnt': 67, 'unp5_amt': 68, 'fut5_cnt': 69, 'fut5_amt': 70,
    'term_end': 71, 'term_begin': 72, 'term_due': 73, 'term_rate': 74,
    'fund_year': 75, 'fund_month': 76, 'licai_year': 77, 'licai_month': 78,
    'wx_friends': 79, 'wx_net': 80, 'wx_read': 81,
    'mkt_norm': 82, 'mkt_time': 83,
}
YW_NCOLS = 83

# 校验：每块抽查几个关键列的三行表头（合并后），对不上说明源表结构变了
CHECK = {
    'ck': {
        2: ('支行', '支行'), 3: ('网点', '网点'), 4: ('客户经理姓名', '客户经理姓名'),
        8: ('总得分', '总得分'), 9: ('增存', '储蓄存款（25分）万元', '存量'),
        17: ('增客', '50万以上客户（15分）户', '存量'),
        25: ('增贷', '融e借（5分）万元', '存量'),
        78: ('履职类', '期缴保险', '当年销量（万元）'),
        88: ('履职类', '营销通任务执行率', '限时营销'),
    },
    'yw': {
        1: ('支行', '支行'), 2: ('客户经理姓名', '客户经理姓名'), 6: ('总得分', '总得分'),
        7: ('增存', '储蓄存款（25分）万元', '存量'),
        15: ('增客', '50万以上客户（15分）户', '存量'),
        23: ('增贷', '融e借（5分）万元', '存量'),
        75: ('履职', '非货币基金', '当年销量（万元）'),
        83: ('履职', '营销通任务执行率', '限时营销'),
    },
}

BLOCKS = {
    'ck': {'sheet': '财客明细', 'label': '财富客户经理', 'short': '财客',
           'cols': CK_COLS, 'ncols': CK_NCOLS, 'has_net': True, 'hdr': 3, 'first': 4},
    'yw': {'sheet': '远维明细', 'label': '远维客户经理', 'short': '远维',
           'cols': YW_COLS, 'ncols': YW_NCOLS, 'has_net': False, 'hdr': 3, 'first': 4},
}

# 聚合方式：平均 vs 求和（其余一律求和）
AVG_KEYS = ('score', 'mkt_norm', 'mkt_time')

# 需要按经理/支行/合计三层都算的指标（顺序即前端展示顺序）
SUM_KEYS = (
    'hu',
    'dep_stock', 'dep_inc',
    'nstock_stock', 'nstock_inc',
    'c50_stock', 'c50_inc',
    'rej_stock', 'rej_inc',
    'kp_stock', 'kp_inc',
    'mobile_inc', 'sb_inc', 'yl_inc',
    'debit_inc', 'cc_inc', 'cp_inc',
    'ins_year', 'fund_year', 'licai_year',
    'wx_friends', 'wx_net',
    'c50_in_hand',
    'sb_stock', 'mobile_stock', 'yl_stock', 'debit_stock', 'cc_stock', 'cp_stock',
)
METRIC_KEYS = ('score',) + SUM_KEYS + ('mkt_norm', 'mkt_time')


# ---------------------------------------------------------------- 工具
def _num(v):
    """数值列可能混字符串（'780.76' / '1,234'），统一转 float。"""
    if isinstance(v, bool) or v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(',', '').replace('%', '')
    if not s or s in ('-', '—', '/', '--'):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _text(v):
    return '' if v is None else str(v).strip()


def _norm(v):
    return re.sub(r'\s+', '', _text(v))


def _header_paths(ws, ncols: int, rows=(1, 2, 3)) -> dict[int, tuple[str, ...]]:
    """把三行表头按合并区展开，得到每列的「分组/子项/字段」路径。"""
    grid = {}
    for r in rows:
        for c in range(1, ncols + 1):
            grid[(r, c)] = ws.cell(r, c).value
    for mr in ws.merged_cells.ranges:
        if mr.min_row not in rows:
            continue
        v = ws.cell(mr.min_row, mr.min_col).value
        for r in range(mr.min_row, min(mr.max_row, rows[-1]) + 1):
            for c in range(mr.min_col, mr.max_col + 1):
                grid[(r, c)] = v
    out = {}
    for c in range(1, ncols + 1):
        path = tuple(_norm(grid.get((r, c))) for r in rows)
        out[c] = tuple(x for x in path if x)
    return out


def _check_headers(name: str, ws, block: str) -> None:
    want = CHECK[block]
    ncols = BLOCKS[block]['ncols']
    if ws.max_column < ncols:
        raise ValueError(f'「{name}/{ws.title}」只有 {ws.max_column} 列，'
                         f'预期 {ncols} 列 —— 源表结构变了，先核对再导')
    paths = _header_paths(ws, ncols)
    for c, expect in want.items():
        got = paths.get(c) or ()
        if tuple(expect) != got[-len(expect):]:
            raise ValueError(
                f'「{name}/{ws.title}」第 {c} 列表头是 {"/".join(got) or "空"}，'
                f'预期 {"/".join(expect)} —— 源表列位置变了，先核对再导')


# ---------------------------------------------------------------- 读一张明细
def _read_block(name: str, ws, block: str) -> dict:
    cfg = BLOCKS[block]
    cols, ncols, first = cfg['cols'], cfg['ncols'], cfg['first']
    _check_headers(name, ws, block)

    detail, managers = [], []
    for r in range(first, ws.max_row + 1):
        raw = [ws.cell(r, c).value for c in range(1, ncols + 1)]
        # 支行列必须有值：远维明细末尾有一片"只有姓名+网点名"的临时名单区（隐藏行），要跳过
        if not _text(raw[cols['branch'] - 1]):
            continue
        detail.append(raw)
        rec = {k: (_text(raw[c - 1]) if k in ('branch', 'net', 'mgr', 'empno') else _num(raw[c - 1]))
               for k, c in cols.items()}
        rec['row'] = r
        managers.append(rec)

    if not managers:
        raise ValueError(f'「{name}/{ws.title}」里没有读到任何客户经理行')

    return {
        'label': cfg['label'], 'short': cfg['short'],
        'has_net': cfg['has_net'],
        'ncols': ncols,
        'detail': detail,
        'managers': managers,
        'src': name,
    }


# ---------------------------------------------------------------- 聚合
def _summarize(managers: list[dict], key_fields: tuple[str, ...]) -> list[dict]:
    """按 key_fields（如 ('branch',)）聚合。得分/执行率取平均，其余求和。"""
    buckets: dict[tuple, list[dict]] = defaultdict(list)
    for m in managers:
        buckets[tuple(m.get(k) or '' for k in key_fields)].append(m)

    out = []
    for key, rows in buckets.items():
        rec = dict(zip(key_fields, key))
        rec['mgrs'] = len(rows)
        for k in METRIC_KEYS:
            vals = [r.get(k) or 0.0 for r in rows]
            # 不四舍五入：成表对账是逐格比 double，截断就会差最后几位
            rec[k] = (sum(vals) / len(vals)) if k in AVG_KEYS else sum(vals)
        out.append(rec)
    return out


def _rank_by(rows: list[dict], key: str = 'score') -> list[dict]:
    """按 key 降序排名（Excel RANK 语义：并列同名次、跳号）。"""
    vals = [r.get(key) or 0.0 for r in rows]
    for r in rows:
        v = r.get(key) or 0.0
        r['rank'] = 1 + sum(1 for x in vals if x > v)
    return sorted(rows, key=lambda r: (r['rank'], r.get('name') or r.get('mgr') or ''))


def _total(managers: list[dict]) -> dict:
    rec = {'mgrs': len(managers)}
    for k in METRIC_KEYS:
        vals = [m.get(k) or 0.0 for m in managers]
        rec[k] = (sum(vals) / len(vals)) if k in AVG_KEYS else sum(vals)
    return rec


def _finish(block: str, body: dict) -> dict:
    """补上 支行 / 网点 / 经理 三层聚合与名次。"""
    managers = body['managers']
    for m in managers:
        m.setdefault('net', '')

    branches = _summarize(managers, ('branch',))
    for b in branches:
        b['name'] = b['branch']
    _rank_by(branches)

    if body['has_net']:
        nets = _summarize(managers, ('branch', 'net'))
        for n in nets:
            n['name'] = n['net']
        _rank_by(nets)
        body['nets'] = nets
    else:
        body['nets'] = []

    mgr_rows = []
    for m in managers:
        rec = {k: m.get(k) for k in METRIC_KEYS}
        rec.update({'mgr': m['mgr'], 'branch': m['branch'], 'net': m.get('net') or '',
                    'empno': m.get('empno') or '', 'row': m.get('row')})
        mgr_rows.append(rec)
    _rank_by(mgr_rows, key='score')
    for i, m in enumerate(mgr_rows):
        m['rank'] = m.get('rank') or (i + 1)

    body['branches'] = branches
    body['mgr_rows'] = sorted(mgr_rows, key=lambda r: (-(r.get('score') or 0), r['mgr']))
    body['total'] = _total(managers)
    body['n'] = len(managers)
    return body


# ---------------------------------------------------------------- 入口
def date_from_name(name: str, default_year: int | None = None) -> str | None:
    """从文件名认日期（复用私银的解析：20261021 / 2026.10.21 / 10.21 / 1021 / 10月21日…）。"""
    from .pbs import date_from_name as _pbs_date
    return _pbs_date(name, default_year=default_year)


def parse_files(files, as_of: str | None = None) -> tuple[str, dict]:
    """解析一到两个工作簿，返回 (as_of, 快照)。

    - 一次给两个也行（财客 + 远维），给一个就只更新那一块
    - `as_of` 优先用调用方给的（手填）；否则从文件名认；都认不出就报错让用户手填
    """
    import io

    import openpyxl

    found: dict[str, dict] = {}
    used = []
    dates = []
    for name, blob in files:
        wb = openpyxl.load_workbook(io.BytesIO(blob), data_only=True)
        hit = None
        for block, cfg in BLOCKS.items():
            if cfg['sheet'] in wb.sheetnames:
                hit = block
                break
        if hit is None:
            raise ValueError(f'「{name}」里找不到「财客明细」或「远维明细」子表'
                             f'（现有子表：{"、".join(wb.sheetnames)}）')
        if hit in found:
            raise ValueError(f'两个文件都是「{BLOCKS[hit]["short"]}」，只能各传一个')
        body = _finish(hit, _read_block(name, wb[BLOCKS[hit]['sheet']], hit))
        body['as_of'] = None
        found[hit] = body
        used.append({'name': name, 'role': f'{BLOCKS[hit]["label"]}明细'})
        d = date_from_name(name)
        if d:
            dates.append(d)

    if as_of:
        dd = as_of
    elif dates:
        dd = max(dates)
    else:
        raise ValueError('文件名里认不出数据日期，请手动指定「数据日期」后再导入')

    for lit, body in found.items():
        body['as_of'] = dd

    snap = {
        'as_of': dd,
        'as_of_cn': f'{int(dd[5:7])}月{int(dd[8:10])}日',
        'blocks': sorted(found),
        'files': used,
        '_notes': [],
        **{k: v for k, v in found.items()},
    }
    return dd, snap


def merge(existing: dict | None, fresh: dict) -> dict:
    """同一数据日期分两次导入时，把没导的那一块从旧快照里带过来。

    只导一块时：
      - 这天之前导过另一块 → 带过来，并注明"沿用"
      - 这天没有另一块   → 另起一行说明"本次只导了X"，不提"沿用"（免得让人以为有旧数据）
    """
    old = (existing or {}).get('payload') or (existing or {})
    out = dict(fresh)
    notes = list(out.get('_notes') or [])
    carried = []
    for block, name in (('ck', '财客'), ('yw', '远维')):
        if block in fresh:
            continue
        if old.get(block):
            out[block] = old[block]
            out['blocks'] = sorted(set(list(out['blocks']) + [block]))
            carried.append(name)
        else:
            notes.append(f'本次只导了{_OTHER[block]}，还没有{name}数据')
    if carried:
        notes.append(f'{"、".join(carried)}沿用该日期此前导入的数据')
    out['_notes'] = notes
    return out


_OTHER = {'ck': '远维', 'yw': '财客'}
