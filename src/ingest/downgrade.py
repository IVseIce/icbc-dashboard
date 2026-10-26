#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""downgrade.py —— 降级挽回：客编级资产/存款变化 → 支行 / 网点汇总与排行。

源数据只有一张表：
  明细：客编, 基期资产, 基期存款, 基期月日均资产, 基期月日均存款,
        末期资产, 末期存款, 末期月日均资产, 末期月日均存款, 数据日期
客编 → 支行/网点 的映射是**固定的**，已内置在 src/report/assets/downgrade_map.json，
不再需要每次上传（新增客编时才需要更新那份 json）。

口径（2026-10-26 与业务确认）：
  * 用**时点**列：本旬提升 = 末期 − 基期（元 → 万元）
  * 数据日期为基期；末期 = 基期 + 6；**通报期间整体后移一天**：
    基期 9.13 → 通报写 9.14-9.20
  * 网均 = 支行合计 ÷ 该支行网点数
  * 综合评价(1:1) = (网均资产提升 + 网均存款提升) ÷ 2
  * 营销先锋排行 = 按 (资产提升 + 存款提升) 降序（等价于按两项评价之和）
  * 网点数只算实体网点：名字以"支行/营业室"结尾（排除"…运行管理部"）
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

MAP_PATH = Path(__file__).resolve().parent.parent / 'report' / 'assets' / 'downgrade_map.json'
EXCLUDE_SUFFIX = ('部',)          # 运行管理部这类非营业网点
REPORT_SHIFT = 1                  # 通报期间相对数据日期整体后移的天数
SPAN_DAYS = 6                     # 末期 = 基期 + 6
UNIT = 10000.0                    # 元 → 万元


def _num(v) -> float:
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace(',', '').replace('，', '').strip()
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _date(v) -> date | None:
    from datetime import datetime
    if isinstance(v, datetime):        # 注意：datetime 是 date 的子类，必须先判
        return v.date()
    if isinstance(v, date):
        return v
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d', '%Y%m%d'):
        try:
            return datetime.strptime(s[:19], fmt).date()
        except ValueError:
            continue
    return None


def _header_index(rows: list[list], must: tuple[str, ...]) -> int | None:
    for i, row in enumerate(rows[:5]):
        cells = {str(c).strip() for c in row if c is not None}
        if all(m in cells for m in must):
            return i
    return None


_MAP_CACHE: dict | None = None


def builtin_mapping() -> dict[str, tuple[str, str]]:
    """内置的 客编 → (支行, 网点) 映射。"""
    global _MAP_CACHE
    if _MAP_CACHE is None:
        rows = json.loads(MAP_PATH.read_text('utf-8'))
        _MAP_CACHE = {r[0]: (r[1], r[2]) for r in rows if r and r[0]}
    return _MAP_CACHE


def is_entity_net(name: str) -> bool:
    """实体营业网点：以"支行 / 营业室"结尾。"""
    n = (name or '').strip()
    return bool(n) and not n.endswith(EXCLUDE_SUFFIX) and (n.endswith('支行') or n.endswith('营业室'))


