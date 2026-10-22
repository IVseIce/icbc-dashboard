/* app.js —— v3 壳：目录驱动导航 + 日期选择（取该日之前最近一期） + 路由
   导航、首页卡片、上传两级选择都由 /api/catalog 生成；
   模块页按 module.page 映射到 pages/* 的实现，未接入的统一走占位页。 */
import { toast } from './ui.js';
import { disposeAll } from './charts.js';

import home from './pages/home.js';
import deposit from './pages/deposit.js';
import online from './pages/online.js';
import wallet from './pages/wallet.js';
import salary from './pages/salary.js';
import community from './pages/community.js';
import importer from './pages/import.js';
import report from './pages/report.js';
import { modulePlaceholder, browse } from './pages/placeholder.js';

const RENDERERS = { deposit, online, wallet, salary, community };

const state = { catalog: null, data: null, date: null, view: document.getElementById('view'), open: new Set(['jg']) };

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
  if (side) side.textContent = `${ok}/5 条线已就绪`;
  const el = document.getElementById('asof');
  el.querySelector('span').textContent = state.date
    ? `所选 ${state.date.slice(5)} · ${ok}/5 条线`
    : `数据截至 ${state.catalog?.latest || '—'}`;
  const pick = document.getElementById('datePick');
  if (pick) {
    pick.min = state.catalog?.earliest || '';
    pick.max = state.catalog?.latest || '';
    if (!pick.value) pick.value = state.date || state.catalog?.latest || '';
  }
}

/* ---------------------------------------------------------------- 导航 */
function moduleLink(m) {
  const on = m.kind === 'metric';
  return `<a href="#/m/${m.id}" data-id="${m.id}" class="nav-item ${on ? '' : 'dim'}">
    <span class="nav-name">${m.name}</span>
    ${on ? '' : '<em class="nav-badge">待接入</em>'}
  </a>`;
}

function renderNav() {
  const nav = document.getElementById('nav');
  const cat = state.catalog;
  const r = parseRoute();
  // 当前路由所属板块默认展开
  if (r.name === 'module') {
    const hit = findModule(r.id);
    if (hit) state.open.add(hit.prof.id);
  }
  if (r.name === 'prof' || r.name === 'group') state.open.add(r.prof || r.id);

  const groups = cat.professionals.filter((p) => p.id !== 'project');
  nav.innerHTML = `
    <a href="#/" data-id="home" class="nav-item"><span class="nav-name">经营总览</span></a>
    ${groups.map((p) => navSection(p)).join('')}
    ${navSection(cat.professionals.find((p) => p.id === 'project'))}
    <div class="nav-sep"></div>
    <a href="#/report" data-id="report" class="nav-item"><span class="nav-name">通报中心</span></a>
    <a href="#/upload" data-id="upload" class="nav-item"><span class="nav-name">导入数据</span></a>`;

  nav.querySelectorAll('.nav-cat').forEach((btn) => {
    btn.onclick = (e) => {
      e.preventDefault();
      const id = btn.dataset.cat;
      if (state.open.has(id)) state.open.delete(id); else state.open.add(id);
      btn.closest('.nav-group').classList.toggle('open', state.open.has(id));
      btn.setAttribute('aria-expanded', state.open.has(id));
    };
  });
  nav.querySelectorAll('a.nav-item').forEach((a) => {
    a.addEventListener('click', () => {
      nav.querySelectorAll('a.nav-item').forEach((x) => x.classList.remove('on'));
      a.classList.add('on');
    });
  });
}

function navSection(p) {
  if (!p) return '';
  const open = state.open.has(p.id);
  const mods = p.groups.flatMap((g) => (g.modules || []).map((m) => ({ ...m, _g: g.name })));
  return `
  <div class="nav-group ${open ? 'open' : ''}" data-group="${p.id}">
    <button class="nav-cat" data-cat="${p.id}" aria-expanded="${open}">
      <span class="nav-cat-name">${p.short || p.name}</span>
      <span class="nav-count">${mods.filter((m) => m.kind === 'metric').length}/${mods.length}</span>
      <svg class="nav-caret" viewBox="0 0 24 24" width="12" height="12"><path d="m9 6 6 6-6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
    </button>
    <div class="nav-sub-wrap">
      <a href="#/p/${p.id}" class="nav-item nav-over">板块总览</a>
      ${p.groups.map((g) => `
        <div class="nav-sub">${g.name}</div>
        ${(g.modules || []).map((m) => `
          <a href="#/m/${m.id}" data-id="${m.id}" class="nav-item ${m.kind === 'metric' ? '' : 'dim'}">
            <span class="nav-name">${m.name}</span>
            ${m.kind === 'metric' ? '' : '<em class="nav-badge">待接入</em>'}
          </a>`).join('')}`).join('')}
    </div>
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
  if (seg[0] === 'report') return { name: 'report' };
  if (seg[0] === 'upload') return { name: 'upload' };
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

function render() {
  const r = parseRoute();
  const view = state.view;
  disposeAll();
  view.innerHTML = '';
  const host = document.createElement('div');
  host.className = 'page';
  view.appendChild(host);
  const ctx = { catalog: state.catalog, data: state.data, date: state.date, reload: refresh };

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
      if (impl && hit.module.kind === 'metric') impl.render(host, state.data, ctx);
      else modulePlaceholder(host, hit);
    } else if (r.name === 'prof') {
      const prof = state.catalog.professionals.find((p) => p.id === r.id);
      if (!prof) throw new Error('板块不存在');
      title = prof.name;
      crumb = `<b>${prof.name}</b>`;
      browse(host, { prof });
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
    } else {
      home.render(host, ctx);
    }
  } catch (err) {
    console.error(err);
    host.innerHTML = `<div class="card"><div class="empty"><b>页面渲染出错</b>${String(err.message || err)}</div></div>`;
  }
  document.getElementById('crumbs').innerHTML = crumb;
  document.title = `${title} · 经营驾驶舱`;
  document.querySelectorAll('.nav a').forEach((a) => {
    a.classList.toggle('on', a.dataset.id === r.id || (r.name === 'home' && a.dataset.id === 'home'));
  });
  host.querySelectorAll('[data-go]').forEach((el) => {
    if (!el.onclick) el.onclick = () => { location.hash = el.dataset.go; };
  });
}

async function refresh(date = state.date) {
  await loadData(date);
  render();
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
  document.getElementById('btnLatest').addEventListener('click', async () => {
    document.getElementById('datePick').value = state.catalog.latest || '';
    await refresh(null);
    toast('已回到最新数据');
  });
  document.getElementById('btnRefresh').addEventListener('click', async (e) => {
    e.currentTarget.style.transform = 'rotate(360deg)';
    setTimeout(() => { e.currentTarget.style.transform = ''; }, 420);
    await refresh();
    toast('数据已刷新');
  });

  window.addEventListener('hashchange', render);
  render();
}

boot();
