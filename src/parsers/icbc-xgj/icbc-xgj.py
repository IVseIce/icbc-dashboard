#!/home/isee/.venvs/data-tools/bin/python
# -*- coding: utf-8 -*-
"""icbc-xgj —— 工银薪管家「聚薪行动」日通报：取信 → 识别四张源表 → 填通报 → 回信。

四张源表 → 通报两个 sheet 的四列，一比一映射：

  支行 年.xlsx  ─┬─ K列 薪酬代发金额（万元） → sheet「支行」B 列（新增代发金额-全年）
  （二级分行汇总） └─ F列 有效使用企业数-新口径（户） → sheet「支行」D 列（新增有效使用单位-全年）
  支行 月.xlsx  ─┬─ K → sheet「支行」C 列（当月）
                 └─ F → sheet「支行」E 列（当月）
  网点 年.xlsx  ─┬─ K → sheet「网点」B 列
                 └─ F → sheet「网点」D 列
  网点 月.xlsx  ─┬─ K → sheet「网点」C 列
                 └─ F → sheet「网点」E 列

用法
----
  icbc-xgj.py find   [--keyword 薪管家] [--date YYYY-MM-DD] [--days 3]
  icbc-xgj.py fetch  --uid U [--uid U ...] [--root DIR] [--workdir DIR]
  icbc-xgj.py build  --workdir DIR [--date YYYY-MM-DD] [--out-name NAME]
  icbc-xgj.py send   --workdir DIR [--dry-run]
  icbc-xgj.py run    --uid U [--uid U ...]
"""
from __future__ import annotations

import argparse
import email
import imaplib
import io
import json
import os
import re
import smtplib
import socket
import ssl
import sys
import warnings
from datetime import date, datetime, timedelta
from email.header import make_header, decode_header
from email.message import EmailMessage
from email.utils import formatdate, parsedate_to_datetime, parseaddr
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    import openpyxl
    import yaml
except ImportError as exc:  # pragma: no cover
    print(json.dumps({'ok': False, 'error': f'缺少依赖: {exc}；请用 /home/isee/.venvs/data-tools/bin/python 运行'},
                     ensure_ascii=False))
    raise SystemExit(2)

warnings.filterwarnings('ignore')

TZ = ZoneInfo('Asia/Shanghai')
DSH_HOME = Path(os.environ.get('DSH_HOME') or (Path.home() / '.dsh'))
SKILL_DIR = Path(__file__).resolve().parent
FALLBACK_TEMPLATE = SKILL_DIR / 'assets' / 'template.xlsx'
DEFAULT_ROOT = Path('/mnt/d/资料/ICBC/automations')
WORKDIR_SUFFIX = '_薪管家'
KEYWORD = '薪管家'

# 回信固定收件人：原发件人 + 这三个；发件人本身在名单里就只发一遍
FIXED_RECIPIENTS = (
    'zhaili.fy@ah.icbc.com.cn',
    'zhangxiang.fy@ah.icbc.com.cn',
    'yaohongcheng.fy@ah.icbc.com.cn',
)

# 源表：sheet「支行」/「网点」，源表列 F=有效使用企业数，K=薪酬代发金额
SRC_SHEET_TITLE = '工银薪管家数据增量表'
COL_F, COL_K = 6, 11          # F / K
COL_BRANCH, COL_NET = 3, 4    # C / D
COL_E = 5                     # E 认证企业数（用来区分年/月）
HDR_AGG = 3                   # 二级分行汇总行
HDR_ROW = 2
DATA_FROM = 3
# 通报 sheet：B/C 新增代发金额(全年/当月)，D/E 新增有效使用单位(全年/当月)
TARGET_FROM_ROW = 4
TARGET_COLS = {'zh_y': ('B', 'D'), 'zh_m': ('C', 'E'),
               'wg_y': ('B', 'D'), 'wg_m': ('C', 'E')}
SHEET_OF = {'zh_y': '支行', 'zh_m': '支行', 'wg_y': '网点', 'wg_m': '网点'}
REQUIRED_ROLES = ('zh_y', 'zh_m', 'wg_y', 'wg_m')
ROLE_LABEL = {'zh_y': '支行-全年', 'zh_m': '支行-当月', 'wg_y': '网点-全年', 'wg_m': '网点-当月'}

PROVIDERS = {
    '163': ('imap.163.com', 993, 'smtp.163.com', 465),
    '126': ('imap.126.com', 993, 'smtp.126.com', 465),
    'qq': ('imap.qq.com', 993, 'smtp.qq.com', 465),
    'sina': ('imap.sina.com.cn', 993, 'smtp.sina.com', 465),
    'aliyun': ('imap.aliyun.com', 993, 'smtp.aliyun.com', 465),
    'gmail': ('imap.gmail.com', 993, 'smtp.gmail.com', 465),
    'outlook': ('outlook.office365.com', 993, 'smtp.office365.com', 587),
    'icloud': ('imap.mail.me.com', 993, 'smtp.mail.me.com', 587),
}


# ================================================================ 邮箱账号
def _read_row_config() -> dict:
    out: dict = {}
    for cfg in sorted((DSH_HOME / 'profiles').glob('*/cordis.patch.yml')):
        try:
            data = yaml.safe_load(cfg.read_text('utf-8')) or []
        except Exception:
            continue
        if not isinstance(data, list):
            continue
        for entry in data:
            if isinstance(entry, dict) and entry.get('id') == 'tool-email':
                conf = entry.get('config')
                if isinstance(conf, dict):
                    out.update(conf)
    return out


