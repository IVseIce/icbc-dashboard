#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""build_yika_assets.py —— 生成「一卡一户」模块的两份静态资产（一次性，改口径时重跑）。

  src/report/assets/yika_targets.json   网点顺序 / 所属支行 / 当日目标（固定值）
  src/report/assets/yika_base.xlsx      样式母版：通报 + 社保卡 + 养老金 三张表，
                                        清掉数据但与格式、合并、条件格式原样保留

来源：D:\\资料\\ICBC\\20261027一卡一户\\10.08一卡一户.xlsx（用户给的最终成表）

用法：
    python scripts/build_yika_assets.py [--src <成表路径>]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import openpyxl

PROJECT = Path(__file__).resolve().parent.parent
ASSETS = PROJECT / 'src' / 'report' / 'assets'
DEFAULT_SRC = Path('/mnt/d/资料/ICBC/20261027一卡一户/10.08一卡一户.xlsx')

# 通报 sheet 的行区间（网点行、小计行、分行行）
FIRST_ROW, LAST_ROW = 4, 52
TITLE_CELL = 'A1'


def read_layout(ws) -> dict:
    """从通报 sheet 提取网点顺序 / 支行 / 目标。列 A 是合并的支行名，需要向下填充。"""
    nets, branches = [], []
    branch = None
    for r in range(FIRST_ROW, LAST_ROW + 1):
        a = ws.cell(r, 1).value
        b = ws.cell(r, 2).value
        if a is not None:
            branch = str(a).strip()
        if b:                                            # 网点行
            nets.append({
                'name': str(b).strip(),
                'branch': branch,
                'target_sb': ws.cell(r, 4).value,        # D 当日目标（社保卡）
                'target_yl': ws.cell(r, 8).value,        # H 当日目标（个人养老金）
            })
        elif a and '小计' in str(a):
            branches.append({'name': str(a).replace('小计', '').strip(), 'row': r})
    return {'nets': nets, 'branches': branches}


def clear_data(wb) -> None:
    """清掉数据，保留表头 / 网点名 / 公式 / 合并 / 格式 / 条件格式。

    **不能整段清空**：社保卡 F/J、养老金 Q/R 是公式，养老金 G/M 列是网点名 ——
    清掉以后成表就散了（第一版踩过，辅助 sheet 全成空白）。
    """
    ws = wb['通报']
    for r in range(FIRST_ROW, LAST_ROW + 1):
        for c in range(3, 13):                           # C..L：8 个数字 + 4 个比率
            ws.cell(r, c).value = None
    ws[TITLE_CELL].value = '“一卡一户”日通报（待导入）'

    # 社保卡：只清「累计值」四列（B/C 上周日、D/E 前一日、H/I 当日）；
    # F / J 是 =B+C-D-E / =B+C-H-I 的公式，A 列是网点名 —— 都留着
    sb = wb['社保卡']
    for r in range(4, 46):
        for c in (2, 3, 4, 5, 8, 9):
            sb.cell(r, c).value = None

    # 养老金：每块 3 列数据（累计/当日新增/本年新增），A / G / M 是网点名，Q/R 是公式
    yl = wb['养老金']
    for r in range(4, 44):
        for c in (2, 3, 4, 8, 9, 10, 14, 15, 16):
            yl.cell(r, c).value = None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', default=str(DEFAULT_SRC))
    a = ap.parse_args()
    src = Path(a.src)
    if not src.exists():
        raise SystemExit(f'找不到成表：{src}')

    wb = openpyxl.load_workbook(src)
    layout = read_layout(wb['通报'])
    print(f"网点 {len(layout['nets'])} 个，支行 {len(layout['branches'])} 个")
    tgt = {n['target_sb'] for n in layout['nets']} | {n['target_yl'] for n in layout['nets']}
    print(f'目标值取值：{sorted(t for t in tgt if t is not None)}'
          f'（社保合计 {sum(n["target_sb"] or 0 for n in layout["nets"])}'
          f' / 养老合计 {sum(n["target_yl"] or 0 for n in layout["nets"])}）')

    out_json = ASSETS / 'yika_targets.json'
    out_json.write_text(json.dumps(layout, ensure_ascii=False, indent=1), 'utf-8')
    print('已写入', out_json.relative_to(PROJECT))

    clear_data(wb)
    out_xlsx = ASSETS / 'yika_base.xlsx'
    wb.save(out_xlsx)
    print('已写入', out_xlsx.relative_to(PROJECT))

    # 自检：清完之后条件格式还在不在
    chk = openpyxl.load_workbook(out_xlsx)
    ws = chk['通报']
    n_rules = sum(len(v) for v in ws.conditional_formatting._cf_rules.values())
    print(f'条件格式规则 {n_rules} 条 · 合并区 {len(ws.merged_cells.ranges)} 个 · '
          f'数字格式样例 E4={ws["E4"].number_format!r} K4={ws["K4"].number_format!r}')


if __name__ == '__main__':
    main()
