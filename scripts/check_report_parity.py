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
    # yika 的成表里 F/J（社保卡当日/本周）和 Q/R（养老金）是公式，两边都要重算再比
    ('yika', '2026-10-25', Path('/mnt/d/资料/ICBC/20261027一卡一户/10.08一卡一户.xlsx'), True),
    # jiepan：成表是"人工剔除 3 户后的整月口径"，所以要用整月区间（EXPORT_ARGS 里给）。
    # 官方 Sheet6 的 B 列是外部链接公式（=[1]网点草稿!B45），必须让 LibreOffice 重算才有值；
    # 官方 G12（合计资金承接率）公式范围只到 4902 行，本身有错，跳过该格。
    ('jiepan', '2026-10-25', Path('/mnt/d/资料/ICBC/20261028定期承接/10.25到期承接率.xlsx'), True),
]

# 每条通报导出时的额外参数（目前只有 jiepan 用得到）
EXPORT_ARGS = {
    'jiepan': {'start': '2026-10-01', 'end': '2026-10-25'},
}
# 已知的"官方本身有错"的单元格：(kind, sheet, row, col) —— 跳过不比
KNOWN_BAD = {('jiepan', 'Sheet7', 12, 7)}
# 按"名称对齐"比数值的通报（行顺序两边不同，逐格比没意义）：
#   jiepan 的 Sheet6 按网点排序、Sheet7 按支行排序；官方 Sheet7 的 A 列顺序本身是错的
#   （它把排名算在固定的 H16:I23 上，数据行又被重排过，`C4=I16` 这类引用整体错位），
#   我们按 RANK 重算名次排序，所以行顺序必然不同 —— 比"每家网点/支行的数值"才对。
ALIGN_BY_NAME = {
    'jiepan': {
        'Sheet6': {'key_col': 2, 'cmp': {4: 'D', 5: 'E', 6: 'F'}},
        'Sheet7': {'key_col': 1, 'cmp': {4: 'D', 5: 'E', 6: 'F', 7: 'G'}, 'last_row': 11},
    },
}


def diff_by_name(ref_ws, our_ws, spec) -> list:
    """按名称列建索引后逐项比数值（行顺序可以不同）。"""
    kc = spec['key_col']
    cmp_cols = spec['cmp']
    last = spec.get('last_row') or min(ref_ws.max_row, our_ws.max_row)

    def index(ws):
        out = {}
        for r in range(3, last + 1):
            v = ws.cell(row=r, column=kc).value
            if isinstance(v, str) and v.strip():
                out[v.strip()] = r
        return out

    ri, oi = index(ref_ws), index(our_ws)
    diffs = []
    for name, rr in ri.items():
        if name not in oi:
            diffs.append((rr, kc, name, '（系统侧缺该行）'))
            continue
        orow = oi[name]
        for c, lbl in cmp_cols.items():
            va = ref_ws.cell(row=rr, column=c).value
            vb = our_ws.cell(row=orow, column=c).value
            if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
                if abs(float(va) - float(vb)) <= 1e-9:
                    continue
                diffs.append((rr, c, f'{name} {lbl}: {va:.9f}', f'{vb:.9f}'))
            elif (va is None) != (vb is None):
                diffs.append((rr, c, f'{name} {lbl}: {va}', vb))
    return diffs


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


def _seed_jiepan(as_of_date: str) -> None:
    """把 jiepan 的原始源表按「排除名单配置」重新导入一次，
    等价于人工在源表里把那几行的两列变化量改成 0。"""
    import json
    src = Path('/mnt/d/资料/ICBC/20261028定期承接/定期承接1025.xlsx')
    if not src.exists():
        return
    cfg = Path(__file__).resolve().parent.parent / 'src' / 'report' / 'assets' / 'jiepan_exclude.json'
    excl = []
    if cfg.exists():
        excl = json.loads(cfg.read_text('utf-8')).get(as_of_date) or []
    from ingest import jiepan as jp
    _d, snap = jp.parse_files([(src.name, src.read_bytes())], exclude=excl)
    snap['line'] = 'jp'
    import viz
    viz.save_snapshot('jp', snap['as_of'], snap)


def main() -> int:
    _seed_jiepan('2026-10-25')
    bad = 0
    for kind, date, ref, need_recalc in CASES:
        if not ref.exists():
            print(f'{kind}: 跳过（参考文件不存在）')
            continue
        args = EXPORT_ARGS.get(kind) or {}
        blob, _name = report.xlsx(kind, date, **args)
        tmp = Path('/tmp') / f'parity_{kind}.xlsx'
        tmp.write_bytes(blob)
        use = recalc(ref) if need_recalc else ref
        ref_wb = openpyxl.load_workbook(use, data_only=need_recalc)
        # 我方成表里也可能带公式（yika 的 F/J、Q/R 照母版留着），这种情况也要重算
        ours_rec = recalc(tmp) if any(
            isinstance(c.value, str) and str(c.value).startswith('=')
            for ws in openpyxl.load_workbook(tmp).worksheets
            for row in ws.iter_rows() for c in row) else tmp
        our_wb = openpyxl.load_workbook(ours_rec, data_only=bool(need_recalc))
        total = 0
        detail = []
        for sn in ref_wb.sheetnames:
            if sn not in our_wb.sheetnames:
                print(f'{kind}/{sn}: 系统侧不含该 sheet（原始表，跳过）')
                continue
            spec = (ALIGN_BY_NAME.get(kind) or {}).get(sn)
            if spec:
                d = diff_by_name(ref_wb[sn], our_wb[sn], spec)
            else:
                d = [x for x in diff_sheets(ref_wb[sn], our_wb[sn])
                     if (kind, sn, x[0], x[1]) not in KNOWN_BAD]
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