def _read_page_config() -> dict:
    try:
        data = yaml.safe_load((DSH_HOME / 'settings.yaml').read_text('utf-8')) or {}
    except Exception:
        return {}
    ns = data.get('dsh-email')
    return ns if isinstance(ns, dict) else {}


def _merge_config(row: dict, page: dict) -> dict:
    cfg = dict(row)
    for key in ('provider', 'user', 'password', 'inboxFolder', 'downloadDir'):
        value = page.get(key)
        if isinstance(value, str) and value.strip():
            cfg[key] = value.strip()
    return cfg


def _pick_account(cfg: dict) -> dict:
    entries, default = None, None
    raw_yaml = cfg.get('accountsYaml') if isinstance(cfg.get('accountsYaml'), str) else ''
    if (raw_yaml or '').strip():
        doc = yaml.safe_load(raw_yaml) or {}
        if isinstance(doc, dict):
            doc = dict(doc)
            default = doc.pop('defaultAccount', None)
            entries = doc
    elif isinstance(cfg.get('accounts'), dict) and cfg['accounts']:
        entries = cfg['accounts']
    if not entries:
        return cfg
    name = cfg.get('defaultAccount') or default or ('default' if 'default' in entries else sorted(entries)[0])
    account = entries.get(name)
    if not isinstance(account, dict):
        raise RuntimeError(f'accountsYaml 里没有默认账号 "{name}"')
    merged = {k: v for k, v in account.items() if v not in (None, '')}
    for key in ('provider', 'user', 'password', 'inboxFolder', 'imap', 'smtp'):
        if key not in merged and cfg.get(key):
            merged[key] = cfg[key]
    return merged


def _env_password():
    pw = os.environ.get('DSH_EMAIL_PASSWORD')
    if pw and pw.strip():
        return pw.strip(), 'DSH_EMAIL_PASSWORD 环境变量'
    for pid in os.listdir('/proc'):
        if not pid.isdigit():
            continue
        try:
            cmd = Path(f'/proc/{pid}/cmdline').read_bytes().replace(b'\0', b' ').decode('utf-8', 'ignore')
            if 'dsh' not in cmd or 'web' not in cmd:
                continue
            for kv in Path(f'/proc/{pid}/environ').read_bytes().split(b'\0'):
                if kv.startswith(b'DSH_EMAIL_PASSWORD='):
                    return kv.split(b'=', 1)[1].decode('utf-8', 'ignore').strip(), '运行中 dsh web 的环境'
        except (OSError, PermissionError):
            continue
    return None


def resolve_account() -> dict:
    cfg = _pick_account(_merge_config(_read_row_config(), _read_page_config()))
    provider = (cfg.get('provider') or '163').strip() or '163'
    imap_host, imap_port, smtp_host, smtp_port = PROVIDERS.get(provider, PROVIDERS['163'])
    imap_conf = cfg.get('imap') if isinstance(cfg.get('imap'), dict) else {}
    smtp_conf = cfg.get('smtp') if isinstance(cfg.get('smtp'), dict) else {}
    pwd = cfg.get('password')
    if isinstance(pwd, str) and pwd.strip():
        password, source = pwd.strip(), '插件配置（设置页/行配置）'
    else:
        found = _env_password()
        if not found:
            raise RuntimeError('取不到邮箱授权码：请在邮件设置页填写，或设置 DSH_EMAIL_PASSWORD')
        password, source = found
    return {
        'provider': provider,
        'user': str(cfg.get('user') or '').strip(),
        'imap_host': str(imap_conf.get('host') or '').strip() or imap_host,
        'imap_port': int(imap_conf.get('port') or imap_port),
        'smtp_host': str(smtp_conf.get('host') or '').strip() or smtp_host,
        'smtp_port': int(smtp_conf.get('port') or smtp_port),
        'password': password,
        'password_source': source,
        'inbox': str(cfg.get('inboxFolder') or 'INBOX'),
    }


def force_ipv4() -> None:
    original = socket.getaddrinfo

    def ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
        return original(host, port, socket.AF_INET, type, proto, flags)

    socket.getaddrinfo = ipv4_only


def connect(acct: dict) -> imaplib.IMAP4_SSL:
    force_ipv4()
    imap = imaplib.IMAP4_SSL(acct['imap_host'], acct['imap_port'],
                             ssl_context=ssl.create_default_context(), timeout=60)
    imap.login(acct['user'], acct['password'])
    try:
        imap.xatom('ID', '("name" "dsh-icbc-xgj" "version" "1.0" "vendor" "dsh")')
    except Exception:
        pass
    return imap


def _decode(value) -> str:
    if value is None:
        return ''
    try:
        return str(make_header(decode_header(str(value))))
    except Exception:
        return str(value)


def dedup_addresses(addrs) -> list:
    """去重同时保持顺序；邮箱大小写不敏感。"""
    seen, out = set(), []
    for a in addrs:
        a = (a or '').strip()
        if not a or a.lower() in seen:
            continue
        seen.add(a.lower())
        out.append(a)
    return out


# ================================================================ 取信
def fetch_message(imap, uid: str) -> dict:
    typ, body = imap.uid('FETCH', uid, '(BODY.PEEK[])')
    if typ != 'OK' or not body or not isinstance(body[0], tuple):
        raise RuntimeError(f'UID {uid} 取信失败')
    msg = email.message_from_bytes(body[0][1])
    try:
        received = parsedate_to_datetime(msg['Date']).astimezone(TZ)
    except Exception:
        received = None
    atts = []
    for part in msg.walk():
        filename = _decode(part.get_filename())
        if not filename:
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        atts.append({'filename': filename, 'blob': payload})
    return {
        'uid': uid,
        'subject': _decode(msg['Subject']),
        'from': _decode(msg['From']),
        'message_id': (msg['Message-ID'] or '').strip(),
        'received': received,
        'received_date': received.date().isoformat() if received else None,
        'attachments': atts,
    }


