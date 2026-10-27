/* app.js —— v3 壳：目录驱动导航 + 日期选择（取该日之前最近一期） + 路由 + 口令准入
   导航、首页卡片、上传两级选择都由 /api/catalog 生成；
   模块页按 module.page 映射到 pages/* 的实现，未接入的统一走占位页。
   「通报中心」「导入数据」进页前要验口令，权限只活在本页内存（刷新即失效）。 */
import { toast, fmt, setAsof, setDatePickers } from './ui.js';
import { disposeAll } from './charts.js';
import { auth, askPassword, openPasswordManager, cancelGate } from './auth.js';

import home from './pages/home.js';
import deposit from './pages/deposit.js';
import online from './pages/online.js';
import wallet from './pages/wallet.js';
import salary from './pages/salary.js';
import community from './pages/community.js';
import payroll from './pages/payroll.js';
import fivecards from './pages/fivecards.js';
import importer from './pages/import.js';
import report from './pages/report.js';
import jgPage from './pages/jg.js';
import toolPage from './pages/tool.js';
import downgrade from './pages/downgrade.js';
import { modulePlaceholder, browse } from './pages/placeholder.js';
import guide, { guideHref } from './pages/guide.js';

const RENDERERS = { deposit, online, wallet, salary, community, payroll, fivecards, downgrade, tool: toolPage };

/** 模块角标：数据页看是否接入，工具页是"开发中" */
function modBadge(m) {
  if (m.kind === 'metric') return '';
  if (m.kind === 'tool') return '<em class="nav-badge">开发中</em>';
  return '<em class="nav-badge">待接入</em>';
}
const GATED = new Set(['report', 'upload']);

const state = { catalog: null, data: null, date: null, mode: 'day',
  view: document.getElementById('view'), open: new Set(['jg']), openGroups: new Set(['jg/jg-deposit']),
  prevHash: '', gating: false };

/* ---------------------------------------------------------------- 数据 */
async function loadCatalog() {
  state.catalog = await fetch('/api/catalog', { cache: 'no-store' }).then((r) => r.json());
  return state.catalog;
}

async function loadData(date) {
  const url = date ? `/api/all?date=${encodeURIComponent(date)}` : '/api/all';
  state.data = await fetch(url, { cache: 'no-store' }).then((r) => r.json());
  state.date = date;
  paintChrome();
  return state.data;
}

function paintChrome() {
  const lines = state.data?.overview?.lines || {};
  const ok = Object.values(lines).filter((l) => l.ok).length;
  const side = document.getElementById('sideStatus');
  if (side) side.textContent = `${ok}/${Object.keys(lines).length} 个条线已就绪`;
  const ver = document.getElementById('sideVer');
  if (ver) {
    ver.textContent = state.catalog?.version ? `v${state.catalog.version}` : '';
    // 悬停可以看到构建号与浏览器信息（内网机排查"某台机器显示不对"时很有用）
    ver.title = `build ${state.catalog?.build || 'dev'}\n${navigator.userAgent}`;
  }
  const pick = document.getElementById('datePick');
  const mpick = document.getElementById('monthPick');
  if (pick) {
    pick.min = state.catalog?.earliest || '';
    pick.max = state.catalog?.latest || '';
    if (!pick.value) pick.value = state.date || state.catalog?.latest || '';
  }
  if (mpick) {
    mpick.min = (state.catalog?.earliest || '').slice(0, 7);
    mpick.max = (state.catalog?.latest || '').slice(0, 7);
    if (!mpick.value) mpick.value = (state.date || state.catalog?.latest || '').slice(0, 7);
  }
  document.getElementById('modeSeg')?.querySelectorAll('button').forEach((b) => {
    b.classList.toggle('on', b.dataset.mode === state.mode);
  });
  if (pick) pick.style.display = state.mode === 'day' ? '' : 'none';
  if (mpick) mpick.style.display = state.mode === 'month' ? '' : 'none';
}

/* ---------------------------------------------------------------- 数据截至（按当前页面自己的模块） */
function lineKeyOf(m) {
  return m?.as_line ? state.catalog?.line_keys?.[m.as_line] : null;
}

