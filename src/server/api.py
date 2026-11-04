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
from pathlib import Path
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


def _jiepan_snap(on: str | None = None, snap: str | None = None) -> dict | None:
    """定期承接用哪一期快照。

    snap 显式指定 `as_of`（页面上"数据期"下拉框选的那个）优先；
    否则退回旧行为：取"不晚于 on"的最新一期。
    显式指定是为了防止**顶栏日期比最新一期早**时静默退回旧快照 ——
    旧的 coverage 到不了新日期，用户就会看到"这个时间段出不了通报"。
    """
    if snap:
        for x in _snaps('jp'):
            if (x.get('as_of') or '') == snap:
                return x
        return None
    return _latest('jp', on)


def jiepan_periods(on: str | None = None) -> list[dict]:
    """可选的数据期（给页面上的"数据期"下拉框）。"""
    out = []
    for x in _snaps('jp'):
        if x.get('partial'):
            continue
        out.append({
            'as_of': x.get('as_of'),
            'as_of_cn': x.get('as_of_cn'),
            'coverage': x.get('coverage') or [x.get('as_of'), x.get('as_of')],
            'days': x.get('days'),
            'rows': len(x.get('rows') or []),
            'edited': x.get('edited') or 0,
        })
    return out


def build_jiepan(on: str | None = None, start: str | None = None, end: str | None = None,
                 snap: str | None = None) -> dict:
    """定期承接：网点 + 支行两层。窗口只能落在单份快照的 coverage 内。

    start/end 缺省 = 取数日往前一周（含头尾 7 天）。
    snap      = 用哪一期（缺省取不晚于 on 的最新一期）
    """
    from ingest import jiepan as jp

    s = _jiepan_snap(on, snap)
    if not s:
        d = _no_data('jp', on)
        d['periods'] = jiepan_periods(on)
        return d

    cov = s.get('coverage') or [s.get('as_of'), s.get('as_of')]
    try:
        agg = jp.aggregate(s, start, end)
    except ValueError as exc:
        return {'ok': False, 'as_of': s.get('as_of'), 'coverage': cov,
                'period': {'start': start, 'end': end},
                'periods': jiepan_periods(on),
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
        'periods': jiepan_periods(on),
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



JBL_LINES = {'lc': 'jbl_lc', 'fund': 'jbl_fund', 'bx': 'jbl_bx'}
# 基保理三条产品线都归到同一个视图 key `jbl`（页面用 `?k=` 切换）。
# catalog 里模块只挂 `jbl_lc`，另两条线靠这张表让前端能认出「数据截至」。
JBL_LINE_KEYS = {'jbl_lc': 'jbl', 'jbl_fund': 'jbl', 'jbl_bx': 'jbl'}
JBL_LABEL = {'lc': '理财', 'fund': '基金', 'bx': '保险'}


def _jbl_one(key: str, on: str | None) -> dict | None:
    """单条产品线（理财/基金/保险）的一期。三条线各存各的快照。"""
    line = JBL_LINES[key]
    s = _latest(line, on)
    if not s:
        return None

    period = s.get('period')
    periods = s.get('periods') or []
    branches = s.get('branches') or []
    nets = s.get('nets') or []

    brs = []
    for i, b in enumerate(branches):
        rec = dict(b)
        rec['rank'] = i + 1
        m = {str(k): v for k, v in (b.get('metric') or {}).items()}
        # 本期也塞进 metric：前端可以统一「按期号取列」，不用为当期单开一列
        if period is not None and b.get('current') is not None:
            m[str(period)] = b['current']
        rec['metric'] = m
        brs.append(rec)

    nets_out = []
    for i, n in enumerate(nets):
        rec = dict(n)
        rec['rank'] = i + 1
        rec['short'] = str(n.get('name') or '').replace('阜阳', '')
        m = {str(k): v for k, v in (n.get('metric') or {}).items()}
        if period is not None and n.get('current') is not None:
            m[str(period)] = n['current']
        rec['metric'] = m
        nets_out.append(rec)

    # 本期销量：优先源表「合计」行（成表口径），缺了才自己加
    cur = (s.get('period_totals') or {}).get(str(period)) if period is not None else None
    if cur is None:
        cur = sum((b.get('current') or 0) for b in branches)
    total_col = s.get('branch_total_row')
    if total_col is None:
        total_col = sum((b.get('total') or 0) for b in branches)
    target = sum((b.get('target') or 0) for b in branches)
    fund = sum((b.get('fund') or 0) for b in branches)

    # 趋势：把所有快照的「按期合计」合并。相邻两次导入的期数会重叠
    # （这次 39/40/41，下次 41/42/43），同一期以**更晚导入**的为准 ——
    # _upto 已按 as_of 升序，直接覆盖写即可。
    tmap = {}
    for x in _upto(line, on):
        for k, v in (x.get('period_totals') or {}).items():
            try:
                pi = int(k)
            except (TypeError, ValueError):
                continue
            if v is None:
                continue
            tmap[pi] = {'period': pi, 'value': _r(v, 4), 'as_of': x.get('as_of')}
    trend = [tmap[k] for k in sorted(tmap)]

    # 支行历史：支行 → 各期销量（画"各支行按期"对比用）
    bh = {}
    for x in _upto(line, on):
        for b in x.get('branches') or []:
            m = bh.setdefault(b['name'], {})
            for k, v in (b.get('metric') or {}).items():
                if v is not None:
                    m[str(k)] = v
            if x.get('period') is not None and b.get('current') is not None:
                m[str(x['period'])] = b['current']

    ranked = sorted(brs, key=lambda b: -(b.get('current') or 0))
    hit = [b for b in brs if (b.get('current') or 0) > 0]
    return {
        'key': key, 'label': JBL_LABEL[key], 'line': line,
        'ok': True, 'as_of': s.get('as_of'), 'as_of_cn': s.get('as_of_cn'),
        'title': s.get('title'),
        'period': period, 'periods': periods,
        'kpi': {
            'current': _r(cur, 2), 'target': _r(target, 2),
            'rate': _r((cur / target) if target else None, 6),
            'total': _r(total_col, 2), 'fund': _r(fund, 2),
            'period': period, 'branches': len(brs), 'nets': len(nets_out),
            'hit': len(hit),
            'best': ranked[0] if ranked else None,
            'worst': ranked[-1] if ranked else None,
        },
        'branches': brs,
        'nets': nets_out,
        'trend': trend,
        'branch_hist': [{'name': k, 'metric': v} for k, v in bh.items()],
        'has': {'branches': bool(brs), 'nets': bool(nets_out)},
        'notes': s.get('_notes') or [],
    }


def build_jbl(on: str | None = None) -> dict:
    """基保理：理财 / 基金 / 保险 三条产品线，各自「支行 + 网点」两层。

    数据口径（用户拍板）：**源表就是成表，原样取，不重算、不校验修正**。
    三条线互不覆盖：`jbl_lc` / `jbl_fund` / `jbl_bx`，可以只导其中一条。
    """
    body = {}
    for key in JBL_LINES:
        try:
            body[key] = _jbl_one(key, on)
        except Exception as exc:                # 单条线出错不该拖垮整页
            body[key] = {'ok': False, 'key': key, 'label': JBL_LABEL[key],
                         'error': f'{type(exc).__name__}: {exc}'}
    got = [k for k in JBL_LINES if body.get(k) and body[k].get('ok')]
    if not got:
        d = _no_data('jbl_lc', on)
        d['kinds'] = []                        # 必须是数组：前端直接 filter
        d['labels'] = {k: JBL_LABEL[k] for k in JBL_LINES}
        return d
    first = body[got[0]]
    return {'ok': True, 'as_of': first.get('as_of'), 'as_of_cn': first.get('as_of_cn'),
            'kinds': got, 'labels': {k: JBL_LABEL[k] for k in JBL_LINES},
            'lc': body.get('lc'), 'fund': body.get('fund'), 'bx': body.get('bx')}


def jbl_kpi(d: dict) -> dict:
    """首页 / 个金总览卡用：各产品线的本期销量与达成率。"""
    if not d.get('ok'):
        return {}
    out = {}
    for k in (d.get('kinds') or []):
        b = d.get(k) or {}
        kk = b.get('kpi') or {}
        out[k] = {'current': kk.get('current'), 'rate': kk.get('rate'),
                  'period': kk.get('period'), 'hit': kk.get('hit'),
                  'as_of': b.get('as_of')}
    return out


def build_scene(on: str | None = None) -> dict:
    """全量客户场景攻坚：6 个场景 × 8 家支行，每格「已落地 / 推进中」的项目文字。

    源表本身就是成表的形态（没有数值指标），所以这一层基本是原样透传 +
    派生几个汇总数字（KPI、每个场景的覆盖支行数）。

    **`changed`（标红→标黄）是本期唯一要强调的东西**：前端据此给条目加黄底。
    """
    s = _latest('scene', on)
    if not s:
        return _no_data('scene', on)

    branches = s.get('branches') or []
    scenes = s.get('scenes') or []
    total = s.get('total') or {}

    # 每个场景：覆盖了哪些支行（有落地的），以及各支行的进度
    order = s.get('branch_order') or BRANCHES
    scene_cards = []
    for sc in scenes:
        name = sc.get('name')
        covered = [b['name'] for b in branches
                   if ((b.get('scenes') or {}).get(name) or {}).get('landed')]
        pending = [b['name'] for b in branches
                   if not ((b.get('scenes') or {}).get(name) or {}).get('landed')]
        scene_cards.append({
            'name': name,
            'landed': sc.get('landed') or 0,
            'ongoing': sc.get('ongoing') or 0,
            'branches': sc.get('branches') or 0,
            'changed': sc.get('changed') or 0,
            'covered': covered,
            'pending': pending,
            'rate': _r((len(covered) / len(order)) if order else None, 4),
        })

    # 支行矩阵：每行一家支行，每列一个场景（已落地/推进中合并成条目列表，便于画表）
    matrix = []
    for b in branches:
        rec = {'name': b['name'], 'scenes': {}, 'landed': 0, 'ongoing': 0, 'changed': 0}
        for sc in scenes:
            cell = (b.get('scenes') or {}).get(sc['name']) or {'landed': [], 'ongoing': []}
            rec['scenes'][sc['name']] = {
                'landed': cell.get('landed') or [],
                'ongoing': cell.get('ongoing') or [],
            }
            rec['landed'] += len(cell.get('landed') or [])
            rec['ongoing'] += len(cell.get('ongoing') or [])
            rec['changed'] += sum(1 for x in (cell.get('landed') or []) + (cell.get('ongoing') or [])
                                  if x.get('changed'))
        matrix.append(rec)
    matrix.sort(key=lambda r: (-(r['landed']), -(r['ongoing'])))

    # 本期有变化的条目（做成一条"本期变化"清单，简报里最好用）
    highlights = []
    for b in branches:
        for sc in scenes:
            cell = (b.get('scenes') or {}).get(sc['name']) or {}
            for state, key in (('已落地', 'landed'), ('推进中', 'ongoing')):
                for it in (cell.get(key) or []):
                    if it.get('changed'):
                        highlights.append({'branch': b['name'], 'scene': sc['name'],
                                           'state': state, 'text': it.get('text')})

    kpi = {
        'scenes': total.get('scenes') or len(scenes),
        'landed': total.get('landed') or 0,
        'ongoing': total.get('ongoing') or 0,
        'branches': total.get('branches') or 0,
        'changed': total.get('changed') or 0,
    }
    return {
        'ok': True,
        'as_of': s.get('as_of'), 'as_of_cn': s.get('as_of_cn'),
        'kpi': kpi,
        'scenes': scene_cards,
        'branches': matrix,
        'branch_order': order,
        'highlights': highlights,
        'notes': s.get('_notes') or [],
    }


def scene_kpi(d: dict) -> dict:
    """首页 / 总览卡片用：四个数字。"""
    if not d.get('ok'):
        return {}
    return d.get('kpi') or {}


BUILDERS = {'deposit': build_deposit, 'online': build_online, 'wallet': build_wallet,
            'salary': build_salary, 'community': build_community, 'payroll': build_payroll,
            'fivecards': build_fivecards, 'downgrade': build_downgrade, 'yika': build_yika,
            'pbs': build_pbs, 'jiepan': build_jiepan, 'team': build_team,
            'jbl': build_jbl, 'scene': build_scene}
LINE_OF = {'deposit': 'dqzz', 'online': 'xsfw', 'wallet': 'sbqb',
           'salary': 'xgj', 'community': 'qwsq', 'payroll': 'dfmx', 'fivecards': 'wk',
           'downgrade': 'jjwh', 'yika': 'ykh', 'pbs': 'pbs', 'jiepan': 'jp',
           'team': 'team', 'jbl': 'jbl_lc', 'scene': 'scene'}


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
    jb = build_jbl(on)
    sc = build_scene(on)
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
        'jbl': {'ok': jb.get('ok'), 'as_of': jb.get('as_of'), 'kpi': jbl_kpi(jb),
                'nearest': jb.get('nearest'), 'period': jb.get('period'),
                'kind': jb.get('kind')},
        'scene': {'ok': sc.get('ok'), 'as_of': sc.get('as_of'), 'kpi': scene_kpi(sc),
                  'nearest': sc.get('nearest')},
    }
    return {'ok': True, 'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'as_of': on, 'lines': lines,
            'priority': ['deposit', 'online', 'wallet', 'salary', 'community']}