_MONTHS = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')


def _imap_date(d: date) -> str:
    return f'{d.day:02d}-{_MONTHS[d.month - 1]}-{d.year}'


def list_recent(imap, since: date, cap: int = 400) -> list:
    """列出 SINCE 之后的邮件抬头。必须用 UID SEARCH：普通 SEARCH 回的是序号。"""
    typ, data = imap.uid('SEARCH', None, f'(SINCE {_imap_date(since)})')
    if typ != 'OK':
        raise RuntimeError(f'IMAP SEARCH 失败：{typ}')
    uids = (data[0] or b'').split()[-cap:]
    out = []
    for u in uids:
        uid = u.decode()
        try:
            typ, d = imap.uid('FETCH', uid, '(BODY.PEEK[HEADER.FIELDS (SUBJECT DATE FROM)])')
        except Exception:
            continue
        if typ != 'OK' or not d or not isinstance(d[0], tuple):
            continue
        msg = email.message_from_bytes(d[0][1])
        try:
            received = parsedate_to_datetime(msg['Date']).astimezone(TZ)
        except Exception:
            received = None
        out.append({'uid': uid, 'subject': _decode(msg['Subject']), 'from': _decode(msg['From']),
                    'received': received,
                    'received_date': received.date().isoformat() if received else None})
    out.sort(key=lambda x: x['received'] or datetime.min.replace(tzinfo=TZ))
    return out


# ================================================================ 源表识别
def _num(v) -> float:
    """源表里的数字有的带千分位、有的带尾部制表符，统一成 float。"""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(',', '').replace('\t', '')
    if s in ('', '-', '--'):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def probe_xgj(blob: bytes):
    """工银薪管家数据增量表 → {level, data, sum_e}；不是这张表返回 None。"""
    try:
        wb = openpyxl.load_workbook(io.BytesIO(blob), data_only=True, read_only=True)
    except Exception:
        return None
    try:
        ws = wb.worksheets[0]
        if str(ws.title).strip() != SRC_SHEET_TITLE:
            return None
        head = [str(c.value or '').strip() for c in next(ws.iter_rows(min_row=HDR_ROW, max_row=HDR_ROW))]
        if COL_F - 1 >= len(head) or '有效使用企业数' not in head[COL_F - 1]:
            return None
        if COL_K - 1 >= len(head) or '薪酬代发金额' not in head[COL_K - 1]:
            return None
        rows = list(ws.iter_rows(min_row=DATA_FROM, values_only=True))
    finally:
        try:
            wb.close()
        except Exception:
            pass

    def cell(r, i):
        return r[i - 1] if r and len(r) >= i else None

    # 第 3 行（DATA_FROM）是二级分行汇总行，取它的 E 作交叉校验
    agg_e = _num(cell(rows[0], COL_E)) if rows else 0.0

    # 有「网点」列 → 网点级；否则支行级
    net_rows = [r for r in rows if cell(r, COL_NET) not in (None, '')]
    if net_rows:
        level, key_col = '网点', COL_NET
    else:
        level, key_col = '支行', COL_BRANCH

    data: dict = {}
    for r in rows:
        name = cell(r, key_col)
        if name in (None, ''):
            continue
        name = str(name).strip()
        if not name or name in data:
            continue
        data[name] = {'F': _num(cell(r, COL_F)), 'K': _num(cell(r, COL_K))}
    if not data:
        return None
    return {'kind': 'xgj', 'level': level, 'data': data,
            'sum_e': sum(v['F'] for v in data.values()),
            'sum_k': sum(v['K'] for v in data.values()),
            'agg_e': agg_e}


COL_AGG_NAME = COL_BRANCH   # 汇总行用支行名列判断


def probe_xgj_template(blob: bytes):
    """薪管家通报（汇总通报表）→ {kind:'template', title, filled}。

    发件人常常直接附**上一天已填好的通报**当版式，所以填过数的也照样当模板用
    （所有数据行都会重写，不会留旧数）。`filled` 只用来在 notices 里提示一句。
    """
    try:
        wb = openpyxl.load_workbook(io.BytesIO(blob))
    except Exception:
        return None
    try:
        if not ({'支行', '网点'} <= set(wb.sheetnames)):
            return None
        ws = wb['支行']
        title = str(ws.cell(row=1, column=1).value or '')
        if '聚薪' not in title and '薪管家' not in title:
            return None
        filled = any(ws.cell(row=r, column=c).value not in (None, '')
                     for r in range(TARGET_FROM_ROW, min(ws.max_row, 30) + 1) for c in range(2, 6))
        return {'kind': 'template', 'title': title, 'filled': filled}
    finally:
        try:
            wb.close()
        except Exception:
            pass


PROBES = (probe_xgj, probe_xgj_template)


def strip_blobs(cls: dict) -> dict:
    return {
        'complete': bool(cls.get('complete')),
        'problems': cls.get('problems', []),
        'notices': cls.get('notices', []),
        'unknown_files': cls.get('unknown_files', []),
        'attachment_count': cls.get('attachment_count', 0),
        'roles': {k: {'file': v.get('filename'), 'level': v.get('level'),
                      'sum_k': v.get('sum_k'), 'nets': len(v.get('data') or {})}
                  for k, v in cls.get('roles', {}).items()},
    }


