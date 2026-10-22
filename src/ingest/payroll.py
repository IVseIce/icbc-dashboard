#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""payroll.py —— 代发明细（月度、网点维度）解析。

源文件：一张工作簿多个 sheet，每个 sheet 一个月份（25.12 / 26.09 …）。
列名在不同月份会变（资产、留存率、产品渗透、流失预警时有时无），
所以按「列名规则」取数，缺列就跳过，不报错。

输出：data/snapshots/dfmx/<YYYY-MM-DD>.json（月末日期作 as_of）
      {as_of, month, nets:[{netno, branch, name, comps, cust, amt_month, amt_year,
                             new_year, tier:{...}, lost, warn}], totals:{...}, cols:[...]}
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import openpyxl

PROJECT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT / 'src'))

import viz  # noqa: E402

MONTHS = {'25.12': '2025-12', '26.01': '2026-01', '26.02': '2026-02', '26.03': '2026-03',
          '26.05': '2026-05', '26.06': '2026-06', '26.07': '2026-07', '26.08': '2026-08',
          '26.09': '2026-09'}


def num(v) -> float:
    if v is None or v == '':
        return 0.0
    try:
        return float(str(v).replace(',', '').strip())
    except ValueError:
        return 0.0


def net_info() -> tuple[dict, dict]:
    m = viz.skill('icbc-sbqb')
    return m.load_netno(m._bundled_netno())


def pick_col(hdr: list[str], *patterns) -> int | None:
    for p in patterns:
        rx = re.compile(p)
        for i, h in enumerate(hdr):
            if h and rx.search(h):
                return i
    return None


