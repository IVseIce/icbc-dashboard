#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""build_team_bases.py —— 从「官方成表」生成经理队伍两份导出母版。

用法（只在换版式时才需要跑，产物入库）：

    python scripts/build_team_bases.py

产物：

    src/report/assets/ck_base.xlsx   财客母版
    src/report/assets/yw_base.xlsx   远维母版

母版规则（HANDOFF 8.10：一律"拿原件当母版、只写数据格"，不要重画）：

  1. 只保留两个子表：`支行通报数据` + 明细（财客明细 / 远维明细）；
     辅助表（计算１ / ＶＬＯＯＫ / Sheet3 / 计算 / VLOOK / Sheet1）全部删掉。
  2. `支行通报数据`：**清掉 A 列名次与 C~AC 的公式/数值**，保留 B 列机构名
     （成表是固定行序，不是按名次排）、表头、合并区、条件格式、隐藏列 J。
  3. 明细：清掉数据行的值，保留三行表头（含合并）。
  4. 远维的 A14 手写备注「阜南支行因远维更换…」是当期说明，母版里清空。
  5. 远维明细末尾 14 行往上是隐藏的临时名单区，直接删行。

⚠️ 不要 `delete_cols`（会让条件格式 sqref 与公式列引用错位，HANDOFF 8.10-66）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'src' / 'report' / 'assets'
SRC = Path('/mnt/d/资料/ICBC/20261029财客远维')

CK_SRC = SRC / '2026年财富客户经理经营业绩通报（2026年10月21日）.xlsx'
YW_SRC = SRC / '2026年远维经理营销PK赛通报（2026年10月21日）.xlsx'

# 报表数据区（各成表一致）：第 5~13 行，第 A 列 + 第 C~AC 列
REPORT_ROWS = range(5, 14)
# B 列（机构名）保留，其余清空；J/K/L 本来就是空列，清不清都一样
KEEP_COLS = {2}


def clear_report(ws, last_col: int) -> None:
    for r in REPORT_ROWS:
        for c in range(1, last_col + 1):
            if c in KEEP_COLS:
                continue
            ws.cell(r, c).value = None
    # 总计行的 A 列是「－」：它是固定标签，不是算出来的，母版里要留住
    ws.cell(13, 1).value = '－'


def clear_detail(ws, first_row: int, ncols: int) -> None:
    for r in range(first_row, ws.max_row + 1):
        for c in range(1, ncols + 1):
            ws.cell(r, c).value = None


def drop_sheets(wb, keep: list[str]) -> None:
    for name in list(wb.sheetnames):
        if name not in keep:
            del wb[name]


def build_ck() -> Path:
    wb = openpyxl.load_workbook(CK_SRC)
    drop_sheets(wb, ['支行通报数据', '财客明细'])
    rep = wb['支行通报数据']
    clear_report(rep, 29)                       # A..AC
    det = wb['财客明细']
    clear_detail(det, 4, 88)                    # 数据列 A..CJ
    dst = OUT / 'ck_base.xlsx'
    wb.save(dst)
    return dst


def build_yw() -> Path:
    wb = openpyxl.load_workbook(YW_SRC)
    drop_sheets(wb, ['支行通报数据', '远维明细'])
    rep = wb['支行通报数据']
    clear_report(rep, 28)                       # A..AB
    rep.cell(14, 1).value = None                # 备注行（当期说明，母版里留空）
    det = wb['远维明细']
    # 末尾隐藏的临时名单区（15~25 行）不是数据，删掉
    if det.max_row > 13:
        det.delete_rows(14, det.max_row - 13)
    clear_detail(det, 4, 83)                    # 数据列 A..CE
    dst = OUT / 'yw_base.xlsx'
    wb.save(dst)
    return dst


def main() -> None:
    if not CK_SRC.exists() or not YW_SRC.exists():
        sys.exit(f'找不到官方成表：{SRC}')
    for f in (build_ck(), build_yw()):
        print(f'  {f.relative_to(ROOT)}  {f.stat().st_size/1024:.0f} KB')


if __name__ == '__main__':
    main()