def classify(attachments: list) -> dict:
    """四张源表按内容定角色。年/月没有日期标记，靠「月 ≤ 年」的累计口径大小区分。"""
    found, unknown = [], []
    for att in attachments:
        got = None
        for probe in PROBES:
            got = probe(att['blob'])
            if got:
                break
        if not got:
            if att['filename'].lower().endswith(('.xls', '.xlsx', '.xlsm', '.csv')):
                unknown.append(att['filename'])
            continue
        got['filename'] = att['filename']
        got['blob'] = att['blob']
        found.append(got)

    src = [f for f in found if f['kind'] == 'xgj']
    tpl = [f for f in found if f['kind'] == 'template']

    roles: dict = {}
    problems: list = []
    notices: list = []
    if unknown:
        problems.append('这些表格附件认不出是哪张源表，请确认是否换了版式：' + '、'.join(unknown))

    for level, suf in (('支行', 'zh'), ('网点', 'wg')):
        grp = [f for f in src if f['level'] == level]
        if len(grp) < 2:
            problems.append(f'{level}级源表需要 2 张（全年 + 当月），实际 {len(grp)} 张'
                            + (f'：{grp[0]["filename"]}' if grp else ''))
            continue
        if len(grp) > 2:
            notices.append(f'{level}级源表有 {len(grp)} 张，取累计数最大的两张：'
                           + '、'.join(f['filename'] for f in grp))
            grp = sorted(grp, key=lambda f: -f['sum_e'])[:2]
        y, m = sorted(grp, key=lambda f: -f['sum_e'])
        if abs(y['sum_e'] - m['sum_e']) < 1e-9:
            problems.append(f'{level}级两张源表的累计「认证企业数」完全相同，分不出年/月，'
                            f'请人工确认：{y["filename"]} 与 {m["filename"]}')
            continue
        y['period'], m['period'] = '年', '月'
        roles[f'{suf}_y'], roles[f'{suf}_m'] = y, m

    if len(tpl) > 1:
        # 多个通报文件时优先用空白的那个，其次用第一个
        tpl.sort(key=lambda t: (t.get('filled', False), t['filename']))
        notices.append('邮件里有 ' + str(len(tpl)) + ' 个通报文件，已选用：' + tpl[0]['filename']
                       + '（其余：' + '、'.join(t['filename'] for t in tpl[1:]) + '）')
    if tpl:
        roles['template'] = tpl[0]
        if tpl[0].get('filled'):
            notices.append(f'模板用的是已填过数的通报（{tpl[0]["filename"]}），'
                           f'所有数据行会按源表重写；标题日期按发信日期的 T-1 另算')
    else:
        notices.append('邮件里没有通报模板，将使用技能内置模板 assets/template.xlsx')

    complete = all(r in roles for r in REQUIRED_ROLES)
    return {'ok': not problems, 'complete': complete, 'roles': roles,
            'unknown_files': unknown, 'problems': problems, 'notices': notices,
            'attachment_count': len(attachments)}


def pool_attachments(imap, uids, cache):
    out = []
    for uid in uids:
        if uid not in cache:
            cache[uid] = fetch_message(imap, uid)
        out.extend(cache[uid]['attachments'])
    return out


def pool_check(imap, uids, cache) -> dict:
    try:
        cls = classify(pool_attachments(imap, uids, cache))
    except Exception as exc:
        return {'complete': False, 'problems': [f'{type(exc).__name__}: {exc}'], 'roles': {},
                'notices': [], 'unknown_files': [], 'attachment_count': 0}
    return cls


def minimal_pick(imap, uids, cache):
    """挑出最少的几封凑齐四张源表；年/月要横向比大小，所以必须整批一起 classify。"""
    pairs = []
    for u in uids:
        if u not in cache:
            cache[u] = fetch_message(imap, u)
        for a in cache[u]['attachments']:
            pairs.append((u, a))
    try:
        cls = classify([a for _, a in pairs])
    except Exception:
        return [], set(), {'roles': {}}
    owner = {}
    for u, a in pairs:
        owner.setdefault(a['filename'], u)
    picked = []
    for role in REQUIRED_ROLES + ('template',):
        entry = cls['roles'].get(role)
        if not entry:
            continue
        u = owner.get(entry['filename'])
        if u and u not in picked:
            picked.append(u)
    ordmap = {u: i for i, u in enumerate(uids)}
    picked.sort(key=lambda u: ordmap.get(u, 0))
    return picked, set(cls['roles']), cls


# ================================================================ 填表
def norm_name(s) -> str:
    return re.sub(r'\s+', '', str(s or '')).replace('（', '(').replace('）', ')')


def ensure_template(cls: dict, src: Path) -> None:
    """邮件没带空白模板时用内置模板兜底。"""
    if not cls.get('ok') or 'template' in cls['roles']:
        return
    if not FALLBACK_TEMPLATE.exists():
        cls['ok'] = False
        cls['problems'].append(f'邮件没带模板，内置模板也缺失：{FALLBACK_TEMPLATE}')
        return
    blob = FALLBACK_TEMPLATE.read_bytes()
    probe = probe_xgj_template(blob) or {}
    fname = FALLBACK_TEMPLATE.name
    (src / fname).write_bytes(blob)
    cls['roles']['template'] = {'kind': 'template', 'filename': fname, 'blob': blob,
                                'title': probe.get('title', ''), 'fallback': True}
    cls['notices'].append(f'使用内置模板兜底（{fname}），如需更新版式请让发件人附上模板')


