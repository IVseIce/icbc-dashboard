#!/home/isee/.venvs/data-tools/bin/python
# -*- coding: utf-8 -*-
"""icbc-sbqb —— 数字人民币个人钱包发展通报：取信 → 计算 → 填表 → 出文案 → 回信。

脚本只做确定性的事：IMAP 取信/下载附件、按内容识别源表、按固定口径汇总、
把数据覆盖进通报模板（保留一切格式与条件格式）、按固定版式生成 HTML 正文、SMTP 回信。
判断类的事（选哪封邮件、文案措辞）交给模型，见同目录 SKILL.md。

用法
----
  icbc-sbqb.py find   [--days 3] [--date YYYY-MM-DD] [--keyword 数币]
  icbc-sbqb.py fetch  --uid U [--uid U ...] [--root DIR] [--workdir DIR]
  icbc-sbqb.py build  --workdir DIR [--source DIR] [--no-text]
  icbc-sbqb.py send   --workdir DIR [--to ADDR] [--subject S] [--dry-run]
  icbc-sbqb.py run    --uid U [--uid U ...] [--root DIR]      # fetch + build，不发信

输出一律 JSON（stdout）。任何源表缺失/不匹配都返回 ok=false 并停止。
"""
from __future__ import annotations

import argparse
import email
import imaplib
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
    import xlrd
except ImportError as exc:  # pragma: no cover
    print(json.dumps({'ok': False, 'error': f'缺少依赖: {exc}；请用 /home/isee/.venvs/data-tools/bin/python 运行'},
                     ensure_ascii=False))
    raise SystemExit(2)

warnings.filterwarnings('ignore')

TZ = ZoneInfo('Asia/Shanghai')
DSH_HOME = Path(os.environ.get('DSH_HOME') or (Path.home() / '.dsh'))
SKILL_DIR = Path(__file__).resolve().parent
FALLBACK_TEMPLATE = SKILL_DIR / 'assets' / 'template.xlsx'
# 网点号对照表：网点基本不变、以后邮件不再发，已固化进技能（原件是 xls 格式）
BUNDLED_NETNO = SKILL_DIR / 'assets' / 'netno.xls'
BODY_STYLE = SKILL_DIR / 'assets' / 'body_style.css'
DEFAULT_ROOT = Path('/mnt/d/资料/ICBC/automations')
WORKDIR_SUFFIX = '_数字人民币钱包'

# ---------------------------------------------------------------- 口径常量
# 源表列号（1-based，来自 原始表例.xlsx 字段字典）
C_LEVEL = 9          # 钱包等级：1/2/3/4 → 一类/二类/三类/四类
C_REGDATE = 27       # 注册日期
C_NETNO = 36         # 网点号
C_PARTDT = 38        # 分区日期（快照日期）

# 网点号 -> (支行, 网点名)。网点号表是 xls(OLE2) 却被存成 .xlsx 后缀，故两套读取器都试。
NETNO_HEADERS = ('支行', '网点', '网点号')

# 映射表的网点名与模板行名的差异，逐条对应（改前先问用户）
TEMPLATE_ALIAS = {
    '颍东岳家湖支行': '阜阳岳家湖支行',    # 模板作「岳家湖」，映射表带「颍东」
    '阜阳城建支行': '阜阳城建支行',        # 映射表已带前缀
}

# 模板结构：A支行 B网点 C一类 D二类 E三类 F四类 G总数 H当月新增 I当日新增
T_FIRST, T_LAST = 3, 42
TOTAL_ROW = 43
COL_BRANCH, COL_NET, COL_FIRST_DATA, COL_LAST_DATA = 1, 2, 3, 9

# 邮件
KEYWORD = '数币'
KEYWORDS_EXTRA = ('数字人民币', '钱包')
FIXED_RECIPIENTS: tuple[str, ...] = ()      # 暂定只回发件人，不追加人