# ---------------------------------------------------------------- 数据管理（管理员）
# 界面上只列"用户看得懂"的条线；qwsq_day / ykh_sb / ykh_yl 是内部线，
# 单独列在"原始数据"下面（删了会影响后续拼装，要警告）。
INTERNAL_LINES = {
    'qwsq_day': '企微社群 · 按日原始数据',
    'ykh_sb': '一卡一户 · 社保卡按日原始',
    'ykh_yl': '一卡一户 · 养老金按日原始',
}


def _delete_warning(line: str, as_of: str) -> dict | None:
    """删掉这一期会不会影响别的期？返回警告（没有就 None）。"""
    if line == 'qwsq_day':
        later = [d for d in store.dates('qwsq') if d > as_of]
        if later:
            return {'level': 'warn',
                    'text': f'{len(later)} 个企微当期（{later[0]} 起）把它当"上周"用；'
                            '删掉后已生成的期不会变，但重新导入时会找不到对比基准。'}
    if line in ('ykh_sb', 'ykh_yl'):
        return {'level': 'warn',
                'text': '一卡一户当期靠"当日/前一日/上周末"三个时点拼出来，'
                        '删掉这个日期后重新导入可能因缺时点失败。'}
    if line == 'pbs':
        return {'level': 'info',
                'text': '私人银行的基线（上年末/上季度末）也以快照保存；'
                        '删当期不影响基线，删基线会让"比上年"变空。'}
    return None