def retitle(blob: bytes, biz: date) -> tuple:
    """把 A1 的「（截至YYYY.MM.DD）」改成业务日；没有就补。返回 (新字节, 新标题)。"""
    wb = openpyxl.load_workbook(io.BytesIO(blob))
    ws = wb['支行']
    old = str(ws.cell(row=1, column=1).value or '')
    stamp = f'截至{biz.year}.{biz.month:02d}.{biz.day:02d}'
    pat = r'截至\s*\d{4}\s*[.．\-/]\s*\d{1,2}\s*[.．\-/]\s*\d{1,2}'
    if re.search(pat, old):
        new = re.sub(pat, stamp, old, count=1)
    elif '（' in old:
        new = old.rstrip('）)') + stamp + '）'
    else:
        new = f'{old}（{stamp}）'
    for sh in wb.sheetnames:
        wb[sh].cell(row=1, column=1).value = new
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue(), new


def title_date(title: str):
    m = re.search(r'(\d{4})\s*[.．\-/]\s*(\d{1,2})\s*[.．\-/]\s*(\d{1,2})', str(title or ''))
    if not m:
        return None
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def fill_report(template_blob: bytes, roles: dict, out_path: Path) -> dict:
    wb = openpyxl.load_workbook(io.BytesIO(template_blob))
    src = {r: roles[r]['data'] for r in REQUIRED_ROLES}
    warns: list = []
    totals: dict = {}

    for surname in ('支行', '网点'):
        if surname not in wb.sheetnames:
            raise RuntimeError(f'模板里没有 sheet「{surname}」')
        ws = wb[surname]
        y_role = 'zh_y' if surname == '支行' else 'wg_y'
        m_role = 'zh_m' if surname == '支行' else 'wg_m'
        y_src, m_src = src[y_role], src[m_role]
        (col_fy, col_uy), (col_fm, col_um) = TARGET_COLS[y_role], TARGET_COLS[m_role]

        target_rows, total_row, seen = [], None, set()
        for r in range(TARGET_FROM_ROW, ws.max_row + 1):
            name = ws.cell(row=r, column=1).value
            if name in (None, ''):
                continue
            name = str(name).strip()
            if name == '总计':
                total_row = r
                continue
            target_rows.append((r, name))
            seen.add(norm_name(name))

        sums = [0.0, 0.0, 0.0, 0.0]
        for r, name in target_rows:
            key = norm_name(name)
            yv = next((v for k, v in y_src.items() if norm_name(k) == key), None)
            mv = next((v for k, v in m_src.items() if norm_name(k) == key), None)
            if yv is None:
                warns.append(f'{surname}「{name}」在全年源表里没有对应行，已按 0 填')
            if mv is None:
                warns.append(f'{surname}「{name}」在当月源表里没有对应行，已按 0 填')
            yv, mv = yv or {'F': 0.0, 'K': 0.0}, mv or {'F': 0.0, 'K': 0.0}
            # 两个金额列（全年/当月代发金额）、两个单位列（全年/当月有效使用单位）
            ws[f'{col_fy}{r}'].value = round(yv['K'], 2)
            ws[f'{col_fm}{r}'].value = round(mv['K'], 2)
            ws[f'{col_uy}{r}'].value = int(round(yv['F']))
            ws[f'{col_um}{r}'].value = int(round(mv['F']))
            for i, val in enumerate((yv['K'], mv['K'], yv['F'], mv['F'])):
                sums[i] += val
        if total_row:
            ws[f'{col_fy}{total_row}'].value = round(sums[0], 2)
            ws[f'{col_fm}{total_row}'].value = round(sums[1], 2)
            ws[f'{col_uy}{total_row}'].value = int(round(sums[2]))
            ws[f'{col_um}{total_row}'].value = int(round(sums[3]))

        totals[surname] = {'rows': len(target_rows),
                           '代发金额_全年': round(sums[0], 2), '代发金额_当月': round(sums[1], 2),
                           '有效使用单位_全年': int(round(sums[2])), '有效使用单位_当月': int(round(sums[3]))}
        # 源表里有、通报里没有的行（虚拟机构等属正常）
        extra = [k for k in y_src if norm_name(k) not in seen]
        if extra:
            warns.append(f'{surname}：源表里的 ' + '、'.join(extra) + ' 未出现在通报中')

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return {'warnings': warns, 'totals': totals}


# ================================================================ 文案
def build_text(title: str, totals: dict, roles: dict) -> str:
    zh = totals.get('支行', {})
    wg = totals.get('网点', {})
    d = title_date(title)
    day = f'{d.month}月{d.day}日' if d else '本日'
    lines = [f'工银薪管家「聚薪行动」日通报（{day}）',
             '',
             f'全行新增代发金额 {zh.get("代发金额_全年", 0):,.2f} 万元（全年）、'
             f'{zh.get("代发金额_当月", 0):,.2f} 万元（当月）；'
             f'新增有效使用单位 {zh.get("有效使用单位_全年", 0)} 户（全年）、'
             f'{zh.get("有效使用单位_当月", 0)} 户（当月）。']
    net = roles.get('wg_y', {}).get('data') or {}
    netm = roles.get('wg_m', {}).get('data') or {}
    if net:
        top = sorted(net.items(), key=lambda kv: -kv[1]['K'])[:3]
        top = [(k, v) for k, v in top if v['K'] > 0]
        if top:
            lines += ['', '全年新增代发金额靠前：' + '、'.join(f'{k} {v["K"]:,.2f}万元' for k, v in top) + '。']
    if netm:
        topm = sorted(netm.items(), key=lambda kv: -kv[1]['K'])[:3]
        topm = [(k, v) for k, v in topm if v['K'] > 0]
        if topm:
            lines += ['当月新增代发金额靠前：' + '、'.join(f'{k} {v["K"]:,.2f}万元' for k, v in topm) + '。']
    lines += ['', '详见附件通报。']
    return '\n'.join(lines) + '\n'


# ================================================================ 子命令
def _brief(m: dict) -> dict:
    return {'uid': m['uid'], 'subject': m['subject'], 'from': m['from'],
            'received_date': m.get('received_date')}