/** 该模块实际用到的时点（取不到返回 null） */
function asOfOfModule(m) {
  const key = lineKeyOf(m);
  const d = key ? state.data?.[key] : null;
  if (!d) return null;
  return d.ok ? (d.as_of || null) : (d.nearest || null);
}

function asOfIsoFor(r) {
  if (r.name === 'module') {
    const hit = findModule(r.id);
    if (!hit || hit.module.kind !== 'metric' || !hit.module.as_line) return null;
    return asOfOfModule(hit.module);
  }
  if (r.name === 'prof' || r.name === 'group') {
    const prof = state.catalog.professionals.find((p) => p.id === (r.prof || r.id));
    if (!prof) return null;
    const groups = r.name === 'group' ? prof.groups.filter((g) => g.id === r.id) : prof.groups;
    const isos = groups.flatMap((g) => g.modules || []).map(asOfOfModule).filter(Boolean).sort();
    return isos.length ? isos[isos.length - 1] : null;
  }
  if (r.name === 'home') return state.date || state.catalog?.latest || null;
  return null;
}

function asofFor(r, iso) {
  const suffix = state.date ? ` · 所选 ≤${fmt.date(state.date)}` : '';
  if (r.name === 'module') {
    const hit = findModule(r.id);
    if (!hit) return '—';
    if (hit.module.kind === 'tool') return '工具 · 无数据时点';
    if (hit.module.kind !== 'metric' || !hit.module.as_line) return '未接入数据';
    return iso ? `数据截至 ${fmt.date(iso)}${suffix}` : '暂无数据';
  }
  if (r.name === 'prof' || r.name === 'group') {
    if (iso) return `数据截至 ${fmt.date(iso)}${suffix}`;
    const prof = state.catalog.professionals.find((p) => p.id === (r.prof || r.id));
    const mods = (prof?.groups || []).flatMap((g) => g.modules || []);
    return mods.length && mods.every((m) => m.kind === 'tool') ? '工具 · 无数据时点' : '暂无数据';
  }
  if (r.name === 'upload') return '各模块独立时点';
  if (r.name === 'guide') return '使用指南 · 与数据时点无关';
  if (r.name === 'report') return null;      // 通报页自己按取到的通报写（含"暂无"）
  return iso ? `数据截至 ${fmt.date(iso)}` : '—';
}

/* ---------------------------------------------------------------- 顶栏右侧：导入入口 / 身份 */
const ICON_IMPORT = '<svg viewBox="0 0 24 24" width="15" height="15"><path d="M12 16V4m0 0L8 8m4-4 4 4M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
const ICON_LOCK = (s = 13) => `<svg viewBox="0 0 24 24" width="${s}" height="${s}" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><rect x="4.5" y="10" width="15" height="10.5" rx="3"/><path d="M8 10V7.5a4 4 0 0 1 8 0V10"/></svg>`;
const ICON_CHEV = '<svg viewBox="0 0 24 24" width="11" height="11"><path d="m6 9 6 6 6-6" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
const ICON_REFRESH = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M20 11a8 8 0 1 0-2.3 5.7M20 5v6h-6"/></svg>';
const ICON_GUIDE = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H19v15H6.5A2.5 2.5 0 0 0 4 20.5V5.5Z"/><path d="M8 7.5h7M8 11h5"/></svg>';

/** 指南入口：放在"导入数据"左边，小一号、低饱和，不抢注意力 */
function guideButton(anchor) {
  const a = document.createElement('a');
  a.className = 'guide-btn';
  a.id = 'topGuide';
  a.href = anchor || '#/guide';
  a.title = '使用指南：每个按钮、每个模块怎么用';
  a.innerHTML = `${ICON_GUIDE}<span>使用指南</span>`;
  return a;
}

/** 当前页面对应的指南章节（模块页 → 该模块 id；其余按页面类型；没有对应节就回指南首页） */
function guideAnchor(r) {
  if (r.name === 'module') return guideHref(r.id);
  if (r.name === 'report') return '#/guide/report';
  if (r.name === 'upload') return '#/guide/import';
  return '#/guide';
}

