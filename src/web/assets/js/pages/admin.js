/* pages/admin.js —— 数据管理（管理员专用）
   路由 #/admin/data

   三件事，按「先看、再动手」的顺序排：
     1. 一期一格：每个模块下把「有数据的日期」排成格子，格子上直接标出
        这期被导入过几次、留档了几个原件 —— 一眼看出"这期是新是旧、来没来过"。
     2. 点开一期：弹窗里写清它的全部来历（哪几次导入算的、用的哪些文件、
        文件还在不在），原件能**预览**（直接在网页里看表格）和**下载**。
     3. 三种动作，风险从低到高：恢复 ← 删除（软，可恢复）← 彻底删除（不可恢复）。

   「删除」只打标记，库里的数据和台账都还在；
   「彻底删除」才是真删，必须先把这期删过、再原样输入日期才肯执行。 */
import { fmt, toast, icon, empty } from '../ui.js';
import { auth, authFetch } from '../auth.js';

const LINK_TXT = { exact: '直接关联', archive: '按归档目录', date: '按数据日期', near: '按日期就近' };
const LINK_CLS = { exact: 'green', archive: '', date: 'amber', near: 'amber' };

/** 字节数 → 人看的大小 */
const bytes = (n) => {
  const v = Number(n) || 0;
  if (v >= 1048576) return `${(v / 1048576).toFixed(1)} MB`;
  if (v >= 1024) return `${Math.round(v / 1024)} KB`;
  return `${v} B`;
};

const esc = (v) => String(v == null ? '' : v)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