def _workdir_for(root: Path, received: date) -> Path:
    return root / f'{received.strftime("%Y%m%d")}{WORKDIR_SUFFIX}'


def cmd_find(args) -> dict:
    """按约定找源邮件：主题含关键词且当天收到 → 直接执行；否则检索后请示。"""
    today = date.fromisoformat(args.date) if args.date else datetime.now(TZ).date()
    keyword = args.keyword
    acct = resolve_account()
    imap = connect(acct)
    try:
        typ, _ = imap.select(acct['inbox'], readonly=True)
        if typ != 'OK':
            raise RuntimeError(f"SELECT {acct['inbox']} 失败")
        recent = list_recent(imap, today - timedelta(days=args.days))
        cache: dict = {}
        kw = [m for m in recent if keyword and keyword in (m['subject'] or '')]
        kw_today = [m for m in kw if m['received_date'] == today.isoformat()]

        base = {'ok': True, 'keyword': keyword, 'today': today.isoformat(),
                'inbox': acct['inbox'], 'scanned': len(recent),
                'keyword_hits': [_brief(m) for m in kw],
                'keyword_hits_today': [_brief(m) for m in kw_today]}

        if kw_today:
            chk = pool_check(imap, [m['uid'] for m in kw_today], cache)
            if chk.get('complete'):
                base.update({'auto': True, 'uids': [m['uid'] for m in kw_today],
                             'proposed': [_brief(m) for m in kw_today],
                             'verification': strip_blobs(chk),
                             'reason': '主题含关键词且为当天邮件，四张源表齐全'})
                return base
            why = '；'.join(chk.get('problems') or []) or '四张源表不全'
        else:
            why = (f'今天（{today.isoformat()}）没有主题含「{keyword}」的邮件'
                   if not kw else f'主题含「{keyword}」的邮件都不是今天收到的')

        days = sorted({m['received_date'] for m in recent if m['received_date']}, reverse=True)
        scopes = [
            (f'窗口内主题含「{keyword}」的邮件', [m['uid'] for m in kw]),
            (f'最近一天（{days[0]}）收到的全部邮件' if days else '',
             [m['uid'] for m in recent if m['received_date'] == days[0]] if days else []),
            ('窗口内收到的全部邮件', [m['uid'] for m in recent]),
        ]
        tried, found = [], None
        for label, uids in scopes:
            if not uids:
                continue
            pick, covered, _ = minimal_pick(imap, uids, cache)
            chk = pool_check(imap, pick, cache) if pick else {'complete': False, 'roles': {}}
            tried.append({'scope': label, 'scanned': len(uids), 'picked': pick,
                          'complete': bool(chk.get('complete')),
                          'roles': sorted(chk.get('roles', {})),
                          'missing': sorted(set(REQUIRED_ROLES) - covered)})
            if chk.get('complete'):
                # 先严后宽，第一个凑齐的就是最贴近约定的，后面的范围只会更松，不必再下载
                found = {'scope': label, 'uids': pick, 'verification': chk}
                break

        base['auto'] = False
        base['reason'] = why
        base['tried'] = tried
        if found:
            uids = found['uids']
            base['uids'] = uids
            base['proposed'] = [_brief(cache[u]) for u in uids]
            base['verification'] = strip_blobs(found['verification'])
            base['question'] = (f'{why}。按附件内容检索（{found["scope"]}），'
                                f'其中 {len(uids)} 封可以凑齐四张源表。是否按这几封继续？'
                                f'（uid：{"、".join(uids)}；以哪封为准也可以直接指定）')
        else:
            missing = sorted({r for t in tried for r in t['missing']})
            base['question'] = (f'{why}，且放宽检索也没能凑齐四张源表。'
                                f'已检索 {len(recent)} 封、{args.days} 天内的邮件。'
                                f'还缺：{"、".join(ROLE_LABEL[m] for m in missing) or "未知"}。'
                                f'请确认源邮件是否已到，或直接指定邮件。')
            base['missing_roles'] = missing
        return base
    finally:
        try:
            imap.logout()
        except Exception:
            pass


def cmd_fetch(args) -> dict:
    acct = resolve_account()
    imap = connect(acct)
    try:
        typ, _ = imap.select(acct['inbox'], readonly=True)
        if typ != 'OK':
            raise RuntimeError(f"SELECT {acct['inbox']} 失败")
        msgs = [fetch_message(imap, u) for u in args.uid]
    finally:
        try:
            imap.logout()
        except Exception:
            pass

    dated = [m for m in msgs if m['received_date']]
    if not dated:
        return {'ok': False, 'error': '取不到邮件日期，无法命名工作目录'}
    _all = classify([a for m in msgs for a in m['attachments']])
    _tpl = _all['roles'].get('template', {}).get('filename')
    main = next((m for m in dated if any(a['filename'] == _tpl for a in m['attachments'])),
                max(dated, key=lambda m: m['received']))
    workdir = Path(args.workdir) if args.workdir else _workdir_for(Path(args.root), main['received'].date())
    src = workdir / 'source'
    attachments = []
    for m in msgs:
        for att in m['attachments']:
            src.mkdir(parents=True, exist_ok=True)
            (src / att['filename']).write_bytes(att['blob'])
            attachments.append(att)
    cls = classify(attachments)
    ensure_template(cls, src)
    meta = {
        'ok': cls['ok'],
        'workdir': str(workdir),
        'source_dir': str(src),
        'received_date': main['received_date'],
        'mails': [{'uid': m['uid'], 'subject': m['subject'], 'from': m['from'],
                   'received_date': m['received_date'],
                   'attachments': [a['filename'] for a in m['attachments']]} for m in msgs],
        'roles': {k: {'file': v['filename'], 'level': v.get('level'), 'period': v.get('period')}
                  for k, v in cls['roles'].items()},
        'unknown_files': cls['unknown_files'],
        'problems': cls['problems'],
        'notices': cls.get('notices', []),
        'attachment_count': cls.get('attachment_count', len(attachments)),
        'reply': {'to': parseaddr(main['from'])[1], 'subject': main['subject'],
                  'message_id': main['message_id'], 'uid': main['uid']},
    }
    payload = {k: {'filename': v['filename'], 'level': v.get('level'), 'period': v.get('period'),
                   'data': v.get('data'), 'sum_e': v.get('sum_e'), 'sum_k': v.get('sum_k'),
                   'title': v.get('title'), 'fallback': v.get('fallback')}
               for k, v in cls['roles'].items()}
    (workdir / 'roles.json').write_text(
        json.dumps({'roles': payload, 'reply': meta['reply'],
                    'received_date': meta['received_date'],
                    'notices': cls.get('notices', [])}, ensure_ascii=False, indent=1), 'utf-8')
    return meta