PROVIDERS = {
    '163': ('imap.163.com', 993, 'smtp.163.com', 465),
    '126': ('imap.126.com', 993, 'smtp.126.com', 465),
    'qq': ('imap.qq.com', 993, 'smtp.qq.com', 465),
    'sina': ('imap.sina.com', 993, 'smtp.sina.com', 465),
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


def _env_password() -> tuple[str, str] | None:
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
        imap.xatom('ID', '("name" "dsh-icbc-sbqb" "version" "1.0" "vendor" "dsh")')
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


def _imap_date(d: date) -> str:
    months = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')
    return f'{d.day:02d}-{months[d.month - 1]}-{d.year}'


def fetch_message(imap, uid: str) -> dict:
    typ, data = imap.uid('FETCH', uid, '(RFC822)')
    if typ != 'OK' or not data or not isinstance(data[0], tuple):
        raise RuntimeError(f'取信失败 uid={uid}')
    msg = email.message_from_bytes(data[0][1])
    received = None
    try:
        dt = parsedate_to_datetime(msg.get('Date'))
        received = dt.astimezone(TZ).date()
    except Exception:
        pass
    return {
        'uid': str(uid),
        'subject': _decode(msg.get('Subject')),
        'from': _decode(msg.get('From')),
        'message_id': (msg.get('Message-ID') or '').strip(),
        'received_date': received.isoformat() if received else None,
        'msg': msg,
    }


def list_recent(imap, since: date, cap: int = 400) -> list[dict]:
    typ, data = imap.uid('SEARCH', None, f'(SINCE {_imap_date(since)})')
    if typ != 'OK':
        raise RuntimeError('IMAP SEARCH 失败')
    uids = (data[0] or b'').split()
    out = []
    for raw in uids[-cap:]:
        uid = raw.decode()
        try:
            m = fetch_message(imap, uid)
        except Exception:
            continue
        out.append(m)
    out.sort(key=lambda m: (m['received_date'] or '', m['uid']))
    return out


def _brief(m: dict) -> dict:
    return {'uid': m['uid'], 'subject': m['subject'], 'from': m['from'],
            'received_date': m['received_date']}


# ================================================================ 附件识别
def iter_attachments(msg) -> list[dict]:
    out = []
    for part in msg.walk():
        fn = part.get_filename()
        if not fn:
            continue
        name = _decode(fn)
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        out.append({'filename': name, 'content_type': part.get_content_type(), 'blob': payload})
    return out


def _xlsx_sheets(blob: bytes) -> list[str]:
    import io
    wb = openpyxl.load_workbook(io.BytesIO(blob), read_only=True)
    try:
        return list(wb.sheetnames)
    finally:
        wb.close()


def _read_any_table(blob: bytes) -> list[list]:
    """读 xlsx；失败则按 xls(OLE2) 读（网点号.xlsx 实为 xls）。"""
    import io
    try:
        wb = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
        try:
            ws = wb.worksheets[0]
            return [list(r) for r in ws.iter_rows(values_only=True)]
        finally:
            wb.close()
    except Exception:
        pass
    book = xlrd.open_workbook(file_contents=blob)
    ws = book.sheet_by_index(0)
    return [[ws.cell_value(r, c) for c in range(ws.ncols)] for r in range(ws.nrows)]


def _as_date(v) -> date | None:
    """把单元格值当日期解析。

    xlsx 里「分区日期」可能是 datetime，也可能是 '2026-10-08' / '20261008' 这类字符串
    （历史上那封 6 万行堆表就是字符串），所以两种都要认。
    """
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if v is None:
        return None
    s = str(v).strip().replace('/', '-').replace('.', '-')
    s = s.split(' ')[0]
    if not s:
        return None
    digits = s.replace('-', '')
    for cand in (s, digits):
        for fmt in ('%Y-%m-%d', '%Y%m%d'):
            try:
                return datetime.strptime(cand, fmt).date()
            except ValueError:
                continue
    return None


def probe_source(blob: bytes) -> dict | None:
    """源表明细：含「网点号」「钱包等级」「注册日期」表头。"""
    try:
        rows = _read_any_table(blob)
    except Exception:
        return None
    if not rows:
        return None
    header = [str(x).strip() if x is not None else '' for x in rows[0]]
    need = {'网点号', '钱包等级', '注册日期'}
    if not need.issubset(set(header)):
        return None
    idx = {h: i for i, h in enumerate(header) if h}
    i_net = idx['网点号']
    # 只算「有网点号」的行，避免尾部空行把行数撑大
    body = [r for r in rows[1:] if i_net < len(r) and norm_netno(r[i_net])]
    if not body:
        return None
    # 快照日期：日报快照里「分区日期」应当**只有一个值**。
    # 历史上发过跨多月的全量堆表（6 万多行、分区日期混杂），那种表不能当日报用，
    # 否则会把几个月的数据当成一天的累计 —— 直接判为不可用。
    snap = None
    snap_dates: list[str] = []
    if '分区日期' in idx:
        j = idx['分区日期']
        snap_dates = sorted({d.isoformat() for d in
                             (_as_date(r[j]) for r in body if j < len(r)) if d})
        if len(snap_dates) == 1:
            snap = snap_dates[0]
    return {'role': 'source', 'rows': len(body), 'snapshot': snap,
            'snapshot_dates': snap_dates[:20], 'snapshot_count': len(snap_dates),
            'single_snapshot': len(snap_dates) == 1,
            'header': header, 'idx': idx, 'data': body}


def probe_netno(blob: bytes) -> dict | None:
    """网点号对照表：表头含 支行/网点/网点号（现由 assets/netno.xls 内置提供）。"""
    try:
        rows = _read_any_table(blob)
    except Exception:
        return None
    if not rows:
        return None
    header = [str(x).strip() if x is not None else '' for x in rows[0]]
    if not set(NETNO_HEADERS).issubset(set(header)):
        return None
    i_no = header.index('网点号')
    body = [r for r in rows[1:] if i_no < len(r) and norm_netno(r[i_no])]
    return {'role': 'netno', 'rows': len(body), 'header': header, 'data': rows}


def probe_template(blob: bytes) -> dict | None:
    """通报模板：A1 含「数字人民币个人钱包发展通报」。"""
    try:
        import io
        wb = openpyxl.load_workbook(io.BytesIO(blob))
        ws = wb.worksheets[0]
        a1 = str(ws.cell(1, 1).value or '')
        if '数字人民币个人钱包发展通报' in a1:
            merged = sorted(str(r) for r in ws.merged_cells.ranges)
            return {'role': 'template', 'title': a1, 'merged': merged,
                    'header': [ws.cell(2, c).value for c in range(1, 10)]}
    except Exception:
        return None
    return None


PROBES = (probe_source, probe_netno, probe_template)


def _bundled_netno() -> dict | None:
    """读技能内置的网点号对照表（网点基本不变，邮件不再发）。"""
    try:
        hit = probe_netno(BUNDLED_NETNO.read_bytes())
    except Exception:
        return None
    if hit:
        hit['filename'] = BUNDLED_NETNO.name
        hit['source'] = 'builtin'
    return hit


def classify(attachments: list[dict]) -> dict:
    roles: dict[str, dict] = {}
    unknown: list[dict] = []
    tmpl_blob = None
    for att in attachments:
        hit = None
        for probe in PROBES:
            try:
                hit = probe(att['blob'])
            except Exception:
                hit = None
            if hit:
                break
        if not hit:
            unknown.append({'filename': att['filename'], 'content_type': att['content_type']})
            continue
        role = hit['role']
        if role == 'template':
            if 'template' not in roles:
                roles['template'] = {**hit, 'filename': att['filename']}
                tmpl_blob = att['blob']
            else:
                unknown.append({'filename': att['filename'], 'content_type': att['content_type'],
                                'note': '模板重复，已忽略后一个'})
            continue
        if role == 'netno':
            # 网点号对照表已固化进技能，邮件里的（若有）只作参考、不采用
            unknown.append({'filename': att['filename'], 'content_type': att['content_type'],
                            'note': '网点号对照表已内置，邮件附件忽略'})
            continue
        if role in roles:
            # 源表重复：**先要有单一快照**（多月份堆表不能用），再比快照日期新的，最后比行数
            old, new = roles[role], hit
            o_ok, n_ok = bool(old.get('single_snapshot')), bool(new.get('single_snapshot'))
            if n_ok != o_ok:
                better = n_ok
            elif not n_ok:
                better = False                      # 两份都不是日报，保留先到的
            else:
                better = ((new.get('snapshot') or '') > (old.get('snapshot') or '')
                          or ((new.get('snapshot') or '') == (old.get('snapshot') or '')
                              and new.get('rows', 0) > old.get('rows', 0)))
            if better:
                roles[role] = {**hit, 'filename': att['filename'], 'blob': att['blob']}
            unknown.append({'filename': att['filename'], 'content_type': att['content_type'],
                            'note': f"{role} 重复，已保留"
                                    f"{'后一份' if better else '先一份'}"
                                    f"（快照 {new.get('snapshot') or '未知'} / {old.get('snapshot') or '未知'}）"})
            continue
        roles[role] = {**hit, 'filename': att['filename'], 'blob': att['blob']}

    # 网点号对照表：一律用内置的
    netno = _bundled_netno()
    if netno:
        roles['netno'] = netno
    else:
        unknown.append({'filename': BUNDLED_NETNO.name, 'content_type': '',
                        'note': '内置网点号对照表读不出来，请检查 assets/'})

    problems = []
    if 'source' not in roles:
        problems.append('没有找到数币明细源表（表头需含 网点号/钱包等级/注册日期）')
    elif not roles['source'].get('single_snapshot'):
        # 多月份全量堆表不能当日报用（会把几个月的数据当成一天的累计）
        got = (roles['source'].get('snapshot_dates') or [])[:5]
        problems.append(
            f"数币明细源表不是「单日快照」：分区日期有 "
            f"{roles['source'].get('snapshot_count', 0)} 个"
            + (f"（如 {got}）" if got else "（该列缺失）")
            + "，无法确定数据日期")
    if 'netno' not in roles:
        problems.append(f'内置网点号对照表不可用（{BUNDLED_NETNO}）')
    return {'roles': {k: {kk: vv for kk, vv in v.items() if kk not in ('blob', 'data', 'idx')}
                      for k, v in roles.items()},
            '_roles': roles, '_tmpl_blob': tmpl_blob,
            'unknown_files': unknown, 'problems': problems,
            'complete': not problems}


# ================================================================ 计算
def norm_netno(v) -> str | None:
    """网点号统一 4 位：先去掉多余的前导 0，再不足则前补 0。

    源表导出格式变过：10-08 及以前是「不补 0」的 2~4 位（555 / 2420），
    10-09 起变成 **5 位零填充**（00319 / 02324 / 09558）。两种情况都要能对上
    4 位的内置对照表，所以先 lstrip('0')：555→0555、00319→0319、2420→2420。
    """
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).strip()
    if s.endswith('.0'):
        s = s[:-2]
    s = s.strip()
    if not s:
        return None
    if s.isdigit():
        s = s.lstrip('0') or '0'
    return s.zfill(4)


