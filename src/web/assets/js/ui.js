/* ui.js —— 格式化、图标、提示、抽屉、数字动画 */

export const fmt = {
  n(v, d = 0) {
    if (v === null || v === undefined || Number.isNaN(v)) return '—';
    return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: d, maximumFractionDigits: d });
  },
  pct(v, d = 1) {
    if (v === null || v === undefined || Number.isNaN(v)) return '—';
    return `${(Number(v) * 100).toFixed(d)}%`;
  },
  /** 已是百分数的值（18.3 → 18.3%） */
  p(v, d = 1) {
    if (v === null || v === undefined || Number.isNaN(v)) return '—';
    return `${Number(v).toFixed(d)}%`;
  },
  sign(v, d = 2, unit = '') {
    if (v === null || v === undefined) return '—';
    const s = Number(v) > 0 ? '+' : '';
    return `${s}${fmt.n(v, d)}${unit}`;
  },
  money(v) {
    if (v === null || v === undefined) return '—';
    if (Math.abs(v) >= 10000) return `${fmt.n(v / 10000, 2)} 亿`;
    return `${fmt.n(v, 0)} 万`;
  },
  date(iso) {
    if (!iso) return '—';
    const [y, m, d] = iso.split('-');
    return `${Number(m)}月${Number(d)}日`;
  },
  short(iso) {
    if (!iso) return '—';
    const p = iso.split('-');
    return `${p[1]}/${p[2]}`;
  },
};

export const cls = (v, invert = false) => {
  if (v === null || v === undefined || Math.abs(v) < 1e-9) return 'flat';
  return (v > 0) !== invert ? 'up' : 'down';
};

export const deltaHTML = (v, text, invert = false) =>
  `<span class="delta ${cls(v, invert)}">${text}</span>`;

const ICONS = {
  overview: '<path d="M4 13h6V4H4v9Zm0 7h6v-5H4v5Zm10 0h6V11h-6v9Zm0-16v5h6V4h-6Z"/>',
  deposit: '<path d="M4 20V9m5 11V4m5 16v-7m5 7V7" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
  online: '<path d="M3 17l5-5 4 3 7-8" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><circle cx="19" cy="7" r="2.4" fill="currentColor"/>',
  wallet: '<rect x="3" y="6" width="18" height="13" rx="3" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M3 10h18" stroke="currentColor" stroke-width="1.8"/><circle cx="17" cy="14.5" r="1.4" fill="currentColor"/>',
  salary: '<path d="M12 3v18M8 7h8a3 3 0 0 1 0 6H8a3 3 0 0 0 0 6h8" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
  community: '<circle cx="9" cy="8" r="3.2" fill="none" stroke="currentColor" stroke-width="1.7"/><circle cx="17" cy="9.5" r="2.4" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M3.5 19c.8-3 3-4.6 5.5-4.6s4.7 1.6 5.5 4.6M14.5 18.6c.5-2 1.9-3.2 3.6-3.2 1 0 1.9.4 2.4 1" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
  import: '<path d="M12 16V4m0 0L8 8m4-4 4 4M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
  arrow: '<path d="M5 12h14m0 0-6-6m6 6-6 6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
  up: '<path d="M12 19V5m0 0-6 6m6-6 6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
  down: '<path d="M12 5v14m0 0 6-6m-6 6-6-6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
  file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M14 3v5h5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>',
  spark: '<path d="M12 3v4m0 10v4M3 12h4m10 0h4M5.6 5.6l2.8 2.8m7.2 7.2 2.8 2.8m0-12.8-2.8 2.8m-7.2 7.2-2.8 2.8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
  expand: '<path d="M9 4H4v5M15 4h5v5M9 20H4v-5M15 20h5v-5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
};

export const icon = (name, size = 17) =>
  `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="currentColor" aria-hidden="true">${ICONS[name] || ''}</svg>`;