def _load_roles(workdir: Path, source=None) -> dict:
    meta_p = workdir / 'roles.json'
    if not meta_p.exists():
        raise RuntimeError(f'缺少 {meta_p}，请先执行 fetch')
    meta = json.loads(meta_p.read_text('utf-8'))
    src = Path(source) if source else (workdir / 'source')
    roles = {}
    for role, info in meta['roles'].items():
        entry = dict(info)
        blob = (src / info['filename']).read_bytes()
        if role == 'template':
            entry['blob'] = blob
        roles[role] = entry
    return {'roles': roles, 'reply': meta.get('reply', {}),
            'received_date': meta.get('received_date'), 'notices': meta.get('notices', []),
            'report_date': meta.get('report_date')}


def _remember_report_date(workdir: Path, biz) -> None:
    """把通报日期补进 roles.json，send 据此组回信标题（格式：薪管家_YYYYMMDD）。"""
    meta_p = workdir / 'roles.json'
    if not meta_p.exists():
        return
    try:
        meta = json.loads(meta_p.read_text('utf-8'))
    except Exception:
        return
    meta['report_date'] = biz.isoformat() if biz else None
    meta_p.write_text(json.dumps(meta, ensure_ascii=False, indent=1), 'utf-8')


def reply_subject(biz) -> str:
    """回信标题：薪管家_YYYYMMDD（通报日期）。"""
    if not biz:
        return '薪管家'
    return f'薪管家_{biz.strftime("%Y%m%d")}'


def cmd_build(args) -> dict:
    workdir = Path(args.workdir)
    loaded = _load_roles(workdir, getattr(args, 'source', None))
    roles = loaded['roles']
    miss = [ROLE_LABEL[r] for r in REQUIRED_ROLES if r not in roles]
    if miss:
        return {'ok': False, 'error': f'缺少源表：{"、".join(miss)}；请检查源邮件或用 fetch 重新取信'}

    blob = roles['template']['blob']
    title = roles['template'].get('title') or ''
    notices = list(dict.fromkeys(loaded.get('notices') or []))
    # 「截至」日期 = 发信日期 T-1（数据统计口径一般为 T-1），除非 --date 特殊注明。
    # 发件人的模板常常是前一天那份，标题日期恰好也是 T-1；但仍以发信日期推算为准。
    if args.date:
        biz = date.fromisoformat(args.date)
        blob, title = retitle(blob, biz)
        notices.append(f'标题日期已按 --date 指定为 {biz.isoformat()}：「{title}」')
    elif loaded.get('received_date'):
        got_d = date.fromisoformat(loaded['received_date'])
        biz = got_d - timedelta(days=1)
        blob, title = retitle(blob, biz)
        notices.append(f'标题日期按发信日期 {got_d.isoformat()} 的 T-1 取 {biz.isoformat()}：「{title}」')
    else:
        biz = title_date(title) or (datetime.now(TZ).date() - timedelta(days=1))
        notices.append(f'取不到发信日期，标题日期沿用模板自带的 {biz.isoformat()}：「{title}」')

    if args.out_name:
        name = args.out_name
    elif biz:
        name = f'薪管家通报{biz.month:02d}{biz.day:02d}.xlsx'
    else:
        name = f'薪管家通报{Path(roles["template"]["filename"]).stem}.xlsx'
    out_path = workdir / 'out' / name
    # 清掉上一次的产物，避免 --date / --out-name 改过之后 out/ 里留着旧文件拿错
    if out_path.parent.is_dir():
        stale = [p for p in out_path.parent.glob('*.xlsx') if p.name != name]
        for p in stale:
            try:
                p.unlink()
                notices.append(f'已清掉上一次的产物 {p.name}')
            except OSError:
                pass
    res = fill_report(blob, roles, out_path)

    body = build_text(title, res['totals'], roles)
    (workdir / '文案.txt').write_text(body, 'utf-8')
    # 把通报日期写回 roles.json，send 要用它组回信标题
    _remember_report_date(workdir, biz)
    return {'ok': True, 'workdir': str(workdir), 'report': str(out_path),
            'report_name': out_path.name, 'title': title,
            'report_date': biz.isoformat() if biz else None,
            'totals': res['totals'], 'warnings': res['warnings'],
            'notices': list(dict.fromkeys(notices)),
            'text_file': str(workdir / '文案.txt'), 'text': body,
            'reply': loaded['reply']}


