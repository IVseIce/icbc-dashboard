#!/home/isee/.venvs/data-tools/bin/python
# -*- coding: utf-8 -*-
"""viz.py —— 可视化平台的存储层 + 导入适配层。

只做两件事：
1. 把上传的文件（按用户选定的大类）交给对应 icbc-* 技能的**解析函数**（classify/compute），
   得到与正式通报一致的规范化结果，写进 SQLite（`store.py`，一行 = 一条线的一天）；
2. 把各条线的最新快照组装成 dashboard_data.json（v1 遗留产物，v3 页面不再读它）。

目录（默认 <项目>/data）：
  icbc.db                          主库（snapshot / source_file / import_log / setting）
  imports/<line>/<stamp>/<原件>    原件留档，不改名不覆盖
  auth.json                        口令哈希
  data/dashboard_data.json         兼容产物
  out/*.html
  legacy_json_<时间戳>/            迁移前的 JSON 快照留档（只读，不再使用）
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import sys
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path

import compat
import store

compat.ensure_zoneinfo()      # Python 3.8：给 vendor 技能补 zoneinfo（3.9+ 是空操作）

PROJECT = Path(__file__).resolve().parent.parent
ROOT = PROJECT / 'data'
# 解析器已随项目打包（parsers/），不再依赖 ~/.dsh/skills；找不到时才回退
SKILLS = Path(__file__).resolve().parent / 'parsers'
SKILLS_FALLBACK = Path.home() / '.dsh' / 'skills'
LINES = {
    'sbqb': {'label': '数字人民币钱包', 'skill': 'icbc-sbqb', 'hint': '明细表：含 网点号/钱包等级/注册日期'},
    'xgj': {'label': '工银薪管家', 'skill': 'icbc-xgj', 'hint': '四张增量表：支行/网点 × 年度/月度'},
    'dqzz': {'label': '定期存款', 'skill': 'icbc-dqzz', 'hint': '分品种、期限时点报表（本月 + 上月）'},
    'xsfw': {'label': '网点线上服务', 'skill': 'icbc-xsfw', 'hint': '动户率×2 + 企微明细×3 + 营销授权'},
    'qwsq': {'label': '企微社群', 'skill': 'icbc-qwsq', 'hint': '成员群聊数据统计（本周 + 上周）'},
    'dfmx': {'label': '代发明细', 'skill': '', 'hint': '月度多 sheet 的代发明细工作簿'},
    'wk': {'label': '五卡唤醒', 'skill': '', 'hint': '五卡汇总表（支行 × 5 类卡）'},
    'jjwh': {'label': '降级挽回', 'skill': '', 'hint': '客编资产明细（客编映射已内置）'},
    'ykh': {'label': '一卡一户', 'skill': '',
            'hint': '社保卡（借记卡发卡统计报表）+ 个人养老金（多日期表），每天导当期即可'},
    'pbs': {'label': '私人银行', 'skill': '',
            'hint': '客编日均资产明细（归属支行/网点 + 本月月日均资产）；日期从文件名识别'},
    'jp': {'label': '定期承接', 'skill': '',
           'hint': '客编明细（含 归属支行/机构名称/最近到期日期/定期余额变化），取数日往前一个月'},
}

_mods: dict[str, object] = {}


# ---------------------------------------------------------------- 基础设施
def skill(sid: str):
    """按路径加载 icbc-* 技能脚本（文件名带连字符，不能直接 import）。"""
    if sid in _mods:
        return _mods[sid]
    path = SKILLS / sid / f'{sid}.py'
    if not path.exists():
        path = SKILLS_FALLBACK / sid / f'{sid}.py'
    spec = importlib.util.spec_from_file_location(sid.replace('-', '_'), path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    _mods[sid] = mod
    return mod


def use_root(root: Path | str | None = None) -> dict:
    """切换数据根目录（--root / 测试用）。库里没有数据而旧 JSON 还在时，自动做一次迁移。"""
    global ROOT
    if root:
        ROOT = Path(root)
    store.use(ROOT)
    store.init()
    store.import_legacy(ROOT)
    return paths(ROOT)


def paths(root: Path | None = None) -> dict:
    r = Path(root or ROOT)
    p = {k: r / k for k in ('imports', 'data', 'out')}
    p['root'] = r
    for v in p.values():
        v.mkdir(parents=True, exist_ok=True)
    return p


def ledger(line: str, rec: dict, root: Path | None = None) -> int:
    return store.log_import({'ts': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'line': line, **rec})


def save_snapshot(line: str, data_date: str, snap: dict, root: Path | None = None) -> int:
    """写入/覆盖一期快照，返回 snapshot.id。"""
    return store.save_snapshot(line, data_date, snap)


def load_snapshots(line: str, root: Path | None = None) -> list[dict]:
    """按 as_of 升序；返回缓存里的同一批 dict，只读。"""
    return store.load_snapshots(line)


def archive(line: str, files: list[tuple[str, bytes]], root: Path | None = None) -> Path:
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    d = paths(root)['imports'] / line / stamp
    d.mkdir(parents=True, exist_ok=True)
    for name, blob in files:
        (d / store.safe_name(name)).write_bytes(blob)
    return d


# ---------------------------------------------------------------- 各条线解析
XGJ_ROLE = {'zh_y': '支行 · 全年', 'zh_m': '支行 · 当月',
            'wg_y': '网点 · 全年', 'wg_m': '网点 · 当月', 'template': '通报模板'}
XSFW_ROLE = {'donghu_day': '到店客群 · 当日', 'donghu_prev': '到店客群 · 前一日',
             'staff_cur': '企微添客 · 当日', 'staff_prev': '企微添客 · 前一日',
             'staff_month': '企微添客 · 当月', 'auth': '营销授权', 'template': '通报模板'}


def _dqzz_roles(files, resolved):
    out = []
    prev, cur = resolved.get('prev') or {}, resolved.get('cur') or {}
    for n, _ in files:
        if n == cur.get('file') and n == prev.get('file'):
            out.append((n, f"上月 {prev.get('sheet')} + 本月 {cur.get('sheet')}"))
        elif n == cur.get('file'):
            out.append((n, f"本月表 {cur.get('sheet')}（{cur.get('date')}）"))
        elif n == prev.get('file'):
            out.append((n, f"上月表 {prev.get('sheet')}（{prev.get('date')}）"))
        else:
            out.append((n, '忽略（未选中）'))
    return out


def _atts(files):
    return [{'filename': n, 'blob': b, 'content_type': ''} for n, b in files]


def import_sbqb(files, line, root):
    mod = skill('icbc-sbqb')
    cls = mod.classify(_atts(files))
    if cls.get('problems'):
        raise ValueError('；'.join(cls['problems']))
    data = mod.compute(cls['_roles'])
    nets = []
    for n in data['nets']:
        lv = n.get('lv') or [0, 0, 0, 0]
        nets.append({**n, 'lv1': lv[0], 'lv2': lv[1], 'lv3': lv[2], 'lv4': lv[3]})
    totals = data['totals']
    snap_date = data['snapshot']
    ranked = sorted(nets, key=lambda n: -n['total'])
    day = sorted(nets, key=lambda n: -n['day'])
    return snap_date, {
        'as_of': snap_date, 'as_of_cn': f"{int(snap_date[5:7])}月{int(snap_date[8:10])}日",
        'total': totals[4], 'totals': totals,
        'top3_total': [{'name': n['name'], 'v': n['total']} for n in ranked[:3]],
        'bot3_total': [{'name': n['name'], 'v': n['total']} for n in ranked[-3:][::-1]],
        'top3_day': [{'name': n['name'], 'v': n['day']} for n in day[:3]],
        'zero_day_count': sum(1 for n in nets if n['day'] == 0),
        'nets': nets,
        '_files': [{'name': n,
                    'role': ('数币明细·快照 ' + snap_date) if n == cls['roles']['source']['filename']
                            else '忽略（非明细表）'} for n, _ in files],
        '_notes': [f"明细 {data['source_rows']} 行，映射到网点 {len(nets)} 个"],
    }


def import_xgj(files, line, root, data_date=None):
    mod = skill('icbc-xgj')
    cls = mod.classify(_atts(files))
    if not cls.get('complete'):
        raise ValueError('；'.join(cls['problems']) or '四张源表不全')
    roles = cls['roles']
    br = {}
    for key in ('zh_y', 'zh_m'):
        r = roles.get(key)
        if not r:
            continue
        for name, v in (r.get('data') or {}).items():
            rec = br.setdefault(name, {'name': name, 'full': name, 'year': 0.0, 'month': 0.0,
                                       'ent_year': 0, 'ent_month': 0})
            if r.get('period') == '年':
                rec['year'] += v.get('K') or 0
                rec['ent_year'] += int(v.get('F') or 0)
            else:
                rec['month'] += v.get('K') or 0
                rec['ent_month'] += int(v.get('F') or 0)
    branches = [b for b in br.values() if '虚拟' not in b['name'] and '电话银行' not in b['name']]
    for b in branches:
        b['name'] = b['name'].replace('阜阳', '').replace('支行', '')
    nets = []
    for key in ('wg_y', 'wg_m'):
        r = roles.get(key)
        if not r:
            continue
        for name, v in (r.get('data') or {}).items():
            rec = next((n for n in nets if n['name'] == name), None)
            if rec is None:
                rec = {'name': name, 'year': 0.0, 'month': 0.0, 'ent_year': 0, 'ent_month': 0}
                nets.append(rec)
            if r.get('period') == '年':
                rec['year'] += v.get('K') or 0
                rec['ent_year'] += int(v.get('F') or 0)
            else:
                rec['month'] += v.get('K') or 0
                rec['ent_month'] += int(v.get('F') or 0)
    nets = [n for n in nets if n['year'] or n['month'] or n['ent_year']]
    nets.sort(key=lambda n: (-n['year'], -n['month']))
    total_year = round(sum(b['year'] for b in branches), 2)
    total_month = round(sum(b['month'] for b in branches), 2)
    dd = data_date or (date.today() - timedelta(days=1)).isoformat()
    return dd, {
        'as_of': dd, 'as_of_cn': f'{int(dd[5:7])}月{int(dd[8:10])}日',
        'total': total_year, 'month_total': total_month,
        'ent_year': sum(b['ent_year'] for b in branches),
        'ent_month': sum(b['ent_month'] for b in branches),
        'branches': sorted(branches, key=lambda b: -b['year']), 'nets': nets,
        '_files': [{'name': n, 'role': XGJ_ROLE.get(next((k for k, v in roles.items()
                                                          if v.get('filename') == n), ''), '未识别')}
                   for n, _ in files],
        '_notes': cls.get('notices') or [],
    }


def import_dqzz(files, line, root):
    mod = skill('icbc-dqzz')
    cands = []
    for name, blob in files:
        cands.extend(mod.read_tables(blob, name))
    if not cands:
        raise ValueError('没有识别出「分品种、期限时点报表」')
    resolved = mod.resolve_tables(cands)
    if resolved.get('problems'):
        raise ValueError('；'.join(resolved['problems']))
    prev_t, cur_t = resolved['prev'], resolved['cur']
    data = mod.compute(prev_t, cur_t)
    br = data['branches']
    branches = [{'name': k, 'full': f'阜阳{k}支行', **v} for k, v in br.items()]
    branches.sort(key=lambda b: -(b.get('cur_bal') or 0))
    dd = cur_t['date'].isoformat()
    return dd, {
        'as_of': dd, 'as_of_cn': f'{int(dd[5:7])}月{int(dd[8:10])}日',
        'prev_as_of': prev_t['date'].isoformat(), 'total': data['total'],
        'branches': branches,
        '_files': [{'name': n, 'role': role} for n, role in _dqzz_roles(files, resolved)],
        '_notes': [f"上月 {prev_t['date']}（{prev_t['file']}#{prev_t['sheet']}）",
                   f"本月 {cur_t['date']}（{cur_t['file']}#{cur_t['sheet']}）"] + (data.get('warnings') or []),
        '_notes': data.get('warnings') or [],
    }


def import_xsfw(files, line, root):
    mod = skill('icbc-xsfw')
    cls = mod.classify(_atts(files))
    if cls.get('problems'):
        raise ValueError('；'.join(cls['problems']))
    # 邮件没带空白模板时用技能内置模板兜底（compute 需要模板行名）
    tmp = paths(root)['imports'] / '_tmp_xsfw'
    tmp.mkdir(parents=True, exist_ok=True)
    mod.ensure_template(cls, tmp)
    if not cls.get('ok'):
        raise ValueError('；'.join(cls['problems']) or '模板兜底失败')
    data = mod.compute(cls['roles'])
    rows = [r for r in data['rows'] if r.get('branch')]
    total_row = next((r for r in data['rows'] if not r.get('branch')), None)
    nets = [{'label': r['label'], 'branch': r['branch'], 'day_rate': round(r['B'], 6),
             'month_rate': round(r['C'], 6), 'cust': r['D'], 'cust_delta': r.get('cust_delta') or 0,
             'add_real': round(r['E'], 6) if r.get('E') is not None else None,
             'add_today': r.get('F') or 0, 'add_month': r.get('G') or 0,
             'sign_rate': round(r['J'], 6) if r.get('J') is not None else None,
             'kh_rate': round(r['M'], 6) if r.get('M') is not None else None,
             'auth_cust': r.get('H'), 'auth_signed': r.get('I'),
             'kh': r.get('K'), 'kh_signed': r.get('L')} for r in rows]
    tot = {'day_rate': round(total_row['B'], 6), 'month_rate': round(total_row['C'], 6),
           'cust': total_row['D'], 'add_today': total_row['F'], 'add_month': total_row['G'],
           'real_rate': round(total_row['E'], 6) if total_row.get('E') is not None else None,
           'auth_cust': total_row.get('H'), 'auth_signed': total_row.get('I'),
           'sign_rate': round(total_row['J'], 6) if total_row.get('J') is not None else None,
           'kh': total_row.get('K'), 'kh_signed': total_row.get('L'),
           'kh_rate': round(total_row['M'], 6) if total_row.get('M') is not None else None}
    dd = data['day_date']
    return dd, {
        'as_of': dd, 'as_of_cn': f'{int(dd[5:7])}月{int(dd[8:10])}日',
        'prev_as_of': data['prev_date'], 'nets': nets, 'tot': tot,
        '_files': [{'name': n, 'role': XSFW_ROLE.get(next((k for k, v in cls['roles'].items()
                                                           if v.get('filename') == n), ''), '未识别')}
                   for n, _ in files],
        '_notes': data.get('warnings') or [],
    }


def _qw_date_from_name(name: str):
    """企微备份文件名里的日期：20261019 / 1005-1011（取区间末日）/ 10.19。"""
    m = re.search(r'(20\d{2})(\d{2})(\d{2})', name)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    m = re.search(r'(\d{2})(\d{2})[-~至](\d{2})(\d{2})', name)
    if m:
        try:
            return date(2026, int(m.group(3)), int(m.group(4)))
        except ValueError:
            pass
    m = re.search(r'(?<!\d)(\d{1,2})[.月](\d{1,2})(?!\d)', name)
    if m:
        try:
            return date(2026, int(m.group(1)), int(m.group(2)))
        except ValueError:
            pass
    return None


def import_qwsq(files, line, root):
    """需要两份：本周 + 上周。按文件名/内容里的日期排序。"""
    mod = skill('icbc-qwsq')
    tmp = paths(root)['imports'] / '_tmp_qwsq'
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    dated = []
    for name, blob in files:
        f = tmp / re.sub(r'[\\/:*?"<>|]', '_', name)
        f.write_bytes(blob)
        d = _qw_date_from_name(name) or datetime.fromtimestamp(f.stat().st_mtime).date()
        dated.append((d, f))
    dated.sort(key=lambda x: x[0])
    if len(dated) < 2:
        raise ValueError('企微社群需要「本周 + 上周」两份成员群聊数据统计')
    cur_d, cur_f = dated[-1]
    # 「上周」= 最接近（本周 - 7 天）的那份备份，而不是简单取上一份
    target = cur_d - timedelta(days=7)
    prev_d, prev_f = min(dated[:-1], key=lambda x: abs((x[0] - target).days))
    cur, _ = mod.aggregate(cur_f)
    prev, _ = mod.aggregate(prev_f)
    branches = []
    cur_br, prev_br = mod.branch_agg(cur), mod.branch_agg(prev)
    for br, v in cur_br.items():
        p = prev_br.get(br, {})
        branches.append({'name': br + '支行', 'groups': v['g'], 'groups_d': v['g'] - p.get('g', 0),
                         'cust': v['c'], 'cust_d': v['c'] - p.get('c', 0),
                         'inter': v['x'], 'inter_d': v['x'] - p.get('x', 0),
                         'rate': v['rate'], 'rate_d': v['rate'] - p.get('rate', 0)})
    nets = []
    for nm, v in cur.items():
        p = prev.get(nm, {})
        nets.append({'name': nm, 'groups': v['g'], 'groups_d': v['g'] - p.get('g', 0),
                     'cust': v['c'], 'cust_d': v['c'] - p.get('c', 0),
                     'inter': v['x'], 'inter_d': v['x'] - p.get('x', 0),
                     'rate': v['rate'], 'rate_d': v['rate'] - p.get('rate', 0)})
    t = mod.totals(cur)
    tp = mod.totals(prev)
    dd = cur_d.isoformat()
    return dd, {
        'as_of': dd, 'as_of_cn': f'{cur_d.month}月{cur_d.day}日',
        'branches': sorted(branches, key=lambda b: -b['cust']), 'nets': nets,
        'total': {'name': '合计', 'groups': t['g'], 'groups_d': t['g'] - tp['g'],
                  'cust': t['c'], 'cust_d': t['c'] - tp['c'], 'inter': t['x'],
                  'inter_d': t['x'] - tp['x'], 'rate': t['rate'],
                  'rate_d': t['rate'] - tp['rate']},
        '_files': [{'name': n, 'role': ('本周 ' if n == cur_f.name else '上周 ') + str(cur_d if n == cur_f.name else prev_d)}
                   for n, _ in files],
        '_notes': [f'本周 {cur_d} / 上周 {prev_d}'],
    }


def import_payroll(files, line, root, data_date=None):
    """代发明细：一个工作簿可能含多个月份 sheet，逐月落快照，返回最新一期。"""
    from ingest import payroll as pr
    from ingest import readers
    no2info, _ = pr.net_info()
    latest, saved, notes = None, [], []
    for name, blob in files:
        for title, rows in readers.sheets(blob, name):
            month = pr.MONTHS.get(title)
            if not month:
                continue
            snap = pr.parse_sheet(rows, month, no2info)
            if not snap.get('nets'):
                continue
            save_snapshot('dfmx', snap['as_of'], {**snap, 'line': 'dfmx'}, root)
            saved.append(month)
            latest = snap
    if not latest:
        raise ValueError('没有识别出代发明细的月度 sheet（sheet 名需形如 26.09）')
    notes.append(f'已导入 {len(saved)} 个月度快照：{"、".join(saved)}')
    return latest['as_of'], {**latest, '_files': [{'name': n, 'role': '代发明细'} for n, _ in files],
                             '_notes': notes}


def import_fivecards(files, line, root, data_date=None):
    """五卡汇总表：单期，日期取参数 / 文件名 / 今天。"""
    import re
    import tempfile
    from ingest import fivecards as fc
    name, blob = files[0]
    as_of = data_date
    if not as_of:
        m = re.search(r'(20\d{2})[-_.]?(\d{2})[-_.]?(\d{2})', name)
        as_of = f'{m.group(1)}-{m.group(2)}-{m.group(3)}' if m else date.today().isoformat()
    with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp:
        tmp.write(blob)
        path = Path(tmp.name)
    try:
        snap = fc.parse(path, as_of)
    finally:
        path.unlink(missing_ok=True)
    if not snap.get('branches'):
        raise ValueError('没有识别出支行数据，请确认是五卡汇总表')
    return as_of, {**snap, '_files': [{'name': n, 'role': '五卡汇总'} for n, _ in files],
                   '_notes': [f'{len(snap["branches"])} 家支行 · {len(snap["cards"])} 类卡']}


def import_downgrade(files, line, root, data_date=None):
    """降级挽回：明细表 + 客编映射表（两份都必传）。"""
    from ingest import downgrade as dg
    return dg.parse_files(files, as_of=data_date)


def import_yika(files, line, root, data_date=None):
    """一卡一户：社保卡 + 养老金两张源表。

    两步：
      1. **按日入库**：每张表识别出的每个日期都落一条快照（`ykh_sb` / `ykh_yl`，
         payload 只有该日各网点的累计值）。所以每天导当期即可，多日期表一次能补历史。
      2. **拼当期**：从库里取「当日 / 前一日 / 上周末」三个时点算成表，写入 `ykh`。

    返回的 snap 带 `_files`（每个 sheet 被当成什么、识别到哪些日期）与 `_notes`
    （本期用到哪几个日期、缺哪个），导入者据此核对日期是否正确。
    """
    from ingest import readers, yika
    roles, sb_dates, yl_dates, notes = [], set(), set(), []
    title_hint = None                     # 成表标题里的期间末日，给"三日期版"定当日
    for name, blob in files:
        titles = readers.sheet_names(blob, name)
        single = len(titles) == 1
        for title, rows in readers.sheets(blob, name):
            tag = name if single else f'{name} » {title}'
            kind = yika.classify(title, rows)
            if kind == 'report':
                roles.append({'name': tag, 'role': '成表输出，已忽略'})
                title_hint = title_hint or yika.parse_report_title(rows)
            elif kind == 'sika':
                if yika.is_prepared_sika(rows):
                    fallback = (date.fromisoformat(data_date) if data_date else
                                (title_hint or _date_from_name(name)))
                    r = yika.parse_sika_prepared(rows, fallback)
                    for d, series in sorted(r['series'].items()):
                        save_snapshot('ykh_sb', d, {'line': 'ykh_sb', 'as_of': d,
                                                    'cum': series,
                                                    'parts': (r.get('detail') or {}).get(d) or {},
                                                    'grand': (r.get('grand') or {}).get(d),
                                                    'rows': len(series)}, root)
                        sb_dates.add(d)
                    ds = sorted(r['series'])
                    roles.append({'name': tag, 'role':
                                  f'社保卡（三日期版）· {"、".join(ds)}'})
                    notes.extend(r.get('warn') or [])
                else:
                    r = yika.parse_sika(rows, fallback=_date_from_name(name))
                    d = r['date'].isoformat()
                    save_snapshot('ykh_sb', d, {'line': 'ykh_sb', 'as_of': d,
                                                'cum': r['cum'], 'parts': r.get('parts') or {},
                                                'grand': r.get('grand'), 'rows': r['rows']}, root)
                    sb_dates.add(d)
                    roles.append({'name': tag, 'role': f'社保卡 · {d}'})
            elif kind == 'yanglao':
                r = yika.parse_yanglao(rows, fallback=_date_from_name(name))
                for d, series in sorted(r['series'].items()):
                    save_snapshot('ykh_yl', d, {'line': 'ykh_yl', 'as_of': d,
                                                'cum': series,
                                                'parts': (r.get('detail') or {}).get(d) or {},
                                                'rows': len(series)}, root)
                    yl_dates.add(d)
                ds = sorted(r['series'])
                roles.append({'name': tag, 'role':
                              f'养老金 · {ds[0]} ~ {ds[-1]}（{len(ds)} 个日期）'})
                notes.extend(r.get('warn') or [])
            else:
                roles.append({'name': tag, 'role': '未识别（跳过）'})

    if not sb_dates and not yl_dates:
        raise ValueError('没识别出社保卡或养老金表：社保卡表标题应含「借记卡发卡统计报表」，'
                         '养老金表第 3 行应有「累计开户数」')

    sb_all = _cum_by_date('ykh_sb')
    yl_all = _cum_by_date('ykh_yl')
    have = sorted(set(sb_all) | set(yl_all))
    if not have:
        raise ValueError('库里没有任何一卡一户数据')

    # 当日：优先用参数；否则取两张表「都有数据」的最新一天
    # （只导了养老金 10.26、社保卡只到 10.25 时，当期就出 10.25，而不是硬凑 10.26）
    both = sorted(set(sb_all) & set(yl_all))
    as_of = data_date or (both[-1] if both else have[-1])
    as_of = min(as_of, have[-1])
    plan = yika.plan_dates(date.fromisoformat(as_of))

    # 三个时点都齐了才能拼当期；缺的日期说清楚，别静默算错
    need = sorted({plan['cur'], plan['prev'], plan['week_end']})
    miss_sb = [d for d in need if d not in sb_all]
    miss_yl = [d for d in need if d not in yl_all]
    if miss_sb or miss_yl:
        bits = []
        if miss_sb:
            bits.append('社保卡缺 ' + '、'.join(miss_sb))
        if miss_yl:
            bits.append('养老金缺 ' + '、'.join(miss_yl))
        raise ValueError(f'当期需要 {need[0]} ~ {need[-1]} 三个时点（当日/前一日/上周末），'
                         + '；'.join(bits) + '。把对应那天的源表一起导进来即可。')

    snap = yika.build(sb_all, yl_all, plan)
    snap['_files'] = roles
    span = f'{plan["cur"]}' if plan['days'] == 1 else f'{plan["block_start"]} ~ {plan["block_end"]}'
    notes.insert(0, f'本期 {span}（当日 {plan["cur"]} · 前一日 {plan["prev"]} · '
                    f'上周末 {plan["week_end"]}）')
    if plan['merged']:
        notes.insert(1, '前一日与上周末是同一天，本周新增 = 当日新增')
    snap['_notes'] = notes
    return as_of, snap


def import_pbs(files, line, root, data_date=None):
    """私人银行：一张客编明细 + 可选的三个时点。

    一次最多三份文件，按文件名里的日期归位：

        当天        → 必填（`as_of`，出通报用）
        上年末      → 算「比上年」，`partial=True` 存进库里当基线
        上季度末    → 算「比9月末」，同上

    识别不出日期就抛错，前端据此提示"手填数据日期"。
    产品销售（遴选/快贷/信托/保险 7 项）是人工维护的，从 setting 读进来合进快照。
    """
    from ingest import pbs

    # 日期 → [(文件名, blob)]
    slots: dict[str, list] = {}
    used = []
    for name, blob in files:
        d = pbs.date_from_name(name)
        if not d:
            raise ValueError(f'「{name}」文件名里认不出日期，请手动指定该文件的数据日期')
        slots.setdefault(d, []).append((name, blob))
        used.append({'name': name, 'role': f'待定（{d}）'})

    # 本次的"当天"：优先参数；否则取最大的日期
    as_of = data_date or max(slots)
    if as_of not in slots:
        raise ValueError(f'标记为当天的 {as_of} 没有对应文件；识别到的日期有：'
                         + '、'.join(sorted(slots)))
    if as_of != max(slots):
        raise ValueError(f'当天 {as_of} 不是最新的一份（最新是 {max(slots)}），请核对文件')

    today_files = slots[as_of]
    if len(today_files) > 1:
        raise ValueError(f'{as_of} 这一天给了多份文件：' + '、'.join(n for n, _ in today_files))

    dd, snap = pbs.parse_files(today_files, as_of=as_of)
    if dd != as_of:
        raise ValueError(f'文件名识别出 {dd}，与指定的 {as_of} 不一致')

    # 其他日期的文件：各存一份 partial 快照当基线
    extras = []
    for d in sorted(slots):
        if d == as_of:
            continue
        files_d = slots[d]
        if len(files_d) > 1:
            raise ValueError(f'{d} 这一天给了多份文件：' + '、'.join(n for n, _ in files_d))
        try:
            _, s2 = pbs.parse_files(files_d, as_of=d)
        except Exception as exc:
            raise ValueError(f'{d} 那份文件解析失败：{exc}')
        s2['_files'] = [{'name': files_d[0][0], 'role': f'{d} 基线'}]
        s2['partial'] = True
        save_snapshot('pbs', d, s2, root)
        extras.append(d)
        used = [{'name': u['name'], 'role': (f'{d} 基线（partial）'
                                            if u['name'] == files_d[0][0] else u['role'])}
                for u in used]

    # 产品销售：从 setting 读（人工维护，可能为空）
    sales = _pbs_sales()
    snap['sales'] = sales
    snap['sales_source'] = '手工维护' if any(v for s2 in sales.values() for v in s2.values()) else '未录入'

    # 时点：本旬用到的三个日期，库里没有的要提示
    snap['period'] = {
        'as_of': as_of,
        'year_end': _pbs_pick_baseline('pbs', _year_end(as_of), extras),
        'quarter': _pbs_pick_baseline('pbs', pbs.quarter_end(as_of), extras),
    }
    notes = list(snap.get('_notes') or [])
    if not snap['period']['year_end']:
        notes.append(f'库里没有上年末（{_year_end(as_of)}）数据，「比上年」会是空的——'
                     '把上年末那份明细一起导进来即可')
    if not snap['period']['quarter']:
        notes.append(f'库里没有上季度末（{pbs.quarter_end(as_of)}）数据，「比上季末」会是空的——'
                     '把上季度末那份明细一起导进来即可')
    if extras:
        notes.insert(0, '同时存入基线：' + '、'.join(extras))
    used = [{'name': u['name'],
             'role': ('私银客编明细（当天）' if u['name'] == today_files[0][0] else u['role'])}
            for u in used]
    snap['_files'] = used
    snap['_notes'] = notes
    return dd, snap


def _year_end(as_of: str) -> str:
    y = int(as_of[:4]) - 1
    return f'{y}-12-31'


def _pbs_pick_baseline(line: str, want: str, just_saved: list) -> str | None:
    """取「不晚于 want 的最新一期」，且必须是库里真有的日期。"""
    dates = sorted({s['as_of'] for s in load_snapshots(line)} | set(just_saved))
    cand = [d for d in dates if d <= want]
    return cand[-1] if cand else None


def _pbs_sales() -> dict:
    """人工维护的产品销售：{支行: {键: 值}}；没录过就是空 dict。"""
    from ingest.pbs import SALES_KEYS
    raw = store.get('pbs_sales') or {}
    out = {}
    for br, rec in (raw.items() if isinstance(raw, dict) else []):
        out[br] = {k: float((rec or {}).get(k) or 0) for k, _ in SALES_KEYS}
    return out


def pbs_set_sales(sales: dict) -> dict:
    """保存产品销售（只存 8 家支行 × 7 项，其余丢弃）。"""
    from ingest.pbs import BRANCHES, SALES_KEYS
    clean = {}
    for br in BRANCHES:
        rec = (sales or {}).get(br) or {}
        clean[br] = {k: float(rec.get(k) or 0) for k, _ in SALES_KEYS}
    store.set_setting('pbs_sales', clean)
    return clean


def refresh_pbs_sales() -> bool:
    """产品销售改了之后，把新值合进最新一期私银快照（不重算明细，只换 sales）。

    页面与通报都读快照里的 sales，所以改完必须跑这一步，否则要等下次导入。
    """
    snaps = [x for x in load_snapshots('pbs') if not x.get('partial')]
    if not snaps:
        return False
    latest = snaps[-1]
    body = latest if isinstance(latest, dict) else {}
    # load_snapshots 返回的是组装好的快照（payload 已摊平）
    as_of = body.get('as_of')
    if not as_of:
        return False
    sales = _pbs_sales()
    body['sales'] = sales
    body['sales_source'] = '手工维护' if any(v for s2 in sales.values() for v in s2.values()) else '未录入'
    save_snapshot('pbs', as_of, body, None)
    return True


def _date_from_name(name: str):
    """文件名里的日期兜底：1026 / 20261026 / 10.26。"""
    import re
    m = re.search(r'(20\d{2})[-_.]?(\d{2})[-_.]?(\d{2})', name)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    m = re.search(r'(?<!\d)(\d{2})[.月-]?(\d{2})(?!\d)', name)
    if m:
        try:
            return date(date.today().year, int(m.group(1)), int(m.group(2)))
        except ValueError:
            pass
    return None


def _cum_by_date(line: str) -> dict:
    """把库里的按日累计快照摊成 {日期: {网点: 累计}}。"""
    return {s['as_of']: (s.get('cum') or {}) for s in load_snapshots(line)}


def import_jiepan(files, line, root, data_date=None):
    """定期承接：客编明细 → 网点/支行两层快照（取数日与覆盖范围都从表里来）。"""
    from ingest import jiepan
    return jiepan.parse_files(files, as_of=data_date)


IMPORTERS = {'sbqb': import_sbqb, 'xgj': import_xgj, 'dqzz': import_dqzz,
             'xsfw': import_xsfw, 'qwsq': import_qwsq,
             'dfmx': import_payroll, 'wk': import_fivecards, 'jjwh': import_downgrade,
             'ykh': import_yika, 'pbs': import_pbs, 'jp': import_jiepan}


def do_import(line: str, files: list[tuple[str, bytes]], data_date: str | None = None,
              root: Path | None = None) -> dict:
    if line not in IMPORTERS:
        return {'ok': False, 'error': f'未知大类：{line}'}
    originals = list(files)                      # 归档用原始文件名（store.source_file 要对得上）
    arch = archive(line, originals, root)

    # 统一格式：按内容纠正扩展名（CSV 被存成 xlsx 这类），并在失败时兜底转 xlsx
    from ingest import readers
    norm, fmt_notes, text_blobs = [], [], []
    for name, blob in files:
        n, b, info = readers.normalize(name, blob)
        if info.get('changed'):
            fmt_notes.append(f'{name} 实际是 {info["detected"]}，已按 {info["to"]} 识别')
        if info.get('detected') == 'text':
            text_blobs.append((n, b))
        norm.append((n, b))
    files = norm
    try:
        if line in ('xgj', 'wk', 'dfmx', 'ykh', 'pbs'):
            dd, snap = IMPORTERS[line](files, line, root, data_date=data_date)
        else:
            dd, snap = IMPORTERS[line](files, line, root)
        snap['line'] = line
        snap['imported_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        sid = save_snapshot(line, dd, snap, root)
        store.add_source_files(line, sid, originals, arch)
        data = assemble(root)
        ledger(line, {'data_date': dd, 'files': [n for n, _ in files], 'ok': True,
                      'archive': str(arch), 'snapshot_id': sid}, root)
        return {'ok': True, 'line': line, 'label': LINES[line]['label'], 'data_date': dd,
                'files': snap.get('_files', []), 'notes': fmt_notes + list(snap.get('_notes') or []),
                'archive': str(arch), 'summary': data['meta']}
    except Exception as exc:
        # 兜底：文本内容转成真正的 xlsx 再试一次（给只认 xlsx 的解析器）
        if text_blobs:
            try:
                conv = [(n, readers.text_to_xlsx(b)) if readers.sniff(b) == 'text' else (n, b)
                        for n, b in files]
                dd, snap = (IMPORTERS[line](conv, line, root, data_date=data_date)
                            if line in ('xgj', 'wk', 'dfmx', 'ykh', 'pbs')
                            else IMPORTERS[line](conv, line, root))
                snap['line'] = line
                snap['imported_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                sid = save_snapshot(line, dd, snap, root)
                store.add_source_files(line, sid, originals, arch)
                data = assemble(root)
                ledger(line, {'data_date': dd, 'files': [n for n, _ in files], 'ok': True,
                              'archive': str(arch), 'note': '按文本转 xlsx 兜底',
                              'snapshot_id': sid}, root)
                fmt_notes.append('按文本内容转成 xlsx 后识别成功')
                return {'ok': True, 'line': line, 'label': LINES[line]['label'], 'data_date': dd,
                        'files': snap.get('_files', []), 'notes': fmt_notes + (snap.get('_notes') or []),
                        'archive': str(arch), 'summary': data['meta']}
            except Exception:
                pass
        ledger(line, {'files': [n for n, _ in files], 'ok': False, 'error': str(exc),
                      'archive': str(arch)}, root)
        return {'ok': False, 'line': line, 'error': str(exc),
                'trace': traceback.format_exc()[-800:], 'archive': str(arch)}


# ---------------------------------------------------------------- 组装
def _trend_sbqb(snaps):
    return [{'d': s['as_of'], 'v': s['total']} for s in sorted(snaps, key=lambda x: x['as_of'])]


def _trend_xgj(snaps):
    return [{'d': s['as_of'], 'year': s['total'], 'month': s['month_total'],
             'ent_year': s['ent_year'], 'ent_month': s['ent_month']}
            for s in sorted(snaps, key=lambda x: x['as_of'])]


def _trend_xsfw(snaps):
    out = []
    for s in sorted(snaps, key=lambda x: x['as_of']):
        nets = s['nets']
        w = sum(n['cust'] for n in nets) or 1
        out.append({'d': s['as_of'],
                    'day_rate': round(sum(n['cust'] * n['day_rate'] for n in nets) / w, 4),
                    'add': int(sum(n['add_today'] for n in nets)),
                    'add_month': int(sum(n['add_month'] for n in nets)),
                    'cust': int(w)})
    return out


def _trend_qwsq(snaps):
    return [{'d': s['as_of'], 'groups': s['total']['groups'], 'cust': s['total']['cust'],
             'inter': s['total']['inter']} for s in sorted(snaps, key=lambda x: x['as_of'])]


def assemble(root: Path | None = None) -> dict:
    """把各条线最新快照 → dashboard_data.json（结构沿用 build.py 的输入）。"""
    sources: dict[str, dict] = {}
    for line in LINES:
        snaps = load_snapshots(line, root)
        if not snaps:
            sources[line] = {'ok': False, 'error': '尚未导入数据'}
            continue
        latest = sorted(snaps, key=lambda s: s['as_of'])[-1]
        obj = {k: v for k, v in latest.items() if not k.startswith('_')}
        obj['ok'] = True
        if line == 'sbqb':
            obj['trend'] = _trend_sbqb(snaps)
        elif line == 'xgj':
            obj['trend'] = _trend_xgj(snaps)
            prev = sorted(snaps, key=lambda s: s['as_of'])[-2] if len(snaps) > 1 else None
            obj['prev'] = ({'d': prev['as_of'], 'year': prev['total'], 'month': prev['month_total']}
                           if prev else {})
        elif line == 'xsfw':
            obj['branches'] = _branch_xsfw(obj)
            obj['trend'] = _trend_xsfw(snaps)
        elif line == 'qwsq':
            obj['trend'] = _trend_qwsq(snaps)
        sources[line] = obj

    data = {'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'branches': ['颍州', '颍泉', '颍东', '界首', '临泉', '阜南', '颍上', '太和'],
            'sources': sources,
            'meta': {'lines': {k: (v.get('as_of') if v.get('ok') else None) for k, v in sources.items()},
                     'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M')}}
    p = paths(root)['data'] / 'dashboard_data.json'
    p.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    return data


def _branch_xsfw(obj):
    rows = obj.get('nets') or []
    out = []
    for b in ['颍州', '颍泉', '颍东', '界首', '临泉', '阜南', '颍上', '太和']:
        rs = [r for r in rows if r['branch'] == b]
        if not rs:
            continue
        w = sum(r['cust'] for r in rs) or 1
        out.append({'name': b, 'full': f'阜阳{b}支行', 'nets': len(rs),
                    'day_rate': round(sum(r['cust'] * r['day_rate'] for r in rs) / w, 4),
                    'month_rate': round(sum(r['cust'] * r['month_rate'] for r in rs) / w, 4),
                    'cust': sum(r['cust'] for r in rs),
                    'cust_delta': sum(r.get('cust_delta') or 0 for r in rs),
                    'sign_rate': round(sum((r.get('sign_rate') or 0) for r in rs) / len(rs), 4),
                    'kh_rate': round(sum((r.get('kh_rate') or 0) for r in rs) / len(rs), 4)})
    return out


use_root(ROOT)


if __name__ == '__main__':
    print(json.dumps({'root': str(ROOT), 'db': str(store.db_path()),
                      'lines': list(LINES)}, ensure_ascii=False, indent=1))