export default {
  id: 'admin',
  title: '数据管理',

  render(view, _data, ctx) {
    if (!auth.admin) {
      view.innerHTML = `<div class="card">${empty('需要管理员权限', '用管理员口令验证后从右上角身份菜单进入')}</div>`;
      return;
    }
    let ALL = [];              // 后端返回的 lines
    let DB = null;
    let q = '';                // 搜索词
    let onlyDeleted = false;

    view.innerHTML = `
      <div class="page-head">
        <div><h1>数据管理</h1>
          <p>按模块 × 期查看来历 · 原件可预览可下载 · 删除可恢复</p></div>
        <div class="spacer"></div>
        <button class="btn" id="admReload">${icon('arrow', 14)} 刷新</button>
      </div>
      <div id="admSummary"></div>
      <div class="card adm-filter">
        <input id="admQ" placeholder="搜模块名或日期（如 薪管家 / 10-2）" autocomplete="off">
        <label class="adm-tgl"><input type="checkbox" id="admOnlyDel"> 只看已删除</label>
        <span class="adm-filter-tip">点任意一格看这一期的导入记录与原始文件</span>
      </div>
      <div id="admBody"><div class="card"><div class="empty"><b>载入中…</b></div></div></div>`;

    const body = view.querySelector('#admBody');
    const summary = view.querySelector('#admSummary');

    // ------------------------------------------------------------ 载入
    const load = async () => {
      body.innerHTML = '<div class="card"><div class="empty"><b>载入中…</b></div></div>';
      try {
        const res = await authFetch('/api/admin/data', { cache: 'no-store' });
        const d = await res.json();
        if (!d.ok) throw new Error(d.error || '读取失败');
        ALL = d.lines || [];
        DB = d.db || null;
        paintSummary();
        paint();
      } catch (err) {
        if (err.auth) return;
        body.innerHTML = `<div class="card"><div class="empty"><b>读取失败</b>${esc(err.message)}</div></div>`;
      }
    };

    const paintSummary = () => {
      if (!DB) { summary.innerHTML = ''; return; }
      const nDel = ALL.reduce((s, l) => s + (l.deleted || []).length, 0);
      summary.innerHTML = `
        <div class="card adm-sum">
          <div><b>${DB.snapshots}</b><span>在用数据期</span></div>
          <div class="${nDel ? 'warn' : ''}"><b>${nDel}</b><span>已删除（可恢复）</span></div>
          <div><b>${DB.imports}</b><span>导入批次</span></div>
          <div><b>${DB.source_files}</b><span>留档原件</span></div>
          <div><b>${DB.size_mb}</b><span>库体积 MB</span></div>
          <div class="adm-sum-path"><span>数据目录</span><code>${esc(DB.db || '')}</code></div>
        </div>`;
    };

    // ------------------------------------------------------------ 渲染
    const md = (asOf) => asOf.slice(5).replace('-', '/');       // 2026-10-19 → 10/19

    const hit = (l) => {
      const kw = q.trim();
      if (onlyDeleted && !(l.deleted || []).length) return null;
      if (!kw) return l;
      const inName = (l.label || '').includes(kw) || (l.line || '').includes(kw);
      const periods = (l.periods || []).filter((p) => String(p.as_of).includes(kw));
      const dels = (l.deleted || []).filter((p) => String(p.as_of).includes(kw));
      if (!inName && !periods.length && !dels.length) return null;
      return { ...l, periods: inName ? l.periods : periods, deleted: inName ? l.deleted : dels };
    };

    const cell = (l, p) => {
      const del = !!p.deleted_at;
      const bits = [];
      if (p.batches) bits.push(`<i class="adm-b b-imp" title="这期被导入过 ${p.batches} 次">${p.batches}</i>`);
      if (p.files) bits.push(`<i class="adm-b b-file" title="留档 ${p.files} 个原件">${p.files}</i>`);
      if (p.partial) bits.push('<i class="adm-b b-partial" title="历史回填的近似快照">估</i>');
      return `<button class="adm-cell${del ? ' del' : ''}${p.as_of === l.latest ? ' latest' : ''}"
        data-line="${l.line}" data-asof="${p.as_of}"
        title="${p.as_of}${del ? '（已删除）' : ''}${p.batches ? ` · 导入 ${p.batches} 次` : ''}">
        <span class="adm-cell-d">${md(p.as_of)}</span>
        ${bits.length ? `<span class="adm-cell-b">${bits.join('')}</span>` : ''}
      </button>`;
    };

    const moduleCard = (l) => {
      const pub = (l.periods || []).filter((p) => !p.deleted_at);
      const del = (l.periods || []).filter((p) => p.deleted_at);
      const cells = pub.length ? pub.map((p) => cell(l, p)).join('')
        : '<span class="adm-none">暂无数据</span>';
      const delRow = del.length ? `
        <div class="adm-del-row">
          <span class="adm-del-tag">已删 ${del.length} 期</span>
          ${del.map((p) => cell(l, p)).join('')}
        </div>` : '';
      return `
        <div class="adm-mod${l.internal ? ' internal' : ''}">
          <div class="adm-mod-head">
            <b>${l.label}</b>
            <span class="chip">${pub.length} 期</span>
            ${l.latest ? `<span class="chip">最新 ${fmt.date(l.latest)}</span>` : ''}
            ${l.internal ? '<span class="chip red">原始数据</span>' : ''}
            <span class="adm-hint" title="${esc(l.hint || '')}">${esc(l.hint || '')}</span>
          </div>
          <div class="adm-cells">${cells}</div>
          ${delRow}
        </div>`;
    };

    const paint = () => {
      const list = ALL.map(hit).filter(Boolean);
      if (!list.length) {
        body.innerHTML = `<div class="card">${empty(q || onlyDeleted ? '没有匹配的数据期' : '还没有任何数据',
          q || onlyDeleted ? '换个关键词，或取消「只看已删除」' : '到「导入数据」里导一次源表')}</div>`;
        return;
      }
      // 按板块分组，组内保持后端给的顺序（该顺序按常用程度排）
      const groups = [];
      const at = {};
      for (const l of list) {
        const g = l.group || '其他';
        if (!(g in at)) { at[g] = groups.length; groups.push({ name: g, items: [] }); }
        groups[at[g]].items.push(l);
      }
      body.innerHTML = groups.map((g) => `
        <div class="adm-group">
          <div class="adm-group-h">${g.name}<span>${g.items.length} 个模块</span></div>
          <div class="card">${g.items.map(moduleCard).join('')}</div>
        </div>`).join('');
      body.querySelectorAll('.adm-cell').forEach((b) => {
        b.onclick = () => openPeriod(b.dataset.line, b.dataset.asof);
      });
    };

    // ------------------------------------------------------------ 弹窗骨架
    let modal = null;
    const closeModal = () => { if (modal) { modal.remove(); modal = null; } };
    const openModal = (html, wide) => {
      closeModal();
      modal = document.createElement('div');
      modal.className = 'adm-modal' + (wide ? ' wide' : '');
      modal.innerHTML = `<div class="adm-m-card">${html}</div>`;
      document.body.appendChild(modal);
      modal.onclick = (e) => { if (e.target === modal) closeModal(); };
      document.addEventListener('keydown', function escKey(e) {
        if (e.key === 'Escape') { closeModal(); document.removeEventListener('keydown', escKey); }
      });
      return modal.querySelector('.adm-m-card');
    };

    // ------------------------------------------------------------ 一期详情
    const openPeriod = async (line, asOf) => {
      const card = openModal('<div class="adm-m-body"><div class="empty"><b>载入中…</b></div></div>', true);
      let d;
      try {
        const res = await authFetch(
          `/api/admin/period?line=${encodeURIComponent(line)}&as_of=${encodeURIComponent(asOf)}`,
          { cache: 'no-store' });
        d = await res.json();
        if (!d.ok) throw new Error(d.error || '读取失败');
      } catch (err) {
        if (err.auth) { closeModal(); return; }
        card.innerHTML = `<div class="adm-m-body"><div class="empty"><b>读取失败</b>${esc(err.message)}</div></div>`;
        return;
      }
      paintPeriod(card, d);
    };

    const paintPeriod = (card, d) => {
      const s = d.snapshot || {};
      const del = !!s.deleted_at;
      const files = d.files || [];
      const batches = d.batches || [];

      const fileRow = (f, i) => `
        <tr>
          <td class="adm-f-name" title="${esc(f.path || '')}">${esc(f.name)}${
            f.times > 1 ? `<i class="adm-x">×${f.times}</i>` : ''}${
            f.dup ? '<i class="adm-x dup" title="同名但内容不同：这是另一份表">同名不同内容</i>' : ''}</td>
          <td class="adm-f-sz">${f.bytes ? bytes(f.bytes) : '—'}</td>
          <td class="adm-f-tm">${f.created_at ? String(f.created_at).replace('T', ' ').slice(0, 16) : '—'}</td>
          <td class="adm-f-ops">
            ${f.exists === false
              ? '<span class="adm-f-miss">文件已不在磁盘</span>'
              : `<button class="adm-mini" data-prev="${i}">预览</button>
                 <button class="adm-mini" data-dl="${i}">下载</button>`}
          </td>
        </tr>`;

      const batchRow = (b) => `
        <tr>
          <td>${(b.ts || '').slice(5, 16)}</td>
          <td><span class="chip ${LINK_CLS[b.linked] || ''}" style="font-size:10px">${
            LINK_TXT[b.linked] || b.linked}</span></td>
          <td>${b.data_date || '—'}</td>
          <td class="adm-b-files" title="${esc((b.files || []).join('、'))}">${
            esc((b.files || []).join('、')) || '—'}</td>
          <td>${b.ok ? '<span class="chip green">成功</span>' : '<span class="chip red">失败</span>'}</td>
        </tr>`;

      card.innerHTML = `
        <div class="adm-m-head">
          <div>
            <h3>${d.label} · ${fmt.date(d.as_of)}</h3>
            <p>${d.as_of} · ${del ? '<span class="chip red">已删除</span>' : '<span class="chip green">在用</span>'}
              ${d.prev ? `<button class="adm-mini" data-jump="${d.prev}">← ${d.prev}</button>` : ''}
              ${d.next ? `<button class="adm-mini" data-jump="${d.next}">${d.next} →</button>` : ''}</p>
          </div>
          <button class="adm-m-x" title="关闭（Esc）">✕</button>
        </div>
        <div class="adm-m-body">
          ${d.warning ? `<p class="adm-note adm-warn">${esc(d.warning.text)}</p>` : ''}

          <div class="adm-sec">
            <h4>这一期的数据</h4>
            <div class="adm-kv-grid">
              <div><span>实体现数</span><b>${s.rows == null ? '—' : s.rows}</b></div>
              <div><span>首次写入</span><b>${String(s.created_at || '').slice(0, 16) || '—'}</b></div>
              <div><span>最后更新</span><b>${String(s.updated_at || '').slice(0, 16) || '—'}</b></div>
              <div><span>快照大小</span><b>${s.payload_bytes ? bytes(s.payload_bytes) : '—'}</b></div>
              <div><span>导入批次</span><b>${batches.length}</b></div>
              <div><span>留档原件</span><b>${d.file_count} 种 · 共留 ${d.occurrences} 次</b></div>
            </div>
            ${del ? `<p class="adm-note">删除于 <b>${s.deleted_at}</b>。数据还在库里，
              点下面的「恢复这一期」就能回到页面和通报里。</p>` : ''}
          </div>

          <div class="adm-sec">
            <h4>原始文件 <span class="adm-sec-hint">同一张表导入多次只算一行，×N 是留档次数</span></h4>
            ${files.length ? `
              <div class="adm-f-wrap"><table class="tbl adm-f-tbl">
                <thead><tr><th>文件名</th><th style="width:80px">大小</th>
                  <th style="width:110px">最近留档</th><th style="width:112px">操作</th></tr></thead>
                <tbody>${files.map(fileRow).join('')}</tbody>
              </table></div>`
              : '<p class="adm-note">这一期没有留档原件。多半是早期导入的 —— 那时还没写原件台账。</p>'}
          </div>

          <div class="adm-sec">
            <h4>导入记录 <span class="adm-sec-hint">时间 / 怎么跟这一期对上的 / 用的文件</span></h4>
            ${batches.length ? `
              <div class="adm-f-wrap" style="max-height:210px"><table class="tbl adm-f-tbl">
                <thead><tr><th style="width:92px">时间</th><th style="width:88px">关联</th>
                  <th style="width:92px">数据日期</th><th>文件</th><th style="width:64px">结果</th></tr></thead>
                <tbody>${batches.map(batchRow).join('')}</tbody>
              </table></div>`
              : '<p class="adm-note">没有对应的导入记录（很早以前用脚本灌的，或从旧库搬来的）。</p>'}
          </div>
        </div>
        <div class="adm-m-acts">
          ${del ? '<button class="btn btn-primary" data-act="restore">恢复这一期</button>'
                : '<button class="btn" data-act="delete">删除（可恢复）</button>'}
          <button class="btn adm-danger" data-act="purge" ${del ? ''
            : 'disabled title="先删除这一期，再来这里彻底删除"'}>彻底删除…</button>
        </div>`;

      card.querySelector('.adm-m-x').onclick = closeModal;
      card.querySelectorAll('[data-jump]').forEach((b) => {
        b.onclick = () => openPeriod(d.line, b.dataset.jump);
      });
      card.querySelectorAll('[data-prev]').forEach((b) => {
        b.onclick = () => openPreview(files[+b.dataset.prev]);
      });
      card.querySelectorAll('[data-dl]').forEach((b) => {
        b.onclick = () => downloadFile(files[+b.dataset.dl], b);
      });
      const act = card.querySelector('[data-act="restore"]');
      if (act) act.onclick = () => doRestore(d.line, d.as_of);
      const delBtn = card.querySelector('[data-act="delete"]');
      if (delBtn) delBtn.onclick = () => askDelete(d);
      const purgeBtn = card.querySelector('[data-act="purge"]');
      if (purgeBtn && del) purgeBtn.onclick = () => askPurge(d);
    };

    // ------------------------------------------------------------ 原件预览
    const srcURL = (f, kind) => (f.id != null
      ? `/api/source/${f.id}${kind}`
      : `/api/source/by-path${kind}?path=${encodeURIComponent(f.path)}&name=${encodeURIComponent(f.name)}`);

    const openPreview = async (f) => {
      const card = openModal(`
        <div class="adm-m-head">
          <div><h3>${esc(f.name)}</h3>
            <p>${f.bytes ? bytes(f.bytes) : ''}${f.times > 1 ? ` · 留档 ${f.times} 次` : ''}</p></div>
          <button class="adm-m-x" title="关闭（Esc）">✕</button>
        </div>
        <div class="adm-m-body"><div class="empty"><b>读取中…</b></div></div>`, true);
      card.querySelector('.adm-m-x').onclick = closeModal;

      let d;
      try {
        const res = await authFetch(srcURL(f, '/preview'), { cache: 'no-store' });
        d = await res.json();
        if (!d.ok) throw new Error(d.error || '读取失败');
      } catch (err) {
        if (err.auth) { closeModal(); return; }
        card.querySelector('.adm-m-body').innerHTML =
          `<div class="empty"><b>预览失败</b>${esc(err.message)}</div>`;
        return;
      }
      paintPreview(card, d, f);
    };

    const paintPreview = (card, d, f) => {
      const body = card.querySelector('.adm-m-body');
      const tabs = (d.sheets || []).length > 1 ? `
        <div class="adm-sheets">
          ${d.sheets.map((s) => `<button class="adm-sheet${s === d.sheet ? ' on' : ''}"
            data-sheet="${esc(s)}">${esc(s)}</button>`).join('')}
        </div>` : '';
      const total = d.total_rows == null ? '行数未统计' : `共 ${d.total_rows} 行`;
      const cols = d.total_cols == null ? '?' : d.total_cols;
      const rowCut = d.total_rows == null || d.shown_rows < d.total_rows;
      const colCut = Number(cols) > d.shown_cols;
      const cut = [];
      if (rowCut) cut.push(`前 ${d.shown_rows} 行`);
      if (colCut) cut.push(`前 ${d.shown_cols} 列`);
      body.innerHTML = `
        ${tabs}
        <div class="adm-prev-meta">
          ${total} · ${cols} 列
          ${cut.length ? `<b>（只显示${cut.join(' / ')}）</b>` : ''}
          ${d.kind === 'text' ? ` · 文本编码 ${esc(d.encoding || '—')}` : ''}
          · 原件原样内容，仅供核对，不参与计算
        </div>
        <div class="adm-prev-wrap">
          <table class="adm-prev"><tbody>${(d.rows || []).map((r, i) => `<tr class="${i === 0 ? 'head' : ''}">
            <td class="adm-prev-n">${i + 1}</td>
            ${r.map((v) => `<td>${esc(v)}</td>`).join('')}</tr>`).join('')}</tbody></table>
        </div>
        <div class="adm-m-acts">
          <button class="btn" data-x>关闭</button>
          <button class="btn btn-primary" data-dl>下载原件</button>
        </div>`;
      body.querySelector('[data-x]').onclick = closeModal;
      body.querySelector('[data-dl]').onclick = (e) => downloadFile(f, e.currentTarget);
      body.querySelectorAll('[data-sheet]').forEach((b) => {
        b.onclick = async () => {
          body.innerHTML = '<div class="empty"><b>读取中…</b></div>';
          try {
            const r = await authFetch(
              `${srcURL(f, '/preview')}${srcURL(f, '/preview').includes('?') ? '&' : '?'}`
              + `sheet=${encodeURIComponent(b.dataset.sheet)}`, { cache: 'no-store' }).then((x) => x.json());
            if (!r.ok) throw new Error(r.error || '读取失败');
            paintPreview(card, r, f);
          } catch (err) {
            if (err.auth) { closeModal(); return; }
            toast(err.message, 'err');
            paintPreview(card, d, f);
          }
        };
      });
    };

    const downloadFile = async (f, btn) => {
      const old = btn.textContent;
      btn.disabled = true;
      btn.textContent = '准备中…';
      try {
        const res = await authFetch(srcURL(f, ''));
        if (!res.ok) {
          const j = await res.json().catch(() => ({}));
          throw new Error(j.error || `下载失败（${res.status}）`);
        }
        const blob = await res.blob();
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = f.name;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 4000);
      } catch (err) {
        if (err.auth) return;
        toast(err.message || '下载失败', 'err');
      } finally {
        btn.disabled = false;
        btn.textContent = old;
      }
    };

    // ------------------------------------------------------------ 三种动作
    const refreshAll = async () => {
      await ctx.reloadData?.();
      await load();
    };

    const doRestore = async (line, asOf) => {
      try {
        const res = await authFetch('/api/admin/restore', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ line, as_of: asOf }),
        });
        const r = await res.json();
        if (!r.ok) throw new Error(r.error || '恢复失败');
        closeModal();
        toast(`已恢复 ${asOf}`);
        await refreshAll();
      } catch (err) {
        if (err.auth) return;
        toast(err.message, 'err');
      }
    };

    const askDelete = (d) => {
      const isLatest = (ALL.find((x) => x.line === d.line) || {}).latest === d.as_of;
      const card = openModal(`
        <div class="adm-m-head"><div><h3>删除这一期？</h3>
          <p>${d.label} · ${d.as_of}</p></div>
          <button class="adm-m-x">✕</button></div>
        <div class="adm-m-body">
          ${isLatest ? '<p class="adm-note adm-warn">这是该模块<b>最新</b>的一期，删掉后页面和通报会退回到上一期。</p>' : ''}
          <p class="adm-note"><b>删除是软的</b>：库里数据、导入记录、原始文件都还在，
            页面和通报立刻看不到它，随时能在「已删」里点一下恢复。删除前系统还会自动备份一次数据库。</p>
          <p class="adm-note">如果是要<b>重新导入同一期</b>，直接去导入就行 ——
            新导入会自动把这期恢复成"在用"，不用先删。</p>
        </div>
        <div class="adm-m-acts">
          <button class="btn" data-x>取消</button>
          <button class="btn btn-primary" data-ok>确认删除</button>
        </div>`);
      card.querySelector('.adm-m-x').onclick = closeModal;
      card.querySelector('[data-x]').onclick = closeModal;
      card.querySelector('[data-ok]').onclick = async (e) => {
        const btn = e.currentTarget;
        btn.disabled = true;
        btn.textContent = '删除中…';
        try {
          const res = await authFetch('/api/admin/delete', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ line: d.line, as_of: d.as_of }),
          });
          const r = await res.json();
          if (!r.ok) throw new Error(r.error || '删除失败');
          closeModal();
          toast(`已删除 ${d.label} ${d.as_of}`);
          if (r.warning && r.warning.text) toast(r.warning.text, 'err');
          await refreshAll();
        } catch (err) {
          if (err.auth) return;
          btn.disabled = false;
          btn.textContent = '确认删除';
          toast(err.message, 'err');
        }
      };
    };

    const askPurge = (d) => {
      const card = openModal(`
        <div class="adm-m-head"><div><h3>彻底删除这一期？</h3>
          <p>${d.label} · ${d.as_of} · <b>不可恢复</b></p></div>
          <button class="adm-m-x">✕</button></div>
        <div class="adm-m-body">
          <p class="adm-note adm-danger-note"><b>这一步没有后悔药。</b>
            这一期的数据会从库里真的抹掉，「恢复」也找不回来（只能拿删除前的备份库手工还原）。
            删除前系统会再自动备份一次数据库。</p>
          <p class="adm-note"><b>原始文件不会被删</b>：${d.file_count} 个留档原件还留在
            <code>data/imports/</code> 下，随时能重新导入这一期。</p>
          <p class="adm-note">确认请把数据日期<b>原样输入</b>下面的框：</p>
          <input class="adm-confirm-in" id="admPurgeIn" placeholder="${d.as_of}" autocomplete="off">
        </div>
        <div class="adm-m-acts">
          <button class="btn" data-x>取消</button>
          <button class="btn adm-danger" data-ok disabled>彻底删除</button>
        </div>`);
      card.querySelector('.adm-m-x').onclick = closeModal;
      card.querySelector('[data-x]').onclick = closeModal;
      const inp = card.querySelector('#admPurgeIn');
      const ok = card.querySelector('[data-ok]');
      inp.oninput = () => { ok.disabled = inp.value.trim() !== d.as_of; };
      inp.focus();
      ok.onclick = async () => {
        ok.disabled = true;
        ok.textContent = '删除中…';
        try {
          const res = await authFetch('/api/admin/purge', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ line: d.line, as_of: d.as_of, confirm: inp.value.trim() }),
          });
          const r = await res.json();
          if (!r.ok) throw new Error(r.error || '彻底删除失败');
          closeModal();
          toast(`已彻底删除 ${d.label} ${d.as_of}`);
          await refreshAll();
        } catch (err) {
          if (err.auth) return;
          ok.disabled = false;
          ok.textContent = '彻底删除';
          toast(err.message, 'err');
        }
      };
    };

    // ------------------------------------------------------------ 绑定
    let qTimer;
    view.querySelector('#admQ').oninput = (e) => {
      q = e.currentTarget.value;
      clearTimeout(qTimer);
      qTimer = setTimeout(paint, 140);
    };
    view.querySelector('#admOnlyDel').onchange = (e) => {
      onlyDeleted = e.currentTarget.checked;
      paint();
    };
    view.querySelector('#admReload').onclick = load;
    load();
  },
};
