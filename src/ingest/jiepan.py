#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""jiepan.py —— 定期承接（到期承接率）：客编明细 → 网点 / 支行两层汇总。

源数据只要一张明细表（Sheet1 或第一个 sheet），18 列：
  二级分行名称 / 归属支行名称 / 机构名称 / 客户编号 / 客户经理编号 /
  近30天到期笔数 / 近30天到期金额 / 最近到期日期 / 承接笔数 /
  30天前定期余额 / 当前定期余额 / 定期余额变化 /
  30天前存款时点 / 当前存款时点 / 时点存款变化 /
  30天前资产时点 / 当前资产时点 / 时点资产变化

口径（2026-10-28 对照《保留10月25到期承接率.xlsx》的活公式逐格核实）：
  * 取数范围固定：每次导出都是「当日往前一个月」，即 31 天。
    表里 `最近到期日期` 的最小值~最大值就是这个范围；最大值 = 取数日（as_of）。
  * **可加性**：`定期余额变化` / `时点资产变化` 是每个客编「这一期」的变化量，
    与窗口无关；按 `最近到期日期` 筛行再求和，就得到任意子区间的结果。
    所以一份快照能出该 31 天内任意区间的成表，不需要多次导入。
  * 定期承接率 = (近30天到期金额 + 定期余额变化) / 近30天到期金额
    资金承接率 = (近30天到期金额 + 时点资产变化) / 近30天到期金额
    （分母是**到期金额**，不是 30 天前余额——按成表公式）
  * 网均未承接 = 支行定期余额变化合计 ÷ 该支行网点数（元 → 万元）
  * 综合评价 = 网均未承接名次×0.4 + 定期承接率名次×0.4 + 资金承接率名次×0.2
    三项名次都是**降序**（值越大名次数字越小），总分升序排前；并列取同一名次（RANK 语义）。
  * 优秀先锋网点 = 网点定期承接率降序前 8
  * 网点只算实体网点：排除「…运行管理部」

**不跨快照合并**：不同批次的「30 天前余额」基准日不同（10.25 的表基准 9.25，
10.19 的表基准 9.19），同一客编的四个余额列在不同批次里数值都不一样。
跨批次拼数据在数学上是错的，所以窗口只在单份快照内切。
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

NETS_PATH = Path(__file__).resolve().parent.parent / 'report' / 'assets' / 'jiepan_nets.json'

# 支行固定顺序（成表 Worksheet 的排列，与 report.BRANCH_ORDER 一致）
BRANCH_ORDER = ['颍州支行', '颍泉支行', '颍东支行', '界首支行', '临泉支行', '阜南支行', '颍上支行', '太和支行']

EXCLUDE_KEY = ('运行管理部',)      # 非营业网点，不计入网点数
SPAN_DAYS = 30                     # 取数范围固定为 当日往前 30 天（含当日共 31 天）
TOP_N = 8                          # 优秀先锋网点个数
UNIT = 10000.0                     # 元 → 万元

# 源表列名 → 内部字段（按列名找，不依赖列序，容忍列被挪动）
COLS = {
    'branch': '归属支行名称',
    'net': '机构名称',
    'custno': '客户编号',
    'due_cnt': '近30天到期笔数',
    'due_amt': '近30天到期金额',
    'due': '最近到期日期',
    'done_cnt': '承接笔数',
    'bal30': '30天前定期余额',
    'bal': '当前定期余额',
    'bal_d': '定期余额变化',
    'dep30': '30天前存款时点',
    'dep_d': '时点存款变化',
    'ast30': '30天前资产时点',
    'ast': '当前资产时点',
    'ast_d': '时点资产变化',
}


def _num(v) -> float:
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace(',', '').replace('，', '').strip()
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _date(v) -> date | None:
    if isinstance(v, datetime):        # datetime 是 date 的子类，必须先判
        return v.date()
    if isinstance(v, date):
        return v
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d', '%Y%m%d'):
        try:
            return datetime.strptime(s[:19], fmt).date()
        except ValueError:
            continue
    return None


