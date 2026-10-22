/* home.js —— 首页：个金 / 网金 两张主卡（第一排）+ 其余四块（第二排）
   数据来自 /api/catalog（模块元信息）与 /api/all（各条线视图模型） */
import { fmt, icon, countUp } from '../ui.js';
import { sparkline, C } from '../charts.js';

const COLORS = { violet: C.violet, blue: C.blue, teal: C.teal, red: C.red, amber: C.amber, green: C.green };

export default {
  id: 'home',
  title: '总览',
  render(view, ctx) {
    const { catalog, data, date } = ctx;
    const L = data.overview?.lines || {};
    const pro = catalog.professionals || [];
    const byId = Object.fromEntries(pro.map((p) => [p.id, p]));

    view.innerHTML = `
      <div class="page-head">
        <div><h1>经营总览</h1>
          <p>六大板块 · ${date ? fmt.date(date) : '最新数据'} · 点卡片进入条线</p></div>
        <div class="spacer"></div>
        <span class="chip">${date ? '所选日期 ' + fmt.date(date) : '最新数据'}</span>
      </div>

      <div class="grid g2" id="heroRow">
        ${heroCard(byId.jg, L, 'jg')}
        ${heroCard(byId.wj, L, 'wj')}
      </div>

      <div class="grid g3" style="margin-top:16px" id="secondRow">
        ${smallCard(byId.loan, 'loan')}
        ${smallCard(byId.card, 'card')}
        ${smallCard(byId.pbs, 'pbs')}
      </div>

      <div style="margin-top:16px">${projectCard(byId.project)}</div>

      <div class="grid g-7-5" style="margin-top:16px">
        ${timeline(L)}
        ${noteCard()}
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

/* ---------------------------------------------------------------- 第一排：主卡 */
function heroCard(p, L, id) {
  if (!p) return '';
  const color = COLORS[p.color] || C.blue;
  const tiles = id === 'jg' ? jgTiles(p, L) : wjTiles(p, L);
  return `
  <div class="card hero-prof" data-go="#/p/${p.id}" style="--accent:${color};cursor:pointer">
    <div class="heroline"></div>
    <div class="hero-prof-head">
      <span class="prof-dot" style="background:${color}"></span>
      <b>${p.name}</b>
      <span class="chip ${p.status === 'active' ? 'green' : ''}">${p.status === 'active' ? '已接入' : '框架'}</span>
      <span class="hp-go">查看板块 ${icon('arrow', 13)}</span>
    </div>
    <div class="prof-desc" style="margin:2px 0 10px">${p.desc || ''}</div>
    <div class="tile-row">${tiles}</div>
  </div>`;
}

function jgTiles(p, L) {
  const d = L.deposit?.kpi, x = L.salary?.kpi;
  return `
    <div class="ptile" data-stop data-go="#/g/jg/jg-deposit">
      <span class="pt-k">增存</span>
      <span class="pt-v"><i data-count="${d?.balance_yi || 0}" data-dec="2">0</i><small>亿</small></span>
      <span class="pt-s">${d ? `当月 +${fmt.n(d.inc, 0)} 万` : '待接入'}</span>
    </div>
    <div class="ptile" data-stop data-go="#/g/jg/jg-customer">
      <span class="pt-k">增客</span>
      <span class="pt-v"><i data-count="${x?.year || 0}" data-dec="0">0</i><small>万</small></span>
      <span class="pt-s">${x ? `有效单位 ${x.ent_year} 户` : '待接入'}</span>
    </div>
    <div class="ptile off" data-stop data-go="#/g/jg/jg-income">
      <span class="pt-k">增收</span>
      <span class="pt-v muted">—</span>
      <span class="pt-s">待接入</span>
    </div>
    <div class="ptile off" data-stop data-go="#/g/jg/jg-loan">
      <span class="pt-k">增贷</span>
      <span class="pt-v muted">—</span>
      <span class="pt-s">暂不涉及</span>
    </div>`;
}

function wjTiles(p, L) {
  const o = L.online?.kpi, w = L.wallet?.kpi, c = L.community?.kpi;
  return `
    <div class="ptile" data-stop data-go="#/m/wj-online-svc">
      <span class="pt-k">线上服务</span>
      <span class="pt-v"><i data-count="${(o?.day_rate || 0) * 100}" data-dec="2">0</i><small>%</small></span>
      <span class="pt-s">当日动户率 · ${o?.nets || 0} 个网点</span>
    </div>
    <div class="ptile" data-stop data-go="#/m/wj-wallet">
      <span class="pt-k">数字人民币</span>
      <span class="pt-v"><i data-count="${w?.total || 0}" data-dec="0">0</i><small>户</small></span>
      <span class="pt-s">${w ? `当日 +${fmt.n(w.day)} · 当月 +${fmt.n(w.month)}` : '待接入'}</span>
    </div>
    <div class="ptile" data-stop data-go="#/m/wj-wecom-social">
      <span class="pt-k">企微社群</span>
      <span class="pt-v"><i data-count="${c?.cust || 0}" data-dec="0">0</i><small>户</small></span>
      <span class="pt-s">${c ? `${c.groups} 个群 · 交互 ${fmt.n(c.inter)}` : '待接入'}</span>
    </div>`;
}

/* ---------------------------------------------------------------- 第二排 */
function smallCard(p, type) {
  if (!p) return '';
  const color = COLORS[p.color] || C.blue;
  const mods = p.groups.flatMap((g) => g.modules || []);
  return `
  <div class="card prof-mini" data-go="#/p/${p.id}" style="--accent:${color};cursor:pointer">
    <div class="heroline"></div>
    <div class="prof-head">
      <span class="prof-dot" style="background:${color}"></span>
      <b>${p.name}</b>
      <span class="chip" style="margin-left:auto">${p.status === 'active' ? '已接入' : '框架'}</span>
    </div>
    <div class="prof-desc">${p.desc || ''}</div>
    <div class="mini-plan">
      ${mods.slice(0, 2).map((m) => `<span><i></i>${m.name}</span>`).join('')}
    </div>
    ${p.groups.length > 1 || p.groups[0]?.name !== p.name ? `<div class="prof-groups">
      ${p.groups.map((g) => `<span class="chip">${g.name}</span>`).join('')}
    </div>` : ''}
  </div>`;
}

function projectCard(p) {
  const mods = p?.groups?.flatMap((g) => g.modules || []) || [];
  return `
  <div class="card prof-mini" style="--accent:${C.green}">
    <div class="heroline"></div>
    <div class="prof-head">
      <span class="prof-dot" style="background:${C.green}"></span>
      <b>重点项目</b>
      <a class="chip blue" href="#/p/project" style="margin-left:auto;text-decoration:none">${mods.length} 个 →</a>
    </div>
    <div class="prof-desc">方案推进与专项攻坚</div>
    <div class="pj-grid">
      ${mods.map((m) => `
        <div class="pj-tile" data-go="#/m/${m.id}">
          <div class="pj-tile-top">
            <span class="pj-dot ${m.kind === 'metric' ? 'on' : ''}"></span>
            <b>${m.name}</b>
            <span class="chip ${m.kind === 'metric' ? 'green' : ''}" style="font-size:9.5px">
              ${m.kind === 'metric' ? '已接入' : '待接入'}</span>
          </div>
          <span class="pj-tile-desc">${m.desc || ''}</span>
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
    <div class="card-head"><h3>数据时点</h3><div class="right"><span class="chip">取该日之前最近一期</span></div></div>
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

function noteCard() {
  return `
  <div class="card">
    <div class="card-head"><h3>说明</h3></div>
    <div style="color:var(--ink-2);font-size:12px;line-height:1.95">
      <div>· 个金按 <b>增存 / 增客 / 增收 / 增贷</b> 组织，增贷暂不涉及</div>
      <div>· 网金含 <b>线上服务 / 数币 / 企微</b>，企微同时是重点项目</div>
      <div>· 个贷 / 银行卡 / 私银已留框架，数据接入后自动出现</div>
      <div style="margin-top:8px"><span class="chip">红=增长 / 绿=下降（银行口径）</span></div>
    </div>
  </div>`;
}
