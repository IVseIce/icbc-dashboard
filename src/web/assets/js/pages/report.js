/* 通报中心：先按大类过滤（口令决定可见范围），再选通报 → 表格 + 文案 + Excel + 图片 */
import { icon, toast, fmt, setAsof, setDatePickers } from '../ui.js';
import { auth, authFetch } from '../auth.js';

const CATS = [
  { id: 'jg', name: '个金' },
  { id: 'wj', name: '网金' },
  { id: 'loan', name: '个贷' },
  { id: 'card', name: '银行卡' },
  { id: 'pbs', name: '私银' },
];

const LINES = [
  { id: 'deposit', name: '定期存款增长', cat: 'jg' },
  { id: 'salary', name: '薪管家聚薪行动', cat: 'jg' },
  { id: 'online', name: '网点线上服务能力', cat: 'wj' },
  { id: 'wallet', name: '数字人民币钱包', cat: 'wj' },
  { id: 'community', name: '企微社群运营', cat: 'wj' },
  { id: 'downgrade', name: '降级挽回营销先锋', cat: 'jg' },
  { id: 'yika', name: '“一卡一户”日通报', cat: 'jg' },
  { id: 'pbs', name: '私人银行核心指标', cat: 'pbs' },
];

export default {
  id: 'report',
  title: '通报中心',
  render(view, _data, ctx) {
    const date = ctx.date;
    const q = (k) => (date ? `?date=${encodeURIComponent(date)}` : '');
    const visible = LINES.filter((l) => auth.can(l.cat));
    const cats = CATS.filter((c) => auth.can(c.id))
      .map((c) => ({ ...c, lines: visible.filter((l) => l.cat === c.id) }))
      .filter((c) => c.lines.length);

    let payload = null;
    let kind = String(location.hash.split('/')[2] || '');
    if (!visible.some((l) => l.id === kind)) kind = visible[0]?.id || '';
    let catId = visible.find((l) => l.id === kind)?.cat || cats[0]?.id || '';

    view.innerHTML = `
      <div class="page-head">
        <div><h1>通报中心</h1><p>按大类查看 · 复制文案 / 下载 Excel / 导出图片</p></div>
        <div class="spacer"></div>
        <span class="chip">${date ? '所选 ' + fmt.date(date) : '最新一期'}</span>
      </div>

      ${cats.length > 1 ? `<div class="rep-cats" id="cats">
        ${cats.map((c) => `<button class="rep-cat ${c.id === catId ? 'on' : ''}" data-c="${c.id}">
          ${c.name}<em>${c.lines.length}</em></button>`).join('')}
      </div>` : ''}

      ${visible.length ? `<div class="card rep-head">
        <div class="rep-tabs" id="tabs"></div>
        <div class="rep-actions">
          <button class="btn btn-primary" id="copyText">${icon('file', 14)} 复制文案</button>
          <button class="btn" id="dlExcel">${icon('down', 14)} 下载 Excel</button>
          <button class="btn" id="copyImg">${icon('spark', 14)} 复制图片</button>
          <button class="btn" id="saveImg">${icon('down', 14)} 导出图片</button>
        </div>
      </div>` : ''}

      <div id="reportBody"><div class="empty">加载中…</div></div>`;

    const body = view.querySelector('#reportBody');
    const tabs = view.querySelector('#tabs');   // 无可见通报时为 null

    view.querySelectorAll('.rep-cat').forEach((b) => {
      b.onclick = () => {
        catId = b.dataset.c;
        view.querySelectorAll('.rep-cat').forEach((x) => x.classList.toggle('on', x === b));
        const first = cats.find((c) => c.id === catId)?.lines[0];
        if (!first) return;
        kind = first.id;
        paintTabs();
        load();
      };
    });

    function paintTabs() {
      if (!tabs) return;
      const lines = cats.find((c) => c.id === catId)?.lines || [];
      tabs.innerHTML = lines.map((l) => `<button class="rep-tab ${l.id === kind ? 'on' : ''}" data-k="${l.id}">
        ${l.name}</button>`).join('');
      tabs.querySelectorAll('.rep-tab').forEach((b) => {
        b.onclick = () => {
          tabs.querySelectorAll('.rep-tab').forEach((x) => x.classList.remove('on'));
          b.classList.add('on');
          kind = b.dataset.k;
          load();
        };
      });
    }

    async function load() {
      if (!kind) {
        setAsof('暂无可查看的通报');
        body.innerHTML = `<div class="card"><div class="empty"><b>当前身份暂无可查看的通报</b>
          ${auth.label} 口令下还没有已接入的通报</div></div>`;
        return;
      }
      body.innerHTML = '<div class="card"><div class="empty">加载中…</div></div>';
      let r;
      try {
        const res = await authFetch(`/api/report/${kind}${q(kind)}`);
        r = await res.json();
      } catch (err) {
        if (!err.auth) body.innerHTML = `<div class="card"><div class="empty"><b>加载失败</b>${err.message}</div></div>`;
        return;
      }
      if (!r.ok) {
        body.innerHTML = `<div class="card"><div class="empty"><b>该日期没有这份通报</b>${r.error || ''}</div></div>`;
        return;
      }
      payload = r;
      const asof = r.as_of ? `数据截至 ${fmt.date(r.as_of)}${date ? ` · 所选 ≤${fmt.date(date)}` : ''}` : '';
      setAsof(asof || '—');
      if (!date && r.as_of) setDatePickers(r.as_of);
      body.innerHTML = `
        <div class="card rep-text-card">
          <div class="card-head"><h3>通报文案</h3>
            <div class="right"><span class="chip">可直接粘贴到企微 / 邮件</span></div></div>
          <div class="rep-text">${escapeHTML(r.text).replace(/\n/g, '<br>')}</div>
        </div>
        ${r.tables.map((t, i) => tableCard(t, i)).join('')}`;

      // 私银的两份成表由一个按钮打包下载（后端返回 zip），这里不用额外按钮。
      // 按钮文案随通报变化，让用户知道下载的是压缩包。
      const dlBtn = view.querySelector('#dlExcel');
      if (dlBtn) {
        dlBtn.innerHTML = kind === 'pbs'
          ? `${icon('down', 14)} 下载 Excel（两份打包）`
          : `${icon('down', 14)} 下载 Excel`;
      }
      view.querySelector('#copyText').onclick = async () => {
        try { await navigator.clipboard.writeText(r.text); toast('文案已复制'); }
        catch { fallbackCopy(r.text); }
      };
      view.querySelector('#saveImg').onclick = () => exportImage('download');
      view.querySelector('#copyImg').onclick = () => exportImage('copy');
      view.querySelector('#dlExcel').onclick = () => downloadExcel();
    }

    async function downloadExcel() {
      const target = kind;
      const btn = view.querySelector('#dlExcel');
      btn.disabled = true;
      try {
        const res = await authFetch(`/api/report/${target}.xlsx${q(target)}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const blob = await res.blob();
        const cd = res.headers.get('Content-Disposition') || '';
        const m = /filename\*=UTF-8''([^;]+)/i.exec(cd);
        const name = m ? decodeURIComponent(m[1]) : `${payload?.title || target}.xlsx`;
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = name; a.click();
        setTimeout(() => URL.revokeObjectURL(url), 3000);
        toast('Excel 已下载');
      } catch (err) {
        if (!err.auth) toast(`下载失败：${err.message}`, 'err');
      } finally {
        btn.disabled = false;
      }
    }

    function tableCard(t, i) {
      const rows = [...t.rows, t.totals].filter(Boolean);
      return `
      <div class="card" style="margin-top:14px">
        <div class="card-head"><h3>${payload.title}${t.name ? ' · ' + t.name : ''}</h3>
          <div class="right">${i === 0 && t.rows.some((r) => r._hl && Object.keys(r._hl).length)
            ? '<span class="chip hl-red">红：该列前 5 名</span><span class="chip hl-green">绿：该列后 5 名</span>' : ''}</div></div>
        <div class="tbl-wrap" style="max-height:none">
          <table class="tbl rep">
            <thead><tr>${t.columns.map((c) => `<th>${c.title}</th>`).join('')}</tr></thead>
            <tbody>${rows.map((row, ri) => {
              const sum = ri === rows.length - 1;
              return `<tr class="${sum ? 'sum' : ''}">${t.columns.map((c) => {
                const v = row[c.key];
                if (v === null || v === undefined || v === '') return '<td class="muted">—</td>';
                const hl = sum ? null : (row._hl || {})[c.key];
                const cls = hl === 'red' ? 'hl-red' : hl === 'green' ? 'hl-green' : '';
                return `<td class="${cls}">${c.type === 'pct' ? `${(v * 100).toFixed(2)}%` : (typeof v === 'number' ? fmt.n(v, Number.isInteger(v) ? 0 : 2) : v)}</td>`;
              }).join('')}</tr>`;
            }).join('')}</tbody>
          </table>
        </div>
      </div>`;
    }

    async function exportImage(mode) {
      document.querySelectorAll('.sheet').forEach((n) => n.remove());
      const node = document.createElement('div');
      node.className = 'sheet';
      node.innerHTML = `<h4>${payload.title}</h4>` + payload.tables.map((t) => sheetTable(t)).join('<div style="height:10px"></div>');
      document.body.appendChild(node);
      try {
        const canvas = await window.html2canvas(node, { scale: 2, backgroundColor: '#ffffff' });
        const blob = await new Promise((res) => canvas.toBlob(res, 'image/png'));
        if (mode === 'copy') {
          try {
            await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
            toast('图片已复制，可直接粘贴');
            return;
          } catch { /* 降级为下载 */ }
        }
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `${payload.title}.png`;
        a.click();
        setTimeout(() => URL.revokeObjectURL(a.href), 3000);
        toast('图片已导出');
      } finally {
        node.remove();
      }
    }

    paintTabs();
    load();
  },
};

function sheetTable(t) {
  const rows = [...t.rows, t.totals].filter(Boolean);
  return `<table><thead><tr>${t.columns.map((c) => `<th>${c.title}</th>`).join('')}</tr></thead>
    <tbody>${rows.map((row, i) => {
      const sum = i === rows.length - 1;
      return `<tr class="${sum ? 'sum' : ''}">${t.columns.map((c) => {
        const v = row[c.key];
        if (v === null || v === undefined || v === '') return '<td>—</td>';
        const hl = sum ? null : (row._hl || {})[c.key];
        const cls = hl === 'red' ? 'hl-red' : hl === 'green' ? 'hl-green' : '';
        return `<td class="${cls}">${c.type === 'pct' ? `${(v * 100).toFixed(2)}%` : (typeof v === 'number' ? fmt.n(v, Number.isInteger(v) ? 0 : 2) : v)}</td>`;
      }).join('')}</tr>`;
    }).join('')}</tbody></table>`;
}

function fallbackCopy(text) {
  const ta = document.createElement('textarea');
  ta.value = text; document.body.appendChild(ta); ta.select();
  document.execCommand('copy'); ta.remove(); toast('文案已复制');
}

function escapeHTML(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}