def _s(v) -> str:
    if v is None:
        return ''
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def is_entity_net(name: str) -> bool:
    """实体网点：以「支行」或「营业室」结尾，且不含排除词。"""
    n = (name or '').strip()
    if not n:
        return False
    if any(k in n for k in EXCLUDE_KEY):
        return False
    return n.endswith('支行') or n.endswith('营业室')


def _find_header(rows: list[list]) -> tuple[int, dict[str, int]]:
    """找表头行（前 5 行内），返回 (行号, {内部字段: 列号})。"""
    for i, row in enumerate(rows[:5]):
        cells = [_s(c) for c in row]
        idx = {}
        for key, cn in COLS.items():
            if cn in cells:
                idx[key] = cells.index(cn)
        if 'net' in idx and 'due' in idx and 'bal_d' in idx:
            return i, idx
    raise ValueError('没有找到明细表表头（需含「机构名称」「最近到期日期」「定期余额变化」列）')


# ---------------------------------------------------------------- 内置网点清单
_NETS_CACHE: dict | None = None


def builtin_nets() -> dict:
    """内置的网点清单（支行 → 网点名列表），防止某次源表缺网点导致顺序/网点数跳变。"""
    global _NETS_CACHE
    if _NETS_CACHE is not None:
        return _NETS_CACHE
    if NETS_PATH.exists():
        _NETS_CACHE = json.loads(NETS_PATH.read_text('utf-8'))
    else:
        _NETS_CACHE = {}
    return _NETS_CACHE


def net_short(net: str, branch: str) -> str:
    """文案里的网点简称：「太和大桥」「颍泉牡丹」「阜南营业室」这种。

    规则：
      * 去掉「阜阳」前缀
      * `XX支行营业室` → `XX营业室`（去掉中间的「支行」，保留「营业室」）
      * `XX支行`       → `XX`
      * 结果里若不含支行短名，前面补上（牡丹支行 属 颍泉 → 颍泉牡丹）
      * 已经带支行名的（太和大桥支行 属 太和）不重复补
    """
    n = (net or '').replace('阜阳', '')
    if n.endswith('支行营业室'):
        n = n.replace('支行营业室', '营业室')
    elif n.endswith('支行'):
        n = n[:-2]
    if n.endswith('新区') and len(n) > 4:      # 临泉政务新区 → 临泉政务
        n = n[:-2]
    b = (branch or '').replace('阜阳', '')
    b = b[:-2] if b.endswith('支行') else b
    if b and b not in n:
        return f'{b}{n}'
    return n


