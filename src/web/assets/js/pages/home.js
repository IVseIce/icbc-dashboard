/* home.js —— 首页：六大板块 + 重点项目 + 数据时点
   数据全部来自 /api/catalog（导航/模块元信息）与 /api/all（各条线视图模型） */
import { fmt, icon, countUp, empty } from '../ui.js';
import { sparkline, C } from '../charts.js';

const COLORS = { violet: C.violet, blue: C.blue, teal: C.teal, red: C.red, amber: C.amber, green: C.green };

export default {
  id: 'home',
  title: '总览',
  render(view, ctx) {
    const { catalog, data, date } = ctx;
    const L = data.overview?.lines || {};
    const pro = catalog.professionals || [];
    const active = pro.filter((p) => p.status === 'active');
    const planned = pro.filter((p) => p.status !== 'active');

    view.innerHTML = `
      <div class="page-head">
        <div>
          <h1>经营总览</h1>
          <p>六大板块 · ${date || '最新'} 数据视图 · 点击卡片进入条线明细</p>
        </div>
        <div class="spacer"></div>
        <span class="chip">${date ? '所选日期 ' + fmt.date(date) : '最新数据'}</span>
      </div>

      <div class="grid g3" id="profCards">
        ${pro.filter((p) => p.id !== 'project').map((p) => profCard(p, L)).join('')}
      </div>

      <div class="grid g-7-5" style="margin-top:16px">
        ${projectCard(pro.find((p) => p.id === 'project'))}
        ${timeline(L)}
      </div>

      <div class="card" style="margin-top:16px">
        <div class="card-head"><h3>说明</h3><div class="right"><span class="chip">六大板块 · 个金/网金已接入</span></div></div>
        <div style="display:flex;gap:22px;flex-wrap:wrap;color:var(--ink-2);font-size:12px;line-height:1.9">
          <div>· 个金按 <b>增存 / 增客 / 增收 / 增贷</b> 四条线组织，增贷暂不涉及</div>
          <div>· 网金含 <b>线上服务 / 数币 / 企微</b>，企微同时是重点项目</div>
          <div>· 个贷、银行卡、私银已留框架，数据接入后自动出现</div>
          <div>· 日期选择遵循「取该日之前最近一期」</div>
        </div>
      </div>`;

    view.querySelectorAll('[data-count]').forEach((el) =>
      countUp(el, Number(el.dataset.count), { decimals: Number(el.dataset.dec || 0) }));
    view.querySelectorAll('[data-go]').forEach((el) => {
      el.onclick = (e) => {
        if (e.target.closest('[data-stop]')) return;
        location.hash = el.dataset.go;
      };
    });
  },
};

/* ---------------------------------------------------------------- 板块卡 */
function profCard(p, L) {
  const stat = profStat(p, L);
  const color = COLORS[p.color] || C.blue;
  return `
  <div class="card prof-card" data-go="#/p/${p.id}" style="--accent:${color};cursor:pointer">
    <div class="heroline"></div>
    <div class="prof-head">
      <span class="prof-dot" style="background:${color}"></span>
      <b>${p.name}</b>
      <span class="chip ${p.status === 'active' ? 'green' : ''}" style="margin-left:auto">
        ${p.status === 'active' ? '已接入' : '框架'}</span>
    </div>
    <div class="prof-desc">${p.desc || ''}</div>
    <div class="prof-body">${stat}</div>
    <div class="prof-groups">
      ${p.groups.map((g) => `<span class="chip ${g.status === 'active' ? 'blue' : ''}"
        data-stop data-go="#/g/${p.id}/${g.id}" style="cursor:pointer">${g.name}</span>`).join('')}
    </div>
  </div>`;
}

function profStat(p, L) {
  if (p.id === 'jg') {
    const d = L.deposit?.kpi, x = L.salary?.kpi;
    if (!d) return emptyLine('暂无数据');
    return `
      <div class="prof-kpis">
        <div><span class="v" data-count="${d.balance_yi}" data-dec="2">0</span><small>亿</small><em>增存·定期余额</em></div>
        <div><span class="v" data-count="${x?.year || 0}" data-dec="2">0</span><small>万</small><em>增客·代发金额</em></div>
        <div><span class="v muted">—</span><em>增收 / 增贷 待接入</em></div>
      </div>`;
  }
  if (p.id === 'wj') {
    const o = L.online?.kpi, w = L.wallet?.kpi, c = L.community?.kpi;
    if (!o && !w) return emptyLine('暂无数据');
    return `
      <div class="prof-kpis">
        <div><span class="v" data-count="${(o?.day_rate || 0) * 100}" data-dec="2">0</span><small>%</small><em>线上动户率</em></div>
        <div><span class="v" data-count="${w?.total || 0}" data-dec="0">0</span><small>户</small><em>数币钱包</em></div>
        <div><span class="v" data-count="${c?.cust || 0}" data-dec="0">0</span><small>户</small><em>企微社群客户</em></div>
      </div>`;
  }
  const mods = p.groups.flatMap((g) => g.modules || []);
  return `<div class="prof-placeholder">${icon('spark', 14)} 框架已预留 · ${mods.length} 个模块待接入</div>`;
}

const emptyLine = (t) => `<div class="prof-placeholder">${t}</div>`;

/* ---------------------------------------------------------------- 重点项目 */
function projectCard(p) {
  const mods = p?.groups?.flatMap((g) => g.modules || []) || [];
  return `
  <div class="card" style="--accent:${C.green}">
    <div class="card-head">
      <h3>重点项目</h3>
      <div class="right"><a class="chip blue" href="#/p/project" style="text-decoration:none">全部 ${mods.length} 个 →</a></div>
    </div>
    <div class="pj-list">
      ${mods.map((m) => `
        <div class="pj-row" data-go="#/m/${m.id}">
          <span class="pj-dot ${m.kind === 'metric' ? 'on' : ''}"></span>
          <div class="pj-txt"><b>${m.name}</b><span>${m.desc || ''}</span></div>
          <span class="chip ${m.kind === 'metric' ? 'green' : ''}">${m.kind === 'metric' ? '已接入' : '待接入'}</span>
        </div>`).join('')}
    </div>
  </div>`;
}

function timeline(L) {
  const rows = [
    ['deposit', '定期存款', C.violet],
    ['online', '网点线上服务', C.red],
    ['wallet', '数字人民币', C.blue],
    ['salary', '薪管家', C.teal],
    ['community', '企微社群', C.amber],
  ];
  return `
  <div class="card">
    <div class="card-head"><h3>数据时点</h3><div class="right"><span class="chip">最近一期</span></div></div>
    <div class="timeline">
      ${rows.map(([k, name, c]) => {
        const l = L[k] || {};
        return `<div class="tl-item" style="--accent:${c}">
          <i class="tl-dot"></i><span class="tl-name">${name}</span>
          <span class="chip ${l.ok ? 'green' : ''}" style="font-size:10px">${l.ok ? '已就绪' : '该日无数据'}</span>
          <span class="tl-sub">${l.ok ? fmt.date(l.as_of) : (l.nearest ? '最近 ' + fmt.date(l.nearest) : '—')}</span>
        </div>`;
      }).join('')}
    </div>
  </div>`;
}
