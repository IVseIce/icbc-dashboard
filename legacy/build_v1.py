#!/home/isee/.venvs/data-tools/bin/python
# -*- coding: utf-8 -*-
"""icbc-dashboard / build —— 把 collect.py 产出的 data.json 渲染成单文件 HTML 驾驶舱。

零依赖、零外链：纯 SVG 图表 + 少量内联 JS（切页/排序），断网也能看。
用法：build.py [--data PATH] [--out PATH]
"""
from __future__ import annotations

import argparse
import html
import json
import math
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
VIZ_ROOT = Path(__file__).resolve().parent.parent / 'data'
DEFAULT_DATA = VIZ_ROOT / 'data' / 'dashboard_data.json'
DEFAULT_OUT = VIZ_ROOT / 'out' / '阜阳分行个人金融经营驾驶舱.html'

CSS = r"""
:root{
  --ink:#101c33; --ink2:#46536b; --ink3:#8391a8; --line:#e6ebf3;
  --bg:#f4f6fa; --card:#fff; --brand:#123a72; --brand2:#1d5bb8;
  --red:#c8102e; --green:#12a06a; --amber:#e08a00; --violet:#6b4fd8;
  --shadow:0 1px 2px rgba(16,28,51,.04),0 8px 24px rgba(16,28,51,.06);
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{
  background:var(--bg); color:var(--ink);
  font-family:"Microsoft YaHei","PingFang SC","Source Han Sans SC","Noto Sans CJK SC",-apple-system,"Segoe UI",sans-serif;
  font-size:13px; line-height:1.5; -webkit-font-smoothing:antialiased;
}
.num{font-variant-numeric:tabular-nums; font-feature-settings:"tnum"}
.wrap{max-width:1360px;margin:0 auto;padding:0 22px 40px}

/* ---------- hero ---------- */
.hero{
  background:linear-gradient(115deg,#0d2a55 0%,#123a72 46%,#1b4f96 100%);
  color:#fff; padding:26px 0 22px; position:relative; overflow:hidden;
}
.hero:after{content:"";position:absolute;right:-120px;top:-140px;width:420px;height:420px;border-radius:50%;
  background:radial-gradient(circle,rgba(200,16,46,.30),rgba(200,16,46,0) 62%)}
.hero .wrap{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;position:relative;z-index:1}
.hero h1{margin:0;font-size:25px;letter-spacing:.5px;font-weight:700}
.hero h1 em{font-style:normal;color:#ffd8de}
.hero p{margin:6px 0 0;color:#b9c9e2;font-size:12.5px;letter-spacing:.4px}
.hero-r{text-align:right;font-size:12px;color:#c9d8ee;white-space:nowrap}
.hero-r b{color:#fff;font-size:13px}
.hero-r .gen{color:#93a9c8;margin-top:4px}

/* ---------- kpi ---------- */
.kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:14px;margin-top:-26px;position:relative;z-index:2}
.kpi{background:var(--card);border-radius:14px;padding:14px 15px 12px;box-shadow:var(--shadow);
  border-top:3px solid var(--k,#1d5bb8); display:flex;flex-direction:column;gap:2px;min-height:132px}
.kpi .t{color:var(--ink3);font-size:11.5px;letter-spacing:.3px;display:flex;justify-content:space-between}
.kpi .t i{font-style:normal;color:var(--ink3);font-size:10.5px;background:#f2f5fa;border-radius:6px;padding:1px 6px}
.kpi .v{font-size:26px;font-weight:700;letter-spacing:-.5px;margin-top:4px}
.kpi .v small{font-size:12px;font-weight:600;color:var(--ink2);margin-left:3px}
.kpi .d{font-size:11.5px;color:var(--ink2);display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.kpi .spark{margin-top:auto}
.up{color:var(--green)} .down{color:var(--red)} .flat{color:var(--ink3)}

/* ---------- generic card ---------- */
.card{background:var(--card);border-radius:14px;box-shadow:var(--shadow);padding:16px 18px 14px}
.card h2{margin:0 0 2px;font-size:14px;font-weight:700;letter-spacing:.2px;display:flex;align-items:center;gap:8px}
.card h2 .dot{width:7px;height:7px;border-radius:2px;background:var(--k,#1d5bb8);display:inline-block}
.card h2 .sub{margin-left:auto;font-weight:400;font-size:11px;color:var(--ink3)}
.card .lead{color:var(--ink3);font-size:11px;margin:0 0 8px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:14px}
section{margin-top:14px}
.legend{display:flex;gap:14px;font-size:11px;color:var(--ink2);flex-wrap:wrap}
.legend i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:5px;vertical-align:-1px}

/* ---------- table ---------- */
table{border-collapse:separate;border-spacing:0;width:100%;font-size:12px}
th,td{padding:6px 7px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}
th{color:var(--ink3);font-weight:600;font-size:11px;background:#fafbfd;position:sticky;top:0;z-index:1}
th:first-child,td:first-child{text-align:left}
tbody tr:hover td{background:#f7f9fd}
td.n{font-variant-numeric:tabular-nums}
.tbl-wrap{max-height:430px;overflow:auto;border-radius:10px;border:1px solid var(--line)}
.pill{display:inline-block;padding:1px 7px;border-radius:20px;font-size:10.5px;font-weight:600}
.pill.g{background:#e6f6ef;color:#0d7a51} .pill.r{background:#fde9ec;color:#a80d26}
.pill.a{background:#fff4e0;color:#9a5c00} .pill.b{background:#e9f0fb;color:#1d5bb8}

/* ---------- matrix ---------- */
.mx td{text-align:center;font-size:11.5px;border-bottom:2px solid #fff;font-weight:600}
.mx th{text-align:center;font-size:10.5px;line-height:1.25;border-bottom:2px solid #fff;background:#f3f6fb}
.mx td:first-child,.mx th:first-child{text-align:left;background:#fff;font-weight:700;color:var(--ink)}
.mx td.hi{color:#fff}
.mx .cap{font-size:10px;color:var(--ink3);font-weight:400;display:block}

/* ---------- module cards ---------- */
.mod{display:flex;flex-direction:column;gap:10px}
.mod .hdr{display:flex;align-items:center;gap:8px}
.mod .hdr b{font-size:12.5px}
.mod .big{font-size:20px;font-weight:700}
.mod .big small{font-size:11px;color:var(--ink2);font-weight:600;margin-left:3px}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{background:#f6f8fc;border:1px solid var(--line);border-radius:8px;padding:3px 8px;font-size:11px;color:var(--ink2)}
.chip b{color:var(--ink);font-weight:700}
.ranks{display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:11px}
.ranks ul{margin:0;padding-left:0;list-style:none}
.ranks li{display:flex;justify-content:space-between;gap:8px;padding:2px 0;color:var(--ink2);border-bottom:1px dashed #eef1f6;
  white-space:nowrap;overflow:hidden}
.ranks li span{overflow:hidden;text-overflow:ellipsis}
.ranks li b{flex:none}
.ranks li b{color:var(--ink);font-weight:700}
.ranks h4{margin:0 0 3px;font-size:10.5px;color:var(--ink3);font-weight:600;letter-spacing:.5px}

/* ---------- tabs ---------- */
.tabs{display:flex;gap:6px;margin:2px 0 10px;flex-wrap:wrap}
.tabs button{border:1px solid var(--line);background:#fff;color:var(--ink2);border-radius:8px;padding:5px 12px;
  font-size:11.5px;cursor:pointer;font-family:inherit;transition:.15s}
.tabs button:hover{color:var(--brand2);border-color:#c5d5ee}
.tabs button.on{background:var(--brand);color:#fff;border-color:var(--brand)}
footer{margin-top:22px;color:var(--ink3);font-size:10.5px;line-height:1.8;text-align:center}
.empty{padding:18px;color:var(--ink3);text-align:center;font-size:11.5px}
@media (max-width:1180px){
  .kpis{grid-template-columns:repeat(3,1fr)}
  .grid2,.grid3{grid-template-columns:1fr}
}
"""