# ---------------------------------------------------------------- 解析
def parse(rows: list[list], as_of: str | None = None, exclude=None) -> dict:
    """把一个明细二维表解析成快照 payload。

    rows     : 明细表二维数组（含表头）
    as_of    : 忽略（取数日固定取表里「最近到期日期」的最大值，不可手填）
    exclude  : 排除的客户编号集合（None = 不排除）
              **语义是"把这两列的变化量置 0"，不是丢掉整行**——这与人工做法一致：
              业务上「大额整体流失户」是有人在源表里把该行的
              「定期余额变化」和「时点资产变化」两列改成 0（到期金额仍保留在分母里）。
              默认不排除；将来要自动剔除时把客编传进来即可。
    """
    hrow, idx = _find_header(rows)
    body = rows[hrow + 1:]
    ex = {str(x).strip() for x in (exclude or ())}

    recs = []
    for r in body:
        if not any(c not in (None, '') for c in r):
            continue
        net = _s(r[idx['net']]) if idx['net'] < len(r) else ''
        if not net:
            continue
        due = _date(r[idx['due']]) if idx['due'] < len(r) else None
        if due is None:
            continue
        custno = _s(r[idx['custno']]) if 'custno' in idx and idx['custno'] < len(r) else ''
        zeroed = bool(custno and custno in ex)
        br = _s(r[idx['branch']]) if 'branch' in idx and idx['branch'] < len(r) else ''
        rec = {
            'branch': br, 'net': net, 'custno': custno, 'due': due,
            'due_cnt': _num(r[idx['due_cnt']]) if 'due_cnt' in idx else 0,
            'due_amt': _num(r[idx['due_amt']]) if 'due_amt' in idx else 0,
            'done_cnt': _num(r[idx['done_cnt']]) if 'done_cnt' in idx else 0,
            'bal30': _num(r[idx['bal30']]) if 'bal30' in idx else 0,
            'bal': _num(r[idx['bal']]) if 'bal' in idx else 0,
            'bal_d': 0.0 if zeroed else _num(r[idx['bal_d']]),
            'dep30': _num(r[idx['dep30']]) if 'dep30' in idx else 0,
            'dep_d': _num(r[idx['dep_d']]) if 'dep_d' in idx else 0,
            'ast30': _num(r[idx['ast30']]) if 'ast30' in idx else 0,
            'ast': _num(r[idx['ast']]) if 'ast' in idx else 0,
            'ast_d': 0.0 if zeroed else (_num(r[idx['ast_d']]) if 'ast_d' in idx else 0),
        }
        recs.append(rec)

    if not recs:
        raise ValueError('明细表里没有可用数据行（缺机构名称或最近到期日期）')

    dates = sorted({r['due'] for r in recs})
    d0, d1 = dates[0], dates[-1]
    as_of_iso = d1.isoformat()

    # 网点清单：源表里出现的实体网点 ∪ 内置清单（保证 40 个稳定）
    seen: dict[str, str] = {}
    for r in recs:
        if is_entity_net(r['net']) and r['net'] not in seen:
            seen[r['net']] = r['branch']
    builtin = builtin_nets()
    nets: list[dict] = []
    used: set[str] = set()
    for br in BRANCH_ORDER:
        names = [n for n, b in seen.items() if b == br]
        if not names:
            names = [n for n in (builtin.get(br) or []) if n in seen or n not in seen]
            names = [n for n in names if n in seen] or (builtin.get(br) or [])
        for n in sorted(names):
            if n in used:
                continue
            used.add(n)
            nets.append({'name': n, 'branch': br})
    # 不在 8 家支行里的实体网点（理论上不该有，兜底接在后面）
    for n, b in sorted(seen.items()):
        if n not in used:
            used.add(n)
            nets.append({'name': n, 'branch': b})

    net_i = {n['name']: i for i, n in enumerate(nets)}
    rows_out = []
    for r in recs:
        i = net_i.get(r['net'])
        if i is None:                        # 非实体网点（运行管理部等）不入网点和明细
            continue
        rows_out.append([
            i, (r['due'] - d0).days,
            round(r['due_amt'], 2), round(r['bal30'], 2), round(r['bal_d'], 2),
            round(r['ast30'], 2), round(r['ast_d'], 2),
        ])

    return {
        'as_of': as_of_iso,
        'as_of_cn': f'{d1.month}月{d1.day}日',
        'coverage': [d0.isoformat(), d1.isoformat()],
        'days': len(dates),
        'branches': BRANCH_ORDER,
        'nets': nets,
        'rows': rows_out,
        'totals': _sum_rows(rows_out, 0, len(dates) - 1),
        'excluded': sorted(ex),
    }


def _sum_rows(rows, lo: int, hi: int) -> dict:
    """区间 [lo, hi]（按 day offset）内各列合计。"""
    out = {'due_amt': 0.0, 'bal30': 0.0, 'bal_d': 0.0, 'ast30': 0.0, 'ast_d': 0.0, 'n': 0}
    for r in rows:
        if lo <= r[1] <= hi:
            out['due_amt'] += r[2]
            out['bal30'] += r[3]
            out['bal_d'] += r[4]
            out['ast30'] += r[5]
            out['ast_d'] += r[6]
            out['n'] += 1
    return out