def load_netno(role: dict) -> tuple[dict[str, tuple[str, str]], dict[str, str]]:
    """返回 no -> (支行, 网点名) 与 网点名 -> no。"""
    rows = role['data']
    header = [str(x).strip() if x is not None else '' for x in rows[0]]
    i_br, i_net, i_no = (header.index('支行'), header.index('网点'), header.index('网点号'))
    no2info, name2no, branch_of = {}, {}, {}
    last_branch = ''
    for r in rows[1:]:
        if len(r) <= max(i_br, i_net, i_no):
            continue
        br = str(r[i_br]).strip() if r[i_br] not in (None, '') else ''
        if br:
            last_branch = br
        net = str(r[i_net]).strip() if r[i_net] not in (None, '') else ''
        no = norm_netno(r[i_no])
        if not no or not net:
            continue
        br_short = last_branch.replace('支行', '') if last_branch else ''
        no2info[no] = (br_short, net)
        name2no[net] = no
        branch_of[net] = br_short
    return no2info, name2no


def compute(roles: dict) -> dict:
    src = roles['source']
    idx = src['idx']
    rows = src['data']
    i_no, i_lv, i_reg = idx['网点号'], idx['钱包等级'], idx['注册日期']
    no2info, _ = load_netno(roles['netno'])

    # 快照日期必须唯一。多月份全量堆表（分区日期混杂）不能当日报累计，
    # 否则「钱包开立总数 / 当月新增 / 当日新增」全都会算错 —— 直接报错让上层拦住。
    if not src.get('single_snapshot') or not src.get('snapshot'):
        got = src.get('snapshot_dates') or []
        raise RuntimeError(
            '源表不是「单日快照」，无法确定数据日期：'
            f'分区日期共 {src.get("snapshot_count", 0)} 个'
            + (f'（如 {got[:5]}）' if got else '（该列缺失）')
            + '。请确认用的是当日快照明细表，而不是历史全量堆表。')
    snap = date.fromisoformat(src['snapshot'])
    month_start = snap.replace(day=1)

    agg: dict[str, list[int]] = {}
    unmapped: dict[str, int] = {}
    for r in rows:
        if len(r) <= max(i_no, i_lv, i_reg):
            continue
        no = norm_netno(r[i_no])
        if no is None:
            continue
        if no not in no2info:
            unmapped[no] = unmapped.get(no, 0) + 1
            continue
        rec = agg.setdefault(no, [0, 0, 0, 0, 0, 0, 0])
        try:
            lv = int(r[i_lv])
        except (TypeError, ValueError):
            lv = None
        if lv in (1, 2, 3, 4):
            rec[lv - 1] += 1
        rec[4] += 1
        dd = _as_date(r[i_reg])
        if dd:
            if month_start <= dd <= snap:
                rec[5] += 1
            if dd == snap:
                rec[6] += 1

    nets = []
    for no, rec in agg.items():
        br, name = no2info[no]
        nets.append({'netno': no, 'branch': br, 'name': name,
                     'lv': rec[:4], 'total': rec[4], 'month': rec[5], 'day': rec[6]})
    nets.sort(key=lambda x: (x['branch'], x['netno']))

    totals = [sum(n['lv'][i] for n in nets) for i in range(4)]
    totals += [sum(n['total'] for n in nets), sum(n['month'] for n in nets), sum(n['day'] for n in nets)]
    return {'nets': nets, 'totals': totals, 'snapshot': snap.isoformat(),
            'month_start': month_start.isoformat(),
            'unmapped_netno': dict(sorted(unmapped.items())),
            'source_rows': src['rows'],
            'mapped_rows': sum(n['total'] for n in nets)}


# ================================================================ 写表
def resolve_row(name2row: dict[str, int], branch: str, net: str) -> int | None:
    """映射表网点名 -> 模板行号（模板名带「阜阳」前缀）。"""
    if net in TEMPLATE_ALIAS:
        return name2row.get(TEMPLATE_ALIAS[net])
    if net in name2row:
        return name2row[net]
    cand = net if net.startswith('阜阳') else '阜阳' + net
    if cand in name2row:
        return name2row[cand]
    # 去掉「阜阳」后比对，容忍后缀差异
    short = {k[2:] if k.startswith('阜阳') else k: v for k, v in name2row.items()}
    return short.get(net[2:] if net.startswith('阜阳') else net)