let toastTimer;
export function toast(msg, type = '') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = `toast on ${type}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.className = 'toast'; }, 2600);
}

/** 数字滚动（首屏用，克制：700ms） */
export function countUp(el, value, { decimals = 0, suffix = '', prefix = '' } = {}) {
  if (!el) return;
  const from = 0, to = Number(value);
  if (!Number.isFinite(to)) { el.textContent = '—'; return; }
  // 无障碍：用户要求减少动效时直接给终值
  if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    el.textContent = `${prefix}${fmt.n(to, decimals)}${suffix}`;
    return;
  }
  const t0 = performance.now(), dur = 700;
  const tick = (t) => {
    const k = Math.min(1, (t - t0) / dur);
    const e = 1 - Math.pow(1 - k, 3);
    el.textContent = `${prefix}${fmt.n(from + (to - from) * e, decimals)}${suffix}`;
    if (k < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

/** 抽屉 */
export function drawer(title, html, sub = '') {
  let mask = document.querySelector('.drawer-mask');
  let box = document.querySelector('.drawer');
  if (!mask) {
    mask = document.createElement('div');
    mask.className = 'drawer-mask';
    document.body.appendChild(mask);
    box = document.createElement('div');
    box.className = 'drawer';
    box.innerHTML = '<div class="drawer-head"><h3></h3><span class="x">✕</span></div><div class="drawer-body"></div>';
    document.body.appendChild(box);
    const close = () => { mask.classList.remove('on'); box.classList.remove('on'); };
    mask.addEventListener('click', close);
    box.querySelector('.x').addEventListener('click', close);
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') close(); });
  }
  box.querySelector('h3').textContent = title;
  box.querySelector('.drawer-body').innerHTML = (sub ? `<p style="margin:-4px 0 12px;color:var(--ink-3);font-size:12px">${sub}</p>` : '') + html;
  requestAnimationFrame(() => { mask.classList.add('on'); box.classList.add('on'); });
}

export const empty = (text = '暂无数据', hint = '导入该条线的源表后即可查看') =>
  `<div class="empty"><b>${text}</b>${hint}</div>`;

/** 表格渲染 + 排序（列配置声明式，便于以后加列） */
export function table(columns, rows, { sortBy = null, limit = null, onRow = null } = {}) {
  const state = { key: sortBy, dir: -1 };
  const wrap = document.createElement('div');
  wrap.className = 'tbl-wrap';
  const renderRows = () => {
    let data = [...rows];
    if (state.key) {
      const col = columns.find((c) => c.key === state.key);
      data.sort((a, b) => {
        const va = col.value ? col.value(a) : a[state.key];
        const vb = col.value ? col.value(b) : b[state.key];
        if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * state.dir;
        return String(va).localeCompare(String(vb), 'zh') * state.dir;
      });
    }
    if (limit) data = data.slice(0, limit);
    const maxByKey = {};
    columns.forEach((c) => {
      if (c.bar) maxByKey[c.key] = Math.max(...rows.map((r) => Number(c.value ? c.value(r) : r[c.key]) || 0), 1);
    });
    wrap.innerHTML = `<table class="tbl"><thead><tr>${columns.map((c) =>
      `<th class="${c.sortable === false ? '' : 'sortable'}" data-k="${c.key}">${c.title}${c.unit ? `<span style="color:var(--ink-4)"> (${c.unit})</span>` : ''}</th>`).join('')}</tr></thead>
      <tbody>${data.map((r, i) => `<tr data-i="${i}">${columns.map((c, ci) => {
        const raw = c.value ? c.value(r) : r[c.key];
        const text = c.render ? c.render(raw, r) : (typeof raw === 'number' ? fmt.n(raw, c.decimals ?? 0) : (raw ?? '—'));
        if (ci === 0 && c.rank !== false) {
          return `<td class="strong"><span class="rank-badge ${i < 3 ? 'top' : ''}">${i + 1}</span> ${text}</td>`;
        }
        if (c.bar) {
          const pct = Math.min(100, (Number(raw) / maxByKey[c.key]) * 100);
          return `<td class="bar-cell ${c.strong ? 'strong' : ''}"><i class="bar" style="width:${pct}%;background:${c.barColor || 'var(--blue-soft)'}"></i><span>${text}</span></td>`;
        }
        return `<td class="${c.strong ? 'strong' : ''} ${c.cls || ''}">${text}</td>`;
      }).join('')}</tr>`).join('')}</tbody></table>`;
    wrap.querySelectorAll('th.sortable').forEach((th) => {
      th.onclick = () => {
        const k = th.dataset.k;
        state.dir = state.key === k ? -state.dir : -1;
        state.key = k;
        renderRows();
      };
    });
    if (onRow) wrap.querySelectorAll('tbody tr').forEach((tr, i) => {
      tr.style.cursor = 'pointer';
      tr.onclick = () => onRow(data[i]);
    });
  };
  renderRows();
  return wrap;
}


/* ------------------------------------------------------------------ 全屏大表
   行数多时自动分栏（2~3 列），尽量在一屏内看全，不用内部滚动 */
export function bigTable({ title, subtitle = '', columns, rows, unit = '', search = true }) {
  const old = document.querySelector('.table-modal');
  if (old) old.remove();

  const modal = document.createElement('div');
  modal.className = 'table-modal';
  modal.innerHTML = `
    <div class="tm-panel">
      <div class="tm-head">
        <div>
          <h3>${title}</h3>
          <p>${subtitle} <span class="chip" style="margin-left:8px">共 ${rows.length} 条</span></p>
        </div>
        <div class="tm-tools">
          ${search ? `<input id="tmSearch" placeholder="搜索…" autocomplete="off">` : ''}
          <button class="tm-close" title="关闭（Esc）">✕</button>
        </div>
      </div>
      <div class="tm-body" id="tmBody"></div>
    </div>`;
  document.body.appendChild(modal);
  requestAnimationFrame(() => modal.classList.add('on'));

  const close = () => { modal.classList.remove('on'); setTimeout(() => modal.remove(), 220); };
  modal.querySelector('.tm-close').onclick = close;
  modal.onclick = (e) => { if (e.target === modal) close(); };
  document.addEventListener('keydown', function esc(e) {
    if (e.key === 'Escape') { close(); document.removeEventListener('keydown', esc); }
  });

  let state = { key: null, dir: -1, q: '' };
  const body = modal.querySelector('#tmBody');

  function paint() {
    let data = rows.filter((r) => !state.q ||
      Object.values(r).some((v) => String(v ?? '').toLowerCase().includes(state.q.toLowerCase())));
    if (state.key) {
      const col = columns.find((c) => c.key === state.key);
      data = [...data].sort((a, b) => {
        const va = col?.value ? col.value(a) : a[state.key];
        const vb = col?.value ? col.value(b) : b[state.key];
        if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * state.dir;
        return String(va ?? '').localeCompare(String(vb ?? ''), 'zh') * state.dir;
      });
    }
    // 列数多的表少分栏，避免挤压
    const per = data.length <= 14 ? 1 : (columns.length > 7 ? 2 : data.length > 34 ? 3 : 2);
    const chunk = Math.ceil(data.length / per) || 1;
    const groups = Array.from({ length: per }, (_, i) => data.slice(i * chunk, (i + 1) * chunk));
    body.dataset.cols = String(groups.length);
    let offset = 0;
    body.innerHTML = groups.map((g) => {
      const start = offset; offset += g.length;
      return `<div class="tm-col">
        <table class="tbl compact">
          <thead><tr>${columns.map((c) => `<th class="${c.sortable === false ? '' : 'sortable'}" data-k="${c.key}">${c.title}${c.unit ? ` <span style="color:var(--ink-4)">(${c.unit})</span>` : ''}</th>`).join('')}</tr></thead>
          <tbody>${g.map((r, i) => `<tr>${columns.map((c, ci) => {
            const raw = c.value ? c.value(r) : r[c.key];
            const text = c.render ? c.render(raw, r) : (typeof raw === 'number' ? fmt.n(raw, c.decimals ?? 0) : (raw ?? '—'));
            if (ci === 0) return `<td class="strong"><span class="rank-badge">${start + i + 1}</span> ${text}</td>`;
            return `<td>${text}</td>`;
          }).join('')}</tr>`).join('')}</tbody>
        </table></div>`;
    }).join('');
    body.querySelectorAll('th.sortable').forEach((th) => {
      th.onclick = () => {
        const k = th.dataset.k;
        state.dir = state.key === k ? -state.dir : -1;
        state.key = k; paint();
      };
    });
    if (!data.length) body.innerHTML = '<div class="empty"><b>没有匹配的记录</b>换个关键词试试</div>';
  }

  const si = modal.querySelector('#tmSearch');
  if (si) si.addEventListener('input', () => { state.q = si.value.trim(); paint(); });
  paint();
  return modal;
}
