#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""yika.py —— 「一卡一户」解析：社保卡 + 个人养老金两张源表 → 按日累计值。

## 口径（对着成表 `通报` 反算验证过）

网点维度（40 个网点，8 家支行小计 + 分行合计）。两个产品各 3 个数字 + 2 个派生：

    社保卡   C 当日开户      = 累计(当日) − 累计(前一日)
             D 当日目标      = 固定值（4 或 6，见 yika_targets.json）
             E 日平台达成率  = C / D
             F 本周开户      = 累计(当日) − 累计(上周末)
    个人养老金（结构同上，G/H/I/J）
    K 当日合计完成率    = (G + C) / (D + H)
    L 合计周任务完成率  = (J + F) / (H * 2 * 6)

**「累计」是什么**：不是户数，而是
  * 社保卡：`柜台新增卡数量（本年累计）` + `批量开户新增卡（本年累计）`
  * 养老金：`本年新增`
两者都是"单调递增的年内累计数"，相减得到区间新增。**不要用「累计开户数」**（那是存量，
含去年及以前，相减跨年就错）。

## 日期口径

    数据块 = 周五 + 周六 + 周日（周日出通报）；其余日子单独一块
    当日    = 出通报那天（周日时代表 周五~周日 三天合计）
    前一日  = 上一个数据块的末日。周日 → 周四；周二 → 周一；周一 → 上周日
    上周末  = 本周（周一~周日）开始前的那个周日 = 当日 − 7 天（周日当天时）
              周一 → 当日 − 1 天；其余 → 当日所在周的上一周周日

当「前一日」与「上周末」是同一天（周一）时，只用到 2 个日期，本周新增 == 当日新增。

## 为什么按日存累计值

每天只导 1 张社保卡 + 1 张养老金（多日期表一次能把历史全存进来），
出通报时按需从库里取三个日期。这样不必每天凑三张表，也能补历史。
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from . import readers

PROJECT = Path(__file__).resolve().parent.parent
TARGETS_PATH = PROJECT / 'report' / 'assets' / 'yika_targets.json'

# 成表里的固定口径
WEEK_DAYS = 6          # L 列分母里的 ×6（周任务按 6 个计分日折算；用户确认值）

# 社保卡源表的两个"本年累计"列名（可能带日期后缀，用前缀匹配）
SB_COLS = ('柜台新增卡数量（本年累计）', '批量开户新增卡（本年累计）')

# 养老金每块的三个子列
YL_SUB = ('累计开户数', '当日新增', '本年新增')


# ---------------------------------------------------------------- 固定配置
def load_targets() -> dict:
    return json.loads(TARGETS_PATH.read_text('utf-8'))


# ---------------------------------------------------------------- 日期
def block_of(d: dt.date) -> tuple[dt.date, dt.date]:
    """这一天的数据块 (起, 止)。周五~周日是一个块，其余当天一个块。"""
    if d.weekday() == 6:                       # 周日
        return d - dt.timedelta(days=2), d
    if d.weekday() == 4:                       # 周五
        return d, d + dt.timedelta(days=2)
    if d.weekday() == 5:                       # 周六
        return d - dt.timedelta(days=1), d + dt.timedelta(days=1)
    return d, d


def prev_block_end(d: dt.date) -> dt.date:
    """「前一日」= 上一个数据块的末日。周日 → 周四。"""
    start, _ = block_of(d)
    return start - dt.timedelta(days=1)


def week_start_sunday(d: dt.date) -> dt.date:
    """「上周末」= 本周（周一~周日）开始前的那个周日。

    周日 2026-10-25 → 10-18；周一 10-26 → 10-25；周四 10-22 → 10-18。
    """
    monday = d - dt.timedelta(days=d.weekday())
    return monday - dt.timedelta(days=1)


def plan_dates(d: dt.date) -> dict:
    """给出这一天出通报需要的三个日期（可能只有两个）。"""
    prev = prev_block_end(d)
    last_sun = week_start_sunday(d)
    start, end = block_of(d)
    dates = [last_sun, prev, d]
    uniq = sorted({x.isoformat() for x in dates})
    return {
        'as_of': d.isoformat(), 'block_start': start.isoformat(), 'block_end': end.isoformat(),
        'cur': d.isoformat(), 'prev': prev.isoformat(), 'week_end': last_sun.isoformat(),
        'dates': uniq, 'merged': prev == last_sun,
        'days': (end - start).days + 1,
    }


