#!/home/isee/.venvs/data-tools/bin/python
# -*- coding: utf-8 -*-
"""api.py —— 视图模型层：把 snapshots 里的事实数据加工成各页面直接可用的 JSON。

设计约束（为了以后好改）：
  * 每个条线一个 build_<line>() 函数，返回**扁平、前端可直接画图**的结构；
  * 新加一个条线 = 写一个 build_xxx + 在 REGISTRY 登记 + 前端加一个 page 文件；
  * 这里只做「取数 + 派生指标」，不做任何样式/文案排版，排版交给前端。
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any

import store
import viz

BRANCHES = ['颍州', '颍泉', '颍东', '界首', '临泉', '阜南', '颍上', '太和']


# ---------------------------------------------------------------- 通用
def _r(v, nd=2):
    if v is None:
        return None
    try:
        return round(float(v), nd)
    except (TypeError, ValueError):
        return None


def _snaps(line: str) -> list[dict]:
    return sorted(viz.load_snapshots(line), key=lambda s: s.get('as_of') or '')


def _latest(line: str, on: str | None = None) -> dict | None:
    """取「不晚于 on」的最新一期；on 为空取最新。
    历史回填的 partial 快照只用来画趋势，不能当作详情页的数据源。"""
    snaps = _snaps(line)
    if on:
        snaps = [x for x in snaps if (x.get('as_of') or '') <= on]
    full = [x for x in snaps if not x.get('partial')]
    return full[-1] if full else None


def _upto(line: str, on: str | None = None) -> list[dict]:
    snaps = _snaps(line)
    return [x for x in snaps if not on or (x.get('as_of') or '') <= on]


def _pct(a, b, nd=2):
    if a is None or not b:
        return None
    return _r(a / b, nd + 2)


def _hist(values: list[float], bins: int = 6) -> dict:
    vals = [v for v in values if v is not None]
    if not vals:
        return {'labels': [], 'counts': []}
    lo, hi = min(vals), max(vals)
    if lo == hi:
        return {'labels': [f'{lo:.0%}'], 'counts': [len(vals)]}
    step = (hi - lo) / bins
    counts = [0] * bins
    for v in vals:
        i = min(bins - 1, int((v - lo) / step))
        counts[i] += 1
    labels = [f'{lo + step * i:.0%}~{lo + step * (i + 1):.0%}' for i in range(bins)]
    return {'labels': labels, 'counts': counts, 'lo': lo, 'hi': hi}


# ---------------------------------------------------------------- 定期存款

def _no_data(line: str, on: str | None = None) -> dict:
    """该日期没有完整数据：告诉前端最近一期是哪天、可选日期有哪些。"""
    all_dates = store.dates(line)
    before = [d for d in all_dates if not on or d <= on]
    return {'ok': False, 'as_of': on, 'nearest': before[-1] if before else (all_dates[-1] if all_dates else None),
            'available': all_dates, 'reason': '该日期没有数据' if before else '所选日期早于最早数据'}


def build_fivecards(on: str | None = None) -> dict:
    """五卡唤醒（支行维度）：每张卡的存量、长尾、未激活/未缴存、未交易。"""
    s = _latest('wk', on)
    if not s:
        return _no_data('wk', on)
    branches = s.get('branches') or []
    total = s.get('total') or {}
    cards = s.get('cards') or []

    def val(rec, card, metric):
        return (rec.get('values') or {}).get(f'{card}|{metric}')

    def pick(rec, card, *names):
        for n in names:
            v = val(rec, card, n)
            if v is not None:
                return n, v
        return None, None

    out_cards = []
    for card in cards:
        stock = val(total, card, '存量客户数')
        if stock is None:
            stock = sum((val(b, card, '存量客户数') or 0) for b in branches)
        long_n = val(total, card, '长尾客户数')
        if long_n is None and any(val(b, card, '长尾客户数') is not None for b in branches):
            long_n = sum((val(b, card, '长尾客户数') or 0) for b in branches)
        idle_name, idle = pick(total, card, '存量未激活', '睡眠户数', '未缴存人数')
        trade_name, trade = pick(total, card, '近一年未交易')
        out_cards.append({
            'name': card, 'stock': stock,
            'long': long_n, 'long_rate': _r(long_n / stock, 4) if stock and long_n is not None else None,
            'idle_label': idle_name, 'idle': idle,
            'idle_rate': _r(idle / stock, 4) if stock and idle is not None else None,
            'trade_label': trade_name, 'trade': trade,
            'trade_rate': _r(trade / stock, 4) if stock and trade is not None else None,
        })

    rows = []
    for b in branches:
        rec = {'name': b['name'], 'cards': {}}
        for card in cards:
            st = val(b, card, '存量客户数')
            ln = val(b, card, '长尾客户数')
            rec['cards'][card] = {'stock': st, 'long': ln,
                                  'long_rate': _r(ln / st, 4) if st and ln is not None else None}
        rows.append(rec)

    return {
        'ok': True, 'as_of': s['as_of'], 'cards': out_cards, 'branches': rows,
        'totals': {'stock': sum(c['stock'] or 0 for c in out_cards),
                   'long': sum(c['long'] for c in out_cards if c['long'] is not None),
                   'long_rate': _r(sum(c['long'] for c in out_cards if c['long'] is not None)
                                   / max(1, sum(c['stock'] for c in out_cards if c['long'] is not None)), 4)},
    }


def build_payroll(on: str | None = None) -> dict:
    """代发明细（月度、网点维度）：金额用「全年代发金额」的年累计，月度值由相邻两期相减。"""
    s = _latest('dfmx', on)
    if not s:
        return _no_data('dfmx', on)
    snaps = _upto('dfmx', on)
    trend, prev_ytd, prev_month = [], None, None
    for x in snaps:
        ytd = (x.get('totals') or {}).get('amt_year') or 0
        mon = x.get('month') or ''
        # 跨年要重置：新年第一个月的「当月」= YTD 本身，不能拿去年累计相减
        if prev_ytd is None:
            amount = None
        elif mon[:4] != (prev_month or '')[:4]:
            amount = round(ytd / 10000, 2)
        else:
            amount = round((ytd - prev_ytd) / 10000, 2)
        trend.append({'month': mon, 'd': x['as_of'], 'ytd': round(ytd / 10000, 2),
                      'amount': amount,
                      'cust': (x.get('totals') or {}).get('cust'),
                      'comps': (x.get('totals') or {}).get('comps')})
        prev_ytd, prev_month = ytd, mon

    nets = s.get('nets') or []
    t = s.get('totals') or {}
    br: dict[str, dict] = {}
    for n in nets:
        b = br.setdefault(n['branch'], {'name': n['branch'], 'nets': 0, 'comps': 0, 'cust': 0.0,
                                        'ytd': 0.0, 'new_year': 0, 'lost': 0, 'warn': 0})
        b['nets'] += 1
        for k in ('comps', 'cust', 'amt_year', 'new_year', 'lost', 'warn'):
            key = 'ytd' if k == 'amt_year' else k
            b[key] = b.get(key, 0) + (n.get(k) or 0)
    branches = sorted(br.values(), key=lambda x: -x['ytd'])
    for b in branches:
        b['ytd'] = round(b['ytd'] / 10000, 2)

    month_amt = next((t['amount'] for t in reversed(trend) if t['amount'] is not None), 0)
    return {
        'ok': True, 'as_of': s['as_of'], 'month': s.get('month'),
        'kpi': {
            'comps': t.get('comps'), 'cust': t.get('cust'),
            'ytd': round((t.get('amt_year') or 0) / 10000, 2), 'month': month_amt,
            'new_year': t.get('new_year'), 'lost': t.get('lost'), 'warn': t.get('warn'),
            'assets': round((t.get('assets') or 0) / 10000, 2) if t.get('assets') else None,
            'pen': t.get('pen') or {},
            'tier': t.get('tier') or {},
            'nets': len(nets), 'cols': s.get('cols') or [],
        },
        'trend': trend,
        'branches': branches,
        'nets': [{'name': n['name'], 'branch': n['branch'], 'comps': n['comps'],
                  'cust': n['cust'], 'ytd': round((n.get('amt_year') or 0) / 10000, 2),
                  'new_year': n.get('new_year'), 'lost': n.get('lost'), 'warn': n.get('warn'),
                  'assets': round((n.get('assets') or 0) / 10000, 2) if n.get('assets') else None,
                  'tier': n.get('tier') or {}, 'pen': n.get('pen') or {}} for n in nets],
    }


def build_deposit(on: str | None = None) -> dict:
    s = _latest('dqzz', on)
    if not s:
        return _no_data('dqzz', on)
    br = sorted(s['branches'], key=lambda b: -(b.get('cur_bal') or 0))
    total = s['total']
    incs = [b['inc'] for b in br]
    idx = sorted(range(len(br)), key=lambda i: -incs[i])
    trend = [{'d': x['as_of'], 'bal': x['total']['cur_bal'], 'inc': x['total']['inc']}
             for x in _upto('dqzz', on) if x.get('total')]
    return {
        'ok': True, 'as_of': s['as_of'], 'prev_as_of': s.get('prev_as_of'),
        'kpi': {
            'balance': total['cur_bal'], 'balance_yi': _r(total['cur_bal'] / 10000, 2),
            'inc': total['inc'], 'rate': _r(total['rate'], 4),
            'prev_balance': total['prev_bal'],
            'positive': sum(1 for v in incs if v > 0), 'negative': sum(1 for v in incs if v < 0),
            'best': {'name': br[idx[0]]['name'], 'inc': br[idx[0]]['inc']},
            'worst': {'name': br[idx[-1]]['name'], 'inc': br[idx[-1]]['inc']},
            'avg_inc_per_branch': _r(total['inc'] / max(1, len(br)), 2),
        },
        'branches': [{'name': b['name'], 'full': b.get('full'),
                      'prev': _r(b.get('prev_bal')), 'cur': _r(b.get('cur_bal')),
                      'inc': _r(b.get('inc')), 'rate': _r(b.get('rate'), 4),
                      'share': _r((b.get('cur_bal') or 0) / total['cur_bal'], 4) if total['cur_bal'] else None,
                      'rank_bal': i + 1,
                      'rank_inc': idx.index(i) + 1} for i, b in enumerate(br)],
        'trend': trend,
        'meta': {'as_of': s['as_of'], 'prev_as_of': s.get('prev_as_of')},
    }


# ---------------------------------------------------------------- 线上服务
def build_online(on: str | None = None) -> dict:
    s = _latest('xsfw', on)
    if not s:
        return _no_data('xsfw', on)
    nets = s.get('nets') or []
    tot = s.get('tot') or {}
    br_map: dict[str, list] = {}
    for n in nets:
        br_map.setdefault(n['branch'], []).append(n)

    branches = []
    for b in BRANCHES:
        rs = br_map.get(b) or []
        if not rs:
            continue
        w = sum(r['cust'] for r in rs) or 1
        add = sum(r['add_month'] for r in rs)
        branches.append({
            'name': b, 'nets': len(rs), 'cust': sum(r['cust'] for r in rs),
            'day_rate': _r(sum(r['cust'] * r['day_rate'] for r in rs) / w, 4),
            'month_rate': _r(sum(r['cust'] * r['month_rate'] for r in rs) / w, 4),
            'cust_delta': sum(r.get('cust_delta') or 0 for r in rs),
            'add_today': sum(r['add_today'] for r in rs), 'add_month': add,
            'real_rate': _r(sum((r.get('add_real') or 0) * (r.get('add_month') or 0) for r in rs) / add, 4) if add else None,
            'sign_rate': _r(sum((r.get('sign_rate') or 0) for r in rs) / len(rs), 4),
            'kh_rate': _r(sum((r.get('kh_rate') or 0) for r in rs) / len(rs), 4),
        })

    ranks = sorted(nets, key=lambda n: -(n['day_rate'] or 0))
    rates = [n['day_rate'] for n in nets]
    trend = [{'d': x['as_of'], 'day_rate': _r(sum((n['cust'] or 0) * (n['day_rate'] or 0)
                                                  for n in x.get('nets') or [])
                                              / max(1, sum(n['cust'] or 0 for n in x.get('nets') or [])), 4)}
             for x in _upto('xsfw', on) if x.get('nets')]
    return {
        'ok': True, 'as_of': s['as_of'], 'prev_as_of': s.get('prev_as_of'),
        'kpi': {
            'day_rate': _r(tot.get('day_rate'), 4), 'month_rate': _r(tot.get('month_rate'), 4),
            'cust': tot.get('cust'), 'add_today': tot.get('add_today'),
            'add_month': tot.get('add_month'),
            'nets': len(nets),
            'avg_day_rate': _r(sum(rates) / len(rates), 4) if rates else None,
            'above55': sum(1 for r in rates if (r or 0) >= 0.55),
            'below45': sum(1 for r in rates if (r or 0) < 0.45),
            'sign_rate': _r(sum((n.get('sign_rate') or 0) for n in nets) / max(1, len(nets)), 4),
            'kh_rate': _r(sum((n.get('kh_rate') or 0) for n in nets) / max(1, len(nets)), 4),
            'real_rate': _r(sum((n.get('add_real') or 0) * (n.get('add_month') or 0) for n in nets)
                            / max(1, sum(n.get('add_month') or 0 for n in nets)), 4),
        },
        'branches': branches,
        'hist': _hist(rates, 6),
        'scatter': [{'name': n.get('label') or n.get('name') or '', 'branch': n.get('branch') or '', 'x': _r((n.get('day_rate') or 0) * 100, 2),
                     'y': _r((n.get('sign_rate') or 0) * 100, 2), 'size': n.get('cust') or 0,
                     'month_rate': _r((n['month_rate'] or 0) * 100, 2),
                     'add_month': n['add_month']} for n in nets],
        'trend': trend,
        'nets': [{'name': n.get('label') or n.get('name') or '', 'branch': n.get('branch') or '',
                  'day_rate': _r((n.get('day_rate') or 0) * 100, 2),
                  'month_rate': _r((n.get('month_rate') or 0) * 100, 2),
                  'cust': n.get('cust') or 0, 'cust_delta': n.get('cust_delta'),
                  'add_today': n.get('add_today') or 0, 'add_month': n.get('add_month') or 0,
                  'real_rate': _r((n.get('add_real') or 0) * 100, 2),
                  'sign_rate': _r((n.get('sign_rate') or 0) * 100, 2),
                  'kh_rate': _r((n.get('kh_rate') or 0) * 100, 2),
                  'auth_cust': n.get('auth_cust'), 'auth_signed': n.get('auth_signed'),
                  'kh': n.get('kh'), 'kh_signed': n.get('kh_signed')} for n in ranks],
    }


# ---------------------------------------------------------------- 数币钱包
def build_wallet(on: str | None = None) -> dict:
    s = _latest('sbqb', on)
    if not s:
        return _no_data('sbqb', on)
    nets = s.get('nets') or []
    totals = s.get('totals') or [0] * 7
    br_map: dict[str, dict] = {}
    for n in nets:
        d = br_map.setdefault(n['branch'], {'total': 0, 'month': 0, 'day': 0, 'nets': 0,
                                            'lv': [0, 0, 0, 0]})
        d['total'] += n['total']; d['month'] += n['month']; d['day'] += n['day']; d['nets'] += 1
        lv = n.get('lv') or [n.get('lv1', 0), n.get('lv2', 0), n.get('lv3', 0), n.get('lv4', 0)]
        for i in range(4):
            d['lv'][i] += lv[i]
    trend = [{'d': x['as_of'], 'total': x.get('total')} for x in _upto('sbqb', on) if x.get('total')]
    ranked = sorted(nets, key=lambda n: -n['total'])
    return {
        'ok': True, 'as_of': s['as_of'],
        'kpi': {'total': totals[4], 'month': totals[5], 'day': totals[6],
                'lv': totals[:4], 'nets': len(nets),
                'zero_day': s.get('zero_day_count') or 0,
                'per_net': _r(totals[4] / max(1, len(nets)), 1),
                'dod': _r(trend[-1]['total'] - trend[-2]['total'], 0) if len(trend) > 1 else None},
        'branches': [{'name': k, 'total': v['total'], 'month': v['month'], 'day': v['day'],
                      'nets': v['nets'], 'lv': v['lv']}
                     for k, v in sorted(br_map.items(), key=lambda kv: -kv[1]['total'])],
        'nets': [{'name': n['name'], 'branch': n['branch'], 'total': n['total'],
                  'month': n['month'], 'day': n['day'],
                  'lv': n.get('lv') or [n.get('lv1', 0), n.get('lv2', 0), n.get('lv3', 0), n.get('lv4', 0)]}
                 for n in ranked],
        'trend': trend,
    }


# ---------------------------------------------------------------- 薪管家
def build_salary(on: str | None = None) -> dict:
    s = _latest('xgj', on)
    if not s:
        return _no_data('xgj', on)
    br = s.get('branches') or []
    nets = s.get('nets') or []
    trend = [{'d': x['as_of'], 'year': x.get('total'), 'month': x.get('month_total'),
              'ents': x.get('ent_year')} for x in _upto('xgj', on) if x.get('total') is not None]
    return {
        'ok': True, 'as_of': s['as_of'],
        'kpi': {'year': s.get('total'), 'month': s.get('month_total'),
                'ent_year': s.get('ent_year'), 'ent_month': s.get('ent_month'),
                'branches_active': sum(1 for b in br if (b.get('year') or 0) > 0),
                'nets_active': sum(1 for n in nets if (n.get('year') or 0) > 0),
                'top': max(br, key=lambda b: b.get('year') or 0) if br else None},
        'branches': sorted(br, key=lambda b: -(b.get('year') or 0)),
        'nets': nets,
        'trend': trend,
    }


# ---------------------------------------------------------------- 企微社群
def build_community(on: str | None = None) -> dict:
    s = _latest('qwsq', on)
    if not s:
        return _no_data('qwsq', on)
    t = s.get('total') or {}
    return {
        'ok': True, 'as_of': s['as_of'],
        'kpi': {'groups': t.get('groups'), 'cust': t.get('cust'), 'inter': t.get('inter'),
                'rate': _r(t.get('rate'), 4), 'rate_d': _r(t.get('rate_d'), 5),
                'groups_d': t.get('groups_d'),
                'cust_d': t.get('cust_d'), 'inter_d': t.get('inter_d'),
                'empty_nets': sum(1 for n in (s.get('nets') or []) if not n.get('groups'))},
        'branches': sorted(s.get('branches') or [], key=lambda b: -(b.get('cust') or 0)),
        'nets': sorted(s.get('nets') or [], key=lambda n: -(n.get('cust') or 0)),
        'trend': [{'d': x['as_of'], 'groups': (x.get('total') or {}).get('groups'),
                   'cust': (x.get('total') or {}).get('cust')} for x in _upto('qwsq', on)],
    }


# ---------------------------------------------------------------- 降级挽回
def build_downgrade(on: str | None = None) -> dict:
    """客编级资产/存款变化 → 支行 / 网点汇总；口径见 ingest/downgrade.py。"""
    s = _latest('jjwh', on)
    if not s:
        return _no_data('jjwh', on)
    branches = [dict(b) for b in (s.get('branches') or [])]
    nets = [dict(n) for n in (s.get('nets') or [])]
    totals = dict(s.get('totals') or {})
    period = s.get('period') or {}

    # 页面要用的派生：增长/下降家数、头尾
    up = sum(1 for b in branches if (b.get('asset') or 0) > 0)
    down = sum(1 for b in branches if (b.get('asset') or 0) < 0)
    by_dep = sorted(branches, key=lambda b: -(b.get('dep') or 0))
    return {
        'ok': True, 'as_of': s['as_of'], 'base_date': s.get('base_date'),
        'period': period,
        'kpi': {
            'asset': totals.get('asset'), 'dep': totals.get('dep'),
            'asset_avg': totals.get('asset_avg'), 'dep_avg': totals.get('dep_avg'),
            'score': totals.get('score'),
            'nets': totals.get('nets'), 'customers': totals.get('customers'),
            'branches': len(branches), 'up': up, 'down': down,
            'best': branches[0] if branches else None,
            'worst': branches[-1] if branches else None,
            'best_dep': by_dep[0] if by_dep else None,
            'worst_dep': by_dep[-1] if by_dep else None,
        },
        'branches': branches,
        'nets': nets,
        'top_nets': s.get('top_nets') or [],
        'customers': (s.get('customers') or [])[:300],
        'trend': [{'d': x['as_of'],
                   'asset': (x.get('totals') or {}).get('asset'),
                   'dep': (x.get('totals') or {}).get('dep')}
                  for x in _upto('jjwh', on) if x.get('totals')],
    }

def build_yika(on: str | None = None) -> dict:
    """一卡一户：支行 + 网点两层；重点给"好的"（达标/靠前）与"差的"（挂零/垫底）。"""
    s = _latest('ykh', on)
    if not s:
        return _no_data('ykh', on)
    nets = [dict(n) for n in (s.get('nets') or [])]
    branches = [dict(b) for b in (s.get('branches') or [])]
    totals = dict(s.get('totals') or {})
    period = s.get('period') or {}

    by_day = sorted(branches, key=lambda b: -(b.get('day_rate') or 0))
    by_week = sorted(branches, key=lambda b: -(b.get('week_rate') or 0))

    # 文案/页面要的三类网点
    sb_active = [n for n in nets if (n.get('sb_day') or 0) > 0]
    yl_active = [n for n in nets if (n.get('yl_day') or 0) > 0]
    reached = [n for n in nets if (n.get('day_rate') or 0) >= 1]
    both_zero = [n for n in nets if (n.get('sb_rate') or 0) <= 0 and (n.get('yl_rate') or 0) <= 0]
    # 低于 25% 的支行，**按完成率升序**（最差的在前），文案取阈值时要用 low[0]
    low_branches = sorted([b for b in by_day if (b.get('day_rate') or 0) < 0.25],
                          key=lambda b: b.get('day_rate') or 0)

    # 趋势：历次成表的两项当日开户
    trend = [{'d': x['as_of'],
              'sb': (x.get('totals') or {}).get('sb_day'),
              'yl': (x.get('totals') or {}).get('yl_day'),
              'day_rate': (x.get('totals') or {}).get('day_rate'),
              'week_rate': (x.get('totals') or {}).get('week_rate')}
             for x in _upto('ykh', on) if x.get('totals')]

    return {
        'ok': True, 'as_of': s['as_of'], 'period': period,
        'kpi': {
            'sb_day': totals.get('sb_day'), 'sb_target': totals.get('sb_target'),
            'sb_week': totals.get('sb_week'), 'sb_rate': totals.get('sb_rate'),
            'yl_day': totals.get('yl_day'), 'yl_target': totals.get('yl_target'),
            'yl_week': totals.get('yl_week'), 'yl_rate': totals.get('yl_rate'),
            'day_rate': totals.get('day_rate'), 'week_rate': totals.get('week_rate'),
            'nets': len(nets), 'branches': len(branches),
            'sb_active': len(sb_active), 'yl_active': len(yl_active),
            'reached': len(reached), 'both_zero': len(both_zero),
            'best_branch': by_day[0] if by_day else None,
            'worst_branch': by_day[-1] if by_day else None,
            'best_week': by_week[0] if by_week else None,
        },
        'branches': [dict(b, rank=i + 1) for i, b in enumerate(by_day)],
        'nets': sorted(nets, key=lambda n: (-(n.get('day_rate') or 0), -(n.get('sb_day') or 0))),
        'top_nets': reached,
        'zero_nets': both_zero,
        'low_branches': low_branches,
        'trend': trend,
    }



# ---------------------------------------------------------------- 定期承接（客编明细）
def _jiepan_snap(on: str | None = None) -> dict | None:
    return _latest('jp', on)


def build_jiepan(on: str | None = None, start: str | None = None, end: str | None = None) -> dict:
    """定期承接：网点 + 支行两层。窗口只能落在单份快照的 coverage 内。

    start/end 缺省 = 取数日往前一周（含头尾 7 天）。
    """
    from ingest import jiepan as jp

    s = _jiepan_snap(on)
    if not s:
        return _no_data('jp', on)

    cov = s.get('coverage') or [s.get('as_of'), s.get('as_of')]
    try:
        agg = jp.aggregate(s, start, end)
    except ValueError as exc:
        return {'ok': False, 'as_of': s.get('as_of'), 'coverage': cov,
                'period': {'start': start, 'end': end},
                'reason': str(exc), 'out_of_range': True}

    nets = [dict(n, short=jp.net_short(n['name'], n['branch'])) for n in agg['nets']]
    top_ids = {n['name'] for n in agg['top_nets']}
    tail_ids = {n['name'] for n in agg['tail_nets']}
    for n in nets:
        n['is_top'] = n['name'] in top_ids
        n['is_tail'] = n['name'] in tail_ids

    branches = [dict(b) for b in agg['branches']]
    t = agg['totals']

    # 趋势：历次快照在同一「周窗口」口径下的未承接金额
    trend = []
    for x in _upto('jp', on):
        try:
            a = jp.aggregate(x, None, None)
        except Exception:
            continue
        trend.append({'d': x['as_of'], 'unpicked': a['totals']['unpicked'],
                      'avg': a['totals']['avg_unpicked'], 'rate': a['totals']['rate']})

    return {
        'ok': True, 'as_of': s['as_of'], 'as_of_cn': s.get('as_of_cn'),
        'coverage': cov, 'period': agg['period'],
        'kpi': {
            'unpicked': t['unpicked'], 'avg_unpicked': t['avg_unpicked'],
            'rate': t['rate'], 'frate': t['frate'],
            'nets': t['nets'], 'branches': len(branches), 'custs': t['custs'],
            'due_amt': t['due_amt'],
            'positive': sum(1 for b in branches if b['unpicked'] > 0),
            'best_branch': branches[0] if branches else None,
            'worst_branch': branches[-1] if branches else None,
        },
        'branches': branches,
        'nets': nets,
        'top_nets': [dict(n, short=jp.net_short(n['name'], n['branch'])) for n in agg['top_nets']],
        'tail_nets': [dict(n, short=jp.net_short(n['name'], n['branch'])) for n in agg['tail_nets']],
        'trend': trend,
    }


def _pbs_snap(on: str | None = None) -> dict | None:
    """私银当期快照（partial 的基线不参与详情）。"""
    return _latest('pbs', on)


def _pbs_baseline(line: str, want: str, on: str | None) -> dict | None:
    """取「不晚于 want」的最新一期（可以是 partial）。"""
    snaps = [x for x in _snaps(line) if (x.get('as_of') or '') <= want and
             (not on or (x.get('as_of') or '') <= on)]
    return snaps[-1] if snaps else None


def build_pbs(on: str | None = None) -> dict:
    """私人银行：支行 + 网点两层。

    - 客户数 / 资产 / 存款 = 当期明细汇总
    - 比上年   = 当期 − 上年末
    - 比上季末 = 当期 − 上季度末
    - 产品销售 7 项 = 快照里合进来的手工维护值
    """
    s = _pbs_snap(on)
    if not s:
        return _no_data('pbs', on)
    snap = s.get('payload') or s
    per = snap.get('period') or {}
    as_of = s['as_of']
    year_end = per.get('year_end')
    quarter = per.get('quarter')

    ye = _pbs_baseline('pbs', year_end, on) if year_end else None
    qt = _pbs_baseline('pbs', quarter, on) if quarter else None

    def base_totals(snap_obj):
        if not snap_obj:
            return {}
        body = snap_obj.get('payload') or snap_obj
        return body.get('totals') or {}

    def base_branch(snap_obj):
        if not snap_obj:
            return {}
        body = snap_obj.get('payload') or snap_obj
        return {b['name']: b for b in (body.get('branches') or [])}

    ye_tot, qt_tot = base_totals(ye), base_totals(qt)
    ye_br, qt_br = base_branch(ye), base_branch(qt)
    sales = snap.get('sales') or {}

    branches = []
    for b in snap.get('branches') or []:
        nm = b['name']
        y = ye_br.get(nm) or {}
        q = qt_br.get(nm) or {}
        sa = sales.get(nm) or {}
        asset, dep = b['asset'] / 10000.0, b['dep'] / 10000.0
        y_asset, q_asset = (y.get('asset') or 0) / 10000.0, (q.get('asset') or 0) / 10000.0
        branches.append({
            'name': nm, 'cust': b['cust'],
            'cust_vs_year': b['cust'] - (y.get('cust') or 0) if ye_br else None,
            'cust_vs_quarter': b['cust'] - (q.get('cust') or 0) if qt_br else None,
            'cust_yoy': _pct(b['cust'] - (y.get('cust') or 0), y.get('cust') or None, 4),
            'asset': _r(asset, 2), 'dep': _r(dep, 2),
            'asset_vs_year': _r(asset - y_asset, 2) if ye_br else None,
            'asset_vs_quarter': _r(asset - q_asset, 2) if qt_br else None,
            'nets': b['nets'], 'active_nets': b['active_nets'],
            'wmp_rate': _pct(b['wmp'], b['cust'], 4), 'fund_rate': _pct(b['fund'], b['cust'], 4),
            'ins_rate': _pct(b['ins'], b['cust'], 4),
            # 产品销售（单位万元 / 户）
            'xl_bal': _r(sa.get('xl_bal'), 2), 'xl_q4': _r(sa.get('xl_q4'), 2),
            'kd_amt': _r(sa.get('kd_amt'), 2), 'xt_out': _r(sa.get('xt_out'), 2),
            'xt_sold': _r(sa.get('xt_sold'), 2), 'bx_out': _r(sa.get('bx_out'), 2),
            'bx_sold': _r(sa.get('bx_sold'), 2),
        })

    tot = snap.get('totals') or {}
    total = {
        'cust': tot.get('cust'), 'asset': _r((tot.get('asset') or 0) / 10000.0, 2),
        'dep': _r((tot.get('dep') or 0) / 10000.0, 2),
        'cust_vs_year': (tot.get('cust') - (ye_tot.get('cust') or 0)) if ye_tot else None,
        'cust_vs_quarter': (tot.get('cust') - (qt_tot.get('cust') or 0)) if qt_tot else None,
        'asset_vs_year': _r(((tot.get('asset') or 0) - (ye_tot.get('asset') or 0)) / 10000.0, 2) if ye_tot else None,
        'asset_vs_quarter': _r(((tot.get('asset') or 0) - (qt_tot.get('asset') or 0)) / 10000.0, 2) if qt_tot else None,
        'nets': tot.get('nets'), 'active_nets': tot.get('active_nets'),
        'zero_nets': [n if isinstance(n, str) else (n.get('name') or '')
                      for n in (tot.get('zero_nets') or [])],
        'xl_bal': _r(sum(b['xl_bal'] or 0 for b in branches), 2),
        'xl_q4': _r(sum(b['xl_q4'] or 0 for b in branches), 2),
        'kd_amt': _r(sum(b['kd_amt'] or 0 for b in branches), 2),
        'xt_out': _r(sum(b['xt_out'] or 0 for b in branches), 2),
        'xt_sold': _r(sum(b['xt_sold'] or 0 for b in branches), 2),
        'bx_out': _r(sum(b['bx_out'] or 0 for b in branches), 2),
        'bx_sold': _r(sum(b['bx_sold'] or 0 for b in branches), 2),
    }

    # 网点层：附上当年对比（用上年末基线同网点值）
    ye_net = {}
    if ye:
        body = ye.get('payload') or ye
        ye_net = {n['name']: n for n in (body.get('nets') or [])}
    nets = []
    for n in snap.get('nets') or []:
        y = ye_net.get(n['name']) or {}
        prev = y.get('cust')
        nets.append(dict(n,
                         asset=_r(n['asset'] / 10000.0, 2), dep=_r(n['dep'] / 10000.0, 2),
                         prev_cust=prev,
                         cust_vs_year=(n['cust'] - (prev or 0)) if ye_net else None,
                         cust_yoy=_pct((n['cust'] - (prev or 0)), prev or None, 4) if ye_net else None))

    by_cust = sorted(branches, key=lambda b: -(b['cust'] or 0))
    by_asset = sorted(branches, key=lambda b: -(b['asset'] or 0))
    by_yoy = sorted([b for b in branches if b['cust_vs_year'] is not None],
                    key=lambda b: -(b['cust_vs_year'] or 0))
    zero = [n for n in nets if not n['cust']]

    return {
        'ok': True, 'as_of': as_of, 'as_of_cn': snap.get('as_of_cn') or '',
        'period': per,
        'kpi': {
            'cust': total['cust'], 'asset': total['asset'], 'dep': total['dep'],
            'cust_vs_year': total['cust_vs_year'], 'cust_vs_quarter': total['cust_vs_quarter'],
            'asset_vs_year': total['asset_vs_year'], 'asset_vs_quarter': total['asset_vs_quarter'],
            'nets': total['nets'], 'active_nets': total['active_nets'],
            'zero_net_count': len(total['zero_nets']),
            'xl_bal': total['xl_bal'], 'xl_q4': total['xl_q4'], 'kd_amt': total['kd_amt'],
            'xt_out': total['xt_out'], 'xt_sold': total['xt_sold'],
            'bx_out': total['bx_out'], 'bx_sold': total['bx_sold'],
            'best': by_cust[0] if by_cust else None,
            'worst': by_cust[-1] if by_cust else None,
            'best_yoy': by_yoy[0] if by_yoy else None,
            'worst_yoy': by_yoy[-1] if by_yoy else None,
            'has_year_end': bool(ye), 'has_quarter': bool(qt),
        },
        'branches': [dict(b, rank=i + 1) for i, b in enumerate(by_cust)],
        'branches_by_asset': [dict(b, rank=i + 1) for i, b in enumerate(by_asset)],
        'branches_by_yoy': [dict(b, rank=i + 1) for i, b in enumerate(by_yoy)],
        'nets': sorted(nets, key=lambda n: -(n['cust'] or 0)),
        'zero_nets': zero,
        'total': total,
        'notes': snap.get('_notes') or [],
        'sales_source': snap.get('sales_source'),
    }

def build_team(on: str | None = None) -> dict:
    """经理队伍：财客 / 远维 两块（同一份快照里各占一个键）。

    每块都给三层：`branches`（8 家支行）、`nets`（财客有 40 个网点）、`mgr_rows`（客户经理）。
    金额一律**原始万元**，换算交给页面与报表（财客成表把理财换成亿元、远维不换）。
    `detail` 是整张明细（导出 Excel 的第二个子表要用），体量大，**不进 /api/all**。
    """
    s = _latest('team', on)
    if not s:
        return _no_data('team', on)

    def pack(b):
        if not b:
            return None
        return {
            'label': b.get('label'), 'short': b.get('short'), 'has_net': b.get('has_net'),
            'n': b.get('n'), 'src': b.get('src'), 'as_of': b.get('as_of'),
            'branches': b.get('branches') or [],
            'nets': b.get('nets') or [],
            'mgr_rows': b.get('mgr_rows') or [],
            'total': b.get('total') or {},
        }

    blocks = s.get('blocks') or []
    out = {'ok': True, 'as_of': s.get('as_of'), 'as_of_cn': s.get('as_of_cn'),
           'blocks': blocks, 'notes': s.get('_notes') or [],
           'ck': pack(s.get('ck')), 'yw': pack(s.get('yw'))}
    if not blocks:
        return _no_data('team', on)
    return out


BUILDERS = {'deposit': build_deposit, 'online': build_online, 'wallet': build_wallet,
            'salary': build_salary, 'community': build_community, 'payroll': build_payroll,
            'fivecards': build_fivecards, 'downgrade': build_downgrade, 'yika': build_yika,
            'pbs': build_pbs, 'jiepan': build_jiepan, 'team': build_team}
LINE_OF = {'deposit': 'dqzz', 'online': 'xsfw', 'wallet': 'sbqb',
           'salary': 'xgj', 'community': 'qwsq', 'payroll': 'dfmx', 'fivecards': 'wk',
           'downgrade': 'jjwh', 'yika': 'ykh', 'pbs': 'pbs', 'jiepan': 'jp',
           'team': 'team'}


def team_kpi(d: dict) -> dict:
    """首页卡片用：财客/远维的总分与存款增量（亿元）。"""
    out = {}
    for k in ('ck', 'yw'):
        b = d.get(k)
        if not b:
            continue
        t = b.get('total') or {}
        out[k] = {'score': _r(t.get('score'), 2),
                  'dep_inc': _r((t.get('dep_inc') or 0) / 10000.0, 2),
                  'nstock_inc': _r((t.get('nstock_inc') or 0) / 10000.0, 2),
                  'mgrs': b.get('n')}
    return out


# ---------------------------------------------------------------- 汇总
def build_overview(on: str | None = None) -> dict:
    d, o = build_deposit(on), build_online(on)
    w, s, c = build_wallet(on), build_salary(on), build_community(on)
    p, f = build_payroll(on), build_fivecards(on)
    g = build_downgrade(on)
    y = build_yika(on)
    jp = build_jiepan(on)
    tm = build_team(on)
    lines = {
        'deposit': {'ok': d.get('ok'), 'as_of': d.get('as_of'), 'prev_as_of': d.get('prev_as_of'),
                    'kpi': d.get('kpi'), 'spark': (d.get('trend') or [])[-12:]},
        'online': {'ok': o.get('ok'), 'as_of': o.get('as_of'), 'prev_as_of': o.get('prev_as_of'),
                   'kpi': o.get('kpi'), 'spark': (o.get('trend') or [])[-12:]},
        'wallet': {'ok': w.get('ok'), 'as_of': w.get('as_of'), 'kpi': w.get('kpi'),
                   'spark': (w.get('trend') or [])[-12:]},
        'salary': {'ok': s.get('ok'), 'as_of': s.get('as_of'), 'kpi': s.get('kpi'),
                   'spark': (s.get('trend') or [])[-12:]},
        'community': {'ok': c.get('ok'), 'as_of': c.get('as_of'), 'kpi': c.get('kpi'),
                      'spark': (c.get('trend') or [])[-12:]},
        'payroll': {'ok': p.get('ok'), 'as_of': p.get('as_of'), 'kpi': p.get('kpi'),
                    'nearest': p.get('nearest')},
        'fivecards': {'ok': f.get('ok'), 'as_of': f.get('as_of'), 'kpi': f.get('kpi'),
                      'nearest': f.get('nearest')},
        'downgrade': {'ok': g.get('ok'), 'as_of': g.get('as_of'), 'kpi': g.get('kpi'),
                      'nearest': g.get('nearest'), 'period': g.get('period')},
        'yika': {'ok': y.get('ok'), 'as_of': y.get('as_of'), 'kpi': y.get('kpi'),
                 'nearest': y.get('nearest'), 'period': y.get('period')},
        'jiepan': {'ok': jp.get('ok'), 'as_of': jp.get('as_of'), 'kpi': jp.get('kpi'),
                   'nearest': jp.get('nearest'), 'period': jp.get('period'),
                   'coverage': jp.get('coverage')},
        'team': {'ok': tm.get('ok'), 'as_of': tm.get('as_of'), 'kpi': team_kpi(tm),
                 'nearest': tm.get('nearest'), 'blocks': tm.get('blocks')},
    }
    return {'ok': True, 'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'as_of': on, 'lines': lines,
            'priority': ['deposit', 'online', 'wallet', 'salary', 'community']}


def build_all(on: str | None = None) -> dict:
    out = {'ok': True, 'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
           'as_of': on, 'overview': build_overview(on)}
    for k, fn in BUILDERS.items():
        try:
            out[k] = fn(on)
        except Exception as exc:
            out[k] = {'ok': False, 'error': f'{type(exc).__name__}: {exc}'}
    return out


def build_line(line: str, on: str | None = None) -> dict:
    fn = BUILDERS.get(line)
    if not fn:
        return {'ok': False, 'error': f'未知条线 {line}'}
    return fn(on)


def available_dates() -> dict:
    """各条线可选日期（供日期选择器显示范围）——只查日期列，不解 payload。"""
    return {line: store.dates(LINE_OF[line]) for line in BUILDERS}


if __name__ == '__main__':
    import json
    print(json.dumps(build_overview(), ensure_ascii=False)[:800])