# 数据管理页的条线顺序：先日常主用的，再内部原料
_ADMIN_ORDER = {k: i for i, k in enumerate([
    'dqzz', 'jp', 'jjwh', 'team', 'xgj', 'ykh', 'dfmx', 'wk', 'scene',
    'xsfw', 'sbqb', 'qwsq', 'pbs', 'jbl_lc', 'jbl_fund', 'jbl_bx',
    'qwsq_day', 'ykh_sb', 'ykh_yl'])}
_ADMIN_GROUP = {
    'dqzz': '个人金融', 'jp': '个人金融', 'jjwh': '个人金融', 'team': '个人金融',
    'xgj': '个人金融', 'ykh': '个人金融', 'dfmx': '个人金融', 'wk': '个人金融',
    'scene': '个人金融', 'jbl_lc': '个人金融', 'jbl_fund': '个人金融', 'jbl_bx': '个人金融',
    'xsfw': '网络金融', 'sbqb': '网络金融', 'qwsq': '网络金融',
    'pbs': '私人银行',
}


def _group_of(line: str) -> str:
    return _ADMIN_GROUP.get(line, '')


def admin_lines() -> dict:
    """数据管理页的「模块 → 期」清单（只读，含已删）。

    一期一条，带 `batches`（这笔数据被导入过几次）/`files`（留档原件数），
    这样在列表上就能看出"这期来过几次"，点开某一期再看它的导入批次与原件。
    """
    stats = {r['line']: r for r in store.line_stats()}
    periods = store.snapshot_periods()
    idx = store.batch_index()
    for line, rows in periods.items():
        for p in rows:
            extra = idx.get((line, p['as_of'])) or {}
            p['batches'] = extra.get('batches', 0)
            p['files'] = extra.get('files', 0)
    rows = []
    for line, meta in viz.LINES.items():
        s = stats.get(line) or {}
        # 一条数据都没有、也没删过记录的线（比如基保理还没接的基金/保险）不列
        if not int(s.get('count') or 0) and not store.deleted_dates(line):
            continue
        rows.append({'line': line, 'label': meta.get('label', line), 'hint': meta.get('hint'),
                     'internal': False, 'group': _group_of(line),
                     'count': int(s.get('count') or 0), 'latest': s.get('as_of'),
                     'dates': store.dates(line), 'deleted': store.deleted_dates(line),
                     'periods': periods.get(line, [])})
    for line, label in INTERNAL_LINES.items():
        if line not in periods and not store.deleted_dates(line):
            continue
        s = stats.get(line) or {}
        rows.append({'line': line, 'label': label,
                     'hint': '内部线：界面上看不到，删了会影响后续拼装',
                     'internal': True, 'group': '原始数据',
                     'count': int(s.get('count') or 0), 'latest': s.get('as_of'),
                     'dates': store.dates(line), 'deleted': store.deleted_dates(line),
                     'periods': periods.get(line, [])})
    rows.sort(key=lambda r: (r['internal'], _ADMIN_ORDER.get(r['line'], 99), r['line']))
    return {'ok': True, 'lines': rows, 'db': store.stats()}