# ---------------------------------------------------------------- 解析：社保卡
def _num(v) -> float:
    """明细里的数字常混字符串与千分位（'1,033'），统一转 float。"""
    if v is None or v == '':
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace(',', '').replace('，', '').strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def _find_date_in_text(s: str, year: int | None = None) -> dt.date | None:
    """从文本里抠日期：`2026年10月26日` / `2026-10-26` / `本年累计10.22` / `10.22` 都认。

    没有年份的（`10.22`）按当前年补；跨年（12 月表、1 月导入）由调用方给 year 兜底。
    """
    txt = str(s)
    m = re.search(r'(20\d{2})\s*[-_.年/]\s*(\d{1,2})\s*[-_.月/]\s*(\d{1,2})', txt)
    if m:
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    m = re.search(r'(?<!\d)(\d{1,2})\s*[-_.月]\s*(\d{1,2})(?!\d)', txt)
    if m:
        try:
            return dt.date(year or dt.date.today().year, int(m.group(1)), int(m.group(2)))
        except ValueError:
            pass
    return None


def parse_sika(rows: list[list], fallback: dt.date | None = None) -> dict:
    """社保卡（借记卡发卡统计报表）→ {date, cum: {网点: 累计新增}}。

    表头 3 行（第 2 行右侧有「日期：2026年10月26日」），第 4 行起是网点，末行「合计」。
    """
    if len(rows) < 5:
        raise ValueError('社保卡表行数太少，不像借记卡发卡统计报表')

    date = None
    for r in rows[:6]:
        for c in r:
            if isinstance(c, dt.datetime):
                date = c.date()
                break
            if isinstance(c, dt.date):
                date = c
                break
            if isinstance(c, str) and ('日期' in c or '时间' in c):
                date = _find_date_in_text(c)
                if date:
                    break
        if date:
            break
    if date is None:
        date = fallback
    if date is None:
        raise ValueError('社保卡表里读不到日期（第 2 行应有「日期：2026年10月26日」）')

    # 表头行：找含「机构」的那一行
    hdr_i = None
    for i, r in enumerate(rows[:8]):
        if r and str(r[0]).strip() == '机构':
            hdr_i = i
            break
    if hdr_i is None:
        hdr_i = 2

    def col_of(prefix: str) -> int | None:
        for c, v in enumerate(rows[hdr_i]):
            if v is None:
                continue
            if str(v).strip().startswith(prefix):
                return c
        return None

    ci_a, ci_b = col_of(SB_COLS[0]), col_of(SB_COLS[1])
    if ci_a is None or ci_b is None:
        raise ValueError(f'社保卡表缺少列：{SB_COLS[0]} / {SB_COLS[1]}')

    cum, parts, rows_used = {}, {}, 0
    grand = None                       # 源表末行「合计」，含运行管理部等非网点机构
    for r in rows[hdr_i + 1:]:
        if not r or not r[0]:
            continue
        name = str(r[0]).strip()
        if name == '合计':
            grand = [_num(r[ci_a] if ci_a < len(r) else 0),
                     _num(r[ci_b] if ci_b < len(r) else 0)]
            continue
        if name == '小计' or name.endswith('合计'):
            continue
        a = _num(r[ci_a] if ci_a < len(r) else 0)
        b = _num(r[ci_b] if ci_b < len(r) else 0)
        cum[name] = a + b
        parts[name] = [a, b]          # [柜台新增累计, 批量开户累计]，导出成表要用分项
        rows_used += 1
    if not cum:
        raise ValueError('社保卡表里没有网点行')
    return {'date': date, 'cum': cum, 'parts': parts, 'grand': grand, 'rows': rows_used}