def write_report(template_blob: bytes, data: dict, out_path: Path) -> dict:
    """只覆盖数据和 A1 标题文本，一切格式/条件格式原样保留。"""
    import io
    from openpyxl.styles import Font
    from openpyxl.styles.colors import Color

    wb = openpyxl.load_workbook(io.BytesIO(template_blob))
    ws = wb.worksheets[0]

    # A1 标题里的「截至X月X日」必须跟随源表快照日：模板自带的日期会过期
    # （10-08 的快照恰好与模板同日，曾把这个问题盖住）。只改文本，字体/合并照旧。
    title = ws.cell(1, 1).value
    if title and '数字人民币个人钱包发展通报' in str(title):
        _, m, d = (int(x) for x in data['snapshot'].split('-'))
        ws.cell(1, 1).value = f'数字人民币个人钱包发展通报（截至{m}月{d}日）'

    # 模板条件格式里「红/绿实心底 + 字色 theme=0」的写法在 Excel 里读法有歧义，
    # 统一落成**显式白字加粗**：标红/标绿的格子数字是白的，正文表格照抄同一份规则。
    for _rng, _rules in ws.conditional_formatting._cf_rules.items():
        for _rule in _rules:
            _dxf = getattr(_rule, 'dxf', None)
            _fill = getattr(_dxf, 'fill', None) if _dxf is not None else None
            if _dxf is None or _fill is None or getattr(_fill, 'patternType', None) != 'solid':
                continue
            if getattr(_dxf, 'font', None) is None:
                _dxf.font = Font(bold=True, color='FFFFFFFF')
            else:
                _dxf.font.color = Color(rgb='FFFFFFFF')
                _dxf.font.b = True

    name2row = {}
    for r in range(T_FIRST, T_LAST + 1):
        v = ws.cell(r, COL_NET).value
        if v:
            name2row[str(v).strip()] = r
    if not name2row:
        raise RuntimeError('模板里没有网点行，结构可能已变')

    written, skipped = set(), []
    for n in data['nets']:
        row = resolve_row(name2row, n['branch'], n['name'])
        if row is None:
            skipped.append({'netno': n['netno'], 'name': n['name'], 'reason': '模板无对应行'})
            continue
        if row in written:
            skipped.append({'netno': n['netno'], 'name': n['name'], 'reason': f'行 {row} 已被占用'})
            continue
        written.add(row)
        n['order'] = row                      # 模板行序，用于并列时稳定排序
        n['display'] = str(ws.cell(row, COL_NET).value).strip()   # 模板里的网点名（带「阜阳」）
        vals = n['lv'] + [n['total'], n['month'], n['day']]
        for k, v in enumerate(vals):
            ws.cell(row, COL_FIRST_DATA + k).value = v

    # 模板里存在但数据里没有的网点补 0
    blanks = []
    for name, row in name2row.items():
        if row not in written:
            blanks.append(name)
            for k in range(7):
                ws.cell(row, COL_FIRST_DATA + k).value = 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return {'rows_written': len(written), 'rows_blanked': blanks,
            'skipped': skipped, 'path': str(out_path)}


# ================================================================ 文案
SHORT_RULES = (
    ('支行营业室', '营业室'),
    ('支行', ''),
)


def short_name(net: str) -> str:
    """仅保留原样网点名（去掉「阜阳」前缀）。

    实测转发通报的正文用的是**完整网点名**（如「临泉政务新区支行」「颍上支行营业室」），
    不要做「支行营业室→营业室」这类缩写，否则与通报口径不一致。
    """
    return net[2:] if net.startswith('阜阳') else net


def build_text(data: dict) -> dict:
    nets = data['nets']
    t = data['totals']
    y, m, d = (int(x) for x in data['snapshot'].split('-'))

    # 并列时按模板行序（order）先后取，与手工通报一致；没有 order 就退化为名称
    key = lambda n, f: (f(n), n.get('order', 10 ** 6), n['name'])
    by_total = sorted(nets, key=lambda n: key(n, lambda x: -x['total']))
    top3 = by_total[:3]
    bot3 = sorted(nets, key=lambda n: key(n, lambda x: x['total']))[:3]
    by_day = sorted(nets, key=lambda n: key(n, lambda x: -x['day']))
    top3_day = by_day[:3]
    zero_day = [n for n in nets if n['day'] == 0]

    j = lambda lst: '、'.join(f"{short_name(n['name'])}（{n['total']}户）" for n in lst)
    jd = lambda lst: '、'.join(f"{short_name(n['name'])}（{n['day']}户）" for n in lst)

    text = (
        f"截至{y}年{m}月{d}日，全行累计开立数字人民币个人钱包{t[4]}户。\n"
        f"数币个人钱包开立总户数前3名网点为：{j(top3)}请继续保持[强][强]；"
        f"后3名网点为：{j(bot3)}请努力追赶[加油][加油]\n"
        f"当日新开户前3名网点为：{jd(top3_day)}[强][强]"
    )
    # 没有「当日新增为 0」的网点时，最后这句整句去掉
    if zero_day:
        text += f"；当日新增为0的网点{len(zero_day)}个[心碎][心碎]，请务必破零[拳头]。"
    return {
        'text': text,
        'date_cn': f'{y}年{m}月{d}日',
        'date_title': f'{m}月{d}日',        # 表标题只用「10月8日」，不带年份
        'date_dot': f'{y}.{m}.{d}',
        'date_mmdd': f'{m}.{d}',
        'month_day': f'{m}月{d}日',
        'total': t[4],
        'top3_total': [{'name': n['name'], 'v': n['total']} for n in top3],
        'bot3_total': [{'name': n['name'], 'v': n['total']} for n in bot3],
        'top3_day': [{'name': n['name'], 'v': n['day']} for n in top3_day],
        'zero_day_count': len(zero_day),
        'totals': t,
    }