def _resolve_file(path: str | None):
    """台账里的一行文件 → 本机真实路径；越界（数据目录外）一律不认。"""
    if not path:
        return None
    base = store.root().resolve()
    p = Path(path)
    cands = [p] if p.is_absolute() else [base / p]
    norm = str(path).replace('\\', '/')
    i = norm.find('imports/')
    if i > 0:
        cands.append(base / norm[i:])
    for c in cands:
        try:
            real = c.resolve()
        except Exception:
            continue
        if real.is_file() and (base == real or base in real.parents):
            return real
    return None


_HASH_CAP = 32 * 1048576        # 超过这个大小不算指纹，退化成"文件名 + 字节数"


def _sha_of(f: dict) -> str | None:
    """原件的指纹：台账里没有就现算一次（源表普遍几百 KB，算一次几毫秒）。

    早期导入没往 `source_file` 写 sha256，盘上那份是"无名氏"，
    不算指纹就会和同名同大小的另一份混成一行 —— 而文件名相同的两份表
    内容可能真的不一样（私银的上月末/上季末表就是这样）。
    """
    if f.get('sha256'):
        return f['sha256']
    p = _resolve_file(f.get('path'))
    if p is None:
        return None
    try:
        if p.stat().st_size > _HASH_CAP:
            return None
        import hashlib
        h = hashlib.sha256()
        with p.open('rb') as fh:
            for chunk in iter(lambda: fh.read(1 << 16), b''):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _group_files(rows: list[dict], line: str) -> list[dict]:
    """同一期的原件按「文件名 + 内容指纹」合并，其余折成 `times`。

    这一期可能被导入过 20 多次，每次都留一份同样的表；逐条列出来没人看得下去。
    合并后「这一期用过哪些文件、各是什么时候留的」一眼能看清。

    指纹缺失时**现算**（`_sha_of`），不能拿"文件名 + 大小"凑合：
    同名同大小但内容不同的表确实存在，凑合会把它们错并成一行。
    """
    out: list[dict] = []
    by_key: dict[tuple, dict] = {}
    for f in rows:
        sha = _sha_of(f)
        key = (f.get('name'), sha or f'nosha:{f.get("bytes")}')
        hit = by_key.get(key)
        if hit is not None:
            hit['times'] += 1
            hit['stamps'].append(f.get('created_at'))
            if not hit.get('sha256') and sha:
                hit['sha256'] = sha
            # 有 id 的（进了 source_file 台账）优先，前端据此走 /api/source/<id>
            if hit.get('id') is None and f.get('id') is not None:
                hit['id'] = f['id']
                hit['path'] = f['path']
            continue
        g = dict(f)
        g['sha256'] = sha
        g['times'] = 1
        g['stamps'] = [f.get('created_at')]
        by_key[key] = g
        out.append(g)
    for g in out:
        g['exists'] = _resolve_file(g.get('path')) is not None
        g['stamps'] = [s for s in g['stamps'] if s][:8]
    # 同名不同内容（私银的上月末/上季末表就叫一个名字）：标出来，不然看着像重复行
    seen: dict[str, int] = {}
    for g in out:
        seen[g.get('name') or ''] = seen.get(g.get('name') or '', 0) + 1
    for g in out:
        g['dup'] = seen.get(g.get('name') or '', 0) > 1
    out.sort(key=lambda g: (g.get('created_at') or '', g.get('name') or ''), reverse=True)
    return out


