#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""对账脚本：把系统导出的通报 xlsx 与技能成表逐单元格比较。

用法：
  python scripts/check_report_parity.py            # 用内置的三组参考文件
输出差异数（0 = 完全一致），便于每次改动后回归。
"""
from __future__ import annotations

import sys
from pathlib import Path

import subprocess
import tempfile
import openpyxl

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'src' / 'server'))

import report  # noqa: E402

A = Path('/mnt/d/资料/ICBC/automations')
CASES = [
    ('online', '2026-10-17', A / '20261020_网点线上服务能力提升通报/out/阜阳分行“网点线上服务能力”提升通报（10.19）.xlsx', False),
    ('salary', '2026-10-21', A / '20261022_薪管家/out/薪管家通报1021.xlsx', False),
    ('wallet', '2026-10-19', A / '20261020_数字人民币钱包/out/数字人民币个人钱包发展通报（10月19日）.xlsx', False),
    ('deposit', '2026-10-15', A / '20261016_定期存款增长/out/定期存款增长（10.15）.xlsx', True),
    ('community', '2026-10-19', Path('/mnt/d/资料/ICBC/20260929企微/企微社群数据统计通报（10.19）.xlsx'), True),
]


def recalc(path: Path) -> Path:
    """成表里是公式时，用 LibreOffice 重算一遍拿到数值。"""
    out = Path(tempfile.mkdtemp())
    subprocess.run(['soffice', '--headless', '--convert-to', 'xlsx', '--outdir', str(out), str(path)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    cand = list(out.glob('*.xlsx'))
    return cand[0] if cand else path


def diff_sheets(a, b):
    wa, wb = a if hasattr(a, 'cell') else a, b
    diffs = []
    rows = max(wa.max_row, wb.max_row)
    cols = max(wa.max_column, wb.max_column)
    for r in range(1, rows + 1):
        for c in range(1, cols + 1):
            va, vb = wa.cell(row=r, column=c).value, wb.cell(row=r, column=c).value
            if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
                if abs(float(va) - float(vb)) <= 1e-9:
                    continue
            if va != vb:
                diffs.append((r, c, va, vb))
    return diffs


def main() -> int:
    bad = 0
    for kind, date, ref, need_recalc in CASES:
        if not ref.exists():
            print(f'{kind}: 跳过（参考文件不存在）')
            continue
        blob, _name = report.xlsx(kind, date)
        tmp = Path('/tmp') / f'parity_{kind}.xlsx'
        tmp.write_bytes(blob)
        use = recalc(ref) if need_recalc else ref
        ref_wb = openpyxl.load_workbook(use, data_only=need_recalc)
        our_wb = openpyxl.load_workbook(tmp, data_only=False)
        total = 0
        detail = []
        for sn in ref_wb.sheetnames:
            if sn not in our_wb.sheetnames:
                print(f'{kind}/{sn}: 系统侧不含该 sheet（原始表，跳过）')
                continue
            d = diff_sheets(ref_wb[sn], our_wb[sn])
            total += len(d)
            detail += [(sn,) + x for x in d[:3]]
        flag = 'OK' if total == 0 else f'{total} 处差异'
        print(f'{kind:8s} {date}  {flag}')
        for x in detail[:5]:
            print('   ', x)
        bad += 1 if total else 0
    return 1 if bad else 0


if __name__ == '__main__':
    raise SystemExit(main())
