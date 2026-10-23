#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""report.py —— 通报中心的数据与导出。

目前实现：网点线上服务能力（表格 + 文案 + Excel）。
文案结构照现有定稿：总述 → 到店动户率 → 企微添客 → 营销授权。
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import api  # noqa: E402

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
    nets = d.get('nets') or []
    # api 视图模型里网点比率是百分数（70.15），合计是小数（0.5185），这里统一成小数
    for n in nets:
        for k in ('day_rate', 'month_rate', 'real_rate', 'sign_rate', 'kh_rate'):
            v = n.get(k)
            if isinstance(v, (int, float)) and abs(v) > 1.5:
                n[k] = round(v / 100, 4)

    order = {b: i for i, b in enumerate(BRANCH_ORDER)}
    rows = sorted(nets, key=lambda n: (order.get(n['branch'], 99), -(n.get('day_rate') or 0)))
    tot = d.get('kpi') or {}
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
            'auth_cust': sum(n.get('auth_cust') or 0 for n in rows) or None,
            'auth_signed': sum(n.get('auth_signed') or 0 for n in rows) or None,
            'kh': sum(n.get('kh') or 0 for n in rows) or None,
            'kh_signed': sum(n.get('kh_signed') or 0 for n in rows) or None,
        },
    }
    return {
        'ok': True, 'kind': 'online', 'title': f'网点线上服务能力提升通报（{d["as_of"][5:].replace("-", ".")}）',
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
            {'name': '支行', 'columns': br_cols,
             'rows': [{'name': b['full'], 'year': b.get('year'), 'month': b.get('month'),
                       'ent_year': b.get('ent_year'), 'ent_month': b.get('ent_month')} for b in brs],
             'totals': {'name': '总计', 'year': k['year'], 'month': k['month'],
                        'ent_year': k['ent_year'], 'ent_month': k['ent_month']}},
            {'name': '网点（有报数）', 'columns': net_cols,
             'rows': [{'name': n['name'], 'year': n.get('year'), 'month': n.get('month'),
                       'ent_year': n.get('ent_year'), 'ent_month': n.get('ent_month')} for n in nets],
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
    rows = [{'branch': n['branch'], 'name': n['name'], 'lv1': n['lv'][0], 'lv2': n['lv'][1],
             'lv3': n['lv'][2], 'lv4': n['lv'][3], 'total': n['total'],
             'month': n['month'], 'day': n['day']} for n in d['nets']]
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


BUILDERS = {'online': build_online, 'salary': build_salary, 'wallet': build_wallet}
TITLES = {'online': '网点线上服务能力', 'salary': '薪管家聚薪行动', 'wallet': '数字人民币钱包'}


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
        last = 12 if sn == '支行' else 43
        for r in range(4, last if sn == '网点' else 12):
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
    by = {(r['name'] or '').replace('阜阳', ''): r for r in rows}
    # 模板里 A 列（支行）有纵向合并，先拆开再逐个网点填
    for rng in list(ws.merged_cells.ranges):
        if rng.min_col == 1 and rng.max_col == 1:
            ws.unmerge_cells(str(rng))
    seen = set()
    for r in range(3, 43):
        name = str(ws.cell(row=r, column=2).value or '').strip().replace('阜阳', '')
        rec = by.get(name)
        if not rec:
            continue
        ws.cell(row=r, column=1).value = rec.get('branch') or ''
        for c, k in ((3, 'lv1'), (4, 'lv2'), (5, 'lv3'), (6, 'lv4'),
                     (7, 'total'), (8, 'month'), (9, 'day')):
            ws.cell(row=r, column=c).value = rec.get(k) or 0
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue(), f"数字人民币个人钱包发展通报（{d['as_of'][5:7]}.{d['as_of'][8:10]}）.xlsx"


XLSX = {'online': online_xlsx, 'salary': salary_xlsx, 'wallet': wallet_xlsx}


def xlsx(kind: str, on: str | None = None) -> tuple[bytes, str]:
    fn = XLSX.get(kind)
    if not fn:
        raise RuntimeError(f'导出未实现：{kind}')
    return fn(on)