def parse_sheet(rows, month: str, no2info: dict) -> dict:
    if not rows:
        return {}
    hdr = [str(h).strip() if h is not None else '' for h in rows[0]]
    c_no = pick_col(hdr, r'^网点号$', r'网点号')
    c_cust = pick_col(hdr, r'其中：代发工资客户', r'^代发客户$')
    c_year = pick_col(hdr, r'^全年代发金额$', r'其中：代发工资金额')
    c_month = pick_col(hdr, r'当月代发')
    c_new_y = pick_col(hdr, r'是否当年新增')
    c_new_m = pick_col(hdr, r'是否当月新增')
    c_tier = pick_col(hdr, r'代发分层')
    c_lost = pick_col(hdr, r'^是否流失$')
    c_warn = pick_col(hdr, r'^是否预警$')
    c_asset = pick_col(hdr, r'资产$')
    c_rate = pick_col(hdr, r'金融资产留存率')
    c_cc = pick_col(hdr, r'^信用卡$')
    c_bind = pick_col(hdr, r'三方绑卡')
    c_sb = pick_col(hdr, r'^社保卡$')
    c_pension = pick_col(hdr, r'^养老金$')
    c_fund = pick_col(hdr, r'^基金$')
    c_ins = pick_col(hdr, r'^保险$')
    c_loan = pick_col(hdr, r'融e借')
    c_mb = pick_col(hdr, r'手机银行')

    nets: dict[str, dict] = {}
    for r in rows[1:]:
        if not r:
            continue
        raw = str(r[c_no]).strip() if c_no is not None and r[c_no] else ''
        if not raw:
            continue
        code = raw[-4:]
        info = no2info.get(code)
        if not info:
            continue
        br, name = info
        rec = nets.setdefault(code, {
            'netno': code, 'branch': br, 'name': name,
            'comps': 0, 'cust': 0.0, 'amt_month': 0.0, 'amt_year': 0.0,
            'new_year': 0, 'new_month': 0, 'lost': 0, 'warn': 0,
            'assets': 0.0, 'rate_sum': 0.0, 'rate_n': 0,
            'pen': {'信用卡': 0, '三方绑卡': 0, '社保卡': 0, '养老金': 0,
                    '基金': 0, '保险': 0, '融e借': 0, '手机银行': 0},
            'tier': {},
        })
        rec['comps'] += 1
        rec['cust'] += num(r[c_cust]) if c_cust is not None else 0
        rec['amt_year'] += num(r[c_year]) if c_year is not None else 0
        if c_new_y is not None and str(r[c_new_y]).strip() == '新增':
            rec['new_year'] += 1
        if c_new_m is not None and str(r[c_new_m]).strip() == '新增':
            rec['new_month'] += 1
        if c_tier is not None and r[c_tier]:
            t = str(r[c_tier]).strip()
            rec['tier'][t] = rec['tier'].get(t, 0) + 1
        if c_lost is not None and str(r[c_lost]).strip() == '是':
            rec['lost'] += 1
        if c_warn is not None and str(r[c_warn]).strip() == '是':
            rec['warn'] += 1
        if c_asset is not None:
            rec['assets'] += num(r[c_asset])
        if c_rate is not None and num(r[c_rate]) > 0:
            rec['rate_sum'] += num(r[c_rate]); rec['rate_n'] += 1
        for key, ci in (('信用卡', c_cc), ('三方绑卡', c_bind), ('社保卡', c_sb), ('养老金', c_pension),
                        ('基金', c_fund), ('保险', c_ins), ('融e借', c_loan), ('手机银行', c_mb)):
            if ci is not None:
                rec['pen'][key] += int(num(r[ci]))

    for rec in nets.values():
        rec['rate'] = round(rec['rate_sum'] / rec['rate_n'], 4) if rec['rate_n'] else None
        rec.pop('rate_sum'); rec.pop('rate_n')

    out = sorted(nets.values(), key=lambda x: -x['amt_year'])
    totals = {
        'comps': sum(n['comps'] for n in out),
        'cust': sum(n['cust'] for n in out),
        'amt_month': round(sum(n['amt_month'] for n in out), 2),
        'amt_year': round(sum(n['amt_year'] for n in out), 2),
        'new_year': sum(n['new_year'] for n in out),
        'new_month': sum(n['new_month'] for n in out),
        'lost': sum(n['lost'] for n in out),
        'warn': sum(n['warn'] for n in out),
        'assets': round(sum(n['assets'] for n in out), 2),
        'pen': {k: sum(n['pen'][k] for n in out) for k in out[0]['pen']} if out else {},
        'tier': {},
    }
    for n in out:
        for t, c in n['tier'].items():
            totals['tier'][t] = totals['tier'].get(t, 0) + c
    have = [k for k, v in {
        '资产': totals['assets'], '留存率': any(n['rate'] for n in out),
        '产品渗透': any(totals['pen'].values()), '流失预警': totals['lost'] + totals['warn'],
    }.items() if v]
    return {'as_of': month + '-28' if month.endswith(('-02',)) else month + '-30',
            'month': month, 'nets': out, 'totals': totals, 'cols': have}


def main() -> None:
    src = Path(sys.argv[1] if len(sys.argv) > 1 else '/mnt/d/资料/ICBC/20261022代发明细/代发明细.xlsx')
    no2info, _ = net_info()
    from ingest import readers
    saved = []
    for title, rows in readers.sheets(src):
        month = MONTHS.get(title)
        if not month:
            m = re.search(r'(\d{2})[.\-年](\d{1,2})', title + ' ' + src.name)
            if not m:
                continue
            yy = int(m.group(1))
            month = f'20{yy:02d}-{int(m.group(2)):02d}' if yy < 100 else f'{yy}-{int(m.group(2)):02d}'
        snap = parse_sheet(rows, month, no2info)
        if not snap.get('nets'):
            continue
        f = viz.paths()['snapshots'] / 'dfmx' / f'{snap["as_of"]}.json'
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(snap, ensure_ascii=False), encoding='utf-8')
        saved.append((snap['month'], len(snap['nets']), snap['totals']['amt_year']))
        if not title or title == 'csv':
            break
    print(json.dumps({'ok': True, 'saved': saved}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
