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


def _latest(line: str) -> dict | None:
    s = _snaps(line)
    return s[-1] if s else None


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
def build_deposit() -> dict:
    s = _latest('dqzz')
    if not s:
        return {'ok': False}
    br = sorted(s['branches'], key=lambda b: -(b.get('cur_bal') or 0))
    total = s['total']
    incs = [b['inc'] for b in br]
    idx = sorted(range(len(br)), key=lambda i: -incs[i])
    trend = [{'d': x['as_of'], 'bal': x['total']['cur_bal'], 'inc': x['total']['inc']}
             for x in _snaps('dqzz') if x.get('total')]
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
def build_online() -> dict:
    s = _latest('xsfw')
    if not s:
        return {'ok': False}
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
            'real_rate': _r(sum((r['add_real'] or 0) * r['add_month'] for r in rs) / add, 4) if add else None,
            'sign_rate': _r(sum((r['sign_rate'] or 0) for r in rs) / len(rs), 4),
            'kh_rate': _r(sum((r['kh_rate'] or 0) for r in rs) / len(rs), 4),
        })

    ranks = sorted(nets, key=lambda n: -(n['day_rate'] or 0))
    rates = [n['day_rate'] for n in nets]
    trend = [{'d': x['as_of'], 'day_rate': _r(sum((n['cust'] or 0) * (n['day_rate'] or 0)
                                                  for n in x.get('nets') or [])
                                              / max(1, sum(n['cust'] or 0 for n in x.get('nets') or [])), 4)}
             for x in _snaps('xsfw') if x.get('nets')]
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
            'sign_rate': _r(sum((n['sign_rate'] or 0) for n in nets) / max(1, len(nets)), 4),
            'kh_rate': _r(sum((n['kh_rate'] or 0) for n in nets) / max(1, len(nets)), 4),
            'real_rate': _r(sum((n['add_real'] or 0) * n['add_month'] for n in nets)
                            / max(1, sum(n['add_month'] for n in nets)), 4),
        },
        'branches': branches,
        'hist': _hist(rates, 6),
        'scatter': [{'name': n['label'], 'branch': n['branch'], 'x': _r((n['day_rate'] or 0) * 100, 2),
                     'y': _r((n['sign_rate'] or 0) * 100, 2), 'size': n['cust'],
                     'month_rate': _r((n['month_rate'] or 0) * 100, 2),
                     'add_month': n['add_month']} for n in nets],
        'trend': trend,
        'nets': [{'name': n['label'], 'branch': n['branch'],
                  'day_rate': _r((n['day_rate'] or 0) * 100, 2),
                  'month_rate': _r((n['month_rate'] or 0) * 100, 2),
                  'cust': n['cust'], 'cust_delta': n.get('cust_delta'),
                  'add_today': n['add_today'], 'add_month': n['add_month'],
                  'real_rate': _r((n['add_real'] or 0) * 100, 2),
                  'sign_rate': _r((n['sign_rate'] or 0) * 100, 2),
                  'kh_rate': _r((n['kh_rate'] or 0) * 100, 2)} for n in ranks],
    }


# ---------------------------------------------------------------- 数币钱包
def build_wallet() -> dict:
    s = _latest('sbqb')
    if not s:
        return {'ok': False}
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
    trend = [{'d': x['as_of'], 'total': x.get('total')} for x in _snaps('sbqb') if x.get('total')]
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
def build_salary() -> dict:
    s = _latest('xgj')
    if not s:
        return {'ok': False}
    br = s.get('branches') or []
    nets = s.get('nets') or []
    trend = [{'d': x['as_of'], 'year': x.get('total'), 'month': x.get('month_total'),
              'ents': x.get('ent_year')} for x in _snaps('xgj') if x.get('total') is not None]
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
def build_community() -> dict:
    s = _latest('qwsq')
    if not s:
        return {'ok': False}
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
                   'cust': (x.get('total') or {}).get('cust')} for x in _snaps('qwsq')],
    }


BUILDERS = {'deposit': build_deposit, 'online': build_online, 'wallet': build_wallet,
            'salary': build_salary, 'community': build_community}


# ---------------------------------------------------------------- 汇总
def build_overview() -> dict:
    d, o = build_deposit(), build_online()
    w, s, c = build_wallet(), build_salary(), build_community()
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
    }
    return {'ok': True, 'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'lines': lines,
            'priority': ['deposit', 'online', 'wallet', 'salary', 'community']}


def build_all() -> dict:
    out = {'ok': True, 'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
           'overview': build_overview()}
    for k, fn in BUILDERS.items():
        try:
            out[k] = fn()
        except Exception as exc:
            out[k] = {'ok': False, 'error': f'{type(exc).__name__}: {exc}'}
    return out


def build_line(line: str) -> dict:
    fn = BUILDERS.get(line)
    if not fn:
        return {'ok': False, 'error': f'未知条线 {line}'}
    return fn()


if __name__ == '__main__':
    import json
    print(json.dumps(build_overview(), ensure_ascii=False)[:800])