def admin_period(line: str, as_of: str) -> dict:
    """某一期的详情：来源（导入批次）+ 留档原件 + 前后期。

    「这期是哪次导入算的、用的是哪几个文件、文件还在不在」一次说清；
    原件可下载、可预览（`/api/source/<id>` 与 `/api/source/<id>/preview`）。
    """
    row = store.snapshot_rows(line, as_of)
    if not row:
        return {'ok': False, 'error': f'库里没有 {line} {as_of} 这一期'}
    sid = int(row['id'])
    batches = store.snapshot_batches(line, as_of, sid)
    files = store.snapshot_sources(sid)

    # 早期导入没写 source_file：把台账归档目录里认得出的文件也补上（只列，不进库）
    loose, seen = [], {f.get('path') for f in files}
    for b in batches:
        d = store.resolve_archive(line, b.get('archive'))
        if not d:
            continue
        for p in store.archive_files(d):
            rel = store.rel_path(p)
            if rel in seen:
                continue
            seen.add(rel)
            loose.append({'id': None, 'name': p.name, 'bytes': p.stat().st_size,
                          'sha256': None, 'path': rel, 'archive': store.rel_path(d),
                          'created_at': (b.get('ts') or '').replace(' ', 'T'),
                          'from_batch': b.get('id')})

    merged = _group_files(files + loose, line)
    label = (viz.LINES.get(line) or {}).get('label') or INTERNAL_LINES.get(line, line)
    others = store.dates(line)
    missing = [g['name'] for g in merged if not g['exists']]
    return {'ok': True, 'line': line, 'label': label, 'as_of': as_of,
            'internal': line in INTERNAL_LINES, 'group': _group_of(line),
            'snapshot': row, 'batches': batches, 'files': merged,
            'file_count': len(merged), 'occurrences': sum(g['times'] for g in merged),
            'missing': missing, 'warning': _delete_warning(line, as_of),
            'prev': ([d for d in others if d < as_of] or [None])[-1],
            'next': ([d for d in others if d > as_of] or [None])[0],
            'deleted_others': [d['as_of'] for d in store.deleted_dates(line)]}