function paintTop(r) {
  const slot = document.getElementById('topSlot');
  if (!slot) return;
  slot.innerHTML = '';
  if (!GATED.has(r.name)) {
    const hit = r.name === 'module' ? findModule(r.id) : null;
    const to = hit?.module?.as_line ? `#/upload/${hit.module.id}` : '#/upload';
    slot.appendChild(guideButton(guideAnchor(r)));
    const b = document.createElement('button');
    b.className = 'btn btn-primary';
    b.id = 'topImport';
    b.title = hit?.module?.as_line ? `导入「${hit.module.name}」的数据` : '导入数据';
    b.innerHTML = `${ICON_IMPORT} 导入数据`;
    b.onclick = () => { location.hash = to; };
    slot.appendChild(b);
    return;
  }
  slot.appendChild(guideButton(guideAnchor(r)));
  if (!auth.ok) {
    const idle = document.createElement('span');
    idle.className = 'id-chip idle';
    idle.textContent = '待验证';
    slot.appendChild(idle);
    return;
  }
  const b = document.createElement('button');
  b.className = `id-chip${auth.admin ? ' admin' : ''}`;
  b.innerHTML = `${auth.admin ? adminIcon() : ICON_LOCK(13)}<span>${auth.label}</span>${ICON_CHEV}`;
  b.title = auth.admin ? '管理员：管理密码 / 重新验证' : `${auth.label} 权限 · 点击重新验证`;
  b.onclick = () => (auth.admin ? adminMenu(b) : reverify());
  slot.appendChild(b);
}

function adminIcon() {
  return '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round"><path d="M12 3.5 19 6v6c0 4.2-2.9 7.2-7 8.5-4.1-1.3-7-4.3-7-8.5V6l7-2.5Z"/><path d="m9 12 2.2 2.2L15.5 10" stroke-linecap="round"/></svg>';
}

function adminMenu(anchor) {
  document.querySelector('.id-menu')?.remove();
  const menu = document.createElement('div');
  menu.className = 'id-menu';
  menu.innerHTML = `
    <button data-act="pw"><span class="im-ic">${ICON_LOCK(14)}</span>
      <span class="im-tx"><b>管理密码</b><small>重置六个身份组的口令</small></span></button>
    <button data-act="again"><span class="im-ic">${ICON_REFRESH}</span>
      <span class="im-tx"><b>重新验证</b><small>换一个身份组进入</small></span></button>`;
  anchor.parentElement.appendChild(menu);
  const close = () => menu.remove();
  setTimeout(() => {
    document.addEventListener('click', (e) => { if (!menu.contains(e.target)) close(); }, { once: true });
  }, 0);
  menu.querySelector('[data-act="pw"]').onclick = () => {
    close();
    openPasswordManager(state.catalog?.roles);
  };
  menu.querySelector('[data-act="again"]').onclick = () => { close(); reverify(); };
}

async function reverify() {
  const ok = await askPassword({
    title: '重新验证',
    sub: '输入另一组口令即可切换可访问的大类',
  });
  if (!ok) return;
  renderNav();
  render();
  toast(`已切换：${auth.label}${auth.admin ? '' : '（含重点项目）'}`);
}

/* ---------------------------------------------------------------- 导航 */
function navItem(m) {
  const on = m.kind === 'metric' || m.kind === 'tool';
  // draggable="false" 很关键：按住导航项稍微一拖，浏览器会把这当成"拖动链接"，
  // 松手就新开一个窗口。鼠标按下后的位移由 guardSidebarDrag() 兜底拦掉。
  return `<a href="#/m/${m.id}" data-id="${m.id}" draggable="false" class="nav-item ${on ? '' : 'dim'}">
    <span class="nav-name">${m.name}</span>
    ${modBadge(m)}
  </a>`;
}

