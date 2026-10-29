#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""xlsx_keep.py —— 保存工作簿时保住母版里的图片（纯 Python，不依赖 Pillow）。

背景（0.1.7.1 的真实事故）：
  openpyxl 读写 xlsx 里的图片**依赖 Pillow**。内网机的运行时不带 Pillow
  （`vendor/pylib` 只有纯 Python 的 openpyxl / xlrd / PyYAML，与架构无关），
  于是 `load_workbook()` 读出来的 `ws._images` 是空的、`save()` 之后
  `xl/media/*` 与 `xl/drawings/*` 全部消失 —— **私银发展情况表的横幅图片就是这样丢的**，
  而且本机有 Pillow，永远复现不出来。

做法：先用 openpyxl 正常保存，再拿母版（也就是 load 的那个 xlsx 模板）做比对，
把它有、产物没有的图片相关部件原样补回去，并补齐三处引用：
  1. `[Content_Types].xml`：`Default Extension="jpeg|png"` + `Override .../drawingN.xml`
  2. `xl/worksheets/sheetN.xml`：补 `<drawing r:id="..."/>`
  3. `xl/worksheets/_rels/sheetN.xml.rels`：补对应 relationship
图片本身（`xl/media/*`、`xl/drawings/*`）直接从母版复制。

只在"产物里没有图片部件、母版里有"时才动手，所以本机（有 Pillow）走的是原路径，
不会重复注入。母版没有图片时这是空操作。
"""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

DRAWING_REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing'
IMAGE_CT = {'jpeg': 'image/jpeg', 'jpg': 'image/jpeg', 'png': 'image/png',
            'gif': 'image/gif', 'bmp': 'image/bmp', 'emf': 'image/x-emf', 'wmf': 'image/x-wmf'}


def _is_media(n: str) -> bool:
    return n.startswith('xl/media/')


def _is_drawing(n: str) -> bool:
    return n.startswith('xl/drawings/')


def _sheet_index(name: str) -> int | None:
    m = re.fullmatch(r'xl/worksheets/sheet(\d+)\.xml', name)
    return int(m.group(1)) if m else None


def _next_rid(rels_xml: str) -> str:
    used = {int(x) for x in re.findall(r'Id="rId(\d+)"', rels_xml)}
    i = 1
    while i in used:
        i += 1
    return f'rId{i}'


def save_like(tpl: Path | str | None, wb) -> bytes:
    """保存 wb，并把母版 `tpl` 里 openpyxl 丢掉的图片部件补回来。

    tpl 传 None 或母版不存在/无图片时，等价于普通的 `wb.save()`。
    """
    buf = io.BytesIO()
    wb.save(buf)
    out = buf.getvalue()
    if not tpl:
        return out
    tpl = Path(tpl)
    if not tpl.exists():
        return out

    with zipfile.ZipFile(tpl) as tz:
        tpl_names = tz.namelist()
        tpl_media = [n for n in tpl_names if _is_media(n)]
        tpl_draw = [n for n in tpl_names if _is_drawing(n)]
        if not tpl_media and not tpl_draw:
            return out                     # 母版本来就没图

        with zipfile.ZipFile(io.BytesIO(out)) as oz:
            out_names = oz.namelist()
            if any(_is_media(n) or _is_drawing(n) for n in out_names):
                return out                 # 已经有图（本机有 Pillow 的情况），不重复注入
            out_data = {n: oz.read(n) for n in out_names}

        # 母版里哪些 sheet 挂了 drawing、用的是哪个 rId
        tpl_sheet_drawing: dict[int, str] = {}
        for n in tpl_names:
            si = _sheet_index(n)
            if si is None:
                continue
            m = re.search(rb'<drawing[^>]*r:id="(rId\d+)"', tz.read(n))
            if m:
                tpl_sheet_drawing[si] = m.group(1).decode()

        add: dict[str, bytes] = {}
        for n in tpl_media + tpl_draw:
            add[n] = tz.read(n)

        # 1) [Content_Types].xml
        ct = out_data.get('[Content_Types].xml', b'').decode('utf-8')
        for n in tpl_media:
            ext = n.rsplit('.', 1)[-1].lower()
            if ext in IMAGE_CT and f'Extension="{ext}"' not in ct:
                ct = ct.replace('</Types>',
                                f'<Default Extension="{ext}" ContentType="{IMAGE_CT[ext]}"/></Types>')
        for n in tpl_draw:
            if n.endswith('.xml') and '/_rels/' not in n:
                part = '/' + n
                if f'PartName="{part}"' not in ct:
                    ct = ct.replace(
                        '</Types>',
                        f'<Override PartName="{part}" ContentType='
                        f'"application/vnd.openxmlformats-officedocument.drawing+xml"/></Types>')
        out_data['[Content_Types].xml'] = ct.encode('utf-8')

        # 2) 每个有图的 sheet：补 <drawing> + rels
        for si, tpl_rid in tpl_sheet_drawing.items():
            sheet = f'xl/worksheets/sheet{si}.xml'
            blob = out_data.get(sheet)
            if blob is None:
                continue
            xml = blob.decode('utf-8')
            if '<drawing' in xml:
                continue
            rels_name = f'xl/worksheets/_rels/sheet{si}.xml.rels'
            rels = out_data.get(rels_name, b'').decode('utf-8')
            # 母版里那个 rId 指向的 drawing 目标
            tpl_rels = tz.read(f'xl/worksheets/_rels/sheet{si}.xml.rels').decode('utf-8') \
                if f'xl/worksheets/_rels/sheet{si}.xml.rels' in tpl_names else ''
            m = re.search(rf'<Relationship[^>]*Id="{tpl_rid}"[^>]*Target="([^"]+)"', tpl_rels)
            target = m.group(1) if m else f'/xl/drawings/drawing1.xml'
            if not rels:
                rid = 'rId1'
                rels = ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
                        'relationships"></Relationships>')
            else:
                rid = _next_rid(rels)
            rels = rels.replace(
                '</Relationships>',
                f'<Relationship Type="{DRAWING_REL}" Target="{target}" Id="{rid}"/>'
                '</Relationships>')
            out_data[rels_name] = rels.encode('utf-8')
            # <drawing> 必须排在 </worksheet> 之前。
            # 注意要把 r 命名空间**就地声明**：openpyxl 生成的 worksheet 根节点可能没带
            # xmlns:r，只写 r:id 会让严格的解析器报 "unbound prefix"（openpyxl 自己重读就会炸）。
            xml = xml.replace(
                '</worksheet>',
                '<drawing xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/'
                f'relationships" r:id="{rid}"/></worksheet>')
            out_data[sheet] = xml.encode('utf-8')

        out_data.update(add)

    # 重打包：把 [Content_Types].xml 放第一个（有些老版本 Excel 认这个顺序）
    dst = io.BytesIO()
    with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as zw:
        order = ['[Content_Types].xml'] + [n for n in out_data if n != '[Content_Types].xml']
        for n in order:
            zw.writestr(n, out_data[n])
    return dst.getvalue()


def add_image_safe(ws, path: Path | str, anchor: str | None = None):
    """没有 Pillow 时 `openpyxl.drawing.image.Image` 会抛 ImportError；这里吞掉。

    返回 True/False 表示是否真的加上了（调用方可以据此决定要不要在文档里提"图片缺失"）。
    """
    try:
        from openpyxl.drawing.image import Image as XLImage
    except ImportError:
        return False
    try:
        img = XLImage(str(path))
    except Exception:
        return False
    if anchor:
        img.anchor = anchor
    ws.add_image(img)
    return True