def source_download(file_id: int) -> dict:
    """下载/预览一个原件（按 `source_file.id`）。"""
    row = store.source_file(int(file_id))
    if not row:
        return {'ok': False, 'error': '没有这个原件记录'}
    p = _resolve_file(row.get('path'))
    if p is None:
        return {'ok': False, 'error': f'文件已不在磁盘上：{row.get("path")}',
                'name': row.get('name'), 'path': row.get('path')}
    return {'ok': True, 'path': str(p), 'name': row.get('name') or p.name,
            'bytes': p.stat().st_size, 'row': row}


def source_by_path(path: str, name: str | None = None) -> dict:
    """没登记进 `source_file` 的老原件：按台账里的路径直接找。

    返回里带 `line`（从 `imports/<line>/<stamp>/` 反推），供调用方做权限判断 ——
    否则这条路会绕过「按条线授权」。
    """
    p = _resolve_file(path)
    if p is None:
        return {'ok': False, 'error': f'文件已不在磁盘上：{path}'}
    norm = str(path).replace('\\', '/')
    i = norm.find('imports/')
    line = None
    if i >= 0:
        parts = norm[i:].split('/')
        if len(parts) >= 3:
            line = parts[1]
    return {'ok': True, 'path': str(p), 'name': name or p.name,
            'bytes': p.stat().st_size, 'row': {'line': line} if line else None,
            'line': line}