# ---------------------------------------------------------------- 聚合（按窗口）
def _rank_desc(values: list[float]) -> list[int]:
    """降序名次，并列同名次、后续跳号（Excel RANK(...,0) 语义）。"""
    keys = [round(v, 10) for v in values]
    order = sorted(keys, reverse=True)
    first = {}
    for i, v in enumerate(order):
        first.setdefault(v, i + 1)          # 并列取第一次出现的位置 → 跳号
    return [first[k] for k in keys]


def _rank_asc(values: list[float]) -> list[int]:
    """升序名次，并列同名次、后续跳号（Excel RANK(...,1) 语义）。"""
    keys = [round(v, 10) for v in values]
    order = sorted(keys)
    first = {}
    for i, v in enumerate(order):
        first.setdefault(v, i + 1)
    return [first[k] for k in keys]


def aggregate(snap: dict, start: str | None = None, end: str | None = None) -> dict:
    """在一份快照内，按 [start, end] 区间聚合出网点 / 支行两层结果。

    start/end 为 ISO 日期；缺省 = 取数日往前一周（含头尾 7 天）。
    区间必须落在快照的 coverage 内，否则抛 ValueError（不跨快照拼数）。
    """
    cov0 = date.fromisoformat(snap['coverage'][0])
    cov1 = date.fromisoformat(snap['coverage'][1])
    as_of = date.fromisoformat(snap['as_of'])

    end_d = date.fromisoformat(end) if end else as_of
    start_d = date.fromisoformat(start) if start else end_d.fromordinal(end_d.toordinal() - 6)
    if start_d > end_d:
        start_d, end_d = end_d, start_d
    if start_d < cov0 or end_d > cov1:
        raise ValueError(
            f'所选区间 {start_d}~{end_d} 超出这份数据取数范围 {cov0}~{cov1}；'
            f'请选择该范围内的日期（本次数据取自 {as_of}）')
    lo = (start_d - cov0).days
    hi = (end_d - cov0).days

    nets = [dict(n) for n in snap['nets']]
    for n in nets:
        n.update(due_amt=0.0, bal_d=0.0, ast_d=0.0, bal30=0.0, ast30=0.0, n=0)
    for r in snap['rows']:
        if not (lo <= r[1] <= hi):
            continue
        n = nets[r[0]]
        n['due_amt'] += r[2]
        n['bal30'] += r[3]
        n['bal_d'] += r[4]
        n['ast30'] += r[5]
        n['ast_d'] += r[6]
        n['n'] += 1

    for n in nets:
        n['rate'] = (n['due_amt'] + n['bal_d']) / n['due_amt'] if n['due_amt'] else None
        n['frate'] = (n['due_amt'] + n['ast_d']) / n['due_amt'] if n['due_amt'] else None
        n['no_cust'] = n['n'] == 0

    # ---- 支行层
    brs: list[dict] = []
    for br in snap['branches']:
        mine = [n for n in nets if n['branch'] == br]
        if not mine:
            continue
        due = sum(n['due_amt'] for n in mine)
        bd = sum(n['bal_d'] for n in mine)
        ad = sum(n['ast_d'] for n in mine)
        brs.append({
            'name': br, 'nets': len(mine),
            'due_amt': due, 'bal_d': bd, 'ast_d': ad,
            'unpicked': bd / UNIT,                      # 定期未承接（万元）
            'avg_unpicked': bd / UNIT / len(mine) if mine else 0,
            'rate': (due + bd) / due if due else 0,
            'frate': (due + ad) / due if due else 0,
        })

    # ---- 综合评价：三项名次加权（4:4:2），总分升序
    r_avg = _rank_desc([b['avg_unpicked'] for b in brs])
    r_rate = _rank_desc([b['rate'] for b in brs])
    r_frate = _rank_desc([b['frate'] for b in brs])
    for i, b in enumerate(brs):
        b['rank_avg'] = r_avg[i]
        b['rank_rate'] = r_rate[i]
        b['rank_frate'] = r_frate[i]
        b['score'] = round(r_avg[i] * 0.4 + r_rate[i] * 0.4 + r_frate[i] * 0.2, 10)
    # 总分名次：RANK 语义（升序，并列同名次、后续跳号）
    score_ranks = _rank_asc([b['score'] for b in brs])
    for b, rk in zip(brs, score_ranks):
        b['rank'] = rk
    brs.sort(key=lambda b: (b['rank'], -b['rate'], b['name']))

    # ---- 优秀先锋：网点定期承接率降序前 8（无数据的排最后）
    ranked_nets = sorted(nets, key=lambda n: (-(n['rate'] if n['rate'] is not None else -1e9), n['name']))
    top = [n for n in ranked_nets if n['rate'] is not None][:TOP_N]

    tot = {'due_amt': sum(n['due_amt'] for n in nets),
           'bal_d': sum(n['bal_d'] for n in nets),
           'ast_d': sum(n['ast_d'] for n in nets),
           'nets': len(nets)}
    tot['unpicked'] = tot['bal_d'] / UNIT
    tot['avg_unpicked'] = tot['unpicked'] / tot['nets'] if tot['nets'] else 0
    tot['rate'] = (tot['due_amt'] + tot['bal_d']) / tot['due_amt'] if tot['due_amt'] else 0
    tot['frate'] = (tot['due_amt'] + tot['ast_d']) / tot['due_amt'] if tot['due_amt'] else 0
    tot['custs'] = sum(n['n'] for n in nets)

    return {
        'as_of': snap['as_of'],
        'coverage': snap['coverage'],
        'period': {'start': start_d.isoformat(), 'end': end_d.isoformat()},
        'totals': tot,
        'nets': ranked_nets,
        'branches': brs,
        'top_nets': top,
        'tail_nets': [n for n in ranked_nets if n['rate'] is not None][-5:][::-1],
    }