function renderNav() {
  const nav = document.getElementById('nav');
  const cat = state.catalog;
  const r = parseRoute();
  if (r.name === 'module') {
    const hit = findModule(r.id);
    if (hit) { state.open.add(hit.prof.id); state.openGroups.add(`${hit.prof.id}/${hit.group.id}`); }
  }
  if (r.name === 'group') state.openGroups.add(`${r.prof}/${r.id}`);
  if (r.name === 'prof' || r.name === 'group') state.open.add(r.prof || r.id);

  const sections = cat.professionals;
  const gateMark = auth.ok ? '' : `<em class="nav-lock" title="需要口令">${ICON_LOCK(11)}</em>`;
  nav.innerHTML = '<a href="#/" data-id="home" draggable="false" class="nav-item nav-home"><span class="nav-name">总览</span></a>'
    + sections.map((p) => navSection(p)).join('');

  // 这两个固定在下半区，不随上面的模块列表滚动
  const pinned = document.getElementById('navPinned');
  pinned.innerHTML = `<a href="#/report" data-id="report" draggable="false" class="nav-item"><span class="nav-name">通报中心</span>${gateMark}</a>`
    + `<a href="#/upload" data-id="upload" draggable="false" class="nav-item"><span class="nav-name">导入数据</span>${gateMark}</a>`;

  // 大类：点名字进板块总览，点箭头只展开/收起
  nav.querySelectorAll('[data-cat-link]').forEach((a) => {
    a.onclick = () => {
      const id = a.dataset.catLink;
      state.open.add(id);
      a.closest('.nav-group').classList.add('open');
    };
  });
  nav.querySelectorAll('[data-caret]').forEach((b) => {
    b.onclick = (e) => {
      e.preventDefault();
      e.stopPropagation();
      const id = b.dataset.caret;
      const grp = b.closest('.nav-group');
      if (state.open.has(id)) { state.open.delete(id); grp.classList.remove('open'); }
      else { state.open.add(id); grp.classList.add('open'); }
    };
  });
  nav.querySelectorAll('[data-subcaret]').forEach((b) => {
    b.onclick = (e) => {
      e.preventDefault(); e.stopPropagation();
      const key = b.dataset.subcaret;
      const box = b.closest('.nav-subgroup');
      if (state.openGroups.has(key)) { state.openGroups.delete(key); box.classList.remove('open'); }
      else { state.openGroups.add(key); box.classList.add('open'); }
    };
  });
  nav.querySelectorAll('[data-subcat]').forEach((a) => {
    a.onclick = () => { state.openGroups.add(a.dataset.subcat); a.closest('.nav-subgroup').classList.add('open'); };
  });
  document.querySelectorAll('.sidebar a.nav-item').forEach((a) => {
    a.addEventListener('click', () => {
      document.querySelectorAll('.sidebar a.nav-item').forEach((x) => x.classList.remove('on'));
      a.classList.add('on');
    });
  });
}

function navSection(p) {
  if (!p) return '';
  const open = state.open.has(p.id);
  const mods = p.groups.flatMap((g) => (g.modules || []).map((m) => ({ ...m, _g: g.name })));
  const multi = !!p.nested && p.groups.length > 1;
  if (!mods.length) {
    // 空板块（如"实用工具"）：只给入口，不给展开箭头
    return `
  <div class="nav-group" data-group="${p.id}">
    <div class="nav-cat">
      <a class="nav-cat-link" href="#/p/${p.id}" data-cat-link="${p.id}" draggable="false">
        <span class="nav-cat-name">${p.short || p.name}</span>
        <span class="nav-count">空</span>
      </a>
    </div>
  </div>`;
  }
  return `
  <div class="nav-group ${open ? 'open' : ''}" data-group="${p.id}">
    <div class="nav-cat">
      <a class="nav-cat-link" href="#/p/${p.id}" data-cat-link="${p.id}" draggable="false">
        <span class="nav-cat-name">${p.short || p.name}</span>
        <span class="nav-count">${mods.filter((m) => m.kind === 'metric').length}/${mods.length}</span>
      </a>
      <button class="nav-caret-btn" data-caret="${p.id}" aria-label="展开/收起">
        <svg viewBox="0 0 24 24" width="12" height="12"><path d="m9 6 6 6-6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </button>
    </div>
    <div class="nav-sub-wrap">
      ${multi ? p.groups.map((g) => navGroup(p, g)).join('')
              : p.groups.flatMap((g) => g.modules || []).map((m) => navItem(m)).join('')}
    </div>
  </div>`;
}