# ---------------------------------------------------------------- 格式化
def esc(s):
    return html.escape(str(s), quote=True)


def fnum(v, nd=0):
    if v is None:
        return '—'
    if nd == 0:
        return f'{v:,.0f}'
    return f'{v:,.{nd}f}'


def pct(v, nd=2):
    return '—' if v is None else f'{v * 100:.{nd}f}%'


def delta_html(cur, prev, nd=2, unit='', invert=False):
    if cur is None or prev is None:
        return '<span class="flat">—</span>'
    d = cur - prev
    if abs(d) < 10 ** (-nd) / 2:
        return f'<span class="flat num">持平</span>'
    good = d < 0 if invert else d > 0
    cls = 'up' if good else 'down'
    sign = '+' if d > 0 else ''
    return f'<span class="{cls} num">{sign}{d:,.{nd}f}{unit}</span>'


# ---------------------------------------------------------------- SVG 基础
def line_chart(points, w=560, h=172, color='#1d5bb8', unit='', nd=0, area=True, ref=None,
               ylab_fmt=None, dot_labels=True):
    """points: [(label, value)]；纯 SVG 折线/面积图。"""
    if not points:
        return '<div class="empty">暂无数据</div>'
    vals = [p[1] for p in points]
    pad_l, pad_r, pad_t, pad_b = 46, 14, 14, 24
    iw, ih = w - pad_l - pad_r, h - pad_t - pad_b
    vmin, vmax = min(vals), max(vals)
    if ref is not None:
        vmin = min(vmin, ref); vmax = max(vmax, ref)
    span = (vmax - vmin) or max(1, abs(vmax) * .1)
    vmin -= span * .18; vmax += span * .18
    n = len(points)

    def X(i):
        return pad_l + (iw * i / max(1, n - 1) if n > 1 else iw / 2)

    def Y(v):
        return pad_t + ih * (1 - (v - vmin) / (vmax - vmin))

    # 网格 + y 轴
    g = []
    for k in range(4):
        val = vmin + (vmax - vmin) * k / 3
        y = Y(val)
        g.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w - pad_r}" y2="{y:.1f}" stroke="#eef1f6"/>')
        txt = ylab_fmt(val) if ylab_fmt else f'{val:,.{nd}f}'
        g.append(f'<text x="{pad_l - 7}" y="{y + 3.5:.1f}" text-anchor="end" font-size="9.5" fill="#98a5ba">{txt}</text>')
    path = ' '.join(f'{"M" if i == 0 else "L"}{X(i):.1f},{Y(v):.1f}' for i, (_, v) in enumerate(points))
    fill = ''
    if area:
        fill = (f'<path d="{path} L{X(n-1):.1f},{pad_t + ih:.1f} L{X(0):.1f},{pad_t + ih:.1f} Z" '
                f'fill="url(#grd{abs(hash(color)) % 999})" opacity=".9"/>')
        fill = (f'<defs><linearGradient id="grd{abs(hash(color)) % 999}" x1="0" y1="0" x2="0" y2="1">'
                f'<stop offset="0" stop-color="{color}" stop-opacity=".26"/>'
                f'<stop offset="1" stop-color="{color}" stop-opacity="0"/></linearGradient></defs>' + fill)
    ref_line = ''
    if ref is not None:
        ref_line = (f'<line x1="{pad_l}" y1="{Y(ref):.1f}" x2="{w - pad_r}" y2="{Y(ref):.1f}" '
                    f'stroke="#c8102e" stroke-dasharray="4 3" stroke-width="1"/>'
                    f'<text x="{w - pad_r - 2}" y="{Y(ref) - 4:.1f}" text-anchor="end" font-size="9" fill="#c8102e">目标 {ref:g}{unit}</text>')
    dots = []
    for i, (lab, v) in enumerate(points):
        if i == n - 1 or (dot_labels and n <= 10):
            dots.append(f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="2.6" fill="#fff" stroke="{color}" stroke-width="1.6"/>')
        dots.append(f'<text x="{X(i):.1f}" y="{h - 7}" text-anchor="middle" font-size="9" fill="#98a5ba">{esc(lab)}</text>')
    last = points[-1]
    dots.append(f'<text x="{X(n-1):.1f}" y="{Y(last[1]) - 7:.1f}" text-anchor="end" font-size="10.5" '
                f'font-weight="700" fill="{color}">{last[1]:,.{nd}f}{unit}</text>')
    from urllib.parse import quote
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" height="{h}" role="img" '
            f'aria-label="{esc(quote(str(points)))}">{"".join(g)}{fill}{ref_line}'
            f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round"/>'
            f'{"".join(dots)}</svg>')


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def hbar(rows, w=320, rowh=20, color='#1d5bb8', nd=0, unit='', maxv=None, red_negative=True):
    """rows: [(label, value)]，横向条形。"""
    if not rows:
        return '<div class="empty">暂无数据</div>'
    rows = [(lab, _f(v)) for lab, v in rows]
    vals = [abs(v) for _, v in rows]
    mx = maxv or max(vals) or 1
    lab_w, val_w = 112, 58
    bw = w - lab_w - val_w - 8
    h = rowh * len(rows) + 6
    out = []
    for i, (lab, v) in enumerate(rows):
        y = i * rowh + 3
        v = v or 0
        blen = max(2, bw * abs(v) / mx)
        c = color if v >= 0 else ('#c8102e' if red_negative else color)
        lab_s = str(lab)
        if len(lab_s) > 9:
            lab_s = lab_s[:8] + '…'
        out.append(f'<text x="0" y="{y + 11.5}" font-size="10.5" fill="#46536b">{esc(lab_s)}</text>')
        out.append(f'<rect x="{lab_w}" y="{y + 3}" width="{bw}" height="10" rx="3" fill="#f1f4f9"/>')
        out.append(f'<rect x="{lab_w}" y="{y + 3}" width="{blen:.1f}" height="10" rx="3" fill="{c}" opacity=".88"/>')
        out.append(f'<text x="{w}" y="{y + 11.5}" text-anchor="end" font-size="10.5" font-weight="600" '
                   f'fill="{"#c8102e" if v < 0 else "#101c33"}">{v:,.{nd}f}{unit}</text>')
    return f'<svg viewBox="0 0 {w} {h}" width="100%" height="{h}">{"".join(out)}</svg>'