def parse_sika_prepared(rows: list[list], as_of: dt.date | None) -> dict:
    """「已整理过的」社保卡表（成表文件里的 `社保卡` 子表，三个日期并排）。

    结构与原始报表不同：每个日期一对列（柜台新增累计 + 批量开户累计），
    第 3 行是列名，第 2 行右侧可能有「上周日」标记，不是日期的那块就是**当日**。
    只有这种表才需要外部告诉它"当日是哪天"。
    """
    if as_of is None:
        raise ValueError('这张社保卡表有三个日期并排、但当日那块没写日期，'
                         '请在导入时填写「数据日期」')
    # 第 3 行：收集所有 (柜台列, 批量列) 对
    sub = rows[2] if len(rows) > 2 else []
    pairs = []
    for c, v in enumerate(sub):
        if v and str(v).strip().startswith('柜台新增卡数量（本年累计'):
            for c2 in range(c + 1, min(c + 3, len(sub))):
                if sub[c2] and str(sub[c2]).strip().startswith('批量开户新增卡（本年累计'):
                    pairs.append((c, c2, str(v)))
                    break
    if not pairs:
        raise ValueError('没认出「柜台新增卡数量（本年累计）」与「批量开户新增卡」的列对')

    # 每块的日期：列名带 (本年累计10.22) 就用它；上方标「上周日」→ 当日−7；其余 → 当日
    label_row = rows[1] if len(rows) > 1 else []
    blocks = []
    for c, c2, title in pairs:
        d = _find_date_in_text(title)
        if d is None:
            lab = ''
            for back in (c, c - 1, c - 2):
                if 0 <= back < len(label_row) and label_row[back]:
                    lab = str(label_row[back])
                    break
            if '上周' in lab or '上周日' in lab:
                d = week_start_sunday(as_of)
            else:
                d = as_of
        blocks.append((d, c, c2))
    for _, v in enumerate(blocks):
        blocks = sorted(blocks)

    out, detail, grand = {}, {}, {}
    warn = []
    for d, c, c2 in blocks:
        series, parts = {}, {}
        for r in rows[3:]:
            if not r or not r[0]:
                continue
            name = str(r[0]).strip()
            if name == '合计':          # 末行合计（含运行管理部等非网点机构）
                grand[d.isoformat()] = [_num(r[c] if c < len(r) else 0),
                                        _num(r[c2] if c2 < len(r) else 0)]
                continue
            if name == '小计' or name.endswith('合计'):
                continue
            a = _num(r[c] if c < len(r) else 0)
            b = _num(r[c2] if c2 < len(r) else 0)
            series[name] = a + b
            parts[name] = [a, b]
        if series:
            out[d.isoformat()] = series
            detail[d.isoformat()] = parts
        else:
            warn.append(f'{d} 这块没有网点数据')
    if not out:
        raise ValueError('整理过的社保卡表里没有网点数据')
    return {'series': out, 'detail': detail, 'grand': grand,
            'blocks': len(blocks), 'warn': warn}


def parse_report_title(rows: list[list], year: int | None = None) -> dt.date | None:
    """成表标题里的期间末日：'“一卡一户”日通报（10.23-10.25）' → 10-25。"""
    first = str((rows[0][0] if rows and rows[0] else '') or '')
    if '通报' not in first:
        return None
    m = re.findall(r'(\d{1,2})[.月](\d{1,2})', first)
    if not m:
        return None
    mm, dd = m[-1]
    y = year or dt.date.today().year
    try:
        return dt.date(y, int(mm), int(dd))
    except ValueError:
        return None


def is_prepared_sika(rows: list[list]) -> bool:
    """是否「三个日期并排」的整理版社保卡表（区别于每天一张的原始报表）。"""
    sub = rows[2] if len(rows) > 2 else []
    n = sum(1 for v in sub if v and str(v).strip().startswith('柜台新增卡数量（本年累计'))
    return n >= 2


# ---------------------------------------------------------------- 解析：养老金
def parse_yanglao(rows: list[list], fallback: dt.date | None = None) -> dict:
    """个人养老金宽表 → {日期: {网点: 本年新增}}。

    结构是「横向平铺的多个日期块」：每块 6 列（网点名 + 三列数据 + 空位），
    第 1 行是块起始日期（合并单元格），第 2 行「类型 / 开户数据统计」，
    第 3 行「累计开户数 / 当日新增 / 本年新增」。
    所以按第 1 行的日期列切块、按第 3 行确认结构，不靠固定列号。
    """
    if not rows:
        raise ValueError('养老金表是空的')

    # 第 1 行：日期锚点
    anchors = []                                  # [(col_index, date)]
    for c, v in enumerate(rows[0]):
        d = None
        if isinstance(v, dt.datetime):
            d = v.date()
        elif isinstance(v, dt.date):
            d = v
        elif isinstance(v, str):
            d = _find_date_in_text(v)
        if d:
            anchors.append((c, d))
    if not anchors:
        if fallback is None:
            raise ValueError('养老金表第一行没有日期，无法切分日期块')
        anchors = [(0, fallback)]
    anchors.sort()

    # 第 3 行（索引 2）：找每块的三个子列
    sub_row = rows[2] if len(rows) > 2 else []
    blocks = []                                   # [(date, name_col, cum_col, day_col, year_col)]
    for i, (col, d) in enumerate(anchors):
        nxt = anchors[i + 1][0] if i + 1 < len(anchors) else len(sub_row)
        span = range(col, min(nxt, len(sub_row)))
        found = {}
        for c in span:
            if c >= len(sub_row) or sub_row[c] is None:
                continue
            t = str(sub_row[c]).strip()
            for k, name in enumerate(YL_SUB):
                if t == name:
                    found[k] = c
        # 网点名列 = 数据列左边第一列（块内第一个非空文本列）
        name_col = found.get(0, col + 1) - 1
        if 1 in found or 2 in found:
            blocks.append((d, name_col, found.get(0), found.get(1), found.get(2)))
    if not blocks:
        raise ValueError('养老金表里没有识别出日期块（每块应有 累计开户数/当日新增/本年新增）')

    out: dict[str, dict[str, float]] = {}
    detail: dict[str, dict[str, list]] = {}
    grand: dict[str, list] = {}
    warn = []
    for d, name_col, cum_c, day_c, year_c in blocks:
        use = year_c if year_c is not None else cum_c
        if use is None:
            warn.append(f'{d} 块缺少可用列，已跳过')
            continue
        series, rows3 = {}, {}
        for r in rows[3:]:
            if not r or name_col >= len(r):
                continue
            name = r[name_col]
            if name is None or str(name).strip() in ('', '合计', '小计'):
                continue
            name = str(name).strip()
            if not name.endswith(('支行', '营业室', '部')):
                continue
            series[name] = _num(r[use] if use < len(r) else 0)
            # [累计开户数, 当日新增, 本年新增]，导出成表时辅助 sheet 要写全
            rows3[name] = [_num(r[c] if c is not None and c < len(r) else 0)
                           for c in (cum_c, day_c, year_c)]
        if series:
            out[d.isoformat()] = series
            detail[d.isoformat()] = rows3
    if not out:
        raise ValueError('养老金表里没有可用的日期块数据')
    return {'series': out, 'detail': detail, 'grand': grand,
            'blocks': len(blocks), 'warn': warn}