# ================================================================ HTML 正文
def _esc(s: str) -> str:
    return (str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


# ------------------------------------------------- 条件格式求值（正文表格照抄出表）
_THEME_RGB = {0: 'FFFFFF', 1: '000000'}      # Excel：theme 0 = 白（Background 1）、1 = 黑（Text 1）


def _color_hex(c) -> str | None:
    """把 openpyxl 的颜色对象归一成 'RRGGBB'；theme 只认 0/1，其余不猜。"""
    if c is None:
        return None
    try:
        t = getattr(c, 'type', None)
        if t == 'rgb':
            s = str(c.rgb or '')
            return s[-6:].upper() if len(s) == 8 and s.upper() != '00000000' else None
        if t == 'theme':
            return _THEME_RGB.get(c.theme)
    except Exception:
        return None
    return None


def _dxf_style(dxf) -> dict:
    """条件格式 dxf → {'fill': 'RRGGBB', 'color': 'RRGGBB', 'bold': bool}。"""
    if dxf is None:
        return {}
    st: dict = {}
    fill = getattr(dxf, 'fill', None)
    if fill is not None and getattr(fill, 'patternType', None) == 'solid':
        # dxf 的实心底色写在 bgColor 上（fgColor 多数是 00000000）
        st['fill'] = _color_hex(getattr(fill, 'bgColor', None)) or _color_hex(getattr(fill, 'fgColor', None))
    font = getattr(dxf, 'font', None)
    if font is not None:
        st['color'] = _color_hex(getattr(font, 'color', None))
        st['bold'] = bool(getattr(font, 'b', False))
    return {k: v for k, v in st.items() if v is not None}


def cf_style_map(xlsx_path, grid: dict) -> dict:
    """按出表自带的**条件格式**算出每格的红绿，正文表格直接用这份结果，免得两边打架。

    语义对齐 Excel 的「前/后 5 项」：阈值取第 5 大 / 第 5 小，**并列值全部着色**；
    同一格被多条规则命中时**优先级数字小的赢**（Excel 里 priority 1 先算）。
    `grid` = {(行, 列): 数值}，要**包含合计行**——`I2:I1048576` 覆盖到第 43 行，
    Excel 同样会给合计的「当日新增」上色。
    """
    wb = openpyxl.load_workbook(xlsx_path)
    ws = wb.worksheets[0]
    rules = []
    for rng, rs in ws.conditional_formatting._cf_rules.items():
        for sq in rng.sqref.ranges:
            for r in rs:
                rules.append((sq, r))
    rules.sort(key=lambda x: x[1].priority or 999)

    out: dict = {}
    for sq, rule in rules:
        if not str(getattr(rule, 'type', '') or '').startswith('top10'):
            continue
        rank = rule.rank or 10
        bottom = bool(rule.bottom)
        inside = [(rc, v) for rc, v in grid.items()
                  if sq.min_row <= rc[0] <= sq.max_row and sq.min_col <= rc[1] <= sq.max_col
                  and isinstance(v, (int, float))]
        if not inside:
            continue
        vals = sorted((v for _, v in inside), reverse=not bottom)
        thr = vals[min(rank, len(vals)) - 1]
        style = _dxf_style(getattr(rule, 'dxf', None))
        for rc, v in inside:
            if rc in out:
                continue
            if (v <= thr) if bottom else (v >= thr):
                out[rc] = style
    return out


def sheet_bg_map(xlsx_path, rows, cols) -> dict:
    """出表里各格的**静态底色**（实心填充）→ {(行, 列): 'RRGGBB'}，正文表格照抄。

    普通单元格的实心色在 `fgColor` 上（条件格式 dxf 才写在 bgColor 上，见 `_dxf_style`）。
    模板的隔行浅灰、合计行浅红底各在哪一格都由这张表决定，正文不再自己算斑马线。
    """
    wb = openpyxl.load_workbook(xlsx_path)
    ws = wb.worksheets[0]
    out: dict = {}
    for r in rows:
        for c in cols:
            f = ws.cell(r, c).fill
            if f is None or getattr(f, 'patternType', None) != 'solid':
                continue
            hexv = _color_hex(getattr(f, 'fgColor', None)) or _color_hex(getattr(f, 'bgColor', None))
            if hexv:
                out[(r, c)] = hexv
    return out


def table_html(data: dict, title: str, cf: dict | None = None, bg: dict | None = None) -> str:
    """按转发通报的版式生成表格。

    红绿**不再手写**：`cf` 是从出表 xlsx 的条件格式求出来的 {(行,列): 样式}；
    `bg` 是同一张表的静态底色。底色/字色/加粗全部照抄，正文表格与 xlsx 完全一致
    （含并列值、含合计行、含支行列的合并底色）。
    """
    nets = data['nets']

    def cell_css(row: int, col: int, base_color: str, base_bg: str, base_bold: bool = False) -> str:
        st = (cf or {}).get((row, col)) or {}
        color = f'#{st["color"]}' if st.get('color') else base_color
        sheet_bg = (bg or {}).get((row, col))
        if st.get('fill'):
            back = f'background:#{st["fill"]};'
        elif sheet_bg:
            back = f'background:#{sheet_bg};'
        else:
            back = base_bg
        weight = 'font-weight:700;' if (st.get('bold') or base_bold) else ''
        return f'color:{color};{weight}{back}'

    t = data['totals']
    H = []
    H.append('<table border="0" cellpadding="0" cellspacing="0" width="1096" '
             'style="font-family:宋体;text-wrap:wrap;border-collapse:collapse;">')
    H.append('<colgroup><col width="72" style="width:54pt;"><col width="224" style="width:168pt;">'
             '<col width="104" style="width:78pt;"><col width="112" span="3" style="width:84pt;">'
             '<col width="136" style="width:102pt;"><col width="112" span="2" style="width:84pt;"></colgroup>')
    H.append('<tbody>')
    H.append('<tr height="30" style="height:22.5pt;"><td colspan="9" '
             'style="padding:1px;color:#FFFFFF;font-size:16pt;font-weight:700;font-family:微软雅黑;'
             'border:0.5pt solid #000000;background:#C00000;text-align:center;vertical-align:middle;">'
             f'{_esc(title)}</td></tr>')
    hdr = ['支行', '网点', '一类', '二类', '三类', '四类', '钱包开立总数', '当月新增', '当日新增']
    H.append('<tr height="22" style="height:16.5pt;">')
    for i, h in enumerate(hdr):
        hbg = '#E7E7E7' if i < 2 else '#F0F0F0'
        sz = '11pt' if i < 2 else '10pt'
        H.append(f'<td style="padding:1px;font-size:{sz};text-wrap:nowrap;color:#222222;font-weight:700;'
                 f'font-family:微软雅黑;border:0.5pt solid #000000;background:{hbg};'
                 f'text-align:center;vertical-align:middle;">{h}</td>')
    H.append('</tr>')

    # 按模板行序排列（与 xlsx 一致），再按支行分组、首行带 rowspan
    nets = sorted(nets, key=lambda n: n.get('order', 10 ** 6))
    groups: dict[str, list[dict]] = {}
    for n in nets:
        groups.setdefault(n['branch'], []).append(n)
    for br, members in groups.items():
        for k, n in enumerate(members):
            row = n.get('order') or 0
            H.append('<tr height="20" style="height:15pt;">')
            if k == 0:
                acss = cell_css(row, COL_BRANCH, '#222222', '')
                H.append(f'<td rowspan="{len(members)}" style="padding:1px;font-size:11pt;'
                         f'font-family:微软雅黑;border:0.5pt solid #000000;{acss}'
                         f'text-align:center;vertical-align:middle;">{_esc(br)}</td>')
            bcss = cell_css(row, COL_NET, '#222222', '')
            H.append(f'<td style="padding:1px;font-size:11pt;font-family:微软雅黑;'
                     f'border:0.5pt solid #000000;{bcss}text-align:center;vertical-align:middle;">'
                     f'{_esc(n.get("display") or n["name"])}</td>')
            vals = n['lv'] + [n['total'], n['month'], n['day']]
            for j, v in enumerate(vals):
                css = cell_css(row, COL_FIRST_DATA + j, '#222222', '')
                H.append(f'<td style="padding:1px;font-size:11pt;font-family:微软雅黑;'
                         f'border:0.5pt solid #000000;{css}text-align:center;vertical-align:middle;">'
                         f'{v:,}</td>')
            H.append('</tr>')

    H.append('<tr height="22" style="height:16.5pt;">')
    total_row = T_LAST + 1
    acss = cell_css(total_row, COL_BRANCH, '#8B1420', 'background:#F9E7E7;', base_bold=True)
    H.append(f'<td colspan="2" style="padding:1px;font-size:11pt;font-family:微软雅黑;'
             f'border:0.5pt solid #000000;{acss}text-align:center;vertical-align:middle;">合计</td>')
    for j, v in enumerate(t):
        css = cell_css(total_row, COL_FIRST_DATA + j, '#8B1420', 'background:#F9E7E7;', base_bold=True)
        H.append(f'<td style="padding:1px;font-size:11pt;font-family:微软雅黑;'
                 f'border:0.5pt solid #000000;{css}text-align:center;vertical-align:middle;">{v:,}</td>')
    H.append('</tr>')
    H.append('</tbody></table>')
    return ''.join(H)


def body_style_maps(data: dict, xlsx_path) -> tuple[dict, dict]:
    """正文表格要用的两套样式，全部从出表 xlsx 现读：条件格式求值 + 静态底色。"""
    grid: dict = {}
    for n in data['nets']:
        row = n.get('order')
        if not row:
            continue
        for j, v in enumerate(n['lv'] + [n['total'], n['month'], n['day']]):
            grid[(int(row), COL_FIRST_DATA + j)] = v
    for j, v in enumerate(data['totals']):
        grid[(T_LAST + 1, COL_FIRST_DATA + j)] = v
    return (cf_style_map(xlsx_path, grid),
            sheet_bg_map(xlsx_path, list(range(T_FIRST, T_LAST + 2)),
                         list(range(COL_BRANCH, COL_LAST_DATA + 1))))


def build_html(data: dict, meta: dict, note: str | None = None,
               cf: dict | None = None, bg: dict | None = None) -> str:
    """正文 = 转发通报同版式：仿宋_GB2312 16pt、首行缩进 2em、红色前3/绿色后3。"""
    t = data['totals']
    bt = meta['top3_total']
    bb = meta['bot3_total']
    bd = meta['top3_day']
    date_cn = meta['date_cn']
    title = f'数字人民币个人钱包发展通报（截至{meta["date_title"]}）'

    jt = '、'.join(f'{short_name(x["name"])}（{x["v"]}户）' for x in bt)
    jb = '、'.join(f'{short_name(x["name"])}（{x["v"]}户）' for x in bb)
    jd = '、'.join(f'{short_name(x["name"])}（{x["v"]}户）' for x in bd)

    style = BODY_STYLE.read_text('utf-8') if BODY_STYLE.exists() else ''
    P = 'font-family:宋体;text-wrap:wrap;font-size:21.3333px;'
    IND = P + 'text-indent:2em;'
    FS = 'font-family:仿宋_GB2312;'
    F16 = 'font-size:16pt;'

    out = []
    if style:
        out.append(f'<style>{style}</style>')
    out.append('<div class="default-font-1791546254880" dir="ltr">')
    out.append(f'<p style="{P}"><span style="{F16}{FS}">各支行：<br></span></p>')
    out.append(f'<p style="{IND}"><span style="{FS}"><span style="{F16}">'
               '数字人民币个人钱包是个人客户使用数字人民币开展收付和支付结算的主要载体，'
               '为加快推动全行数字人民币个人钱包开立，现将相关情况通报如下：</span></span></p>')
    out.append(f'<p style="{IND}"><span style="{FS}"><span style="{F16}">'
               '<strong>一、各行数币个人钱包情况</strong></span></span></p>')
    out.append(f'<p style="{IND}"><span style="{FS}"><span style="{F16}">'
               f'截至{date_cn}，全行累计开立数字人民币个人钱包{t[4]}户。</span></span></p>')
    out.append(
        f'<p style="{IND}"><span style="{FS}"><span style="{F16}">数币个人钱包开立总户数前3名网点为：'
        f'<span style="color:#FF0000;"><strong>{jt}</strong></span>请继续保持[强][强]；后3名网点为：'
        f'<span style="color:#00B050;"><strong>{jb}</strong></span>请努力追赶[加油][加油]</span></span></p>')
    tail = (f'；当日新增为0的网点{meta["zero_day_count"]}个[心碎][心碎]，请务必破零[拳头]。'
            if meta.get('zero_day_count') else '')
    out.append(
        f'<p style="{IND}"><span style="{FS}"><span style="{F16}">当日新开户前3名网点为：'
        f'<span style="color:#FF0000;"><strong>{jd}</strong></span>[强][强]'
        f'{tail}</span></span><br></p>')
    out.append(f'<p style="{P}"><span style="{F16}"></span></p>')
    out.append(table_html(data, title, cf, bg))
    out.append('<p><br></p>')
    if note:
        out.append(f'<p style="{IND}"><span style="{FS}"><span style="{F16}">{_esc(note)}</span></span></p>')
    out.append(f'<p style="{IND}"><span style="{FS}"><span style="{F16}">'
               '<strong>二、工作要求</strong></span></span></p>')
    out.append(f'<p style="{IND}"><span style="{FS}"><span style="{F16}">'
               '一是深耕厅堂主阵地，打造沉浸式数币宣传场景。各行需组织网点为宣传核心阵地，'
               '全方位营造“开数币、用数币”浓厚氛围，抓住到店客户流量实现精准科普、同步拓户。'
               '同时严格落新开卡客户100%联动开立数币钱包机制，依托智能机开卡流程，'
               '实现新开卡+数字人民币钱包+三方支付绑卡一站式联动营销，从源头夯实新增钱包基数。'
               '</span><span style="font-size:16pt;"></span><br></span></p>')
    out.append(f'<p style="{IND}"><span style="{FS}"><span style="{F16}">'
               '二是压实责任传导压力，凝聚全员攻坚合力。各行需组织网点将个人钱包拓展列为月度重点工作，'
               '细化分解目标任务，落实到人、每日跟进进度。定期梳理营销短板，组织员工交流推介技巧，'
               '要求柜面、大堂全员主动开口营销，树立“人人都是营销员”意识，形成比学赶超的良好氛围。'
               '</span></span></p>')
    out.append('<p><br></p><p><br></p><p><br></p></div>')
    return ''.join(out)


# ================================================================ 命令
def _workdir_for(root: Path, day: date) -> Path:
    return root / f'{day:%Y%m%d}{WORKDIR_SUFFIX}'


def _save(path: Path, blob: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)


def cmd_find(args) -> dict:
    """按约定找源邮件：主题含关键词且当天收到 → auto=true；否则放宽检索并请示。"""
    today = date.fromisoformat(args.date) if args.date else datetime.now(TZ).date()
    kws = [args.keyword] + [k for k in KEYWORDS_EXTRA if k != args.keyword]
    acct = resolve_account()
    imap = connect(acct)
    try:
        typ, _ = imap.select(acct['inbox'], readonly=True)
        if typ != 'OK':
            raise RuntimeError(f"SELECT {acct['inbox']} 失败")
        recent = list_recent(imap, today - timedelta(days=args.days))
        hit = lambda m: any(k in (m['subject'] or '') for k in kws)
        kw = [m for m in recent if hit(m)]
        kw_today = [m for m in kw if m['received_date'] == today.isoformat()]

        base = {'ok': True, 'keyword': kws, 'today': today.isoformat(), 'inbox': acct['inbox'],
                'scanned': len(recent), 'keyword_hits': [_brief(m) for m in kw],
                'keyword_hits_today': [_brief(m) for m in kw_today]}

        # 单封邮件的附件识别结果缓存，避免同一封被反复下载解析
        att_cache: dict[str, list] = {}

        def atts_of(uid: str) -> list:
            if uid not in att_cache:
                att_cache[uid] = iter_attachments(fetch_message(imap, uid)['msg'])
            return att_cache[uid]

        def check(uids):
            atts = []
            for u in uids:
                atts.extend(atts_of(u))
            return classify(atts)

        # 约定命中：关键词 + 当天 + 附件齐
        if kw_today:
            cls = check([m['uid'] for m in kw_today])
            if cls['complete']:
                base.update({'auto': True, 'uids': [m['uid'] for m in kw_today],
                             'proposed': [_brief(m) for m in kw_today],
                             'verification': cls['roles'], 'unknown_files': cls['unknown_files'],
                             'reason': '主题含关键词且为当天邮件，附件齐全'})
                return base
            why = '；'.join(cls['problems'])
            base['keyword_today_problems'] = cls['problems']
        else:
            why = (f'今天（{today.isoformat()}）没有主题含关键词的邮件'
                   if not kw else '主题含关键词的邮件都不是今天收到的')

        # 放宽：按附件内容逐级扩大范围。
        # 网点号对照表已内置，所以只需要找**明细源表**；源数据常与通报分两天到
        # （源数据 T-1、转发通报 T），第二级先单独试「最近一封带明细源表的邮件」。
        days = sorted({m['received_date'] for m in recent if m['received_date']}, reverse=True)

        def latest_with(pred):
            for m in reversed(recent):
                for att in iter_attachments(m['msg']):
                    try:
                        if pred(att['blob']):
                            return m['uid']
                    except Exception:
                        continue
            return None

        # 优先找**当日快照**的明细源表：历史全量堆表（分区日期混杂）不能当日报用
        src_uid = latest_with(lambda b: (probe_source(b) or {}).get('single_snapshot'))
        if not src_uid:
            src_uid = latest_with(probe_source)          # 退而求其次，仍会由 build 校验
        single = [src_uid] if src_uid else []

        scopes = [
            (f'窗口内主题含关键词的邮件（{args.days} 天）', [m['uid'] for m in kw]),
            ('最近一封带明细源表的邮件（网点号对照表已内置）', single),
            (f'最近一天（{days[0]}）收到的全部邮件' if days else '',
             [m['uid'] for m in recent if m['received_date'] == days[0]] if days else []),
            ('窗口内收到的全部邮件', [m['uid'] for m in recent]),
        ]
        tried, found = [], None
        for label, uids in scopes:
            if not uids:
                continue
            # 只报「最少需要哪几封」：逐封试，能单独满足的就取那一封。
            # （网点号已内置，通常一封带当日快照的明细表就够）
            pick, cls = [], None
            for u in uids:
                c1 = check([u])
                if c1['complete']:
                    pick, cls = [u], c1
                    break
            if cls is None:
                pick, cls = uids, check(uids)
            tried.append({'scope': label, 'scanned': len(uids), 'picked': pick,
                          'complete': cls['complete'], 'roles': sorted(cls['roles']),
                          'problems': cls['problems'],
                          'files': cls['roles']})
            if cls['complete']:
                found = {'scope': label, 'uids': pick, 'verification': cls['roles'],
                         'unknown': cls['unknown_files']}
                break

        base['auto'] = False
        base['reason'] = why
        base['tried'] = tried
        if found:
            base['uids'] = found['uids']
            base['proposed'] = [_brief(fetch_message(imap, u)) for u in found['uids']]
            base['verification'] = found['verification']
            base['unknown_files'] = found['unknown']
            base['question'] = (f'{why}。按附件内容检索（{found["scope"]}），'
                                f'其中 {len(found["uids"])} 封可以凑齐必需附件。是否按这几封继续？'
                                f'（uid：{"、".join(found["uids"])}）')
        else:
            base['question'] = (f'{why}，且放宽检索也没能凑齐必需附件。'
                                f'已检索 {len(recent)} 封、{args.days} 天内的邮件。'
                                f'请确认源邮件是否已到，或直接指定邮件。')
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
    received = max((m['received_date'] for m in dated), default=None)
    day = date.fromisoformat(received) if received else datetime.now(TZ).date()
    workdir = Path(args.workdir) if args.workdir else _workdir_for(Path(args.root), day)
    src_dir = workdir / 'source'
    src_dir.mkdir(parents=True, exist_ok=True)

    atts = []
    for m in msgs:
        for att in iter_attachments(m['msg']):
            att['uid'] = m['uid']
            atts.append(att)
            _save(src_dir / att['filename'], att['blob'])

    cls = classify(atts)
    roles = cls['_roles']
    tmpl_blob = cls['_tmpl_blob'] or FALLBACK_TEMPLATE.read_bytes()
    tmpl_src = 'builtin' if not cls['_tmpl_blob'] else roles.get('template', {}).get('filename', 'email')
    _save(workdir / 'template_used.xlsx', tmpl_blob)

    roles_meta = {k: {kk: vv for kk, vv in v.items() if kk not in ('blob', 'data', 'idx')}
                  for k, v in roles.items()}
    (workdir / 'roles.json').write_text(json.dumps({
        'mails': [_brief(m) for m in msgs], 'received_date': received,
        'roles': roles_meta, 'template_source': tmpl_src,
        'unknown_files': cls['unknown_files'], 'problems': cls['problems'],
        'scope': getattr(args, 'scope', None),
    }, ensure_ascii=False, indent=1), 'utf-8')
    return {'ok': not cls['problems'], 'workdir': str(workdir),
            'received_date': received, 'attachment_count': len(atts),
            'roles': roles_meta, 'template_source': tmpl_src,
            'unknown_files': cls['unknown_files'], 'problems': cls['problems'],
            'mails': [_brief(m) for m in msgs]}


def _load_workdir(workdir: Path) -> dict:
    roles_path = workdir / 'roles.json'
    if not roles_path.exists():
        raise RuntimeError(f'{workdir} 下没有 roles.json，请先 fetch')
    meta = json.loads(roles_path.read_text('utf-8'))
    return meta


def cmd_build(args) -> dict:
    workdir = Path(args.workdir)
    meta = _load_workdir(workdir)
    src_dir = Path(args.source) if args.source else workdir / 'source'

    # 从 source/ 重新按内容识别（不再依赖内存里的 blob）
    atts = []
    for p in sorted(src_dir.glob('*')):
        if p.is_file():
            atts.append({'filename': p.name, 'content_type': '', 'blob': p.read_bytes()})
    cls = classify(atts)
    roles = cls['_roles']
    if cls['problems']:
        return {'ok': False, 'error': '；'.join(cls['problems']),
                'roles': cls['roles'], 'unknown_files': cls['unknown_files'],
                'note': 'source/ 下的附件不足以完成计算，请确认 fetch 是否齐全'}

    data = compute(roles)
    tmpl_blob = (workdir / 'template_used.xlsx').read_bytes() if (workdir / 'template_used.xlsx').exists() \
        else FALLBACK_TEMPLATE.read_bytes()

    y, m, d = (int(x) for x in data['snapshot'].split('-'))
    out_name = args.out_name or f'数字人民币个人钱包发展通报（{m}月{d}日）.xlsx'
    out_dir = workdir / 'out'
    # 先填表：会顺带把每个网点的模板行序（order）写回 data，
    # 文案的并列名次排序依赖它，所以必须在 build_text 之前
    written = write_report(tmpl_blob, data, out_dir / out_name)
    meta_txt = build_text(data)

    # 正文表格的底色/红绿直接照抄出表：条件格式求值 + 静态底色都从 xlsx 现读，
    # 两边用同一份规则，不会各算一套（含并列值、合计行、支行合并底色）。
    cf, bg = body_style_maps(data, written['path'])

    html = build_html(data, meta_txt, cf=cf, bg=bg)
    (workdir / 'mail_body.html').write_text(html, 'utf-8')
    (workdir / '文案.txt').write_text(meta_txt['text'], 'utf-8')
    (workdir / 'data.json').write_text(json.dumps(
        {**meta_txt, 'nets': data['nets'], 'snapshot': data['snapshot'],
         'unmapped_netno': data['unmapped_netno'], 'source_rows': data['source_rows'],
         'mapped_rows': data['mapped_rows'], 'report': written},
        ensure_ascii=False, indent=1), 'utf-8')

    warnings_out = []
    if data['unmapped_netno']:
        warnings_out.append(f"源表中有网点号在对照表里找不到，已忽略：{data['unmapped_netno']}")
    if written['skipped']:
        warnings_out.append(f"模板无对应行，未写入：{written['skipped']}")
    if written['rows_blanked']:
        warnings_out.append(f"模板有行但源表无数据，已补 0：{written['rows_blanked']}")
    if cls['unknown_files']:
        warnings_out.append(f"认不出的附件（已忽略）：{[x['filename'] for x in cls['unknown_files']]}")

    return {'ok': True, 'workdir': str(workdir), 'report': written['path'],
            'out_name': out_name, 'text': meta_txt['text'], 'html': str(workdir / 'mail_body.html'),
            'data': data, 'meta': meta_txt, 'warnings': warnings_out}


def reply_subject(meta_txt: dict) -> str:
    return f'数字人民币个人钱包发展通报（{meta_txt["date_mmdd"]}）'


def cmd_send(args) -> dict:
    workdir = Path(args.workdir)
    meta = _load_workdir(workdir)
    out_dir = workdir / 'out'
    xlsx = sorted(out_dir.glob('*.xlsx'))
    if not xlsx:
        return {'ok': False, 'error': f'{out_dir} 下没有 xlsx，请先 build'}
    report = xlsx[0]

    data_path = workdir / 'data.json'
    if not data_path.exists():
        return {'ok': False, 'error': '没有 data.json，请先 build'}
    data = json.loads(data_path.read_text('utf-8'))
    if (workdir / 'mail_body.html').exists():
        html = (workdir / 'mail_body.html').read_text('utf-8')
    else:
        cf, bg = body_style_maps(data, report)
        html = build_html({'nets': data['nets'], 'totals': data['totals']}, data, cf=cf, bg=bg)
    text = (workdir / '文案.txt').read_text('utf-8') if (workdir / '文案.txt').exists() else ''

    # 收件人：只回发件人（暂不追加固定收件人）
    sender = (args.to or '').strip()
    if not sender:
        mails = meta.get('mails') or []
        if mails:
            sender = parseaddr(mails[-1].get('from') or '')[1]
    if not sender:
        return {'ok': False, 'error': '没有收件人（源邮件没有解析出发件人地址）'}
    recips = []
    for a in [sender, *FIXED_RECIPIENTS]:
        if a and a.lower() not in [x.lower() for x in recips]:
            recips.append(a)
    to = ', '.join(recips)

    subject = args.subject or reply_subject(data)
    acct = resolve_account()
    msg = EmailMessage()
    msg['From'] = acct['user']
    msg['To'] = to
    msg['Subject'] = subject
    msg['Date'] = formatdate(localtime=True)
    mails = meta.get('mails') or []
    if mails and mails[-1].get('message_id'):
        msg['In-Reply-To'] = mails[-1]['message_id']
        msg['References'] = mails[-1]['message_id']
    msg.set_content(text or '数字人民币个人钱包发展通报，详见附件。')
    msg.add_alternative(html, subtype='html')
    msg.add_attachment(report.read_bytes(), maintype='application',
                       subtype='vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                       filename=report.name)

    if args.dry_run:
        return {'ok': True, 'dry_run': True, 'to': to, 'recipients': recips, 'subject': subject,
                'attachment': report.name, 'bytes': len(report.read_bytes()),
                'smtp': f"{acct['smtp_host']}:{acct['smtp_port']}",
                'html_bytes': len(html), 'text': text}

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
    return {'ok': True, 'sent': True, 'to': to, 'recipients': recips, 'subject': subject,
            'attachment': report.name, 'smtp': f"{acct['smtp_host']}:{acct['smtp_port']}"}


def cmd_run(args) -> dict:
    got = cmd_fetch(args)
    if not got.get('ok'):
        return got
    out = cmd_build(argparse.Namespace(workdir=got['workdir'], source=None, out_name=None))
    for k in ('received_date', 'attachment_count', 'problems', 'roles', 'workdir', 'mails',
              'unknown_files', 'template_source'):
        out.setdefault(k, got.get(k))
    out['fetch'] = got
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description='数字人民币个人钱包发展通报：取信/计算/填表/回信')
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('find', help='按约定找源邮件')
    p.add_argument('--days', type=int, default=3)
    p.add_argument('--date')
    p.add_argument('--keyword', default=KEYWORD)
    p.set_defaults(func=cmd_find)

    p = sub.add_parser('fetch', help='按 uid 取信并识别附件')
    p.add_argument('--uid', action='append', required=True)
    p.add_argument('--root', default=str(DEFAULT_ROOT))
    p.add_argument('--workdir')
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser('build', help='计算 + 填表 + 出文案')
    p.add_argument('--workdir', required=True)
    p.add_argument('--source')
    p.add_argument('--out-name')
    p.set_defaults(func=cmd_build)

    p = sub.add_parser('send', help='回信给发件人')
    p.add_argument('--workdir', required=True)
    p.add_argument('--to')
    p.add_argument('--subject')
    p.add_argument('--dry-run', action='store_true')
    p.set_defaults(func=cmd_send)

    p = sub.add_parser('run', help='fetch + build（不发信）')
    p.add_argument('--uid', action='append', required=True)
    p.add_argument('--root', default=str(DEFAULT_ROOT))
    p.add_argument('--workdir')
    p.set_defaults(func=cmd_run)

    args = ap.parse_args()
    try:
        result = args.func(args)
    except Exception as exc:
        result = {'ok': False, 'error': f'{type(exc).__name__}: {exc}'}
    print(json.dumps(result, ensure_ascii=False, indent=1, default=str))
    raise SystemExit(0 if result.get('ok') else 1)


if __name__ == '__main__':
    main()