def spark(vals, w=150, h=30, color='#1d5bb8'):
    if len(vals) < 2:
        return '<div style="height:30px"></div>'
    mn, mx = min(vals), max(vals)
    span = (mx - mn) or 1
    pts = ' '.join(f'{i * w / (len(vals) - 1):.1f},{h - 3 - (v - mn) / span * (h - 6):.1f}' for i, v in enumerate(vals))
    last = pts.split()[-1].split(',')
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" height="{h}" preserveAspectRatio="none">'
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.6" stroke-linejoin="round"/>'
            f'<circle cx="{last[0]}" cy="{last[1]}" r="2.2" fill="{color}"/></svg>')


# ---------------------------------------------------------------- 数据加工
def by_branch(items, key, namekey='name', strip=('支行', '阜阳')):
    out = {}
    for it in items:
        nm = str(it.get(namekey) or '')
        for s in strip:
            nm = nm.replace(s, '')
        nm = nm.replace('营业室', '营业室')
        out[nm.strip()] = it.get(key)
    return out


def matrix_cell(val, lo, hi, text, invert=False):
    """把数值映射到蓝/红色阶，显示文本单独传入。"""
    if val is None:
        return '<td style="background:#f8fafd;color:#b6c0d0">—</td>'
    t = 0.5 if hi == lo else (val - lo) / (hi - lo)
    t = max(0, min(1, t))
    if invert:
        t = 1 - t
    if val < 0:
        bg, fg = '#fde9ec', '#a80d26'
    elif t > .72:
        bg, fg = '#123a72', '#fff'
    elif t > .45:
        bg, fg = '#4a7fc4', '#fff'
    elif t > .22:
        bg, fg = '#c3d6ef', '#12315e'
    else:
        bg, fg = '#eef3fa', '#46536b'
    cls = ' class="hi"' if fg == '#fff' else ''
    return f'<td{cls} style="background:{bg};color:{fg}">{text}</td>'


def module_card(title, kicker, color, big_html, chips, bar_rows, top_title, top_rows, bot_title, bot_rows, note=''):
    chips_html = ''.join(chips)
    def rk(t, rows):
        lis = ''.join(f'<li><span>{esc(a)}</span><b>{esc(b)}</b></li>' for a, b in rows)
        return f'<div><h4>{esc(t)}</h4><ul>{lis}</ul></div>'
    return f"""
    <div class="card mod" style="--k:{color}">
      <div class="hdr"><span class="dot" style="width:8px;height:8px;border-radius:2px;background:{color}"></span>
        <b>{esc(title)}</b><span class="sub" style="margin-left:auto;color:var(--ink3);font-size:10.5px">{esc(kicker)}</span></div>
      <div class="big">{big_html}</div>
      <div class="chips">{chips_html}</div>
      {hbar(bar_rows, color=color)}
      <div class="ranks">{rk(top_title, top_rows)}{rk(bot_title, bot_rows)}</div>
      {f'<div style="color:var(--ink3);font-size:10.5px">{note}</div>' if note else ''}
    </div>"""


