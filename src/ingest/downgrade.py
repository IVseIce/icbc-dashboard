#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""downgrade.py —— 降级挽回：客编级资产/存款变化 → 支行 / 网点汇总与排行。

源数据只有一张表：
  明细：客编, 基期资产, 基期存款, 基期月日均资产, 基期月日均存款,
        末期资产, 末期存款, 末期月日均资产, 末期月日均存款, 数据日期
客编 → 支行/网点 的映射是**固定的**，已内置在 src/report/assets/downgrade_map.json，
不再需要每次上传（新增客编时才需要更新那份 json）。

口径（2026-10-26 与业务确认；2026-11-05 修订期间规则）：
  * 用**时点**列：本旬提升 = 末期 − 基期（元 → 万元）
  * 数据日期为基期；末期 = 基期 + 6
  * **通报期间 = 数据日期 ~ 数据日期+6**（含首尾共 7 天）：
    数据日期 9.13 → 通报写 9.13-9.19。不再整体后移一天。
    导入时也可手动指定 xxx-xxx（见 `parse(period=…)`），指定值与
    "数据日期" 不一致时由前端弹确认；这里只如实记录并在 `_notes` 里说明。
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
SPAN_DAYS = 6                     # 通报期间 = 数据日期 ~ 数据日期 + 6（含首尾 7 天）
UNIT = 10000.0                    # 元 → 万元
PERIOD_FORMAT = '%Y-%m-%d'        # 通报期间在库里/接口里的写法


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


def default_period(base: date) -> tuple[date, date]:
    """通报期间的默认值：数据日期（基期）~ 数据日期 + 6，含首尾共 7 天。"""
    return base, base + timedelta(days=SPAN_DAYS)


def resolve_period(base: date, period_start=None, period_end=None) -> dict:
    """定「通报期间」。见文件头的口径说明。

    规则（2026-11-05 与业务确认）：
      * 都不指定 → 数据日期 ~ 数据日期+6（现有 9.13 的数据就是 9.13-9.19）
      * 只给一端 → 另一端按 7 天补齐（给 start 则 end = start+6；给 end 则 start = end-6）
      * 两端都给 → 原样使用；首 > 尾 直接报错，跨度也不强制 7 天（业务可能真有长假）
      * 起点与数据日期不一致**不报错**——那是导入页该弹的确认，这里只如实记录并回话，
        由 `matches_base` / `_notes` 让用户看得见。
    """
    s = _date(period_start) if period_start else None
    e = _date(period_end) if period_end else None
    if period_start and s is None:
        raise ValueError(f'通报开始日期无法解析：{period_start}')
    if period_end and e is None:
        raise ValueError(f'通报结束日期无法解析：{period_end}')

    custom = bool(s or e)
    if s is None and e is None:
        s, e = default_period(base)
    elif s is None:
        s = e - timedelta(days=SPAN_DAYS)
    elif e is None:
        e = s + timedelta(days=SPAN_DAYS)

    if s > e:
        raise ValueError(f'通报期间开始 {s.isoformat()} 晚于结束 {e.isoformat()}')

    span = (e - s).days + 1
    return {
        'start': s.isoformat(), 'end': e.isoformat(),
        'label': f'{s.month:02d}{s.day:02d}-{e.month:02d}{e.day:02d}',
        'label_cn': f'{s.month}月{s.day}日-{e.month}月{e.day}日',
        'base_date': base.isoformat(),
        'span_days': span,
        'custom': custom,                       # 是否手动指定过（含只给一端）
        # 起点 = 数据日期？否 → 前端提示"与表里的数据日期不符"
        'matches_base': s == base,
        'default_label': _default_label(base),  # 默认期间，供前端"设为默认"用
    }


def _default_label(base: date) -> str:
    s, e = default_period(base)
    return f'{s.month}月{s.day}日-{e.month}月{e.day}日'