def cmd_send(args) -> dict:
    workdir = Path(args.workdir)
    loaded = _load_roles(workdir)
    reply = loaded['reply']
    xlsx = [p for p in sorted((workdir / 'out').glob('*.xlsx'))]
    if not xlsx:
        return {'ok': False, 'error': f'{workdir}/out 下没有 xlsx，请先 build'}
    report = xlsx[0]
    txt = workdir / '文案.txt'
    if not txt.exists():
        return {'ok': False, 'error': '没有文案文件，请先 build'}
    body = txt.read_text('utf-8')
    sender = (args.to or reply.get('to') or '').strip()
    if not sender:
        return {'ok': False, 'error': '没有收件人（源邮件没有解析出发件人地址）'}
    to_list = dedup_addresses([sender] + list(FIXED_RECIPIENTS))
    to = ', '.join(to_list)
    # 回信标题统一为「薪管家_YYYYMMDD」（通报日期），不再沿用原邮件主题
    biz = None
    if loaded.get('report_date'):
        biz = date.fromisoformat(loaded['report_date'])
    else:
        m = re.search(r'(\d{4})(\d{2})(\d{2})', report.stem)
        if m:
            biz = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    subject = args.subject or reply_subject(biz)

    acct = resolve_account()
    msg = EmailMessage()
    msg['From'] = acct['user']
    msg['To'] = to
    msg['Subject'] = subject
    msg['Date'] = formatdate(localtime=True)
    if reply.get('message_id'):
        msg['In-Reply-To'] = reply['message_id']
        msg['References'] = reply['message_id']
    msg.set_content(body)
    msg.add_attachment(report.read_bytes(), maintype='application',
                       subtype='vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                       filename=report.name)
    if args.dry_run:
        return {'ok': True, 'dry_run': True, 'to': to, 'recipients': to_list,
                'subject': subject, 'attachment': report.name,
                'bytes': len(report.read_bytes()),
                'smtp': f"{acct['smtp_host']}:{acct['smtp_port']}", 'body': body}

    force_ipv4()
    ctx = ssl.create_default_context()
    if acct['smtp_port'] == 465:
        server = smtplib.SMTP_SSL(acct['smtp_host'], acct['smtp_port'], context=ctx, timeout=60)
    else:
        server = smtplib.SMTP(acct['smtp_host'], acct['smtp_port'], timeout=60)
        server.starttls(context=ctx)
    try:
        server.login(acct['user'], acct['password'])
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except Exception:
            pass
    return {'ok': True, 'sent': True, 'to': to, 'recipients': to_list,
            'subject': subject, 'attachment': report.name,
            'smtp': f"{acct['smtp_host']}:{acct['smtp_port']}"}


def cmd_run(args) -> dict:
    got = cmd_fetch(args)
    if not got.get('ok'):
        return got
    out = cmd_build(argparse.Namespace(workdir=got['workdir'], source=None,
                                       date=getattr(args, 'date', None), out_name=None))
    for k in ('received_date', 'attachment_count', 'problems', 'unknown_files', 'roles',
              'workdir', 'mails'):
        out.setdefault(k, got.get(k))
    # notices 两边都可能有，合并后去重（顺序保持）
    out['notices'] = list(dict.fromkeys(list(got.get('notices') or []) + list(out.get('notices') or [])))
    out['fetch'] = got
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description='工银薪管家「聚薪行动」日通报：取信/填表/回信')
    sub = ap.add_subparsers(dest='cmd', required=True)

    d = sub.add_parser('find', help='按约定找源邮件：主题含关键词且当天收到则直接执行，否则报告并请示')
    d.add_argument('--keyword', default=KEYWORD, help=f'主题关键词，默认「{KEYWORD}」')
    d.add_argument('--date', default=None, help='把哪天当作"今天"（YYYY-MM-DD）')
    d.add_argument('--days', type=int, default=3, help='放宽检索的回看天数，默认 3')
    d.set_defaults(func=cmd_find)

    f = sub.add_parser('fetch', help='按 uid 取信并把附件存到工作目录')
    f.add_argument('--uid', action='append', required=True)
    f.add_argument('--root', default=str(DEFAULT_ROOT), help='工作目录根，默认 D:\\资料\\ICBC\\automations')
    f.add_argument('--workdir', default=None)
    f.set_defaults(func=cmd_fetch)

    b = sub.add_parser('build', help='把四张源表填进通报模板')
    b.add_argument('--workdir', required=True)
    b.add_argument('--source', default=None)
    b.add_argument('--date', default=None, help='重写标题里的「截至」日期（YYYY-MM-DD）')
    b.add_argument('--out-name', default=None, help='输出文件名，默认沿用模板名')
    b.set_defaults(func=cmd_build)

    s = sub.add_parser('send', help='把通报回复给发件人 + 三个固定收件人')
    s.add_argument('--workdir', required=True)
    s.add_argument('--to', default=None)
    s.add_argument('--subject', default=None, help='覆盖回信标题，默认「薪管家_YYYYMMDD」')
    s.add_argument('--dry-run', action='store_true')
    s.set_defaults(func=cmd_send)

    r = sub.add_parser('run', help='fetch + build（不发信）')
    r.add_argument('--uid', action='append', required=True)
    r.add_argument('--root', default=str(DEFAULT_ROOT))
    r.add_argument('--workdir', default=None)
    r.add_argument('--date', default=None)
    r.set_defaults(func=cmd_run)

    args = ap.parse_args()
    try:
        out = args.func(args)
    except Exception as exc:
        import traceback
        out = {'ok': False, 'error': f'{type(exc).__name__}: {exc}',
               'traceback': traceback.format_exc()[-1500:]}
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    raise SystemExit(0 if out.get('ok') else 1)


if __name__ == '__main__':
    main()
