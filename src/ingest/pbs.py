#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""pbs.py —— 「私人银行」解析：客编日均资产明细 → 支行 + 网点两层。

## 源表（一张明细表，每行一个达标客户）

必含列（按名字找，允许前后空格）：

    归属支行名称 / 归属网点名称 / 客户编号
    本月月日均资产     ← 资产口径（元）
    本月存款日均       ← 存款口径（元）

选含列（判定产品渗透用，缺了就当 0）：

    本月基金日均 / 本月理财产品（零售）日均 / 本月理财产品（私人银行）日均
    本月银保通日均

## 时点

**源表里没有日期**，必须由调用方给（文件名识别 / 手填）。三个时点各有用途：

    as_of      当天（出通报那天）
    year_end   上年末（如 2025-12-31）：算「比年初」
    quarter    上季度末（如 2026-09-30）：算「比上季度末」

`as_of` 落一个快照（`pbs`）；`year_end` / `quarter` 也各落一个快照（`pbs` 线，
只是 `partial=True`），这样"导入一次就留在库里"，以后只导当天即可。

## 支行归属（踩过，别改）

源表的「归属支行名称」有 12 个值，其中 4 个不是 8 家支行之一，必须映射：

    阜阳牡丹支行   → 颍泉
    阜阳文峰支行   → 颍州
    阜阳城建支行   → 颍州
    阜阳汇通支行   → 颍东

其余按名字前缀（颍州/颍泉/颍东/界首/临泉/阜南/颍上/太和）归。
**这是对着成表验算确认的**：颍州 38 = 营业室 20 + 城建 6 + 文峰 12；
颍泉 37 = 营业室 32 + 牡丹 5；颍东 19 = 营业室 15 + 汇通 4。

## 网点清单

固定 40 个（含当期 0 户的岳家湖、颍上十字街），清单与"网点→支行"存在
`report/assets/pb_nets.json`（从成表提取）。成表行序、小计行都按它来。

## 产品销售（U~AB 列）

**不在这里算**。7 个指标（遴选余额 / 遴选四季度增量 / 快贷提款金额 /
信托已出单 / 信托已销售 / 保险已出单 / 保险已销售）是人工维护的，
存 `store` 的 setting（见 `pbs_sales` 相关函数），导入时合进快照。
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from . import readers

PROJECT = Path(__file__).resolve().parent.parent
NETS_PATH = PROJECT / 'report' / 'assets' / 'pb_nets.json'

# 源表列名
C_BRANCH = '归属支行名称'
C_NET = '归属网点名称'
C_CUST = '客户编号'
C_ASSET = '本月月日均资产'
C_DEP = '本月存款日均'
C_FUND = '本月基金日均'
C_WMP_RETAIL = '本月理财产品（零售）日均'
C_WMP_PB = '本月理财产品（私人银行）日均'
C_INS = '本月银保通日均'

BRANCHES = ['颍州', '颍泉', '颍东', '界首', '临泉', '阜南', '颍上', '太和']

# 源表「归属支行」不是 8 家支行时的映射（成表口径）
BRANCH_ALIAS = {
    '阜阳牡丹支行': '颍泉',
    '阜阳文峰支行': '颍州',
    '阜阳城建支行': '颍州',
    '阜阳汇通支行': '颍东',
}

# 产品销售 7 项（人工维护），键名与前端/报表共用
SALES_KEYS = [
    ('xl_bal', '遴选余额'),
    ('xl_q4', '遴选四季度增量'),
    ('kd_amt', '快贷提款金额'),
    ('xt_out', '信托已出单'),
    ('xt_sold', '信托已销售'),
    ('bx_out', '保险已出单'),
    ('bx_sold', '保险已销售'),
]


# ---------------------------------------------------------------- 配置
def nets_config() -> dict:
    """网点清单 + 网点→支行（固定 40 个，含当期 0 户的）。"""
    return json.loads(NETS_PATH.read_text('utf-8'))


def branch_of(raw: str) -> str | None:
    """源表「归属支行名称」→ 8 家支行之一。认不出返回 None。"""
    s = str(raw or '').strip()
    if not s:
        return None
    if s in BRANCH_ALIAS:
        return BRANCH_ALIAS[s]
    n = s.replace('阜阳', '')
    for b in BRANCHES:
        if n.startswith(b):
            return b
    return None


def net_of(raw: str) -> str:
    """网点名归一（去掉"阜阳"前缀，统一成全名）。"""
    s = str(raw or '').strip()
    return s


def _num(v) -> float:
    """数值列可能混字符串（'780.76'、带千分位），统一转 float。"""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(',', '').replace('，', '')
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _col_idx(header: list, name: str) -> int | None:
    """按列名找下标；先精确、再"去空格 + 子串"。"""
    want = name.strip()
    for i, h in enumerate(header):
        if str(h or '').strip() == want:
            return i
    for i, h in enumerate(header):
        if want in str(h or '').replace(' ', ''):
            return i
    return None