def import_files(log_id: int) -> dict:
    """某一次导入留档了哪些原件（导入页「最近导入」点开看）。

    先看 `source_file` 按归档目录登记过的，再补归档目录里剩下的文件 ——
    早期导入没写 `source_file`，光查台账会显示"没有文件"。
    """
    rec = store.import_row(log_id)
    if not rec:
        return {'ok': False, 'error': '没有这条导入记录'}
    line = rec.get('line')
    d = store.resolve_archive(line, rec.get('archive'))

    rows = [dict(r) for r in store.connect().execute(
        'SELECT id, name, sha256, bytes, path, archive, created_at FROM source_file'
        ' WHERE archive=? ORDER BY id', (rec.get('archive'),))] if rec.get('archive') else []
    seen = {r['path'] for r in rows}
    loose = []
    if d is not None:
        for p in store.archive_files(d):
            rel = store.rel_path(p)
            if rel in seen:
                continue
            seen.add(rel)
            loose.append({'id': None, 'name': p.name, 'sha256': None,
                          'bytes': p.stat().st_size, 'path': rel,
                          'archive': store.rel_path(d), 'created_at': rec.get('ts')})
    merged = _group_files(rows + loose, line or '')
    return {'ok': True, 'id': rec['id'], 'line': line,
            'label': (viz.LINES.get(line) or {}).get('label') or INTERNAL_LINES.get(line, line),
            'ts': rec.get('ts'), 'data_date': rec.get('data_date'), 'ok': bool(rec.get('ok')),
            'error': rec.get('error'), 'archive': store.rel_path(d) if d else rec.get('archive'),
            'archive_exists': d is not None,
            'files': merged, 'file_count': len(merged),
            'missing': [g['name'] for g in merged if not g['exists']]}


def _backup_before(label: str, line: str, as_of: str) -> tuple[object | None, str | None]:
    """改动前热备份；失败返回 (None, 错误说明)，调用方据此中止。"""
    bak_dir = store.root() / 'backups'
    try:
        bak_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        bak = bak_dir / f'before-{label}-{line}-{as_of}-{stamp}.db'
        store.backup_to(bak)
        return bak, None
    except Exception as exc:
        return None, str(exc)


