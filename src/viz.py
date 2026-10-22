#!/home/isee/.venvs/data-tools/bin/python
# -*- coding: utf-8 -*-
"""viz.py —— 可视化平台的存储层 + 导入适配层。

只做两件事：
1. 把上传的文件（按用户选定的大类）交给对应 icbc-* 技能的**解析函数**（classify/compute），
   得到与正式通报一致的规范化结果，存成 snapshots/<line>/<data_date>.json；
2. 把各条线的最新快照组装成 dashboard_data.json，交给 build.py 渲染。

目录（默认 D:\\资料\\ICBC\\Visualizations）：
  imports/<line>/<stamp>/<原件>    原件留档，不改名不覆盖
  snapshots/<line>/<data_date>.json
  data/dashboard_data.json
  out/*.html
  ledger.jsonl
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


def paths(root: Path | None = None) -> dict:
    r = Path(root or ROOT)
    p = {k: r / k for k in ('imports', 'snapshots', 'data', 'out')}
    p['root'] = r
    for v in p.values():
        v.mkdir(parents=True, exist_ok=True)
    return p


def ledger(line: str, rec: dict, root: Path | None = None) -> None:
    p = paths(root)
    rec = {'ts': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'line': line, **rec}
    with (p['root'] / 'ledger.jsonl').open('a', encoding='utf-8') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')


def save_snapshot(line: str, data_date: str, snap: dict, root: Path | None = None) -> Path:
    p = paths(root)['snapshots'] / line
    p.mkdir(parents=True, exist_ok=True)
    f = p / f'{data_date}.json'
    f.write_text(json.dumps(snap, ensure_ascii=False), encoding='utf-8')
    return f


def load_snapshots(line: str, root: Path | None = None) -> list[dict]:
    p = paths(root)['snapshots'] / line
    out = []
    for f in sorted(p.glob('*.json')):
        try:
            d = json.loads(f.read_text('utf-8'))
            out.append(d)
        except Exception:
            continue
    return out


def archive(line: str, files: list[tuple[str, bytes]], root: Path | None = None) -> Path:
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    d = paths(root)['imports'] / line / stamp
    d.mkdir(parents=True, exist_ok=True)
    for name, blob in files:
        safe = re.sub(r'[\\/:*?"<>|]', '_', name)
        (d / safe).write_bytes(blob)
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
    nets = [{'label': r['label'], 'branch': r['branch'], 'day_rate': round(r['B'], 4),
             'month_rate': round(r['C'], 4), 'cust': r['D'], 'cust_delta': r.get('cust_delta') or 0,
             'add_real': round(r['E'], 4) if r.get('E') is not None else None,
             'add_today': r.get('F') or 0, 'add_month': r.get('G') or 0,
             'sign_rate': round(r['J'], 4) if r.get('J') is not None else None,
             'kh_rate': round(r['M'], 4) if r.get('M') is not None else None,
             'auth_cust': r.get('H'), 'auth_signed': r.get('I'),
             'kh': r.get('K'), 'kh_signed': r.get('L')} for r in rows]
    tot = {'day_rate': round(total_row['B'], 4), 'month_rate': round(total_row['C'], 4),
           'cust': total_row['D'], 'add_today': total_row['F'], 'add_month': total_row['G']}
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
                         'rate': round(v['rate'], 5), 'rate_d': round(v['rate'] - p.get('rate', 0), 5)})
    nets = []
    for nm, v in cur.items():
        p = prev.get(nm, {})
        nets.append({'name': nm, 'groups': v['g'], 'groups_d': v['g'] - p.get('g', 0),
                     'cust': v['c'], 'cust_d': v['c'] - p.get('c', 0),
                     'inter': v['x'], 'inter_d': v['x'] - p.get('x', 0),
                     'rate': round(v['rate'], 5), 'rate_d': round(v['rate'] - p.get('rate', 0), 5)})
    t = mod.totals(cur)
    tp = mod.totals(prev)
    dd = cur_d.isoformat()
    return dd, {
        'as_of': dd, 'as_of_cn': f'{cur_d.month}月{cur_d.day}日',
        'branches': sorted(branches, key=lambda b: -b['cust']), 'nets': nets,
        'total': {'name': '合计', 'groups': t['g'], 'groups_d': t['g'] - tp['g'],
                  'cust': t['c'], 'cust_d': t['c'] - tp['c'], 'inter': t['x'],
                  'inter_d': t['x'] - tp['x'], 'rate': round(t['rate'], 5),
                  'rate_d': round(t['rate'] - tp['rate'], 5)},
        '_files': [{'name': n, 'role': ('本周 ' if n == cur_f.name else '上周 ') + str(cur_d if n == cur_f.name else prev_d)}
                   for n, _ in files],
        '_notes': [f'本周 {cur_d} / 上周 {prev_d}'],
    }


IMPORTERS = {'sbqb': import_sbqb, 'xgj': import_xgj, 'dqzz': import_dqzz,
             'xsfw': import_xsfw, 'qwsq': import_qwsq}


def do_import(line: str, files: list[tuple[str, bytes]], data_date: str | None = None,
              root: Path | None = None) -> dict:
    if line not in IMPORTERS:
        return {'ok': False, 'error': f'未知大类：{line}'}
    arch = archive(line, files, root)

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
        if line == 'xgj':
            dd, snap = IMPORTERS[line](files, line, root, data_date=data_date)
        else:
            dd, snap = IMPORTERS[line](files, line, root)
        snap['line'] = line
        snap['imported_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        save_snapshot(line, dd, snap, root)
        data = assemble(root)
        ledger(line, {'data_date': dd, 'files': [n for n, _ in files], 'ok': True,
                      'archive': str(arch)}, root)
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
                            if line == 'xgj' else IMPORTERS[line](conv, line, root))
                snap['line'] = line
                snap['imported_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                save_snapshot(line, dd, snap, root)
                data = assemble(root)
                ledger(line, {'data_date': dd, 'files': [n for n, _ in files], 'ok': True,
                              'archive': str(arch), 'note': '按文本转 xlsx 兜底'}, root)
                fmt_notes.append('按文本内容转成 xlsx 后识别成功')
                return {'ok': True, 'line': line, 'label': LINES[line]['label'], 'data_date': dd,
                        'files': snap.get('_files', []), 'notes': fmt_notes + (snap.get('_notes') or []),
                        'archive': str(arch), 'summary': data['meta']}
            except Exception:
                pass
        ledger(line, {'files': [n for n, _ in files], 'ok': False, 'error': str(exc)}, root)
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


if __name__ == '__main__':
    print(json.dumps({'root': str(ROOT), 'lines': list(LINES)}, ensure_ascii=False, indent=1))