# ---------------------------------------------------------------- 日期识别
DATE_PATTERNS = [
    # 连续 8 位：20261024 / 20251231
    (re.compile(r'(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)'), 'ymd'),
    # 带分隔：2026-10-24 / 2026.10.24 / 2026_10_24 / 2026年10月24日
    (re.compile(r'(20\d{2})[-_.年](\d{1,2})[-_.月](\d{1,2})日?'), 'ymd'),
    # 202512（年月）→ 当月末
    (re.compile(r'(?<!\d)(20\d{2})(0[1-9]|1[0-2])(?!\d)'), 'ym'),
    # 10.24 / 10-24 / 10月24日（无年，按当年）
    (re.compile(r'(?<!\d)(\d{1,2})[-_.月](\d{1,2})日?(?!\d)'), 'md'),
    # 1024 / 1225（四位纯数字）
    (re.compile(r'(?<!\d)(\d{2})(\d{2})(?!\d)'), 'md4'),
]


def date_from_name(name: str, default_year: int | None = None) -> str | None:
    """从文件名认日期。

    认得：`20261024` / `2026-10-24` / `2026.10.24` / `10.24` / `1024` / `20251231`。
    不带年的按 `default_year`（默认今年）。认不出返回 None（调用方据此让用户手填）。
    """
    s = str(name or '')
    stem = re.sub(r'\.(xlsx|xls|csv)$', '', s, flags=re.I)
    year = default_year or dt.date.today().year

    for rx, kind in DATE_PATTERNS:
        for m in rx.finditer(stem):
            try:
                if kind == 'ymd':
                    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    got = dt.date(y, mo, d)
                elif kind == 'ym':
                    y, mo = int(m.group(1)), int(m.group(2))
                    nxt = dt.date(y + 1, 1, 1) if mo == 12 else dt.date(y, mo + 1, 1)
                    got = nxt - dt.timedelta(days=1)
                elif kind == 'md4':
                    mo, d = int(m.group(1)), int(m.group(2))
                    got = dt.date(year, mo, d)
                else:
                    mo, d = int(m.group(1)), int(m.group(2))
                    got = dt.date(year, mo, d)
            except ValueError:
                continue
            return got.isoformat()
    return None


def quarter_end(iso: str) -> str:
    """上季度末：3/6/9/12 月末往前推一个季度。"""
    d = dt.date.fromisoformat(iso)
    q_end_months = [3, 6, 9, 12]
    m = d.month
    # 本月所在的"上一个已结束季度末"
    for qm in reversed(q_end_months):
        if qm < m:
            return dt.date(d.year, qm, month_last_day(d.year, qm)).isoformat()
    # 1 月 → 去年 12 月末
    return dt.date(d.year - 1, 12, 31).isoformat()


def month_last_day(y: int, m: int) -> int:
    nxt = dt.date(y + 1, 1, 1) if m == 12 else dt.date(y, m + 1, 1)
    return (nxt - dt.timedelta(days=1)).day


