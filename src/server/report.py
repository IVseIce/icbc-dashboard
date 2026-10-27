#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""report.py —— 通报中心的数据与导出。

目前实现：网点线上服务能力（表格 + 文案 + Excel）。
文案结构照现有定稿：总述 → 到店动户率 → 企微添客 → 营销授权。
"""
from __future__ import annotations

import io
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import api  # noqa: E402
import viz  # noqa: E402

BRANCH_ORDER = ['颍州', '颍泉', '颍东', '界首', '临泉', '阜南', '颍上', '太和']

COLS = [
    ('网点', 'name', 'text', 22),
    ('到店当日手机银行动户率', 'day_rate', 'pct', 13),
    ('到店当月手机银行动户率', 'month_rate', 'pct', 12),
    ('企微添客总数', 'cust', 'int', 11),
    ('企微添客实名率', 'real_rate', 'pct', 11),
    ('当日添客', 'add_today', 'int', 9),
    ('当月添客', 'add_month', 'int', 9),
    ('营销授权客户数', 'auth_cust', 'int', 11),
    ('累计签约数', 'auth_signed', 'int', 10),
    ('签约率', 'sign_rate', 'pct', 9),
    ('管户数', 'kh', 'int', 9),
    ('管户签约数', 'kh_signed', 'int', 10),
    ('管户签约率', 'kh_rate', 'pct', 11),
]


def _short(name: str) -> str:
    return (name or '').replace('阜阳', '').replace('支行营业室', '营业室')


def build_online(on: str | None = None) -> dict:
    d = api.build_online(on)
    if not d.get('ok'):
        return {'ok': False, 'error': d.get('reason') or '该日期无线上服务数据',
                'nearest': d.get('nearest')}
    # 直接用快照里的原始比率（6 位小数），避免 api 层为展示做的取整
    snap = api._latest('xsfw', on)
    nets = (snap or {}).get('nets') or []
    for n in nets:
        n['name'] = n.get('label') or n.get('name') or ''
        n['real_rate'] = n.get('add_real')

    order = {b: i for i, b in enumerate(BRANCH_ORDER)}
    rows = sorted(nets, key=lambda n: (order.get(n['branch'], 99), -(n.get('day_rate') or 0)))
    tot = (snap or {}).get('tot') or d.get('kpi') or {}
    annotate(rows)
    table = {
        'name': '网点明细',
        'columns': [{'key': k, 'title': t, 'type': ty, 'width': w} for t, k, ty, w in COLS],
        'rows': rows,
        'totals': {
            'name': '合计', 'day_rate': tot.get('day_rate'), 'month_rate': tot.get('month_rate'),
            'cust': tot.get('cust'), 'real_rate': tot.get('real_rate'),
            'add_today': tot.get('add_today'), 'add_month': tot.get('add_month'),
            'sign_rate': tot.get('sign_rate'), 'kh_rate': tot.get('kh_rate'),
            'auth_cust': tot.get('auth_cust'), 'auth_signed': tot.get('auth_signed'),
            'kh': tot.get('kh'), 'kh_signed': tot.get('kh_signed'),
        },
    }
    return {
        'ok': True, 'kind': 'online',
        'title': f'阜阳分行“网点线上服务能力”提升通报（{d["as_of"][5:].replace("-", ".")}）',
        'as_of': d['as_of'], 'prev_as_of': d.get('prev_as_of'),
        'tables': [table], 'text': build_text(d, rows),
    }


RATE_KEYS = ('day_rate', 'month_rate', 'real_rate', 'sign_rate', 'kh_rate')
COUNT_KEYS = ('cust', 'add_today', 'add_month', 'auth_cust', 'auth_signed', 'kh', 'kh_signed')


def annotate(rows: list[dict], n: int = 5) -> None:
    """每列前 n 标红、后 n 标绿（与正式通报的着色规则一致）。"""
    for r in rows:
        r['_hl'] = {}
    for key in RATE_KEYS + COUNT_KEYS:
        vals = [(i, r.get(key)) for i, r in enumerate(rows) if isinstance(r.get(key), (int, float))]
        if len(vals) <= n * 2:
            continue
        vals.sort(key=lambda x: x[1])
        for i, _v in vals[-n:]:
            rows[i]['_hl'][key] = 'red'
        for i, _v in vals[:n]:
            rows[i]['_hl'][key] = 'green'


def build_text(d: dict, rows: list[dict]) -> str:
    k = d.get('kpi') or {}
    day = f"{d['as_of'][5:7]}月{d['as_of'][8:10]}日"
    by_rate = sorted(rows, key=lambda n: -(n.get('day_rate') or 0))
    by_add = sorted(rows, key=lambda n: -(n.get('add_today') or 0))
    by_sign = sorted([r for r in rows if r.get('sign_rate') is not None], key=lambda n: n['sign_rate'])
    by_kh = sorted([r for r in rows if r.get('kh_rate') is not None], key=lambda n: n['kh_rate'])

    top = '、'.join(f"{_short(n['name'])}{n['day_rate'] * 100:.2f}%" for n in by_rate[:3])
    low = '、'.join(f"{_short(n['name'])}{n['day_rate'] * 100:.2f}%" for n in by_rate[-3:][::-1])
    add_top = '、'.join(f"{_short(n['name'])}{int(n['add_today'])}" for n in by_add[:3])
    add_low = '、'.join(f"{_short(n['name'])}{int(n['add_today'])}" for n in by_add[-3:][::-1])
    sign_low = '、'.join(f"{_short(n['name'])}{n['sign_rate'] * 100:.2f}%" for n in by_sign[:2])
    kh_low = '、'.join(f"{_short(n['name'])}{n['kh_rate'] * 100:.2f}%" for n in by_kh[:2])

    p1 = (f"{day}，全行当月到店客户手机银行动户率{(k.get('month_rate') or 0) * 100:.2f}%，"
          f"当日企微添客{int(k.get('add_today') or 0)}户，全量客户营销授权率{(k.get('sign_rate') or 0) * 100:.2f}%。")
    p2 = (f"到店动户率方面，{top}领跑[强][强]；{low}排名靠后[加油][加油]")
    p3 = (f"企微添客方面，{add_top}当日领先全行。{add_low}暂时落后[心碎][心碎]")
    p4 = (f"营销授权方面，{sign_low}签约率垫底；{kh_low}管户签约率靠后。"
          f"请各支行持续抓好存量客户签约转化[加油][加油]")
    return '\n\n'.join([p1, p2, p3, p4])




# ---------------------------------------------------------------- 薪管家
def build_salary(on: str | None = None) -> dict:
    d = api.build_salary(on)
    if not d.get('ok'):
        return {'ok': False, 'error': d.get('reason') or '该日期无薪管家数据', 'nearest': d.get('nearest')}
    k = d['kpi']
    brs = d['branches']
    nets = d['nets']
    as_of = d['as_of']
    title = f'工银薪管家“聚薪行动”日通报（截至{as_of[:4]}.{as_of[5:7]}.{as_of[8:10]}）'
    try:
        br_names = _template_names(SALARY_BASE, '支行', 4, 11)
        net_names = _template_names(SALARY_BASE, '网点', 4, 43)
    except Exception:
        br_names, net_names = [b['full'] for b in brs], [n['name'] for n in nets]
    br_by = {b['full']: b for b in brs}
    net_by = {n['name']: n for n in nets}
    br_rows = []
    for nm in br_names:
        b = br_by.get(nm) or {}
        br_rows.append({'name': nm, 'year': b.get('year') or 0, 'month': b.get('month') or 0,
                        'ent_year': b.get('ent_year') or 0, 'ent_month': b.get('ent_month') or 0})
    net_rows = []
    for nm in net_names:
        n = net_by.get(nm) or {}
        net_rows.append({'name': nm, 'year': n.get('year') or 0, 'month': n.get('month') or 0,
                         'ent_year': n.get('ent_year') or 0, 'ent_month': n.get('ent_month') or 0})

    br_cols = [
        {'key': 'name', 'title': '支行', 'type': 'text'},
        {'key': 'year', 'title': '全年代发金额(万元)', 'type': 'num'},
        {'key': 'month', 'title': '当月代发金额(万元)', 'type': 'num'},
        {'key': 'ent_year', 'title': '全年有效单位(户)', 'type': 'num'},
        {'key': 'ent_month', 'title': '当月有效单位(户)', 'type': 'num'},
    ]
    net_cols = [
        {'key': 'name', 'title': '网点', 'type': 'text'},
        {'key': 'year', 'title': '全年代发金额(万元)', 'type': 'num'},
        {'key': 'month', 'title': '当月代发金额(万元)', 'type': 'num'},
        {'key': 'ent_year', 'title': '全年有效单位(户)', 'type': 'num'},
        {'key': 'ent_month', 'title': '当月有效单位(户)', 'type': 'num'},
    ]
    top_y = sorted(nets, key=lambda b: -(b.get('year') or 0))[:3]
    top_m = sorted(nets, key=lambda b: -(b.get('month') or 0))[:3]
    text = '\n\n'.join([
        title,
        f"全行新增代发金额 {k['year']:,.2f} 万元（全年）、{k['month']:,.2f} 万元（当月）；"
        f"新增有效使用单位 {k['ent_year']} 户（全年）、{k['ent_month']} 户（当月）。",
        '全年新增代发金额靠前：' + '、'.join(f"{b['name']} {(b.get('year') or 0):,.2f}万元" for b in top_y) + '。',
        '当月新增代发金额靠前：' + '、'.join(f"{b['name']} {(b.get('month') or 0):,.2f}万元" for b in top_m) + '。',
        '详见附件通报。',
    ])
    return {
        'ok': True, 'kind': 'salary', 'title': title, 'as_of': as_of,
        'tables': [
            {'name': '支行', 'columns': br_cols, 'rows': br_rows,
             'totals': {'name': '总计', 'year': k['year'], 'month': k['month'],
                        'ent_year': k['ent_year'], 'ent_month': k['ent_month']}},
            {'name': '网点', 'columns': net_cols, 'rows': net_rows,
             'totals': {'name': '总计', 'year': k['year'], 'month': k['month'],
                        'ent_year': k['ent_year'], 'ent_month': k['ent_month']}},
        ],
        'text': text,
    }


# ---------------------------------------------------------------- 数币
def build_wallet(on: str | None = None) -> dict:
    d = api.build_wallet(on)
    if not d.get('ok'):
        return {'ok': False, 'error': d.get('reason') or '该日期无数币数据', 'nearest': d.get('nearest')}
    k = d['kpi']
    as_of = d['as_of']
    day = f"{int(as_of[5:7])}月{int(as_of[8:10])}日"
    cols = [
        {'key': 'branch', 'title': '支行', 'type': 'text'},
        {'key': 'name', 'title': '网点', 'type': 'text'},
        {'key': 'lv1', 'title': '一类', 'type': 'num'},
        {'key': 'lv2', 'title': '二类', 'type': 'num'},
        {'key': 'lv3', 'title': '三类', 'type': 'num'},
        {'key': 'lv4', 'title': '四类', 'type': 'num'},
        {'key': 'total', 'title': '钱包开立总数', 'type': 'num'},
        {'key': 'month', 'title': '当月新增', 'type': 'num'},
        {'key': 'day', 'title': '当日新增', 'type': 'num'},
    ]
    by = {_key(n['name']): n for n in d['nets']}
    by.update({n['name']: n for n in d['nets']})
    try:
        names = _template_names(WALLET_BASE, None, 3, 42, col=2)
    except Exception:
        names = [n['name'] for n in d['nets']]
    rows = []
    for nm in names:
        n = _match(nm, by)
        if n:
            rows.append({'branch': n['branch'], 'name': nm, 'lv1': n['lv'][0], 'lv2': n['lv'][1],
                         'lv3': n['lv'][2], 'lv4': n['lv'][3], 'total': n['total'],
                         'month': n['month'], 'day': n['day']})
        else:
            rows.append({'branch': '', 'name': nm, 'lv1': 0, 'lv2': 0, 'lv3': 0, 'lv4': 0,
                         'total': 0, 'month': 0, 'day': 0})
    ranked = sorted(rows, key=lambda x: -x['total'])
    best = ranked[:3]
    worst = ranked[-3:][::-1]
    top_day = sorted(rows, key=lambda x: -x['day'])[:3]
    zero = k.get('zero_day') or 0
    title = f'数字人民币个人钱包发展通报（截至{day}）'
    text = '\n'.join([
        f'截至{as_of[:4]}年{int(as_of[5:7])}月{int(as_of[8:10])}日，全行累计开立数字人民币个人钱包{k["total"]:,}户。',
        '数币个人钱包开立总户数前3名网点为：' + '、'.join(f"{x['name']}（{x['total']}户）" for x in best)
        + '请继续保持[强][强]；后3名网点为：' + '、'.join(f"{x['name']}（{x['total']}户）" for x in worst)
        + '请努力追赶[加油][加油]',
        '当日新开户前3名网点为：' + '、'.join(f"{x['name']}（{x['day']}户）" for x in top_day)
        + f'[强][强]；当日新增为0的网点{zero}个[心碎][心碎]，请务必破零[拳头]。',
    ])
    return {
        'ok': True, 'kind': 'wallet', 'title': title, 'as_of': as_of,
        'tables': [{'name': '网点明细', 'columns': cols, 'rows': rows,
                    'totals': {'branch': '合计', 'name': '', 'lv1': k['lv'][0], 'lv2': k['lv'][1],
                               'lv3': k['lv'][2], 'lv4': k['lv'][3], 'total': k['total'],
                               'month': k['month'], 'day': k['day']}}],
        'text': text,
    }




# ---------------------------------------------------------------- 定期存款
DEPOSIT_BASE = Path(__file__).resolve().parent.parent / 'report' / 'assets' / 'deposit_base.xlsx'


def build_deposit(on: str | None = None) -> dict:
    snap = api._latest('dqzz', on)
    if not snap:
        nd = api.build_deposit(on)
        return {'ok': False, 'error': nd.get('reason') or '该日期无定期存款数据', 'nearest': nd.get('nearest')}
    d = {'ok': True, 'as_of': snap['as_of'], 'prev_as_of': snap.get('prev_as_of'),
         'branches': snap['branches'], 'total': snap['total']}
    t = snap['total']
    k = {'balance': t['cur_bal'], 'inc': t['inc'], 'rate': t['rate'], 'prev_balance': t['prev_bal']}
    as_of = d['as_of']
    prev = d.get('prev_as_of')
    title = f'{int(as_of[5:7])}月{int(as_of[8:10])}日阜阳分行定期增长情况表（单位：万元）'
    cols = [
        {'key': 'name', 'title': '支行', 'type': 'text'},
        {'key': 'cur', 'title': '定期余额', 'type': 'num'},
        {'key': 'inc', 'title': '当月增量', 'type': 'num'},
        {'key': 'rate', 'title': '当月增幅', 'type': 'pct'},
        {'key': 'prev', 'title': f'{int((prev or as_of)[5:7])}月定期余额', 'type': 'num'},
    ]
    by = {b['name']: b for b in d['branches']}
    try:
        order = _template_names(DEPOSIT_BASE, None, 3, 10)
    except Exception:
        order = list(by)
    rows = [{'name': nm, 'cur': (by.get(nm) or {}).get('cur_bal'),
             'inc': (by.get(nm) or {}).get('inc'), 'rate': (by.get(nm) or {}).get('rate'),
             'prev': (by.get(nm) or {}).get('prev_bal')} for nm in order]
    totals = {'name': '合计', 'cur': k['balance'], 'inc': k['inc'], 'rate': k['rate'],
              'prev': k['prev_balance']}
    text = (f'截至{int(as_of[5:7])}月{int(as_of[8:10])}日，全行定期存款余额 {k["balance"]:,.2f} 万元，'
            f'当月增量 {k["inc"]:,.2f} 万元，当月增幅 {k["rate"] * 100:.2f}%'
            f'（对照 {int((prev or as_of)[5:7])}月{int((prev or as_of)[8:10])}日 {k["prev_balance"]:,.2f} 万元）。\n'
            f'增量前三：' + '、'.join(f'{b["name"]} {b["inc"]:+,.2f} 万元'
                                     for b in sorted(rows, key=lambda x: -(x['inc'] or 0))[:3]) + '；'
            f'负增长：' + ('、'.join(f'{b["name"]} {b["inc"]:,.2f} 万元'
                                   for b in rows if (b['inc'] or 0) < 0) or '无') + '。')
    return {'ok': True, 'kind': 'deposit', 'title': title, 'as_of': as_of,
            'tables': [{'name': '通报', 'columns': cols, 'rows': rows, 'totals': totals}],
            'text': text}


# ---------------------------------------------------------------- 企微社群
COMMUNITY_BASE = Path(__file__).resolve().parent.parent / 'report' / 'assets' / 'community_base.xlsx'


def build_community(on: str | None = None) -> dict:
    snap = api._latest('qwsq', on)
    if not snap:
        nd = api.build_community(on)
        return {'ok': False, 'error': nd.get('reason') or '该日期无企微社群数据', 'nearest': nd.get('nearest')}
    d = {'ok': True, 'as_of': snap['as_of'], 'branches': snap.get('branches') or [],
         'nets': snap.get('nets') or [], 'total': snap.get('total') or {}}
    t0 = d['total']
    k = {'groups': t0.get('groups'), 'groups_d': t0.get('groups_d'), 'cust': t0.get('cust'),
         'cust_d': t0.get('cust_d'), 'inter': t0.get('inter'), 'inter_d': t0.get('inter_d'),
         'rate': t0.get('rate'), 'rate_d': t0.get('rate_d')}
    as_of = d['as_of']
    title = f'企微个微社群数据统计表（{int(as_of[5:7])}月{int(as_of[8:10])}日）'
    cols = [
        {'key': 'name', 'title': '机构', 'type': 'text'},
        {'key': 'groups', 'title': '群数量', 'type': 'num'},
        {'key': 'groups_d', 'title': '较上周', 'type': 'num'},
        {'key': 'cust', 'title': '客户数', 'type': 'num'},
        {'key': 'cust_d', 'title': '较上周', 'type': 'num'},
        {'key': 'inter', 'title': '交互数', 'type': 'num'},
        {'key': 'inter_d', 'title': '较上周', 'type': 'num'},
        {'key': 'rate', 'title': '熟识率', 'type': 'pct'},
        {'key': 'rate_d', 'title': '较上周', 'type': 'pct'},
    ]

    def rows_of(items, suffix=''):
        return [{'name': (i['name'] or '') + suffix, 'groups': i['groups'], 'groups_d': i['groups_d'],
                 'cust': i['cust'], 'cust_d': i['cust_d'], 'inter': i['inter'], 'inter_d': i['inter_d'],
                 'rate': i['rate'], 'rate_d': i['rate_d']} for i in items]

    try:
        br_order = _template_names(COMMUNITY_BASE, '支行维度', 4, 11)
        net_order = _template_names(COMMUNITY_BASE, '网点维度', 4, 43)
    except Exception:
        br_order = [b['name'] for b in d['branches']]
        net_order = [n['name'] for n in d['nets']]
    br_by = {b['name']: b for b in d['branches']}
    net_by = {n['name']: n for n in d['nets']}
    br_rows = [{**rows_of([br_by.get(nm)])[0]} if br_by.get(nm) else
               {'name': nm, 'groups': 0, 'groups_d': 0, 'cust': 0, 'cust_d': 0,
                'inter': 0, 'inter_d': 0, 'rate': 0, 'rate_d': 0} for nm in br_order]
    net_rows = [{**rows_of([net_by.get(nm)])[0]} if net_by.get(nm) else
                {'name': nm, 'groups': 0, 'groups_d': 0, 'cust': 0, 'cust_d': 0,
                 'inter': 0, 'inter_d': 0, 'rate': 0, 'rate_d': 0} for nm in net_order]
    tot = {'name': '合计', 'groups': k['groups'], 'groups_d': k['groups_d'],
           'cust': k['cust'], 'cust_d': k['cust_d'], 'inter': k['inter'], 'inter_d': k['inter_d'],
           'rate': k['rate'], 'rate_d': k['rate_d']}

    top_cust = sorted(d['nets'], key=lambda n: -(n.get('cust') or 0))[:3]
    top_grp = sorted(d['branches'], key=lambda b: -(b.get('groups') or 0))[:2]
    text = '\n\n'.join([
        f'企微个微社群数据统计（截至{as_of[:4]}年{int(as_of[5:7])}月{int(as_of[8:10])}日）',
        f'累计建群 {k["groups"]} 个，较上周 {k["groups_d"]:+d} 个；客户数 {k["cust"]:,} 户，'
        f'较上周 {k["cust_d"]:+d} 户；交互数 {k["inter"]:,} 条，较上周 {k["inter_d"]:+d} 条；'
        f'熟识率 {k["rate"] * 100:.2f}%，较上周 {k["rate_d"] * 100:+.2f} 个百分点。',
        '客户数前三网点：' + '、'.join(f'{n["name"]}（{n["cust"]}户）' for n in top_cust) + '。',
        '建群领先支行：' + '、'.join(f'{b["name"]}建群{b["groups"]}个' for b in top_grp) + '。',
    ])
    return {'ok': True, 'kind': 'community', 'title': title, 'as_of': as_of,
            'tables': [{'name': '支行维度', 'columns': cols, 'rows': br_rows, 'totals': tot},
                       {'name': '网点维度', 'columns': cols, 'rows': net_rows, 'totals': tot}],
            'text': text}

# ---------------------------------------------------------------- 降级挽回
DOWNGRADE_BASE = Path(__file__).resolve().parent.parent / 'report' / 'assets' / 'downgrade_base.xlsx'


def _signed(v: float, unit: str = '万元', nd: int = 1) -> str:
    """把带符号的数说成人话：+ → 增长，− → 下降。"""
    v = 0.0 if v is None else float(v)
    word = '增长' if v >= 0 else '下降'
    return f'{word}{abs(v):,.{nd}f}{unit}'


def build_downgrade(on: str | None = None) -> dict:
    d = api.build_downgrade(on)
    if not d.get('ok'):
        return {'ok': False, 'error': d.get('reason') or '该日期无降级挽回数据',
                'nearest': d.get('nearest')}
    k = d['kpi']
    per = d['period']
    branches = d['branches']
    top = (d.get('top_nets') or [])[:5]
    span = f"{per['start'][5:7]}月{per['start'][8:10]}日-{per['end'][5:7]}月{per['end'][8:10]}日"
    title = f'阜阳分行“降级挽回”营销先锋（{per["label"]}）'

    # 前三 / 后三一律按名次取，不要按"评分为正/为负"筛：
    # 某期可能只有两家是正数（如 1020-1026），按正负筛会把第三名吞掉
    ranked = sorted(branches, key=lambda b: b.get('rank') or 0)
    up_br = [b['name'] for b in ranked[:3]]
    down_br = [b['name'] for b in ranked[-3:]][::-1]     # 后三名，末位最差放最前
    text = '\n\n'.join([
        '【财客管户“降级挽回”营销先锋】',
        f'1️⃣整体情况：{span}，全行锁包降级管户金融资产{_signed(k["asset"])}，'
        f'储蓄存款{_signed(k["dep"])}。',
        f'2️⃣支行排名：{"、".join(up_br) or "—"}位居前三，'
        f'{"、".join(down_br) or "—"}居后三名！',
        f'3️⃣营销先锋：单边降级提升前{len(top)}名网点为'
        f'{"、".join(n["name"] for n in top) or "—"}，全行领先！',
        '降级客户具体明细清单已发送各支行分管行长及个金部主任邮箱。',
    ])

    br_cols = [
        {'key': 'rank', 'title': '排序', 'type': 'num'},
        {'key': 'name', 'title': '支行', 'type': 'text'},
        {'key': 'nets', 'title': '网点数', 'type': 'num'},
        {'key': 'score', 'title': '综合评价(1:1)', 'type': 'num'},
        {'key': 'asset', 'title': '本旬资产提升额', 'type': 'num'},
        {'key': 'asset_avg', 'title': '网均资产提升额', 'type': 'num'},
        {'key': 'dep', 'title': '本旬存款提升额', 'type': 'num'},
        {'key': 'dep_avg', 'title': '网均存款提升额', 'type': 'num'},
    ]
    net_cols = [
        {'key': 'rank', 'title': '排名', 'type': 'num'},
        {'key': 'name', 'title': '网点', 'type': 'text'},
        {'key': 'asset', 'title': '资产提升额', 'type': 'num'},
        {'key': 'dep', 'title': '存款提升额', 'type': 'num'},
    ]
    detail_cols = [
        {'key': 'rank', 'title': '排名', 'type': 'num'},
        {'key': 'branch', 'title': '支行', 'type': 'text'},
        {'key': 'net', 'title': '网点', 'type': 'text'},
        {'key': 'customers', 'title': '客户数', 'type': 'num'},
        {'key': 'asset', 'title': '资产提升额', 'type': 'num'},
        {'key': 'dep', 'title': '存款提升额', 'type': 'num'},
        {'key': 'score', 'title': '综合评价', 'type': 'num'},
    ]
    # 网点明细：按综合评价（两项提升额的 1:1 平均）从高到低，全表一个序列
    detail_rows = []
    for n in d['nets']:
        detail_rows.append({'branch': n['branch'], 'net': n['name'],
                            'customers': n['customers'],
                            'asset': n['asset'], 'dep': n['dep'],
                            'score': round(((n['asset'] or 0) + (n['dep'] or 0)) / 2, 4)})
    detail_rows.sort(key=lambda r: -r['score'])
    for i, r in enumerate(detail_rows, 1):
        r['rank'] = i

    return {
        'ok': True, 'kind': 'downgrade', 'title': title, 'as_of': d['as_of'],
        'period': per, 'text': text,
        'tables': [
            {'name': '支行', 'columns': br_cols, 'rows': branches,
             'totals': {'rank': '', 'name': '阜阳分行', 'nets': k['nets'],
                        'score': k['score'], 'asset': k['asset'], 'asset_avg': k['asset_avg'],
                        'dep': k['dep'], 'dep_avg': k['dep_avg']}},
            {'name': '营销先锋', 'columns': net_cols, 'rows': top, 'totals': None},
            {'name': '网点明细', 'columns': detail_cols, 'rows': detail_rows, 'totals': None},
        ],
    }


def downgrade_xlsx(on: str | None = None) -> tuple[bytes, str]:
    """按正式成表（0914-0920 那份）的版式写数：左 8 支行 + 合计，右 5 个先锋网点。"""
    import openpyxl
    d = build_downgrade(on)
    if not d.get('ok'):
        raise RuntimeError('该日期没有降级挽回数据')
    wb = openpyxl.load_workbook(DOWNGRADE_BASE)
    ws = wb['通报']
    ws['A1'] = d['title']

    # 左表：4..11 行 = 8 家支行（按综合评分名次），12 行合计（A12:B12 已合并）
    br = d['tables'][0]
    by_rank = {b['rank']: b for b in br['rows']}
    for r in range(4, 12):
        rec = by_rank.get(r - 3)
        if not rec:
            continue
        for ci, v in enumerate([rec['rank'], rec['name'], rec['nets'], rec['score'],
                                rec['asset'], rec['asset_avg'], rec['dep'], rec['dep_avg']],
                               start=1):
            ws.cell(row=r, column=ci, value=v)
        hl = rec.get('hl')
        if hl:
            ws.cell(row=r, column=4).fill = openpyxl.styles.PatternFill(
                'solid', fgColor='FFF2A8' if hl == 'yellow' else 'C6E0B4')

    t = br['totals']
    for ci, v in enumerate([None, None, t['nets'], t['score'], t['asset'],
                            t['asset_avg'], t['dep'], t['dep_avg']], start=1):
        if v is not None:
            ws.cell(row=12, column=ci, value=v)

    # 右表：4..8 行 = 营销先锋前 5
    for i, rec in enumerate(d['tables'][1]['rows'][:5]):
        r = 4 + i
        ws.cell(row=r, column=9, value=rec['rank'])
        ws.cell(row=r, column=10, value=rec['name'])
        ws.cell(row=r, column=11, value=rec['asset'])
        ws.cell(row=r, column=12, value=rec['dep'])

    # 第二个 sheet：网点明细（按支行分组，组内资产降序）
    ws2 = wb['网点明细']
    ws2['A1'] = f'阜阳分行“降级挽回”网点明细（{d["period"]["label"]}）'
    for i, rec in enumerate(d['tables'][2]['rows']):
        r = 3 + i
        for ci, v in enumerate([rec.get('rank'), rec['branch'], rec['net'], rec['customers'],
                                rec['asset'], rec['dep'], rec['score']], start=1):
            ws2.cell(row=r, column=ci, value=v)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue(), f'降级挽回营销先锋（{d["period"]["label"]}）.xlsx'


# ---------------------------------------------------------------- 一卡一户
YIKA_BASE = Path(__file__).resolve().parent.parent / 'report' / 'assets' / 'yika_base.xlsx'
YIKA_FIRST_ROW, YIKA_LAST_ROW = 4, 52


def _md(iso: str) -> str:
    """'2026-10-25' → '10月25日'。"""
    return f'{int(iso[5:7])}月{int(iso[8:10])}日'


def _span_label(period: dict) -> str:
    """通报标题里的期间：周日出 10.23-10.25，其他日子只写当天 10.26。"""
    s, e = period['start'], period['end']
    if s == e:
        return f'{int(s[5:7])}.{int(s[8:10])}'
    return f'{int(s[5:7])}.{int(s[8:10])}-{int(e[5:7])}.{int(e[8:10])}'


def _span_cn(period: dict) -> str:
    """文案里的期间：`10月23-25日`（同月省略后一个"月"），单日 `10月26日`。"""
    s, e = period['start'], period['end']
    if s == e:
        return f'{int(s[5:7])}月{int(s[8:10])}日'
    if s[5:7] == e[5:7]:
        return f'{int(s[5:7])}月{int(s[8:10])}-{int(e[8:10])}日'
    return f'{int(s[5:7])}月{int(s[8:10])}日-{int(e[5:7])}月{int(e[8:10])}日'


def _low_threshold(low: list[dict]) -> tuple[list[dict], int]:
    """「完成率不足 X%」：取最低的一家，阈值向上取整到 5 的倍数；
    若最低两家都不足 25%，两家一起报（用户确认的口径）。"""
    if not low:
        return [], 0
    worst = low[0]['day_rate']
    thr = max(5, int(math.ceil(worst * 100 / 5.0)) * 5)
    picked = [b for b in low if b['day_rate'] < thr / 100]
    return picked, thr


def build_yika(on: str | None = None) -> dict:
    d = api.build_yika(on)
    if not d.get('ok'):
        return {'ok': False, 'error': d.get('reason') or '该日期无一卡一户数据',
                'nearest': d.get('nearest')}
    k, per, branches = d['kpi'], d['period'], d['branches']
    label = _span_label(per)
    title = f'“一卡一户”日通报（{label}）'

    top2 = branches[:2]
    low, thr = _low_threshold(d.get('low_branches') or [])
    reached = d.get('top_nets') or []
    zero = d.get('zero_nets') or []

    # 文案严格照用户给的标准模板（缩进也照抄，粘到企微/微信里排版才对）
    lines = [
        '“一卡一户”业务日通报：',
        f'     {_span_cn(per)}，阜阳分行共计开立社保卡{int(k["sb_day"])}张、'
        f'个人养老金账户{int(k["yl_day"])}户！',
        '支行层面：',
        f'    {"、".join(b["name"] for b in top2) or "—"}支行两项指标合计任务完成率靠前[强][强]',
    ]
    if low:
        lines.append(f'    {"、".join(b["name"] for b in low)}支行两项产品合计营销完成率'
                     f'不足{thr}%[心碎][心碎]请加强“一卡一户”业务关注度！')
    lines.append('网点层面：')
    lines.append(f'     {k["sb_active"]}家网点实现社保卡营销，{k["yl_active"]}家网点实现'
                 f'个人养老金账户突破[烟花][烟花]其中'
                 f'{"、".join(_short_net(n) for n in reached) or "—"}合计完成率达标！')
    if zero:
        lines.append(f'     {"、".join(_short_net(n) for n in zero)}两项指标均无业绩！[凋谢][凋谢]')
        lines.append('    请社保卡、个人养老金两项指标均无业绩的网点负责人在本群反馈“0”拓户原因'
                     '及明天两项指标预计开户数。')
    text = '\n'.join(lines)

    br_cols = [
        {'key': 'rank', 'title': '排名', 'type': 'num'},
        {'key': 'name', 'title': '支行', 'type': 'text'},
        {'key': 'nets', 'title': '网点数', 'type': 'num'},
        {'key': 'sb_day', 'title': '社保卡当日', 'type': 'num'},
        {'key': 'sb_week', 'title': '社保卡本周', 'type': 'num'},
        {'key': 'yl_day', 'title': '养老金当日', 'type': 'num'},
        {'key': 'yl_week', 'title': '养老金本周', 'type': 'num'},
        {'key': 'day_rate', 'title': '当日合计完成率', 'type': 'pct'},
        {'key': 'week_rate', 'title': '周任务完成率', 'type': 'pct'},
    ]
    net_cols = [
        {'key': 'name', 'title': '网点', 'type': 'text'},
        {'key': 'branch', 'title': '支行', 'type': 'text'},
        {'key': 'sb_day', 'title': '社保卡当日', 'type': 'num'},
        {'key': 'sb_rate', 'title': '社保日达成', 'type': 'pct'},
        {'key': 'sb_week', 'title': '社保卡本周', 'type': 'num'},
        {'key': 'yl_day', 'title': '养老金当日', 'type': 'num'},
        {'key': 'yl_rate', 'title': '养老金日达成', 'type': 'pct'},
        {'key': 'yl_week', 'title': '养老金本周', 'type': 'num'},
        {'key': 'day_rate', 'title': '当日合计', 'type': 'pct'},
        {'key': 'week_rate', 'title': '周任务', 'type': 'pct'},
    ]
    total_row = {'rank': '', 'name': '阜阳分行', 'nets': k['nets'],
                 'sb_day': k['sb_day'], 'sb_week': k['sb_week'],
                 'yl_day': k['yl_day'], 'yl_week': k['yl_week'],
                 'day_rate': k['day_rate'], 'week_rate': k['week_rate']}
    return {
        'ok': True, 'kind': 'yika', 'title': title, 'as_of': d['as_of'],
        'period': per, 'text': text,
        'label': label, 'low': low, 'low_thr': thr,
        'tables': [
            {'name': '支行', 'columns': br_cols, 'rows': branches, 'totals': total_row},
            {'name': '网点明细', 'columns': net_cols, 'rows': d['nets'], 'totals': None},
        ],
    }


def _short_net(rec: dict) -> str:
    """通报文案里的网点叫法 = 支行名 + 网点名，各去掉「阜阳」「支行」。

    成表文案就是这么写的：`阜阳城建支行`（颍州）→ `颍州城建`；
    `临泉姜尚支行`（临泉）→ `临泉姜尚`。直接去掉「阜阳」「支行」会丢掉支行信息，
    变成「城建」「姜尚」，别人不知道是哪个支行。
    """
    n = (rec.get('name') or '').strip()
    if n.startswith('阜阳'):
        n = n[2:]
    if n.endswith('支行'):
        n = n[:-2]
    br = (rec.get('branch') or '').strip()
    if br and not n.startswith(br):
        return f'{br}{n}'
    return n


def yika_xlsx(on: str | None = None) -> tuple[bytes, str]:
    """按成表版式写数：通报 / 社保卡 / 养老金 三张 sheet 全填。

    社保卡 sheet 的列布局（母版第 3 行就是列名，照它填，别自己数）：
        B+C = 上周日累计    D+E = 前一日累计    H+I = 当日累计
        F = B+C-D-E（当日开户，公式保留）      J = B+C-H-I（本周开户，公式保留）
    前一日 == 上周末（周一）时，只填 D+E 与 H+I 两块。

    条件格式是母版自带的（前 3 标红 / 后 3 标绿 / =0 标绿），这里**绝不要手工涂色**，
    否则会和条件格式打架，也让"多个 0 时都标绿"失效。
    """
    import openpyxl
    d = build_yika(on)
    if not d.get('ok'):
        raise RuntimeError('该日期没有一卡一户数据')
    src = api.build_yika(on)
    per = d['period']
    wb = openpyxl.load_workbook(YIKA_BASE)

    # ---------------------------------------------------------- 通报
    ws = wb['通报']
    ws['A1'] = d['title']
    net_by_name = {n['name'].replace('阜阳', ''): n for n in src['nets']}
    br_by_name = {b['name']: b for b in src['branches']}
    COLS = [(3, 'sb_day'), (4, 'sb_target'), (5, 'sb_rate'), (6, 'sb_week'),
            (7, 'yl_day'), (8, 'yl_target'), (9, 'yl_rate'), (10, 'yl_week'),
            (11, 'day_rate'), (12, 'week_rate')]
    for r in range(YIKA_FIRST_ROW, YIKA_LAST_ROW + 1):
        name = ws.cell(r, 2).value
        label = ws.cell(r, 1).value
        if name:                                        # 网点行
            rec = net_by_name.get(str(name).strip().replace('阜阳', ''))
            if not rec:
                raise RuntimeError(f'母版网点「{name}」在数据里找不到')
        elif label and '小计' in str(label):             # 支行小计行
            rec = br_by_name.get(str(label).replace('小计', '').strip())
            if not rec:
                continue
        elif label and str(label).strip() == '阜阳分行':  # 分行合计行
            rec = src['kpi']
        else:
            continue
        for ci, key in COLS:
            ws.cell(r, ci, rec.get(key, 0))

    # ---------------------------------------------------------- 社保卡
    sb = wb['社保卡']
    sb['G2'] = '上周日'
    # 列对：(累计柜台列, 累计批量列)
    blocks = [(per['week_end'], 8, 9), (per['prev'], 4, 5), (per['cur'], 2, 3)]
    if per['prev'] == per['week_end']:                  # 周一：前一日 = 上周末，只填两块
        blocks = [(per['week_end'], 8, 9), (per['cur'], 2, 3)]
    for r in range(4, 46):
        name = sb.cell(r, 1).value
        if not name:
            continue
        key = str(name).strip()
        for day, c1, c2 in blocks:
            if key == '合计':          # 末行合计：源表「合计」行（含运行管理部等非网点机构）
                grand = _grand_of('ykh_sb', day)
                if grand is None or len(grand) < 2:
                    grand = [0, 0]
                    for n in src['nets']:
                        pr = _parts_of('ykh_sb', day, n['name'])
                        grand[0] += pr[0]
                        grand[1] += pr[1]
                sb.cell(r, c1, int(grand[0]))
                sb.cell(r, c2, int(grand[1]))
            else:
                parts = _parts_of('ykh_sb', day, key)
                sb.cell(r, c1, int(parts[0]))
                sb.cell(r, c2, int(parts[1]))

    # ---------------------------------------------------------- 养老金
    yl = wb['养老金']
    yblocks = [(per['week_end'], 1), (per['prev'], 7), (per['cur'], 13)]   # A / G / M
    if per['prev'] == per['week_end']:
        yblocks = [(per['week_end'], 1), (per['cur'], 13)]
    for day, c0 in yblocks:
        yl.cell(1, c0, _date_obj(day))
    for r in range(4, 44):
        name = yl.cell(r, 1).value
        if not name:
            continue
        key = str(name).strip()
        for day, c0 in yblocks:
            parts = _parts_of('ykh_yl', day, key)
            # 三列：累计开户数 / 当日新增 / 本年新增
            yl.cell(r, c0 + 1, int(parts[0]))
            yl.cell(r, c0 + 2, int(parts[1]))
            yl.cell(r, c0 + 3, int(parts[2]))

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue(), f'一卡一户日通报（{d["label"]}）.xlsx'


def _grand_of(line: str, day: str) -> list | None:
    """源表末行「合计」（社保卡含运行管理部，与 40 个网点之和可能差几户/张）。"""
    for s in viz.load_snapshots(line):
        if s.get('as_of') == day:
            return s.get('grand')
    return None


def _parts_of(line: str, day: str, name: str) -> list:
    """取某天某网点的分项（社保卡=[柜台,批量]；养老金=[累计,当日新增,本年新增]）。"""
    for s in viz.load_snapshots(line):
        if s.get('as_of') == day:
            parts = s.get('parts') or {}
            hit = _lookup_name(parts, name) if parts else None
            if hit:
                return list(hit)
            v = _lookup_name(s.get('cum') or {}, name) or 0
            return [v] + [0, 0][:2]
    return [0, 0, 0]


def _cum_of(line: str, day: str) -> dict:
    """从库里取某天的累计值；没有返回空 dict（缺失在 api 层已经拦过）。"""
    for s in viz.load_snapshots(line):
        if s.get('as_of') == day:
            return s.get('cum') or {}
    return {}


def _lookup_name(series: dict, name: str) -> float | None:
    from ingest.yika import _lookup
    return _lookup(series, name)


def _date_obj(iso: str):
    from datetime import date
    return date.fromisoformat(iso)


BUILDERS = {'online': build_online, 'salary': build_salary, 'wallet': build_wallet,
            'deposit': build_deposit, 'community': build_community,
            'downgrade': build_downgrade, 'yika': build_yika}
TITLES = {'online': '网点线上服务能力', 'salary': '薪管家聚薪行动', 'wallet': '数字人民币钱包'}

# 每份通报归属的大类（口令按大类放行；前端 report.js 的 LINES[].cat 要与这里一致）
CAT_OF = {'online': 'wj', 'salary': 'jg', 'wallet': 'wj', 'deposit': 'jg', 'community': 'wj',
          'downgrade': 'jg', 'yika': 'jg'}


def build(kind: str, on: str | None = None) -> dict:
    fn = BUILDERS.get(kind)
    if not fn:
        return {'ok': False, 'error': f'通报未实现：{kind}'}
    return fn(on)

# ---------------------------------------------------------------- Excel（套用技能模板）
TEMPLATE = Path(__file__).resolve().parent.parent / 'report' / 'assets' / 'online_base.xlsx'
FMT = {'day_rate': '0.00%', 'month_rate': '0.00%', 'real_rate': '0.00%', 'sign_rate': '0.00%',
       'kh_rate': '0.00%', 'cust': '#,##0', 'add_today': '#,##0', 'add_month': '#,##0',
       'auth_cust': '#,##0', 'auth_signed': '#,##0', 'kh': '#,##0', 'kh_signed': '#,##0'}
RED = 'FFFF0000'
GREEN = 'FF008000'


def online_xlsx(on: str | None = None) -> tuple[bytes, str]:
    import openpyxl
    from copy import copy

    d = build_online(on)
    if not d.get('ok'):
        raise RuntimeError('该日期没有线上服务数据')
    wb = openpyxl.load_workbook(TEMPLATE)
    ws = wb.active
    ws['A1'] = d['title']

    rows = d['tables'][0]['rows']
    by_name = {n['name']: n for n in rows}
    by_short = {_short(n['name']): n for n in rows}

    keys = ['day_rate', 'month_rate', 'cust', 'real_rate', 'add_today', 'add_month',
            'auth_cust', 'auth_signed', 'sign_rate', 'kh', 'kh_signed', 'kh_rate']
    total = d['tables'][0]['totals']

    for row_i in range(4, 44):
        name = str(ws.cell(row=row_i, column=1).value or '').strip()
        rec = by_name.get(name) or by_short.get(_short(name))
        if not rec:
            continue
        for ci, key in enumerate(keys, start=2):
            cell = ws.cell(row=row_i, column=ci)
            v = rec.get(key)
            if v is None:
                continue
            cell.value = v
            cell.number_format = FMT[key]
            hl = (rec.get('_hl') or {}).get(key)
            if hl and cell.font:
                f = copy(cell.font)
                f.color = openpyxl.styles.Color(rgb=RED if hl == 'red' else GREEN)
                cell.font = f

    for ci, key in enumerate(keys, start=2):
        v = total.get(key)
        if v is None:
            continue
        cell = ws.cell(row=44, column=ci)
        cell.value = v
        cell.number_format = FMT[key]

    buf = io.BytesIO()
    wb.save(buf)
    name = f"网点线上服务能力提升通报（{d['as_of'][5:].replace('-', '.')}）.xlsx"
    return buf.getvalue(), name



BRANCH_PREFIX = ('颍州', '颍泉', '颍东', '界首', '临泉', '阜南', '颍上', '太和')


def _key(name: str) -> str:
    """网点名归一：只去「阜阳」前缀（支行前缀可能有也可能没有，另做后缀匹配）。"""
    n = (name or '').strip()
    return n[2:] if n.startswith('阜阳') else n


def _match(name: str, pool: dict) -> dict | None:
    """先精确、再忽略「阜阳」、最后按后缀唯一匹配（岳家湖支行 ↔ 颍东岳家湖支行）。"""
    if name in pool:
        return pool[name]
    k = _key(name)
    if k in pool:
        return pool[k]
    cands = [v for kk, v in pool.items() if kk.endswith(k) or k.endswith(kk)]
    return cands[0] if len(cands) == 1 else None


def _template_names(path: Path, sheet: str | None, r0: int, r1: int, col: int = 1) -> list[str]:
    """从样式母版里取行名（网点/支行），用来保证行序与正式通报表一致。"""
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb[sheet] if sheet else wb.active
    names = [str(ws.cell(row=r, column=col).value or '').strip() for r in range(r0, r1 + 1)]
    wb.close()
    return [n for n in names if n]


SALARY_BASE = Path(__file__).resolve().parent.parent / 'report' / 'assets' / 'salary_base.xlsx'
WALLET_BASE = Path(__file__).resolve().parent.parent / 'report' / 'assets' / 'wallet_base.xlsx'


def salary_xlsx(on: str | None = None) -> tuple[bytes, str]:
    import openpyxl
    d = build_salary(on)
    if not d.get('ok'):
        raise RuntimeError('该日期没有薪管家数据')
    wb = openpyxl.load_workbook(SALARY_BASE)
    for sn, key in (('支行', 0), ('网点', 1)):
        ws = wb[sn]
        ws['A1'] = d['title']
        rows = d['tables'][key]['rows']
        by = {r['name']: r for r in rows}
        last = 12 if sn == '支行' else 44      # 网点是 4..43（含）
        for r in range(4, last):
            name = str(ws.cell(row=r, column=1).value or '').strip()
            rec = by.get(name)
            if not rec:
                continue
            for c, k in ((2, 'year'), (3, 'month'), (4, 'ent_year'), (5, 'ent_month')):
                ws.cell(row=r, column=c).value = rec.get(k) or 0
        if sn == '支行':
            t = d['tables'][key]['totals']
            for c, k in ((2, 'year'), (3, 'month'), (4, 'ent_year'), (5, 'ent_month')):
                ws.cell(row=12, column=c).value = t.get(k) or 0
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue(), f"薪管家通报{d['as_of'][5:7]}{d['as_of'][8:10]}.xlsx"


def wallet_xlsx(on: str | None = None) -> tuple[bytes, str]:
    import openpyxl
    d = build_wallet(on)
    if not d.get('ok'):
        raise RuntimeError('该日期没有数币数据')
    wb = openpyxl.load_workbook(WALLET_BASE)
    ws = wb.active
    ws['A1'] = d['title']
    rows = d['tables'][0]['rows']
    by = {r['name']: r for r in rows}
    by.update({_key(r['name']): r for r in rows})
    # 模板里 A 列（支行）有纵向合并，先拆开再逐个网点填
    for rng in list(ws.merged_cells.ranges):
        if rng.min_col == 1 and rng.max_col == 1:
            ws.unmerge_cells(str(rng))
    last_br = None
    for r in range(3, 43):
        rec = _match(str(ws.cell(row=r, column=2).value or ''), by)
        if not rec:
            continue
        br = rec.get('branch') or ''
        ws.cell(row=r, column=1).value = br if br != last_br else None
        last_br = br
        for c, k in ((3, 'lv1'), (4, 'lv2'), (5, 'lv3'), (6, 'lv4'),
                     (7, 'total'), (8, 'month'), (9, 'day')):
            ws.cell(row=r, column=c).value = rec.get(k) or 0
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue(), f"数字人民币个人钱包发展通报（{d['as_of'][5:7]}.{d['as_of'][8:10]}）.xlsx"




def deposit_xlsx(on: str | None = None) -> tuple[bytes, str]:
    import openpyxl
    d = build_deposit(on)
    if not d.get('ok'):
        raise RuntimeError('该日期没有定期存款数据')
    wb = openpyxl.load_workbook(DEPOSIT_BASE)
    ws = wb.active
    ws['A1'] = d['title']
    rows = d['tables'][0]['rows']
    by = {r['name']: r for r in rows}
    for r in range(3, 11):
        name = str(ws.cell(row=r, column=1).value or '').strip()
        rec = by.get(name)
        if not rec:
            continue
        for c, k, fmt in ((2, 'cur', '#,##0.00'), (3, 'inc', '#,##0.00'),
                          (4, 'rate', '0.00%'), (5, 'prev', '#,##0.00')):
            cell = ws.cell(row=r, column=c)
            cell.value = rec.get(k)
            cell.number_format = fmt
    t = d['tables'][0]['totals']
    for c, k, fmt in ((2, 'cur', '#,##0.00'), (3, 'inc', '#,##0.00'),
                      (4, 'rate', '0.00%'), (5, 'prev', '#,##0.00')):
        cell = ws.cell(row=11, column=c)
        cell.value = t.get(k)
        cell.number_format = fmt
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue(), f"定期存款增长（{d['as_of'][5:7]}.{d['as_of'][8:10]}）.xlsx"


def community_xlsx(on: str | None = None) -> tuple[bytes, str]:
    import openpyxl
    d = build_community(on)
    if not d.get('ok'):
        raise RuntimeError('该日期没有企微社群数据')
    wb = openpyxl.load_workbook(COMMUNITY_BASE)
    keys = [(2, 'groups', '#,##0'), (3, 'groups_d', '#,##0'), (4, 'cust', '#,##0'),
            (5, 'cust_d', '#,##0'), (6, 'inter', '#,##0'), (7, 'inter_d', '#,##0'),
            (8, 'rate', '0.00%'), (9, 'rate_d', '0.00%')]
    for idx, (sheet, r0, r1) in enumerate((('支行维度', 4, 11), ('网点维度', 4, 43))):
        ws = wb[sheet]
        ws['A1'] = d['title']
        rows = d['tables'][idx]['rows']
        by = {r['name']: r for r in rows}
        for r in range(r0, r1 + 1):
            name = str(ws.cell(row=r, column=1).value or '').strip()
            rec = by.get(name)
            if not rec:
                continue
            for c, k, fmt in keys:
                cell = ws.cell(row=r, column=c)
                cell.value = rec.get(k)
                cell.number_format = fmt
        t = d['tables'][0]['totals']
        total_row = 12 if sheet == '支行维度' else 44
        for c, k, fmt in keys:
            cell = ws.cell(row=total_row, column=c)
            cell.value = t.get(k)
            cell.number_format = fmt
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue(), f"企微社群数据统计通报（{d['as_of'][5:7]}.{d['as_of'][8:10]}）.xlsx"

XLSX = {'online': online_xlsx, 'salary': salary_xlsx, 'wallet': wallet_xlsx,
        'deposit': deposit_xlsx, 'community': community_xlsx, 'downgrade': downgrade_xlsx,
        'yika': yika_xlsx}


def xlsx(kind: str, on: str | None = None) -> tuple[bytes, str]:
    fn = XLSX.get(kind)
    if not fn:
        raise RuntimeError(f'导出未实现：{kind}')
    return fn(on)