# ---------------------------------------------------------------- 入口
def parse_files(files, as_of: str | None = None, exclude=None) -> tuple[str, dict]:
    """导入入口：收一张明细表。"""
    from ingest import readers

    found = None
    used = []
    for name, blob in files:
        for sheet, rows in readers.sheets(blob, name):
            try:
                _find_header(rows)
            except ValueError:
                used.append({'name': name, 'role': f'未识别（{sheet}）'})
                continue
            if found is not None:
                used.append({'name': name, 'role': f'多余，忽略（{sheet}）'})
                continue
            found = (name, sheet, rows)
            used.append({'name': name, 'role': f'客编明细（{sheet}）'})

    if found is None:
        raise ValueError('没有找到明细表（需含「机构名称」「最近到期日期」「定期余额变化」列）')

    name, sheet, rows = found
    snap = parse(rows, as_of=as_of, exclude=exclude)
    snap['_files'] = used
    snap['_notes'] = [
        f'取数范围 {snap["coverage"][0]} ~ {snap["coverage"][1]}（{snap["days"]} 天），'
        f'取数日 {snap["as_of"]}',
        f'实体网点 {len(snap["nets"])} 个，明细 {len(snap["rows"])} 行',
    ]
    if snap['excluded']:
        snap['_notes'].append(f'按需排除 {len(snap["excluded"])} 个客户')
    return snap['as_of'], snap


if __name__ == '__main__':
    import sys
    src = sys.argv[1] if len(sys.argv) > 1 else '/mnt/d/资料/ICBC/20261028定期承接/定期承接1025.xlsx'
    from ingest import readers
    blob = Path(src).read_bytes()
    _, snap = parse_files([(Path(src).name, blob)])
    print(json.dumps({k: v for k, v in snap.items() if k not in ('rows', 'nets')},
                     ensure_ascii=False, indent=1)[:1200])
    agg = aggregate(snap)
    print('窗口', agg['period'], '合计', agg['totals'])
    for b in agg['branches']:
        print(f"  {b['rank']:>2} {b['name']:6s} {b['unpicked']:>11,.2f}万 "
              f"网均{b['avg_unpicked']:>9,.2f} {b['rate']:.4f} {b['frate']:.4f}")
    print('优秀先锋:', '、'.join(net_short(n['name'], n['branch']) for n in agg['top_nets']))