# ---------------------------------------------------------------- 解析
def parse(rows: list[list], as_of: str | None = None) -> dict:
    """一张明细表 → 快照 payload（不含产品销售，由上层合进来）。

    返回：
        {'as_of', 'as_of_cn', 'branches': [...8], 'nets': [...40], 'totals': {...},
         'branch_raw': {...}, 'customers': n, 'notes': [...]}
    """
    if not rows:
        raise ValueError('明细表是空的')
    header = list(rows[0])
    i_b = _col_idx(header, C_BRANCH)
    i_n = _col_idx(header, C_NET)
    i_c = _col_idx(header, C_CUST)
    i_a = _col_idx(header, C_ASSET)
    i_d = _col_idx(header, C_DEP)
    miss = [n for n, i in ((C_BRANCH, i_b), (C_NET, i_n), (C_ASSET, i_a), (C_DEP, i_d)) if i is None]
    if miss:
        raise ValueError('明细表缺少列：' + '、'.join(miss))
    i_f = _col_idx(header, C_FUND)
    i_wr = _col_idx(header, C_WMP_RETAIL)
    i_wp = _col_idx(header, C_WMP_PB)
    i_i = _col_idx(header, C_INS)

    cfg = nets_config()
    net_branch = {n['name']: n['branch'] for n in cfg['nets']}
    order = [n['name'] for n in cfg['nets']]

    agg = {}          # net -> dict
    for name in order:
        agg[name] = {'name': name, 'branch': net_branch[name], 'cust': 0,
                     'asset': 0.0, 'dep': 0.0, 'fund': 0, 'wmp': 0, 'ins': 0}

    notes = []
    seen = set()
    unknown_branch, unknown_net = {}, {}
    rows_used = 0
    for r in rows[1:]:
        if not r or all(v in (None, '') for v in r[:6]):
            continue
        cid = str(r[i_c]).strip() if i_c is not None and i_c < len(r) and r[i_c] else ''
        if cid:
            if cid in seen:           # 同一客编重复出现只算一次
                continue
            seen.add(cid)
        raw_b = r[i_b] if i_b < len(r) else None
        raw_n = r[i_n] if i_n < len(r) else None
        b = branch_of(raw_b)
        n = net_of(raw_n)
        if b is None:
            unknown_branch[str(raw_b or '(空)')] = unknown_branch.get(str(raw_b or '(空)'), 0) + 1
            continue
        if n not in agg:
            # 网点不在固定清单里：并到支行层，网点层不出现（记一条提示）
            unknown_net[n] = unknown_net.get(n, 0) + 1
            agg.setdefault('__extra__', {'branch': b, 'cust': 0, 'asset': 0.0, 'dep': 0.0})['cust'] += 1
            agg['__extra__']['asset'] += _num(r[i_a])
            agg['__extra__']['dep'] += _num(r[i_d])
            rows_used += 1
            continue
        rec = agg[n]
        rec['cust'] += 1
        rec['asset'] += _num(r[i_a])
        rec['dep'] += _num(r[i_d])
        if i_f is not None and _num(r[i_f]) > 0:
            rec['fund'] += 1
        if i_wr is not None or i_wp is not None:
            v = 0.0
            if i_wr is not None:
                v += _num(r[i_wr])
            if i_wp is not None:
                v += _num(r[i_wp])
            if v > 0:
                rec['wmp'] += 1
        if i_i is not None and _num(r[i_i]) > 0:
            rec['ins'] += 1
        rows_used += 1

    if unknown_branch:
        notes.append('这些归属支行认不出，已跳过：' +
                     '、'.join(f'{k}（{v}）' for k, v in sorted(unknown_branch.items())))
    if unknown_net:
        notes.append('这些网点不在固定清单里，只并入支行合计：' +
                     '、'.join(f'{k}（{v}）' for k, v in sorted(unknown_net.items())))

    nets = [agg[n] for n in order]
    branches = []
    for b in BRANCHES:
        mine = [n for n in nets if n['branch'] == b]
        extra = agg.get('__extra__') if agg.get('__extra__', {}).get('branch') == b else None
        branches.append({
            'name': b,
            'nets': len(mine),
            'active_nets': sum(1 for n in mine if n['cust'] > 0),
            'cust': sum(n['cust'] for n in mine) + (extra['cust'] if extra else 0),
            'asset': sum(n['asset'] for n in mine) + (extra['asset'] if extra else 0),
            'dep': sum(n['dep'] for n in mine) + (extra['dep'] if extra else 0),
            'fund': sum(n['fund'] for n in mine),
            'wmp': sum(n['wmp'] for n in mine),
            'ins': sum(n['ins'] for n in mine),
        })

    totals = {
        'cust': sum(b['cust'] for b in branches),
        'asset': sum(b['asset'] for b in branches),
        'dep': sum(b['dep'] for b in branches),
        'nets': len(nets),
        'active_nets': sum(1 for n in nets if n['cust'] > 0),
        'zero_nets': [n['name'] for n in nets if n['cust'] == 0],
    }

    out = {
        'as_of': as_of,
        'as_of_cn': cn_date(as_of) if as_of else '',
        'branches': branches,
        'nets': nets,
        'totals': totals,
        'customers': rows_used,
        'notes': notes,
    }
    return out


def cn_date(iso: str | None) -> str:
    if not iso:
        return ''
    d = dt.date.fromisoformat(iso)
    return f'{d.year}年{d.month}月{d.day}日'


# ---------------------------------------------------------------- 导入入口
def parse_files(files, as_of: str | None = None) -> tuple[str, dict]:
    """只收一张明细表（产品销售由上层从 stting 读入后合进来）。"""
    table = None
    used = []
    for name, blob in files:
        rows = readers.read_table(blob, name)
        if not rows:
            used.append({'name': name, 'role': '空表，跳过'})
            continue
        head = ' '.join(str(c or '') for c in rows[0][:40])
        if C_BRANCH in head and C_ASSET in head:
            if table is not None:
                raise ValueError('只支持一张明细表，这次给了两张：'
                                 f'{used[0]["name"]}、{name}')
            table = rows
            used.append({'name': name, 'role': '私银客编明细'})
        else:
            used.append({'name': name, 'role': '未识别（缺「归属支行名称」或「本月月日均资产」）'})
    if table is None:
        raise ValueError('没找到私银明细表：表头应有「归属支行名称」「归属网点名称」「本月月日均资产」')

    if not as_of:
        guess = date_from_name(used[0]['name'])
        if not guess:
            raise ValueError('文件名里认不出日期，请手动指定"数据日期"')
        as_of = guess
    snap = parse(table, as_of=as_of)
    snap['_files'] = used
    return as_of, snap