def admin_delete(line: str, as_of: str) -> dict:
    """软删除某条线的某一期：先热备份，再标记 deleted_at。"""
    if line not in viz.LINES and line not in INTERNAL_LINES:
        return {'ok': False, 'error': f'未知条线：{line}'}
    row = store.snapshot_rows(line, as_of)
    if not row:
        return {'ok': False, 'error': f'库里没有 {line} {as_of} 这一期'}
    if row.get('deleted_at'):
        return {'ok': False, 'error': '这一期已经是删除状态'}

    # 删之前热备份（软删除本身可恢复，备份是最后一道保险）
    bak, err = _backup_before('delete', line, as_of)
    if err:
        return {'ok': False, 'error': f'删除前备份失败，已中止：{err}'}

    warn = _delete_warning(line, as_of)
    if not store.soft_delete(line, as_of):
        return {'ok': False, 'error': '删除失败（可能已被别处改过）'}
    return {'ok': True, 'line': line, 'as_of': as_of, 'backup': str(bak),
            'warning': warn, 'label': (viz.LINES.get(line) or {}).get('label', line)}


def admin_restore(line: str, as_of: str) -> dict:
    if not store.restore_snapshot(line, as_of):
        return {'ok': False, 'error': '这一期不是在删除状态'}
    return {'ok': True, 'line': line, 'as_of': as_of}


def admin_purge(line: str, as_of: str, confirm: str | None = None) -> dict:
    """【彻底删除】把这一期从库里真的抹掉 —— 不可恢复。

    两道闸：
      1. 只允许删**已经在软删除状态**的期（先"删除"再"彻底删除"，
         逼着操作的人分两步走，不会一键点没）；
      2. 必须把数据日期原样打字确认（`confirm` 要等于 `as_of`）。
    删之前照样热备份；`source_file` 的行由外键置空、磁盘上的原件**不动**
    （"这期算错了"和"这台机器上有没有这个文件"是两件事）。
    """
    if line not in viz.LINES and line not in INTERNAL_LINES:
        return {'ok': False, 'error': f'未知条线：{line}'}
    row = store.snapshot_rows(line, as_of)
    if not row:
        return {'ok': False, 'error': f'库里没有 {line} {as_of} 这一期'}
    if not row.get('deleted_at'):
        return {'ok': False, 'error': '要先把这一期「删除」，确认没影响到别处，再来彻底删除',
                'need_soft_delete': True}
    if (confirm or '').strip() != as_of:
        return {'ok': False, 'error': f'确认日期不对：请原样输入 {as_of}', 'need_confirm': True}

    bak, err = _backup_before('purge', line, as_of)
    if err:
        return {'ok': False, 'error': f'彻底删除前备份失败，已中止：{err}'}
    n_files = len(store.snapshot_sources(int(row['id'])))
    if not store.purge_snapshot(line, as_of):
        return {'ok': False, 'error': '彻底删除失败（可能已被别处改过）'}
    return {'ok': True, 'line': line, 'as_of': as_of, 'backup': str(bak),
            'files_kept': n_files,
            'label': (viz.LINES.get(line) or {}).get('label', line)}



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


def line_key_map() -> dict:
    """真实条线 → 视图 key。`line_keys`（前端认「数据截至」用）以它为底。"""
    out = {line: key for key, line in LINE_OF.items()}
    out.update(JBL_LINE_KEYS)
    return out


def available_dates() -> dict:
    """各条线可选日期（供日期选择器显示范围）——只查日期列，不解 payload。"""
    return {line: store.dates(LINE_OF[line]) for line in BUILDERS}


if __name__ == '__main__':
    import json
    print(json.dumps(build_overview(), ensure_ascii=False)[:800])