# ---------------------------------------------------------------- 分类（导入时判断给了哪张表）
def classify(name: str, rows: list[list]) -> str:
    """'sika' | 'yanglao' | 'report' | 'unknown'。按内容判断，不看文件名。"""
    first = str((rows[0][0] if rows and rows[0] else '') or '')
    if ('日通报' in first or '一卡一户' in first) and '统计报表' not in first:
        return 'report'
    head = ' '.join(str(c) for c in (rows[0] if rows else [])[:8])
    if '借记卡发卡统计报表' in head:
        return 'sika'
    for r in rows[:3]:
        txt = ' '.join(str(c) for c in r[:8] if c is not None)
        if '借记卡发卡统计报表' in txt:
            return 'sika'
    # 养老金：第 3 行出现「累计开户数」
    if len(rows) > 2 and any(str(c).strip() == '累计开户数' for c in rows[2] if c is not None):
        return 'yanglao'
    # 兜底：社保卡特有列
    flat = ' '.join(str(c) for r in rows[:5] for c in r if c is not None)
    if SB_COLS[0] in flat:
        return 'sika'
    if '累计开户数' in flat:
        return 'yanglao'
    return 'unknown'


# ---------------------------------------------------------------- 网点名归一
# 三张表的网点名写法不一致（都是真实踩过的）：
#   * 成表/养老金：`界首支行营业室`     * 社保卡源表：`阜阳界首支行营业室`（多一个"阜阳"前缀）
#   * 社保卡源表还多一行 `安徽阜阳分行运行管理部`（不是网点，要排除）
def _norm(name: str) -> str:
    n = (name or '').strip()
    for pre in ('安徽阜阳分行', '阜阳'):
        if n.startswith(pre):
            return n[len(pre):]
    return n


def _lookup(series: dict[str, float], name: str) -> float | None:
    """精确 → 去「阜阳」前缀 → 后缀唯一匹配。命中返回数值，否则 None。"""
    if name in series:
        return series[name]
    k = _norm(name)
    flat = {}
    for kk, vv in series.items():
        flat.setdefault(_norm(kk), vv)
    if k in flat:
        return flat[k]
    cands = [vv for kk, vv in flat.items() if kk.endswith(k) or k.endswith(kk)]
    return cands[0] if len(cands) == 1 else None


