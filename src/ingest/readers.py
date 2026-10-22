#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""readers.py —— 统一读取层：不信任扩展名，按内容判断真实格式。

支持的容器：xlsx(zip) / xls(OLE) / csv、txt(纯文本)
处理三类现实问题：
  1. 内容与扩展名不一致（最常见的：CSV 被另存成 .xlsx）
  2. CSV 编码不一（UTF-8 BOM / GBK / UTF-16）
  3. 分隔符不一（逗号 / 制表符 / 分号 / 单列整行文本）

对上游（各模块的解析器）只做最小侵入：
  - normalize() 返回「扩展名与内容一致」的 (name, blob)，其余不动；
  - read_table() 给新写的解析器直接用（返回二维表）。
"""
from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

ZIP_MAGIC = b'PK\x03\x04'
OLE_MAGIC = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'
OLE_MAGIC_ALT = b'\xd0\xcf\x11\xe0'

TEXT_EXTS = ('.csv', '.txt', '.tsv')
XLSX_EXTS = ('.xlsx', '.xlsm')
XLS_EXTS = ('.xls',)


# ---------------------------------------------------------------- 嗅探
def sniff(blob: bytes) -> str:
    """返回 'xlsx' | 'xls' | 'text' | 'unknown'。"""
    if not blob:
        return 'unknown'
    head = blob[:8]
    if head.startswith(ZIP_MAGIC) or blob[:2] == b'PK':
        return 'xlsx'
    if head.startswith(OLE_MAGIC) or head.startswith(OLE_MAGIC_ALT):
        return 'xls'
    # 文本：前 4KB 里没有 NUL，且能按常见编码解开
    sample = blob[:4096]
    if b'\x00' in sample:
        # UTF-16 文本会带 NUL，但成对出现
        if b'\x00' in sample[1::2]:
            return 'text'
        return 'unknown'
    return 'text'


def decode_text(blob: bytes) -> tuple[str, str]:
    for enc in ('utf-8-sig', 'gb18030', 'utf-16', 'big5'):
        try:
            return blob.decode(enc), enc
        except (UnicodeDecodeError, UnicodeError):
            continue
    return blob.decode('utf-8', 'replace'), 'utf-8/replace'


def parse_rows(text: str) -> list[list[str]]:
    """CSV/TSV → 二维表；自动猜分隔符；单列整行文本保持单列。"""
    sample = '\n'.join(text.splitlines()[:20])
    delim = ','
    try:
        delim = csv.Sniffer().sniff(sample, delimiters=',;\t|').delimiter
    except csv.Error:
        if '\t' in sample:
            delim = '\t'
        elif ';' in sample:
            delim = ';'
    return [row for row in csv.reader(io.StringIO(text), delimiter=delim)]


def to_xlsx(rows: list[list], sheet: str = 'Sheet1') -> bytes:
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet[:31] or 'Sheet1'
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------- 对外
def normalize(filename: str, blob: bytes) -> tuple[str, bytes, dict]:
    """只修正扩展名，不改内容（内容由各解析器按真实格式读）。

    - 文本内容却叫 .xlsx/.xls → 改名 .csv
    - xlsx 内容却叫 .csv/.xls → 改名 .xlsx
    - xls 内容却叫 .xlsx/.csv → 改名 .xls
    """
    ext = Path(filename).suffix.lower()
    kind = sniff(blob)
    info = {'declared': ext, 'detected': kind, 'changed': False}
    want = None
    if kind == 'text' and ext in XLSX_EXTS + XLS_EXTS:
        want = '.csv'
    elif kind == 'xlsx' and ext in TEXT_EXTS + XLS_EXTS:
        want = '.xlsx'
    elif kind == 'xls' and ext in XLSX_EXTS + TEXT_EXTS:
        want = '.xls'
    if want and want != ext:
        filename = str(Path(filename).with_suffix(want))
        info.update(changed=True, to=want)
    return filename, blob, info


def text_to_xlsx(blob: bytes) -> bytes:
    """兜底：把文本内容的表转成真正的 xlsx（给只认 xlsx 的解析器用）。"""
    return to_xlsx(parse_rows(decode_text(blob)[0]))


def read_table(path_or_bytes, filename: str | None = None) -> list[list]:
    """给解析器用的通用读表：xlsx / xls / csv 都能读成二维表（取第一个 sheet）。"""
    if isinstance(path_or_bytes, (bytes, bytearray)):
        blob, name = bytes(path_or_bytes), (filename or 'a.xlsx')
    else:
        p = Path(path_or_bytes)
        blob, name = p.read_bytes(), p.name
    kind = sniff(blob)
    if kind == 'text':
        return parse_rows(decode_text(blob)[0])
    if kind == 'xls':
        import xlrd
        book = xlrd.open_workbook(file_contents=blob)
        sh = book.sheet_by_index(0)
        return [[sh.cell_value(r, c) for c in range(sh.ncols)] for r in range(sh.nrows)]
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(blob), data_only=True)
    ws = wb.worksheets[0]
    return [list(r) for r in ws.iter_rows(values_only=True)]


def sheet_names(path_or_bytes, filename: str | None = None) -> list[str]:
    if isinstance(path_or_bytes, (bytes, bytearray)):
        blob, name = bytes(path_or_bytes), (filename or 'a.xlsx')
    else:
        p = Path(path_or_bytes)
        blob, name = p.read_bytes(), p.name
    if sniff(blob) == 'xls':
        import xlrd
        return xlrd.open_workbook(file_contents=blob).sheet_names()
    if sniff(blob) == 'text':
        return ['csv']
    import openpyxl
    return openpyxl.load_workbook(io.BytesIO(blob), read_only=True).sheetnames


def sheets(path_or_bytes, filename: str | None = None) -> list[tuple[str, list[list]]]:
    """统一按 sheet 读：返回 [(sheet_name, rows)]；CSV 视为单个 sheet。"""
    if isinstance(path_or_bytes, (bytes, bytearray)):
        blob, name = bytes(path_or_bytes), (filename or 'a.xlsx')
    else:
        p = Path(path_or_bytes)
        blob, name = p.read_bytes(), p.name
    kind = sniff(blob)
    if kind == 'text':
        return [('csv', parse_rows(decode_text(blob)[0]))]
    if kind == 'xls':
        import xlrd
        book = xlrd.open_workbook(file_contents=blob)
        out = []
        for sn in book.sheet_names():
            sh = book.sheet_by_name(sn)
            out.append((sn, [[sh.cell_value(r, c) for c in range(sh.ncols)] for r in range(sh.nrows)]))
        return out
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(blob), data_only=True)
    return [(ws.title, [list(r) for r in ws.iter_rows(values_only=True)]) for ws in wb.worksheets]


if __name__ == '__main__':
    import json
    import sys
    for f in sys.argv[1:]:
        p = Path(f)
        blob = p.read_bytes()
        print(json.dumps({'file': p.name, 'sniff': sniff(blob),
                          'normalize': normalize(p.name, blob)[2]}, ensure_ascii=False))