LBL = {'sbqb': '数币', 'xgj': '薪管家', 'dqzz': '定期', 'xsfw': '线上服务', 'qwsq': '企微社群'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', default=str(DEFAULT_DATA))
    ap.add_argument('--out', default=str(DEFAULT_OUT))
    a = ap.parse_args()
    src = Path(a.data)
    if not src.exists() and (BASE / 'assets' / 'dashboard_data.json').exists():
        src = BASE / 'assets' / 'dashboard_data.json'
    D = json.load(open(src, encoding='utf-8'))
    S = D['sources']
    sbqb, xgj, dqzz, xsfw, qwsq = (S['sbqb'], S['xgj'], S['dqzz'], S['xsfw'], S['qwsq'])
    BR = D['branches']

    # ---- 数币按支行
    sb_br = {}
    for n in sbqb['nets']:
        b = n['branch']
        if not b:
            continue
        d = sb_br.setdefault(b, {'total': 0, 'month': 0, 'day': 0, 'nets': 0})
        d['total'] += n['total']; d['month'] += n['month']; d['day'] += n['day']; d['nets'] += 1
    sb_total, sb_month, sb_day = sbqb['total'], sbqb['totals'][5], sbqb['totals'][6]
    sb_prev = sbqb['trend'][-2]['v'] if len(sbqb['trend']) > 1 else None

    # ---- 薪管家
    xg_br = {b['name']: b for b in xgj['branches']}
    xg_prev = xgj['prev']

    # ---- 定期
    dq_br = {b['name']: b for b in dqzz['branches']}

    # ---- 企微
    qw_br = {}
    for b in qwsq.get('branches', []):
        nm = str(b['name']).replace('支行', '').replace('阜阳', '')
        qw_br[nm] = b
    qw_tot = qwsq['total']

    # ---- 线上服务
    xs_br = {b['name']: b for b in xsfw['branches']}
    xs_tot = xsfw['tot']

    footer_src = ' · '.join(f"{LBL[k]} {D['sources'][k].get('as_of') or '未导入'}"
                            for k in ('sbqb', 'xgj', 'dqzz', 'xsfw', 'qwsq'))
    latest = max([sbqb['as_of'], xgj['as_of'], dqzz['as_of'], xsfw['as_of'], qwsq['as_of']])
    earliest = min([sbqb['as_of'], xgj['as_of'], dqzz['as_of'], xsfw['as_of'], qwsq['as_of']])

    # ================================================== KPI
    kpis = []
    def kpi(title, tag, value, unit, delta, sparkline='', color='#1d5bb8'):
        kpis.append(f"""
        <div class="kpi" style="--k:{color}">
          <div class="t"><span>{esc(title)}</span><i>{esc(tag)}</i></div>
          <div class="v num">{value}<small>{unit}</small></div>
          <div class="d">{delta}</div>
          <div class="spark">{sparkline}</div>
        </div>""")

    kpi('数字人民币钱包', sbqb['as_of'][5:], f'{sb_total:,}', '户',
        f"当日 <b class='num'>+{sb_day}</b> 户 · 当月 <b class='num'>+{sb_month}</b> 户"
        + (f' · {delta_html(sb_total, sb_prev, 0, "户")} 较上日' if sb_prev else ''),
        spark([t['v'] for t in sbqb['trend']]), '#1d5bb8')
    kpi('薪管家代发金额', xgj['as_of'][5:], f"{xgj['total']:,.2f}", '万元(全年)',
        f"当月 <b class='num'>{xgj['month_total']:,.2f}</b> 万元 · "
        + (delta_html(xgj['total'], xg_prev.get('year'), 2, '万') + ' 较上日' if xg_prev else '—')
        + f" · 有效单位 <b class='num'>{xgj['ent_year']}</b> 户",
        spark([t['year'] for t in xgj['trend']]), '#12a06a')
    dq_tot = dqzz['total']
    kpi('定期存款余额', dqzz['as_of'][5:], f"{dq_tot['cur_bal'] / 10000:,.2f}", '亿元',
        f"当月增量 <b class='num'>{dq_tot['inc']:,.2f}</b> 万 · 增幅 <b class='num'>{pct(dq_tot['rate'])}</b>",
        '', '#6b4fd8')
    kpi('企微社群', qwsq['as_of'][5:], f"{qw_tot['groups']:,}", '个群',
        f"客户 <b class='num'>{qw_tot['cust']:,}</b> 户（较上周 {qw_tot['cust_d']:+d}）· 熟识率 <b class='num'>{pct(qw_tot['rate'])}</b>",
        '', '#e08a00')
    kpi('线上服务·当日动户率', xsfw['as_of'][5:], f"{xs_tot['day_rate'] * 100:.2f}", '%',
        f"当月添客 <b class='num'>{xs_tot['add_month']:,}</b> 户 · 当日 <b class='num'>{xs_tot['add_today']:,}</b> 户",
        '', '#c8102e')
    kpi('数据覆盖', latest[5:], f"{len(BR)}", '家支行 · 5 条线',
        f"最新 {latest[5:]} · 最早 {earliest[5:]}（定期为 {dqzz['as_of'][5:]}）", '', '#46536b')

    # ================================================== 趋势图
    def labels(points, step=None):
        n = len(points)
        step = step or max(1, n // 7)
        return [(p[0][5:].replace('-', '/') if i % step == 0 or i == n - 1 else '') for i, p in enumerate(points)]

    sb_pts = [(t['d'], t['v']) for t in sbqb['trend']]
    sb_lab = labels(sb_pts)
    chart_sb = line_chart(list(zip(sb_lab, [v for _, v in sb_pts])), color='#1d5bb8', unit='户')

    xg_pts = [(t['d'], t['year']) for t in xgj['trend']]
    xg_lab = labels(xg_pts)
    chart_xg = line_chart(list(zip(xg_lab, [v for _, v in xg_pts])), color='#12a06a', nd=1, unit='万')

    xs_pts = [(t['d'], round(t['day_rate'] * 100, 1)) for t in xsfw['trend']]
    xs_lab = labels(xs_pts)
    chart_xs = line_chart(list(zip(xs_lab, [v for _, v in xs_pts])), color='#c8102e', nd=1, unit='%', ref=55)

    qw_rows = [(str(b['name']).replace('阜阳', ''), b['cust']) for b in
               sorted(qwsq.get('branches', []), key=lambda x: -(x['cust'] or 0))]
    chart_qw = hbar(qw_rows, color='#e08a00', w=480)

    # ================================================== 支行矩阵
    cols = [
        ('数币钱包', '累计户', [sb_br.get(b, {}).get('total') for b in BR], 0),
        ('数币钱包', '当月新增', [sb_br.get(b, {}).get('month') for b in BR], 0),
        ('薪管家', '全年万元', [(xg_br.get(b) or {}).get('year') for b in BR], 1),
        ('薪管家', '当月万元', [(xg_br.get(b) or {}).get('month') for b in BR], 1),
        ('定期存款', '余额万元', [(dq_br.get(b) or {}).get('cur_bal') for b in BR], 0),
        ('定期存款', '当月增幅', [(dq_br.get(b) or {}).get('rate') for b in BR], 2),
        ('企微社群', '客户户', [(qw_br.get(b) or {}).get('cust') for b in BR], 0),
        ('线上服务', '动户率', [(xs_br.get(b) or {}).get('day_rate') for b in BR], 2),
    ]
    head = ''.join(f'<th>{esc(g)}<span class="cap">{esc(m)}</span></th>' for g, m, _, _ in cols)
    body = []
    for i, b in enumerate(BR):
        tds = []
        for gi, (g, m, vals, nd) in enumerate(cols):
            v = vals[i]
            valid = [x for x in vals if x is not None]
            lo, hi = (min(valid), max(valid)) if valid else (0, 1)
            if v is None:
                tds.append(matrix_cell(None, lo, hi, ''))
                continue
            if m in ('当月增幅', '动户率'):
                txt = f'{v * 100:+.2f}%' if m == '当月增幅' else pct(v, 1)
            elif nd == 0:
                txt = f'{v:,.0f}'
            else:
                txt = f'{v:,.{nd}f}'
            tds.append(matrix_cell(v, lo, hi, txt, invert=(m == '当月增幅')))
        body.append(f'<tr><td>{esc(b)}</td>{"".join(tds)}</tr>')
    # 合计行
    tot_cells = [f'{sb_total:,}', f'{sb_month:,}', f"{xgj['total']:,.1f}", f"{xgj['month_total']:,.1f}",
                 f"{dq_tot['cur_bal']:,.0f}", f"{dq_tot['rate'] * 100:+.2f}%", f"{qw_tot['cust']:,}",
                 pct(xs_tot['day_rate'])]
    tot_row = ''.join(f'<td style="background:#eef2f9;color:#12315e;font-weight:700">{c}</td>' for c in tot_cells)
    matrix = f"""
      <table class="mx">
        <thead><tr><th>支行<span class="cap">8 家</span></th>{head}</tr></thead>
        <tbody>{''.join(body)}
          <tr><td style="background:#eef2f9">合计/加权</td>{tot_row}</tr>
        </tbody>
      </table>"""

    # ================================================== 模块卡
    sb_rank = sorted(sb_br.items(), key=lambda kv: -kv[1]['total'])
    sb_bar = [(k, v['total']) for k, v in sb_rank]
    sb_top = [(k, f"{v['total']} 户 / 当月 +{v['month']}") for k, v in sb_rank[:3]]
    sb_bot = [(k, f"{v['total']} 户 / 当日 +{v['day']}") for k, v in sb_rank[-3:][::-1]]
    card_sb = module_card('数字人民币个人钱包', f"截至 {sbqb['as_of_cn']}",
                          '#1d5bb8',
                          f"{sb_total:,}<small>户</small> &nbsp;<span style='color:var(--ink3);font-size:11px'>一类 {sbqb['totals'][0]} · 二类 {sbqb['totals'][1]:,} · 三类 {sbqb['totals'][2]} · 四类 {sbqb['totals'][3]}</span>",
                          [f'<span class="chip">当日 <b>+{sb_day}</b> 户</span>',
                           f'<span class="chip">当月 <b>+{sb_month}</b> 户</span>',
                           f'<span class="chip">当日零开 <b>{sbqb["zero_day_count"]}</b> 个网点</span>',
                           f'<span class="chip">网点 <b>{len(sbqb["nets"])}</b> 个</span>'],
                          sb_bar, '累计前三', sb_top, '累计后三', sb_bot,
                          note=f"当日前三：" + '、'.join(f"{x['name']} {x['v']}" for x in sbqb['top3_day']))

    xg_rank = sorted(xgj['branches'], key=lambda b: -(b['year'] or 0))
    xg_bar = [(b['name'], b['year']) for b in xg_rank]
    xg_top = [(b['name'], f"{b['year']:,.2f} 万") for b in xg_rank[:3]]
    xg_bot = [(b['name'], f"{(b['year'] or 0):,.2f} 万") for b in xg_rank[-3:][::-1]]
    card_xg = module_card('工银薪管家「聚薪行动」', f"截至 {xgj['as_of']}",
                          '#12a06a',
                          f"{xgj['total']:,.2f}<small>万元(全年)</small> &nbsp;<span style='color:var(--ink3);font-size:11px'>当月 {xgj['month_total']:,.2f} 万</span>",
                          [f'<span class="chip">有效单位 <b>{xgj["ent_year"]}</b> 户</span>',
                           f'<span class="chip">当月新增单位 <b>{xgj["ent_month"]}</b> 户</span>',
                           f'<span class="chip">较上日 <b>{xgj["total"] - (xg_prev.get("year") or 0):+,.2f}</b> 万</span>'],
                          xg_bar, '全年前三', xg_top, '全年后三', xg_bot,
                          note='当月前三：' + '、'.join(f"{b['name']} {b['month']:,.2f}" for b in
                                                    sorted(xgj['branches'], key=lambda b: -(b['month'] or 0))[:3]))

    dq_rank = sorted(dqzz['branches'], key=lambda b: -(b['inc'] or 0))
    dq_bar = [(b['name'], b['inc']) for b in dq_rank]
    dq_top = [(b['name'], f"+{b['inc']:,.2f} 万") for b in dq_rank[:3]]
    dq_bot = [(b['name'], f"{b['inc']:,.2f} 万") for b in dq_rank[-3:][::-1]]
    card_dq = module_card('定期存款增长', f"{dqzz['prev_as_of'][5:]} → {dqzz['as_of'][5:]}",
                          '#6b4fd8',
                          f"{dq_tot['cur_bal']:,.0f}<small>万元</small> &nbsp;<span style='color:var(--ink3);font-size:11px'>较上月 {dq_tot['inc']:+,.2f} 万（{pct(dq_tot['rate'])}）</span>",
                          [f'<span class="chip">当月增量 <b>{dq_tot["inc"]:,.2f}</b> 万</span>',
                           f'<span class="chip">增幅 <b>{pct(dq_tot["rate"])}</b></span>',
                           f'<span class="chip">负增长 <b>{sum(1 for b in dqzz["branches"] if (b["inc"] or 0) < 0)}</b> 家</span>'],
                          dq_bar, '增量前三', dq_top, '增量后三', dq_bot,
                          note='口径：整存整取等定期品种合计，按原表公式计算')

    qw_rank = sorted(qwsq.get('branches', []), key=lambda b: -(b['cust'] or 0))
    qw_bar2 = [(str(b['name']).replace('阜阳', ''), b['cust']) for b in qw_rank]
    qw_top = [(str(b['name']).replace('阜阳', ''), f"{b['cust']} 户 / 上周 {b['cust_d']:+d}") for b in qw_rank[:3]]
    qw_bot = [(str(b['name']).replace('阜阳', ''), f"{b['inter']} 交互 / 熟识率 {pct(b['rate'])}") for b in qw_rank[-3:][::-1]]
    card_qw = module_card('企业微信社群运营', f"截至 {qwsq['as_of_cn']}（周频）",
                          '#e08a00',
                          f"{qw_tot['groups']}<small>个群</small> &nbsp;<span style='color:var(--ink3);font-size:11px'>客户 {qw_tot['cust']:,} 户（周环比 {qw_tot['cust_d']:+d}）</span>",
                          [f'<span class="chip">建群 <b>+{qw_tot["groups_d"]}</b></span>',
                           f'<span class="chip">交互 <b>{qw_tot["inter"]:,}</b> 条</span>',
                           f'<span class="chip">熟识率 <b>{pct(qw_tot["rate"])}</b></span>',
                           f'<span class="chip">未建群 <b>{sum(1 for x in qwsq.get("nets", []) if not x["groups"])}</b> 个网点</span>'],
                          qw_bar2, '客户数前三', qw_top, '交互后三', qw_bot,
                          note='口径：本日备份 vs 上周备份；只统计企微群')

    xs_rank = sorted(xsfw['nets'], key=lambda n: -(n['day_rate'] or 0))
    xs_bar = [(n['label'].replace('阜阳', ''), round((n['day_rate'] or 0) * 100, 1)) for n in xs_rank[:12]]
    xs_top = [(n['label'].replace('阜阳', ''), f"{pct(n['day_rate'])}") for n in xs_rank[:3]]
    xs_bot = [(n['label'].replace('阜阳', ''), f"{pct(n['day_rate'])} / 添客 {int(n['add_today']):+d}") for n in xs_rank[-3:][::-1]]
    card_xs = module_card('网点线上服务能力', f"{xsfw['prev_as_of'][5:]} → {xsfw['as_of'][5:]}",
                          '#c8102e',
                          f"{xs_tot['day_rate'] * 100:.2f}<small>% 当日动户率</small> &nbsp;<span style='color:var(--ink3);font-size:11px'>当月 {pct(xs_tot['month_rate'])}</span>",
                          [f'<span class="chip">当日添客 <b>{xs_tot["add_today"]:,}</b></span>',
                           f'<span class="chip">当月添客 <b>{xs_tot["add_month"]:,}</b></span>',
                           f'<span class="chip">签约率 <b>{pct(sum(n["sign_rate"] for n in xsfw["nets"]) / len(xsfw["nets"]))}</b></span>',
                           f'<span class="chip">网点 <b>{len(xsfw["nets"])}</b> 个</span>'],
                          xs_bar, '动户率前三（网点）', xs_top, '动户率后三（网点）', xs_bot,
                          note='动户率 = 当日手机银行动户 / 到店客群（按到店客群加权）；红线段为 55% 参考线')

    # ================================================== 网点明细（可切换）
    views = {}
    views['数币钱包'] = {
        'cols': ['网点', '支行', '累计户', '当月新增', '当日新增', '一类', '二类'],
        'rows': [[n['name'].replace('阜阳', ''), n['branch'], n['total'], n['month'], n['day'],
                  n['lv1'], n['lv2']] for n in sorted(sbqb['nets'], key=lambda x: -x['total'])],
        'num_from': 2, 'nd': [0, 0, 0, 0, 0],
    }
    views['线上服务'] = {
        'cols': ['网点', '支行', '当日动户率', '当月动户率', '到店客群', '当日添客', '当月添客', '签约率', '管户签约率'],
        'rows': [[n['label'].replace('阜阳', ''), n['branch'], round(n['day_rate'] * 100, 2),
                  round(n['month_rate'] * 100, 2), int(n['cust']), int(n['add_today']), int(n['add_month']),
                  round(n['sign_rate'] * 100, 2), round(n['kh_rate'] * 100, 2)]
                 for n in sorted(xsfw['nets'], key=lambda x: -x['day_rate'])],
        'num_from': 2, 'nd': [2, 2, 0, 0, 0, 2, 2],
    }
    views['薪管家'] = {
        'cols': ['网点', '全年金额(万)', '当月金额(万)', '全年单位', '当月单位'],
        'rows': [[n['name'].replace('阜阳', ''), n['year'], n['month'], n['ent_year'], n['ent_month']]
                 for n in xgj['nets']],
        'num_from': 1, 'nd': [2, 2, 0, 0],
    }
    views['企微社群'] = {
        'cols': ['网点', '群数量', '较上周', '客户数', '较上周', '交互数', '较上周', '熟识率'],
        'rows': [[str(n['name']).replace('阜阳', ''), n['groups'], n['groups_d'], n['cust'], n['cust_d'],
                  n['inter'], n['inter_d'], round(n['rate'] * 100, 2)]
                 for n in sorted(qwsq.get('nets', []), key=lambda x: -(x['cust'] or 0))],
        'num_from': 1, 'nd': [0, 0, 0, 0, 0, 0, 2],
    }
    views['定期存款'] = {
        'cols': ['支行', '上月余额(万)', '当月余额(万)', '当月增量(万)', '当月增幅'],
        'rows': [[b['name'], b['prev_bal'], b['cur_bal'], b['inc'], round(b['rate'] * 100, 2)]
                 for b in dqzz['branches']],
        'num_from': 1, 'nd': [2, 2, 2, 2],
    }

    # ================================================== HTML
    tabs = ''.join(f'<button class="{"on" if i == 0 else ""}" data-v="{k}">{k}（{len(v["rows"])}）</button>'
                   for i, (k, v) in enumerate(views.items()))

    html_out = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>阜阳分行个人金融经营驾驶舱 · {latest}</title>
<style>{CSS}{IMPORT_CSS}</style></head>
<body>
<header class="hero"><div class="wrap">
  <div class="hero-l">
    <h1>阜阳分行 <em>个人金融经营驾驶舱</em></h1>
    <p>数字人民币钱包 · 工银薪管家 · 定期存款 · 企业微信社群 · 网点线上服务能力</p>
  </div>
  <div class="hero-r">
    <div>数据截至 <b>{esc(latest)}</b></div>
    <div class="gen">生成于 {esc(D['generated_at'])} · 数据源：{len([k for k, v in S.items() if v.get('ok')])}/5 条线</div>
    <button class="btn-import" id="btnImport">＋ 导入数据</button>
  </div>
</div></header>

<div class="wrap">
  <section class="kpis">{''.join(kpis)}</section>

  <section class="grid2">
    <div class="card" style="--k:#1d5bb8">
      <h2><span class="dot"></span>数字人民币钱包 · 累计走势<span class="sub">{esc(sbqb['as_of'])} · 共 {len(sbqb['trend'])} 个时点</span></h2>
      <p class="lead">按每次通报的累计开立户数；最新 {sb_total:,} 户，较 10.08 增加 {sb_total - sbqb['trend'][0]['v']:,} 户</p>
      {chart_sb}
    </div>
    <div class="card" style="--k:#12a06a">
      <h2><span class="dot"></span>薪管家「聚薪行动」· 全年累计代发<span class="sub">{esc(xgj['as_of'])}</span></h2>
      <p class="lead">全年累计新增代发金额（万元）；当月累计 {xgj['month_total']:,.2f} 万元，有效使用单位 {xgj['ent_year']} 户</p>
      {chart_xg}
    </div>
  </section>

  <section class="grid2">
    <div class="card" style="--k:#c8102e">
      <h2><span class="dot"></span>网点线上服务 · 当日到店手机银行动户率<span class="sub">近 {len(xsfw['trend'])} 个工作日</span></h2>
      <p class="lead">加权口径：各网点到店客群加权；虚线为 55% 参考线，最新 {xs_tot['day_rate'] * 100:.2f}%</p>
      {chart_xs}
    </div>
    <div class="card" style="--k:#e08a00">
      <h2><span class="dot"></span>企微社群 · 支行客户数<span class="sub">{esc(qwsq['as_of'])}</span></h2>
      <p class="lead">共 {qw_tot['groups']} 个群、{qw_tot['cust']:,} 户客户、{qw_tot['inter']:,} 条交互；熟识率 {pct(qw_tot['rate'])}</p>
      {chart_qw}
    </div>
  </section>

  <section class="card" style="--k:#123a72">
    <h2><span class="dot"></span>8 家支行 · 五线指标对照<span class="sub">列内相对强弱，深蓝=领先，红=负值</span></h2>
    <p class="lead">同一家支行在五个条线上的位置一眼可见；合计行为全行口径（线上服务为加权值）</p>
    {matrix}
  </section>

  <section class="grid2">
    {card_sb}{card_xg}
  </section>
  <section class="grid2">
    {card_dq}{card_qw}
  </section>
  <section class="grid2">
    {card_xs}
    <div class="card" style="--k:#46536b">
      <h2><span class="dot"></span>数据与更新</h2>
      <p class="lead">右上角「导入数据」：选大类 → 放源表 → 自动识别、归档、重算</p>
      <ul style="margin:0;padding-left:16px;color:var(--ink2);font-size:11.5px;line-height:1.9">
        <li>原件存 <code style="background:#f3f5f9;padding:1px 5px;border-radius:4px">D:\\资料\\ICBC\\Visualizations\\imports</code>，按大类+时间留档，不改名不覆盖</li>
        <li>每导入一次生成一个快照，趋势图随之增长；同日重复导入按最新一份覆盖该日</li>
        <li>数字人民币钱包 / 薪管家 / 定期存款 / 线上服务：日频；企微社群：周频（本周 vs 上周）</li>
        <li>各条线口径不同，跨条线只看“排名 / 相对位置”，不看绝对数大小</li>
      </ul>
    </div>
  </section>

  <section class="card" style="--k:#1d5bb8">
    <h2><span class="dot"></span>网点 / 支行明细<span class="sub">点击切换条线，表内按首列指标降序</span></h2>
    <div class="tabs">{tabs}</div>
    <div class="tbl-wrap"><table id="detail"><thead></thead><tbody></tbody></table></div>
  </section>

  <footer>
    数据源：{esc(footer_src)}<br>
    本页由脚本生成；数字口径与各条线正式通报一致，导入即刷新。
  </footer>
</div>

{IMPORT_HTML}
<script>
const VIEWS = {json.dumps(views, ensure_ascii=False)};
const state = {{key: Object.keys(VIEWS)[0], sort: null, dir: -1}};
function fmtCell(v, nd) {{
  if (v === null || v === undefined || v === '') return '—';
  if (typeof v === 'number') return v.toLocaleString('zh-CN', {{minimumFractionDigits: nd||0, maximumFractionDigits: nd||0}});
  return v;
}}
function render() {{
  const v = VIEWS[state.key];
  const ths = v.cols.map((c, i) => `<th data-i="${{i}}" style="cursor:pointer">${{c}}${{i ? ' ⇅' : ''}}</th>`).join('');
  let rows = v.rows.slice();
  if (state.sort !== null) {{
    const i = state.sort;
    rows.sort((a, b) => {{
      const x = a[i], y = b[i];
      if (typeof x === 'number' && typeof y === 'number') return (x - y) * state.dir;
      return String(x).localeCompare(String(y), 'zh') * state.dir;
    }});
  }}
  const body = rows.map(r => '<tr>' + r.map((c, i) => {{
    if (i === 0) return `<td style="font-weight:600">${{c}}</td>`;
    const isNum = typeof c === 'number';
    const nd = isNum && v.nd ? v.nd[i - v.num_from] : 0;
    let cls = isNum ? ' class="n"' : '';
    let txt = fmtCell(c, nd);
    if (isNum && (txt.startsWith('-') && txt !== '—')) cls = ' class="n down"';
    if (i >= v.num_from && isNum && (String(c).includes('%') === false) && nd === 2 && v.cols[i].includes('率')) txt += '%';
    return `<td${{cls}}>${{txt}}</td>`;
  }}).join('') + '</tr>').join('');
  document.querySelector('#detail thead').innerHTML = `<tr>${{ths}}</tr>`;
  document.querySelector('#detail tbody').innerHTML = body;
  document.querySelectorAll('#detail th').forEach(th => th.onclick = () => {{
    const i = +th.dataset.i;
    if (i === 0) return;
    state.dir = (state.sort === i) ? -state.dir : -1;
    state.sort = i; render();
  }});
}}
document.querySelectorAll('.tabs button').forEach(b => b.onclick = () => {{
  document.querySelectorAll('.tabs button').forEach(x => x.classList.remove('on'));
  b.classList.add('on'); state.key = b.dataset.v; state.sort = null; render();
}});
render();
{IMPORT_JS}
document.getElementById('btnImport').onclick = () => document.getElementById('mask').classList.add('show');
</script>
</body></html>
"""
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_out, encoding='utf-8')
    print(json.dumps({'ok': True, 'out': str(out), 'bytes': len(html_out.encode()),
                      'latest': latest}, ensure_ascii=False, indent=1))



# ================================================================ 导入按钮
IMPORT_CSS = r"""
.btn-import{background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.35);color:#fff;
  border-radius:10px;padding:8px 14px;font-size:12.5px;cursor:pointer;font-family:inherit;margin-top:10px;
  transition:.15s;display:inline-flex;align-items:center;gap:6px}
.btn-import:hover{background:rgba(255,255,255,.22)}
.btn-import[disabled]{opacity:.5;cursor:not-allowed}
.mask{position:fixed;inset:0;background:rgba(12,20,36,.55);backdrop-filter:blur(2px);z-index:50;
  display:none;align-items:flex-start;justify-content:center;overflow:auto;padding:40px 16px}
.mask.show{display:flex}
.modal{background:#fff;border-radius:16px;width:min(760px,100%);box-shadow:0 24px 60px rgba(9,20,40,.35);
  overflow:hidden;animation:pop .18s ease-out}
@keyframes pop{from{transform:translateY(8px);opacity:0}to{transform:none;opacity:1}}
.modal header{display:flex;align-items:center;gap:10px;padding:16px 20px;border-bottom:1px solid var(--line)}
.modal header b{font-size:14.5px}
.modal header .st{margin-left:auto;font-size:11px;color:var(--ink3)}
.modal .body{padding:16px 20px 4px}
.modal footer{display:flex;gap:10px;justify-content:flex-end;padding:14px 20px;border-top:1px solid var(--line);
  background:#fafbfd}
.modal footer button{border-radius:9px;padding:8px 16px;font-size:12.5px;cursor:pointer;font-family:inherit;border:1px solid var(--line)}
.modal footer .primary{background:var(--brand);border-color:var(--brand);color:#fff;font-weight:600}
.modal footer .primary[disabled]{opacity:.55;cursor:not-allowed}
.linegrid{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin:8px 0 14px}
.linegrid label{border:1px solid var(--line);border-radius:10px;padding:9px 8px;cursor:pointer;font-size:12px;
  display:flex;flex-direction:column;gap:2px;color:var(--ink2);transition:.12s;background:#fff}
.linegrid label:hover{border-color:#c5d5ee}
.linegrid label.on{border-color:var(--brand);background:#f2f6fd;color:var(--brand);font-weight:700;
  box-shadow:inset 0 0 0 1px var(--brand)}
.linegrid label small{font-size:9.5px;color:var(--ink3);font-weight:400;line-height:1.25}
.linegrid input{display:none}
.frow{display:flex;align-items:center;gap:10px;margin:0 0 12px;font-size:12px;color:var(--ink2)}
.frow input[type=date]{border:1px solid var(--line);border-radius:8px;padding:6px 9px;font-family:inherit;font-size:12px}
.frow .tip{color:var(--ink3);font-size:11px}
.drop{border:1.5px dashed #c8d4e6;border-radius:12px;padding:22px;text-align:center;color:var(--ink3);
  font-size:12px;cursor:pointer;transition:.15s;background:#fbfcfe}
.drop:hover,.drop.over{border-color:var(--brand2);background:#f4f8ff;color:var(--brand2)}
.drop b{color:var(--ink);font-size:12.5px}
.picked{list-style:none;margin:10px 0 0;padding:0;max-height:150px;overflow:auto}
.picked li{display:flex;justify-content:space-between;gap:10px;font-size:11.5px;padding:4px 6px;
  border-bottom:1px dashed #eef1f6;color:var(--ink2)}
.picked li b{font-weight:600}
.picked li .rm{color:var(--ink3);cursor:pointer}
.res{margin:12px 0 8px;font-size:12px;line-height:1.7}
.res .ok{color:var(--green);font-weight:700}
.res .bad{color:var(--red);font-weight:700}
.res ul{margin:6px 0 0;padding-left:16px;color:var(--ink2)}
.res code{background:#f3f5f9;border-radius:4px;padding:1px 5px;font-size:11px}
"""

IMPORT_HTML = r"""
<div class="mask" id="mask">
  <div class="modal">
    <header><span class="dot" style="width:8px;height:8px;border-radius:2px;background:var(--brand)"></span>
      <b>导入源数据</b><span class="st" id="apiState">正在连接…</span></header>
    <div class="body">
      <div class="frow" style="margin-bottom:4px"><b style="font-size:12px">① 选择大类</b>
        <span class="tip">按大类认表：同一批文件里自动分辨本期/上期、支行/网点</span></div>
      <div class="linegrid" id="linegrid"></div>
      <div class="frow"><b style="font-size:12px">② 数据日期</b>
        <input type="date" id="dataDate"><span class="tip">可不填：表内带日期的自动取；薪管家默认昨天</span></div>
      <div class="frow" style="margin-bottom:6px"><b style="font-size:12px">③ 放入源表</b>
        <span class="tip" id="lineHint">可多选，支持 xlsx / xls / csv</span></div>
      <div class="drop" id="drop"><b>点击选择文件</b>，或把文件拖到这里<br>
        <span id="dropSub">选好大类后按该类的口径识别</span></div>
      <input type="file" id="fileInput" multiple accept=".xlsx,.xls,.csv" hidden>
      <ul class="picked" id="picked"></ul>
      <div class="res" id="res"></div>
    </div>
    <footer>
      <button id="btnCancel">取消</button>
      <button id="btnSubmit" class="primary" disabled>开始导入</button>
    </footer>
  </div>
</div>
"""

IMPORT_JS = r"""
const LINES = {
  sbqb:{label:'数字人民币钱包',hint:'钱包开立明细表（含网点号/钱包等级/注册日期），单日快照'},
  xgj:{label:'工银薪管家',hint:'四张增量表：支行/网点 × 年度/月度，可一次全选'},
  dqzz:{label:'定期存款',hint:'《分品种、期限时点报表》：本月 + 上月，可放多份'},
  xsfw:{label:'网点线上服务',hint:'动户率×2 + 企微明细×3 + 营销授权（模板可缺）'},
  qwsq:{label:'企微社群',hint:'成员群聊数据统计：本周 + 上周，自动对比'}
};
const st = {line:'', files:[], api:false};
const $ = s => document.querySelector(s);

async function initApi(){
  try{
    const r = await fetch('/api/state', {cache:'no-store'});
    const j = await r.json();
    st.api = !!j.ok;
    const win = (p => p.replace(/^\/mnt\/([a-z])\//, (m,d) => d.toUpperCase() + ':\\').replace(/\//g, '\\'))(j.root);
    $('#apiState').textContent = st.api ? '已连接 ' + win : '未连接服务';
    if(j.lines) j.lines.forEach(l => {
      const el = document.querySelector(`#linegrid label[data-k="${l.id}"] small`);
      if(el && l.as_of) el.textContent = '最新 ' + l.as_of;
    });
  }catch(e){
    st.api = false;
    $('#apiState').textContent = '未连接服务（请用 serve.py 启动）';
    $('#btnSubmit').dataset.blocked = '1';
  }
}

function buildLines(){
  const g = $('#linegrid');
  g.innerHTML = Object.entries(LINES).map(([k,v]) => `
    <label data-k="${k}"><span>${v.label}</span><small>${v.hint}</small></label>`).join('');
  g.querySelectorAll('label').forEach(el => el.onclick = () => {
    g.querySelectorAll('label').forEach(x => x.classList.remove('on'));
    el.classList.add('on'); st.line = el.dataset.k;
    $('#lineHint').textContent = LINES[st.line].hint;
    $('#dropSub').textContent = '将按「' + LINES[st.line].label + '」的口径识别';
    sync();
  });
}

function sync(){
  $('#btnSubmit').disabled = !(st.line && st.files.length) || !st.api;
  const ul = $('#picked');
  ul.innerHTML = st.files.map((f,i) =>
    `<li><span><b>${f.name}</b> <span style="color:var(--ink3)">${(f.size/1024).toFixed(0)} KB</span></span>
     <span class="rm" data-i="${i}">移除</span></li>`).join('');
  ul.querySelectorAll('.rm').forEach(el => el.onclick = () => {
    st.files.splice(+el.dataset.i,1); sync();
  });
}

function addFiles(list){
  for(const f of list){
    if(!/\.(xlsx|xls|csv)$/i.test(f.name)) continue;
    if(!st.files.some(x => x.name===f.name && x.size===f.size)) st.files.push(f);
  }
  sync();
}

function renderResult(r){
  const box = $('#res');
  if(r.ok){
    const files = (r.files||[]).map(f => `<li>${f.name} <code>${f.role||'源表'}</code></li>`).join('');
    const notes = (r.notes||[]).filter(Boolean).map(n => `<li>${n}</li>`).join('');
    box.innerHTML = `<div><span class="ok">导入成功</span> · ${LINES[r.line]?.label||''} ·
      数据日期 <b>${r.data_date}</b></div>
      <div style="color:var(--ink3);font-size:11px">已归档：<code>${r.archive||''}</code></div>
      <ul>${files}${notes}</ul>
      <div style="margin-top:8px;color:var(--brand2)">正在刷新看板…</div>`;
    setTimeout(() => location.reload(), 1200);
  }else{
    box.innerHTML = `<div><span class="bad">导入失败</span> · ${r.error||'未知错误'}</div>`;
  }
}

async function submit(){
  if(!st.line || !st.files.length) return;
  $('#btnSubmit').disabled = true;
  $('#res').innerHTML = '<span style="color:var(--ink3)">正在识别并计算…</span>';
  const fd = new FormData();
  fd.append('line', st.line);
  const d = $('#dataDate').value; if(d) fd.append('date', d);
  st.files.forEach(f => fd.append('files', f, f.name));
  try{
    const resp = await fetch('/api/import', {method:'POST', body:fd});
    const j = await resp.json();
    renderResult(j);
    if(!j.ok) $('#btnSubmit').disabled = false;
  }catch(e){
    $('#res').innerHTML = `<div><span class="bad">请求失败</span> · ${e.message}</div>`;
    $('#btnSubmit').disabled = false;
  }
}

buildLines(); initApi(); sync();
$('#drop').onclick = () => $('#fileInput').click();
$('#fileInput').onchange = e => { addFiles(e.target.files); e.target.value=''; };
['dragenter','dragover'].forEach(ev => $('#drop').addEventListener(ev, e => {
  e.preventDefault(); $('#drop').classList.add('over'); }));
['dragleave','drop'].forEach(ev => $('#drop').addEventListener(ev, e => {
  e.preventDefault(); $('#drop').classList.remove('over'); }));
$('#drop').addEventListener('drop', e => addFiles(e.dataTransfer.files));
$('#btnCancel').onclick = () => { $('#mask').classList.remove('show'); $('#res').innerHTML=''; };
$('#btnSubmit').onclick = submit;
$('#mask').onclick = e => { if(e.target.id==='mask') $('#btnCancel').onclick(); };
document.addEventListener('keydown', e => { if(e.key==='Escape') $('#btnCancel').onclick(); });
"""


if __name__ == '__main__':
    main()
