#!/home/isee/.venvs/data-tools/bin/python
# -*- coding: utf-8 -*-
"""bootstrap.py —— 一次性把现存 automations 里的今天的源表灌进 Visualizations。

跑完就能用 serve.py 起服务；以后每天只用网页上的「导入数据」。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent / 'src'))

from datetime import datetime
from pathlib import Path

import viz

AUTO = Path('/mnt/d/资料/ICBC/automations')
QW = Path('/mnt/d/资料/ICBC/20260929企微/企微导出表')


def latest(suffix: str) -> Path | None:
    ds = sorted([d for d in AUTO.glob(f'*{suffix}') if d.is_dir() and d.name[:8].isdigit()],
                key=lambda d: d.name[:8])
    return ds[-1] if ds else None


def source_files(suffix: str, exts=('.xlsx', '.xls', '.csv')) -> list[Path]:
    d = latest(suffix)
    if not d:
        return []
    return sorted(p for p in (d / 'source').iterdir()
                  if p.suffix.lower() in exts and not p.name.startswith('~$'))


def today_files() -> dict[str, list[Path]]:
    backups = sorted(QW.glob('成员群聊数据统计2*.xlsx'))
    return {
        'sbqb': source_files('_数字人民币钱包'),
        'xgj': source_files('_薪管家'),
        'dqzz': source_files('_定期存款增长'),
        'xsfw': source_files('_网点线上服务能力提升通报'),
        'qwsq': backups[-2:],
    }


def backfill_trends() -> list[str]:
    """历史趋势点位：数币/薪管家只有汇总数，没有源表，直接补轻量快照。"""
    done = []
    # 数币：历次 data.json 的 total
    snaps = {s['as_of'] for s in viz.load_snapshots('sbqb')}
    for p in sorted(AUTO.glob('*_数字人民币钱包/data.json'), key=lambda p: p.name[:8]):
        try:
            d = json.loads(p.read_text('utf-8'))
            iso = d['date_dot'].replace('.', '-')
            y, m, dd = iso.split('-')
            iso = f'{y}-{int(m):02d}-{int(dd):02d}'
        except Exception:
            continue
        if iso in snaps:
            continue
        viz.save_snapshot('sbqb', iso, {'as_of': iso, 'total': d['total'], 'partial': True})
        done.append(f'sbqb {iso} {d["total"]}')
    # 薪管家：历次通报 xlsx 的「总计」行
    import openpyxl
    snaps = {s['as_of'] for s in viz.load_snapshots('xgj')}
    for p in sorted(AUTO.glob('*_薪管家/out/*.xlsx'), key=lambda p: p.name):
        if p.name.startswith('~$'):
            continue
        try:
            wb = openpyxl.load_workbook(p, data_only=True)
            ws = wb['支行']
            rows = list(ws.iter_rows(values_only=True))
            tot = next(r for r in rows if str(r[0]).strip() in ('总计', '合计'))
            import re as _re
            mm = _re.search(r'(20\d{2})\.(\d{2})\.(\d{2})', str(rows[0][0]))
            if not mm:
                continue
            iso = '-'.join(mm.groups())
        except Exception:
            continue
        if iso in snaps:
            continue
        viz.save_snapshot('xgj', iso, {'as_of': iso, 'total': round(tot[1] or 0, 2),
                                       'month_total': round(tot[2] or 0, 2),
                                       'ent_year': int(tot[3] or 0), 'ent_month': int(tot[4] or 0),
                                       'partial': True})
        done.append(f'xgj {iso}')
    # 线上服务：历次 data.json 的加权动户率
    snaps = {s['as_of'] for s in viz.load_snapshots('xsfw')}
    for p in sorted(AUTO.glob('*_网点线上服务能力提升通报/data.json'), key=lambda p: p.name[:8]):
        try:
            d = json.loads(p.read_text('utf-8'))
            rs = [r for r in d['rows'] if r.get('branch')]
            w = sum(r['D'] for r in rs) or 1
            iso = d['day_date']
        except Exception:
            continue
        if iso in snaps:
            continue
        viz.save_snapshot('xsfw', iso, {
            'as_of': iso, 'partial': True,
            'nets': [{'branch': r['branch'], 'cust': r['D'],
                      'day_rate': round(r['B'] or 0, 4), 'month_rate': round(r['C'] or 0, 4),
                      'add_today': int(r.get('F') or 0), 'add_month': int(r.get('G') or 0)} for r in rs]})
        done.append(f'xsfw {iso}')
    return done


def main() -> None:
    out = []
    for line, files in today_files().items():
        missing = [str(f) for f in files if not f.exists()]
        if not files:
            out.append({'line': line, 'ok': False, 'error': '没有找到源表'}); continue
        if missing:
            out.append({'line': line, 'ok': False, 'error': f'缺文件: {missing}'})
            continue
        blobs = [(f.name, f.read_bytes()) for f in files]
        r = viz.do_import(line, blobs)
        out.append({k: r.get(k) for k in ('ok', 'line', 'data_date', 'error', 'notes')})
        print(line, r.get('ok'), r.get('data_date'), str(r.get('error') or '')[:120])
    print('--- 回填历史趋势')
    for x in backfill_trends():
        print('  ', x)
    data = viz.assemble()
    print('--- 已组装：', json.dumps(data['meta'], ensure_ascii=False))
    print('生成时间', datetime.now().strftime('%H:%M:%S'))


if __name__ == '__main__':
    main()