def normalize_period(snap: dict) -> dict:
    """把老版本存下来的快照期间换成现行规则（读的时候顺手做，不必重新导入）。

    0.1.12 及以前的期间是「数据日期后移一天 ~ +7」，如基期 9.13 → 0914-0920。
    现行规则是「数据日期 ~ +6」（9.13-9.19），且期间字段多了 span_days / matches_base。
    所以**缺这些字段的就是老快照**，按数据日期重算；新快照原样返回。
    """
    if not isinstance(snap, dict):
        return snap
    per = snap.get('period')
    base = _date(snap.get('base_date') or snap.get('as_of'))
    if base is None:
        return snap
    if isinstance(per, dict) and 'span_days' in per and 'matches_base' in per:
        return snap                          # 已经是现行规则存的
    out = dict(snap)
    out['period'] = resolve_period(base)
    return out


def parse(data_rows: list[list], map_rows: list[list] | None = None,
          as_of: str | None = None, mapping: dict | None = None,
          period_start: str | None = None, period_end: str | None = None) -> dict:
    """明细行 + 映射（不传则用内置的 downgrade_map.json）。返回快照 dict。

    `period_start` / `period_end` 是导入时手动指定的通报期间（可只给一端），
    不传就按「数据日期 ~ 数据日期+6」。
    """
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

    period = resolve_period(base, period_start, period_end)

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
    notes = [
        f'客编 {len(mapping)} 个，参与统计 {len(customers)} 个'
        + (f'，未匹配 {missing} 个' if missing else '')
        + (f'，非营业网点 {outside} 个已排除' if outside else ''),
        f'基期 {base.isoformat()} → 通报期间 {period["start"]} ~ {period["end"]}'
        + ('（手动指定）' if period['custom'] else '（数据日期 +6）'),
    ]
    if not period['matches_base']:
        notes.append(
            f'注意：通报期间从 {period["start"]} 开始，与表里的数据日期 {base.isoformat()} 不一致')
    return {
        'as_of': base.isoformat(), 'as_of_cn': f'{base.month}月{base.day}日',
        'base_date': base.isoformat(),
        'period': period,
        'branches': branches, 'nets': nets,
        'top_nets': nets[:5],
        'totals': totals,
        'customers': customers,
        '_notes': notes,
    }


def probe_period(files, as_of: str | None = None) -> dict:
    """只读「数据日期」，用来在导入页预填通报期间（不做汇总，很快）。

    读不出日期时抛 ValueError —— 调用方（导入页）把它当提示，不拦提交。
    """
    from ingest import readers

    for name, blob in files:
        rows = readers.read_table(blob, name)
        head = ' '.join(str(c) for c in (rows[0] if rows else [])[:12])
        if '基期' not in head or '末期' not in head:
            continue
        di = _header_index(rows, ('客编', '基期资产', '末期资产'))
        if di is None:
            continue
        col = {str(c).strip() if c is not None else '': i for i, c in enumerate(rows[di])}
        if '数据日期' not in col:
            raise ValueError('明细表里没有「数据日期」列')
        dates = set()
        for row in rows[di + 1:]:
            if not row or row[col['客编']] in (None, ''):
                continue
            d = _date(row[col['数据日期']])
            if d:
                dates.add(d)
        if not dates:
            raise ValueError('明细表里读不到「数据日期」')
        if len(dates) > 1:
            raise ValueError(f'明细表里有多个数据日期：{sorted(d.isoformat() for d in dates)}，一次只能导一期')
        base = _date(as_of) if as_of else next(iter(dates))
        return {'ok': True, 'file': name, 'base_date': base.isoformat(),
                'period': resolve_period(base)}
    raise ValueError('没有找到明细表（需含 客编 / 基期资产 / 末期资产 列）')


def parse_files(files, as_of: str | None = None,
                period_start: str | None = None,
                period_end: str | None = None) -> tuple[str, dict]:
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

    snap = parse(data_tbl, extra_map, as_of=as_of,
                 period_start=period_start, period_end=period_end)
    snap['_files'] = used
    if extra_map is None:
        snap['_notes'].append('客编映射使用内置表（src/report/assets/downgrade_map.json）')
    return snap['as_of'], snap