def parse(data_rows: list[list], map_rows: list[list] | None = None,
          as_of: str | None = None, mapping: dict | None = None) -> dict:
    """明细行 + 映射（不传则用内置的 downgrade_map.json）。返回快照 dict。"""
    di = _header_index(data_rows, ('客编', '基期资产', '末期资产'))
    if di is None:
        raise ValueError('明细表缺少「客编 / 基期资产 / 末期资产」列')

    dh = [str(c).strip() if c is not None else '' for c in data_rows[di]]
    col = {name: i for i, name in enumerate(dh)}

    if mapping is None:
        mapping = builtin_mapping() if map_rows is None else {}
        if map_rows is not None:
            mi = _header_index(map_rows, ('客编', '支行', '网点'))
            if mi is None:
                raise ValueError('映射表缺少「客编 / 支行 / 网点」列')
            mcol = {name: i for i, name in enumerate(
                str(c).strip() if c is not None else '' for c in map_rows[mi])}
            for row in map_rows[mi + 1:]:
                if not row or row[mcol['客编']] in (None, ''):
                    continue
                key = str(row[mcol['客编']]).strip()
                if key:
                    mapping[key] = (str(row[mcol['支行']]).strip(), str(row[mcol['网点']]).strip())

    # 网点 → 支行（只保留实体网点）
    nets_of: dict[str, set] = defaultdict(set)
    branch_of_net: dict[str, str] = {}
    for _k, (b, n) in mapping.items():
        if is_entity_net(n):
            nets_of[b].add(n)
            branch_of_net[n] = b

    base_dates = set()
    br_asset = defaultdict(float)
    br_dep = defaultdict(float)
    br_cust = defaultdict(int)
    net_asset = defaultdict(float)
    net_dep = defaultdict(float)
    net_cust = defaultdict(int)
    customers = []
    missing = 0
    outside = 0

    for row in data_rows[di + 1:]:
        if not row or row[col['客编']] in (None, ''):
            continue
        key = str(row[col['客编']]).strip()
        hit = mapping.get(key)
        if not hit:
            missing += 1
            continue
        branch, net = hit
        d = _date(row[col['数据日期']]) if '数据日期' in col else None
        if d:
            base_dates.add(d)

        a = _num(row[col['末期资产']]) - _num(row[col['基期资产']])
        p = _num(row[col['末期存款']]) - _num(row[col['基期存款']])
        if not is_entity_net(net):
            outside += 1
            continue

        br_asset[branch] += a
        br_dep[branch] += p
        br_cust[branch] += 1
        net_asset[net] += a
        net_dep[net] += p
        net_cust[net] += 1
        customers.append({'ke': key, 'branch': branch, 'net': net,
                          'asset': round(a / UNIT, 4), 'dep': round(p / UNIT, 4)})

    if not base_dates:
        raise ValueError('明细表里读不到「数据日期」')
    if len(base_dates) > 1:
        raise ValueError(f'明细表里有多个数据日期：{sorted(base_dates)}，一次只能导一期')
    base = _date(as_of) if as_of else next(iter(base_dates))
    if base is None:
        raise ValueError(f'数据日期无法解析：{as_of}')

    span_start = base + timedelta(days=REPORT_SHIFT)
    span_end = base + timedelta(days=SPAN_DAYS + REPORT_SHIFT)

    branches = []
    for branch in nets_of:
        n = len(nets_of[branch])
        asset = round(br_asset[branch] / UNIT, 4)
        dep = round(br_dep[branch] / UNIT, 4)
        asset_avg = round(asset / n, 4) if n else 0.0
        dep_avg = round(dep / n, 4) if n else 0.0
        branches.append({
            'name': branch.replace('支行营业室', ''), 'full': branch,
            'nets': n, 'customers': br_cust[branch],
            'asset': asset, 'asset_avg': asset_avg,
            'dep': dep, 'dep_avg': dep_avg,
            'score': round((asset_avg + dep_avg) / 2, 4),
        })
    branches.sort(key=lambda x: -x['score'])
    for i, b in enumerate(branches, 1):
        b['rank'] = i
        # 与成表一致：前 2 名黄、后 2 名绿，其余不填
        b['hl'] = 'yellow' if i <= 2 else ('green' if i > len(branches) - 2 else '')

    nets = []
    for net, branch in branch_of_net.items():
        asset = round(net_asset[net] / UNIT, 4)
        dep = round(net_dep[net] / UNIT, 4)
        nets.append({'name': net, 'branch': branch.replace('支行营业室', ''),
                     'customers': net_cust[net], 'asset': asset, 'dep': dep,
                     'sum': round(asset + dep, 4)})
    nets.sort(key=lambda x: -x['sum'])
    for i, n in enumerate(nets, 1):
        n['rank'] = i
        n['hl'] = 'red' if i <= 3 else ('green' if i > len(nets) - 3 else '')

    total_nets = sum(len(v) for v in nets_of.values())
    total_asset = round(sum(br_asset.values()) / UNIT, 4)
    total_dep = round(sum(br_dep.values()) / UNIT, 4)
    totals = {
        'nets': total_nets,
        'customers': sum(net_cust.values()),
        'asset': total_asset, 'dep': total_dep,
        'asset_avg': round(total_asset / total_nets, 4) if total_nets else 0.0,
        'dep_avg': round(total_dep / total_nets, 4) if total_nets else 0.0,
    }
    totals['score'] = round((totals['asset_avg'] + totals['dep_avg']) / 2, 4)

    customers.sort(key=lambda c: c['asset'])          # 降级最多的排前面
    return {
        'as_of': base.isoformat(), 'as_of_cn': f'{base.month}月{base.day}日',
        'base_date': base.isoformat(),
        'period': {
            'start': span_start.isoformat(), 'end': span_end.isoformat(),
            'label': f'{span_start.month:02d}{span_start.day:02d}-{span_end.month:02d}{span_end.day:02d}',
            'label_cn': f'{span_start.month}月{span_start.day}日-{span_end.month}月{span_end.day}日',
        },
        'branches': branches, 'nets': nets,
        'top_nets': nets[:5],
        'totals': totals,
        'customers': customers,
        '_notes': [
            f'客编 {len(mapping)} 个，参与统计 {len(customers)} 个'
            + (f'，未匹配 {missing} 个' if missing else '')
            + (f'，非营业网点 {outside} 个已排除' if outside else ''),
            f'基期 {base.isoformat()} → 通报期间 {span_start.isoformat()} ~ {span_end.isoformat()}',
        ],
    }


def parse_files(files, as_of: str | None = None) -> tuple[str, dict]:
    """只收一张明细表；映射用内置的。若误传了映射表，自动忽略。"""
    from ingest import readers

    data_tbl = None
    used = []
    extra_map = None
    for name, blob in files:
        rows = readers.read_table(blob, name)
        head = ' '.join(str(c) for c in (rows[0] if rows else [])[:12])
        if '基期' in head and '末期' in head:
            data_tbl = rows
            used.append({'name': name, 'role': '客编资产/存款明细'})
        elif '支行' in head and '网点' in head:
            extra_map = rows
            used.append({'name': name, 'role': '映射表已内置，忽略该文件'})
        else:
            used.append({'name': name, 'role': '未识别（忽略）'})

    if data_tbl is None:
        raise ValueError('没有找到明细表（需含 客编 / 基期资产 / 末期资产 列）')

    snap = parse(data_tbl, extra_map, as_of=as_of)
    snap['_files'] = used
    if extra_map is None:
        snap['_notes'].append('客编映射使用内置表（src/report/assets/downgrade_map.json）')
    return snap['as_of'], snap