function navGroup(p, g) {
  const key = `${p.id}/${g.id}`;
  const open = state.openGroups.has(key);
  const mods = g.modules || [];
  return `
  <div class="nav-subgroup ${open ? 'open' : ''}">
    <div class="nav-subcat">
      <a class="nav-subcat-link" href="#/g/${p.id}/${g.id}" data-subcat="${key}" draggable="false">
        ${g.name}
        <em class="nav-count">${mods.filter((m) => m.kind === 'metric').length}/${mods.length}</em>
      </a>
      <button class="nav-caret-btn small" data-subcaret="${key}" aria-label="展开/收起">
        <svg viewBox="0 0 24 24" width="11" height="11"><path d="m9 6 6 6-6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </button>
    </div>
    <div class="nav-sub-wrap2">${mods.map(navItem).join('')}</div>
  </div>`;
}

/* ---------------------------------------------------------------- 路由 */
function parseRoute() {
  const h = location.hash.replace(/^#/, '') || '/';
  const seg = h.split('/').filter(Boolean);
  if (!seg.length) return { name: 'home' };
  if (seg[0] === 'm') return { name: 'module', id: seg[1] };
  if (seg[0] === 'p') return { name: 'prof', id: seg[1] };
  if (seg[0] === 'g') return { name: 'group', prof: seg[1], id: seg[2] };
  if (seg[0] === 'report') return { name: 'report', kind: seg[1] };
  if (seg[0] === 'upload') return { name: 'upload', moduleId: seg[1] };
  if (seg[0] === 'guide') return { name: 'guide', section: seg[1] || null };
  return { name: 'home' };
}

function findModule(id) {
  for (const p of state.catalog.professionals) {
    for (const g of p.groups) {
      for (const m of g.modules || []) {
        if (m.id === id) return { prof: p, group: g, module: m };
      }
    }
  }
  return null;
}

/* ---------------------------------------------------------------- 口令门 */
function gatedHash(h) {
  const seg = String(h || '').replace(/^#/, '').split('/').filter(Boolean);
  return seg[0] === 'report' || seg[0] === 'upload';
}

function lockCard(label) {
  return `<div class="card gate-hold">
    <div class="gh-emblem">${ICON_LOCK(26)}</div>
    <b>${label}需要验证口令</b>
    <p>口令按大类区分：输入哪个大类的口令，就进入哪个大类（「重点项目」对五个大类均开放）。
      验证只在本次打开网页期间有效，刷新或关闭网页需重新验证。</p>
    <div class="gh-actions">
      <button class="btn btn-primary" id="gateOpen">${ICON_LOCK(14)} 输入口令</button>
      <a class="btn" href="#/">返回总览</a>
    </div>
  </div>`;
}

async function startGate(r, force = false) {
  if (state.gating) return;
  state.gating = true;
  const label = r.name === 'report' ? '通报中心' : '导入数据';
  let ok = false;
  try {
    ok = await askPassword({
      title: `${label} · 身份验证`,
      sub: '输入分管大类的口令进入；管理员口令可访问全部',
      note: '五大类口令 → 对应大类，均可看「重点项目」<br>管理员口令 → 全部大类',
    });
  } catch (err) {
    // 弹窗都建不起来时，至少别把 gating 卡死（否则之后点"输入口令"永远没反应）
    console.error('[auth] 口令框异常', err);
    toast('验证窗口没能打开，请刷新页面重试', 'err');
  } finally {
    state.gating = false;
  }
  if (ok === null) {
    // 口令框还没输完就切到别的页面了：只关框，不跳转（别把用户拽回口令页）
    return;
  }
  if (ok) {
    renderNav();
    render();
    toast(`已验证：${auth.label}${auth.admin ? '' : '（含重点项目）'}`);
  } else if (!force) {
    // 取消就退回上一个"非口令页"；上一个也是口令页（会话过期后连着点）就回总览
    location.hash = state.prevHash && !gatedHash(state.prevHash) ? state.prevHash : '#/';
  }
}

/* ---------------------------------------------------------------- 渲染 */
function render() {
  // 换页时把还开着的口令框关掉：否则它会盖在新页面上，取消时还会把用户拽回口令页
  cancelGate();
  const r = parseRoute();
  const view = state.view;
  disposeAll();
  view.innerHTML = '';
  const host = document.createElement('div');
  host.className = 'page';
  view.appendChild(host);

  if (GATED.has(r.name) && !auth.ok) {
    const label = r.name === 'report' ? '通报中心' : '导入数据';
    document.getElementById('crumbs').innerHTML = `<b>${label}</b>`;
    document.title = `${label} · 经营驾驶舱`;
    host.innerHTML = lockCard(label);
    host.querySelector('#gateOpen').onclick = () => startGate(r, true);
    paintTop(r);
    setAsof('待验证');
    document.querySelectorAll('.sidebar a[data-id]').forEach((a) => a.classList.toggle('on', a.dataset.id === r.name));
    if (!state.gating) startGate(r);
    return;
  }
  state.prevHash = location.hash || '#/';

  const ctx = { catalog: state.catalog, data: state.data, date: state.date, moduleId: r.moduleId,
    reload: refresh,
    /** 静默刷新数据（不重渲染页面，导入成功后用，保留结果提示） */
    reloadData: async () => { await loadCatalog(); await loadData(state.date); } };

  let title = '经营总览';
  let crumb = '<b>经营总览</b>';
  try {
    if (r.name === 'module') {
      const hit = findModule(r.id);
      if (!hit) throw new Error('模块不存在');
      title = hit.module.name;
      crumb = `<a href="#/p/${hit.prof.id}" style="color:var(--ink-3)">${hit.prof.name}</a>
        <span class="sep">/</span><b>${hit.module.name}</b>`;
      const impl = RENDERERS[hit.module.page];
      if (impl) impl.render(host, state.data, ctx);      // 有渲染器就用（数据页/工具页）
      else modulePlaceholder(host, hit);
    } else if (r.name === 'prof') {
      const prof = state.catalog.professionals.find((p) => p.id === r.id);
      if (!prof) throw new Error('板块不存在');
      title = prof.name;
      crumb = `<b>${prof.name}</b>`;
      if (prof.id === 'jg') jgPage.render(host, state.data, ctx);
      else browse(host, { prof });
    } else if (r.name === 'group') {
      const prof = state.catalog.professionals.find((p) => p.id === r.prof);
      const group = prof?.groups.find((g) => g.id === r.id);
      if (!prof || !group) throw new Error('分组不存在');
      title = `${prof.name} · ${group.name}`;
      crumb = `<a href="#/p/${prof.id}" style="color:var(--ink-3)">${prof.name}</a>
        <span class="sep">/</span><b>${group.name}</b>`;
      browse(host, { prof, group });
    } else if (r.name === 'report') {
      title = '通报中心';
      crumb = '<b>通报中心</b>';
      report.render(host, state.data, ctx);
    } else if (r.name === 'upload') {
      title = '导入数据';
      crumb = '<b>导入数据</b>';
      importer.render(host, state.data, ctx);
    } else if (r.name === 'guide') {
      title = '使用指南';
      crumb = '<b>使用指南</b>';
      guide.render(host, { catalog: state.catalog, section: r.section });
    } else {
      home.render(host, ctx);
    }
  } catch (err) {
    console.error(err);
    host.innerHTML = `<div class="card"><div class="empty"><b>页面渲染出错</b>${String(err.message || err)}</div></div>`;
  }
  document.getElementById('crumbs').innerHTML = crumb;
  document.title = `${title} · 经营驾驶舱`;
  document.querySelectorAll('.sidebar a[data-id]').forEach((a) => {
    a.classList.toggle('on', a.dataset.id === r.id || (r.name === 'home' && a.dataset.id === 'home')
      || (r.name === 'report' && a.dataset.id === 'report') || (r.name === 'upload' && a.dataset.id === 'upload'));
  });
  host.querySelectorAll('[data-go]').forEach((el) => {
    if (!el.onclick) el.onclick = () => { location.hash = el.dataset.go; };
  });
  const iso = asOfIsoFor(r);
  const asofText = asofFor(r, iso);
  if (asofText) setAsof(asofText);
  // 未筛选时，日期控件跟着本页实际时点走（避免和"数据截至"两个日期打架）
  if (!state.date) setDatePickers(iso || (r.name === 'upload' ? state.catalog?.latest : null));
  // 换页回到顶部（指南里"回到最上边"按钮也是这条路）
  window.scrollTo(0, 0);
  paintTop(r);
  if (r.name === 'guide') guide.after(host, r.section);
}

async function refresh(date = state.date) {
  await loadData(date);
  render();
}

/* ---------------------------------------------------------------- 侧栏防误拖
   症状：按住侧栏某一项、手抖挪动几像素再松手，浏览器按"拖动链接"处理，
   直接新开一个窗口/标签页，原来的页面还停在原地。
   四道防线：
     ① 导航项 draggable="false"（CSS 里还有 -webkit-user-drag:none）；
     ② 侧栏内禁止 dragstart 默认行为；
     ③ 按下到松开位移超过 6px 就不认这次点击（当成误触，不跳转）；
     ④ 松手后（无论松在哪）清掉按下记录，避免误触记录残留把下一次正常点击也吃掉。 */
function guardSidebarDrag() {
  const side = document.querySelector('.sidebar');
  if (!side) return;
  let down = null;

  side.addEventListener('dragstart', (e) => e.preventDefault());

  side.addEventListener('mousedown', (e) => {
    if (e.button !== 0) return;
    const a = e.target.closest && e.target.closest('a[href]');
    down = a ? { a, x: e.clientX, y: e.clientY } : null;
  }, true);

  side.addEventListener('click', (e) => {
    if (!down) return;
    const moved = Math.abs(e.clientX - down.x) + Math.abs(e.clientY - down.y);
    const a = down.a;
    down = null;
    if (moved <= 6) return;         // 正常点击，放行
    e.preventDefault();
    e.stopPropagation();            // 位移过大：不跳转，避免"手一抖跳到别处"
    if (a) a.blur();
  }, true);

  // click 在 mouseup 之后同步触发，所以延到下一个宏任务再清，不影响上面那次判断
  document.addEventListener('mouseup', () => setTimeout(() => { down = null; }, 0), true);
}

/* ---------------------------------------------------------------- 启动 */
async function boot() {
  try {
    await loadCatalog();
    await loadData(null);
  } catch (err) {
    document.getElementById('boot').innerHTML =
      '<div class="empty"><b>无法连接服务</b>请用 <code>python run.py</code> 启动</div>';
    console.error(err);
    return;
  }
  renderNav();
  const bootEl = document.getElementById('boot');
  bootEl.classList.add('gone');
  setTimeout(() => bootEl.remove(), 420);

  document.getElementById('datePick').addEventListener('change', async (e) => {
    const v = e.target.value || null;
    await refresh(v);
    toast(v ? `已切换到 ${v}（取该日之前最近一期）` : '已回到最新数据');
  });
  document.getElementById('monthPick').addEventListener('change', async (e) => {
    const m = e.target.value;
    if (!m) return;
    const [y, mm] = m.split('-').map(Number);
    const last = new Date(y, mm, 0).getDate();
    const date = `${m}-${String(last).padStart(2, '0')}`;
    await refresh(date);
    toast(`已切换到 ${m}（取该月内最新一期）`);
  });
  document.querySelectorAll('#modeSeg button').forEach((b) => {
    b.onclick = async () => {
      state.mode = b.dataset.mode;
      paintChrome();
      if (state.mode === 'month' && state.date) {
        const m = state.date.slice(0, 7);
        document.getElementById('monthPick').value = m;
      }
    };
  });
  // 「回到最新」：一个按钮同时干两件事 —— 清掉日期筛选、重新拉数据。
  // （以前是"回到最新"+"刷新"两个按钮，功能重叠，容易点错，合并掉刷新那个。）
  document.getElementById('btnLatest').addEventListener('click', async (e) => {
    const btn = e.currentTarget;
    btn.classList.add('spinning');            // 类名切换，不用内联 transform（老内核不会卡住）
    document.getElementById('datePick').value = state.catalog?.latest || '';
    document.getElementById('monthPick').value = (state.catalog?.latest || '').slice(0, 7);
    await refresh(null);
    setTimeout(() => btn.classList.remove('spinning'), 460);
    toast('已回到最新数据');
  });

  const brand = document.querySelector('.brand');
  if (brand) { brand.style.cursor = 'pointer'; brand.title = '返回总览'; brand.onclick = () => { location.hash = '#/'; }; }

  guardSidebarDrag();

  // 服务端会话过期 / token 失效：清权限并回到口令门
  window.addEventListener('dash:auth-lost', () => {
    renderNav();
    render();
    toast('验证已失效，请重新输入口令', 'err');
  });

  window.addEventListener('hashchange', render);
  render();
}

boot();