# ---------------------------------------------------------------- 出成表
def build(sika_cum: dict[str, dict[str, float]],
          yl_cum: dict[str, dict[str, float]],
          plan: dict, targets: dict | None = None) -> dict:
    """把三个日期的累计值拼成一期成表数据。

    sika_cum / yl_cum: {日期: {网点: 累计值}}，键必须包含 plan['dates'] 里的日期。
    """
    t = targets or load_targets()
    cur, prev, wk = plan['cur'], plan['prev'], plan['week_end']
    missing = [d for d in {cur, prev, wk} if d not in sika_cum or d not in yl_cum]
    if missing:
        raise ValueError('缺少这些日期的数据：' + '、'.join(sorted(missing)))

    nets = []
    for meta in t['nets']:
        name = meta['name']
        s_cur, s_prev, s_wk = (_lookup(sika_cum[cur], name), _lookup(sika_cum[prev], name),
                               _lookup(sika_cum[wk], name))
        y_cur, y_prev, y_wk = (_lookup(yl_cum[cur], name), _lookup(yl_cum[prev], name),
                               _lookup(yl_cum[wk], name))
        if None in (s_cur, s_prev, s_wk):
            raise ValueError(f'社保卡源表里找不到网点「{name}」')
        if None in (y_cur, y_prev, y_wk):
            raise ValueError(f'养老金源表里找不到网点「{name}」')
        sb_day = s_cur - s_prev
        yl_day = y_cur - y_prev
        sb_week = s_cur - s_wk
        yl_week = y_cur - y_wk
        sb_t, yl_t = int(meta['target_sb']), int(meta['target_yl'])
        nets.append({
            'name': name, 'branch': meta['branch'],
            'sb_day': sb_day, 'sb_target': sb_t,
            'sb_rate': (sb_day / sb_t) if sb_t else 0,
            'sb_week': sb_week,
            'yl_day': yl_day, 'yl_target': yl_t,
            'yl_rate': (yl_day / yl_t) if yl_t else 0,
            'yl_week': yl_week,
            'day_rate': (sb_day + yl_day) / (sb_t + yl_t) if (sb_t + yl_t) else 0,
            'week_rate': (sb_week + yl_week) / (yl_t * 2 * WEEK_DAYS) if yl_t else 0,
        })

    # 支行小计
    branches = []
    for b in t['branches']:
        rows = [n for n in nets if n['branch'] == b['name']]
        if not rows:
            continue
        sb_d = sum(x['sb_day'] for x in rows)
        yl_d = sum(x['yl_day'] for x in rows)
        sb_w = sum(x['sb_week'] for x in rows)
        yl_w = sum(x['yl_week'] for x in rows)
        sb_t = sum(x['sb_target'] for x in rows)
        yl_t = sum(x['yl_target'] for x in rows)
        branches.append({
            'name': b['name'], 'nets': len(rows),
            'sb_day': sb_d, 'sb_target': sb_t, 'sb_week': sb_w, 'sb_rate': sb_d / sb_t if sb_t else 0,
            'yl_day': yl_d, 'yl_target': yl_t, 'yl_week': yl_w, 'yl_rate': yl_d / yl_t if yl_t else 0,
            'day_rate': (sb_d + yl_d) / (sb_t + yl_t) if (sb_t + yl_t) else 0,
            'week_rate': (sb_w + yl_w) / (yl_t * 2 * WEEK_DAYS) if yl_t else 0,
        })

    # 分行合计（成表最后一行：各项除以 2，因为上面小计行已经加过一遍 → 见口径说明）
    tot = {
        'sb_day': sum(n['sb_day'] for n in nets), 'sb_target': sum(n['sb_target'] for n in nets),
        'sb_week': sum(n['sb_week'] for n in nets),
        'yl_day': sum(n['yl_day'] for n in nets), 'yl_target': sum(n['yl_target'] for n in nets),
        'yl_week': sum(n['yl_week'] for n in nets),
    }
    tot['sb_rate'] = tot['sb_day'] / tot['sb_target'] if tot['sb_target'] else 0
    tot['yl_rate'] = tot['yl_day'] / tot['yl_target'] if tot['yl_target'] else 0
    tot['day_rate'] = (tot['sb_day'] + tot['yl_day']) / (tot['sb_target'] + tot['yl_target']) \
        if (tot['sb_target'] + tot['yl_target']) else 0
    tot['week_rate'] = (tot['sb_week'] + tot['yl_week']) / (tot['yl_target'] * 2 * WEEK_DAYS) \
        if tot['yl_target'] else 0

    # 排名（页面/通报文案要）
    for group in (branches,):
        by_day = sorted(group, key=lambda x: -x['day_rate'])
        for i, x in enumerate(by_day):
            x['rank_day'] = i + 1
        by_week = sorted(group, key=lambda x: -x['week_rate'])
        for i, x in enumerate(by_week):
            x['rank_week'] = i + 1

    return {
        'as_of': cur, 'period': {'start': plan['block_start'], 'end': plan['block_end'],
                                 'cur': cur, 'prev': prev, 'week_end': wk,
                                 'days': plan['days'], 'merged': plan['merged'],
                                 'dates': plan['dates']},
        'nets': nets, 'branches': branches, 'totals': tot,
    }
