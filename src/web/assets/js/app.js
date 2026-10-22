/* app.js —— 壳：数据加载、导航、路由、刷新
   页面模块契约：{ id, title, nav, icon, tag?, order, render(view, data, ctx) }
   新增一个条线 = 写 pages/xxx.js + 在 PAGES 里登记（其余自动） */
import { icon, toast } from './ui.js';
import { disposeAll } from './charts.js';

import overview from './pages/overview.js';
import deposit from './pages/deposit.js';
import online from './pages/online.js';
import wallet from './pages/wallet.js';
import salary from './pages/salary.js';
import community from './pages/community.js';
import importer from './pages/import.js';

const PAGES = [overview, deposit, online, wallet, salary, community, importer];
const byId = Object.fromEntries(PAGES.map((p) => [p.id, p]));

const store = { data: null, state: null };
const view = document.getElementById('view');

/* ---------------------------------------------------------------- 数据 */
async function load(showToast = false) {
  const [all, state] = await Promise.all([
    fetch('/api/all', { cache: 'no-store' }).then((r) => r.json()),
    fetch('/api/state', { cache: 'no-store' }).then((r) => r.json()).catch(() => null),
  ]);
  store.data = all;
  store.state = state;
  if (showToast) toast('数据已刷新');
  paintChrome();
  return all;
}

function latestDate() {
  const lines = store.data?.overview?.lines || {};
  const ds = Object.values(lines).map((l) => l.as_of).filter(Boolean).sort();
  return ds.length ? ds[ds.length - 1] : null;
}

function paintChrome() {
  const asof = document.getElementById('asof');
  const d = latestDate();
  asof.querySelector('span').textContent = d ? `数据截至 ${d}` : '暂无数据';
  const st = document.getElementById('sideStatus');
  const ok = Object.values(store.data?.overview?.lines || {}).filter((l) => l.ok).length;
  st.textContent = `${ok}/5 条线已就绪 · ${(store.data?.generated_at || '').slice(11, 16)}`;
}

/* ---------------------------------------------------------------- 导航 */
function renderNav() {
  const nav = document.getElementById('nav');
  const main = PAGES.filter((p) => p.nav);
  const tool = PAGES.filter((p) => !p.nav);
  const item = (p) => `<a href="#/${p.id}" data-id="${p.id}">
      ${icon(p.icon)}
      <span>${p.nav || p.title}</span>
      ${p.tag ? `<em class="tag ${p.tag === '重点' ? 'hot' : ''}" style="font-style:normal">${p.tag}</em>` : ''}
    </a>`;
  nav.innerHTML = `
    <div class="nav-label">经营条线</div>
    ${main.map(item).join('')}
    ${tool.length ? `<div class="nav-label">数据</div>${tool.map(item).join('')}` : ''}`;
  nav.querySelectorAll('a').forEach((a) => {
    a.addEventListener('click', () => {
      document.querySelectorAll('.nav a').forEach((x) => x.classList.remove('on'));
      a.classList.add('on');
    });
  });
}

/* ---------------------------------------------------------------- 路由 */
function currentId() {
  const m = location.hash.match(/^#\/([\w-]+)/);
  return m ? m[1] : 'overview';
}

function render() {
  const id = currentId();
  const page = byId[id] || byId.overview;
  disposeAll();
  view.innerHTML = '';
  const host = document.createElement('div');
  host.className = 'page';
  view.appendChild(host);
  document.querySelectorAll('.nav a').forEach((a) => a.classList.toggle('on', a.dataset.id === page.id));
  document.getElementById('crumbs').innerHTML = page.id === 'overview'
    ? '<b>总览</b><span class="sep">·</span><span>全行五条线</span>'
    : `<a href="#/overview" style="color:var(--ink-3)">总览</a><span class="sep">/</span><b>${page.title}</b>`;
  document.title = `${page.title} · 个人金融经营驾驶舱`;
  try {
    page.render(host, store.data, { store, reload: () => load(true), state: store.state });
  } catch (err) {
    console.error(err);
    host.innerHTML = `<div class="card"><div class="empty"><b>页面渲染出错</b>${String(err.message || err)}</div>
      <pre style="font-size:11px;color:#a80d26;white-space:pre-wrap;text-align:left;max-width:900px;margin:10px auto">${String(err.stack || '').split('\n').slice(0, 6).join('\n')}</pre></div>`;
  }
}

/* ---------------------------------------------------------------- 启动 */
async function boot() {
  renderNav();
  window.addEventListener('hashchange', render);
  document.getElementById('btnRefresh').addEventListener('click', async (e) => {
    e.currentTarget.style.transform = 'rotate(360deg)';
    setTimeout(() => { e.currentTarget.style.transform = ''; }, 420);
    await load(true);
    render();
  });
  document.querySelectorAll('[data-route]').forEach((b) => {
    b.addEventListener('click', () => { location.hash = b.dataset.route; });
  });
  try {
    await load();
    const bootEl = document.getElementById('boot');
    bootEl.classList.add('gone');
    setTimeout(() => bootEl.remove(), 420);
  } catch (err) {
    document.getElementById('boot').innerHTML =
      `<div class="empty"><b>无法连接服务</b>请通过 <code>python server/app.py</code> 启动后访问</div>`;
    console.error(err);
    return;
  }
  render();
}

boot();
