/* 通报中心：线上服务 / 薪管家 / 数币（表格 + 文案 + Excel + 图片） */
import { icon, toast, fmt } from '../ui.js';

const LINES = [
  { id: 'online', name: '网点线上服务能力', ready: true },
  { id: 'salary', name: '薪管家聚薪行动', ready: true },
  { id: 'wallet', name: '数字人民币钱包', ready: true },
  { id: 'deposit', name: '定期存款增长', ready: true },
  { id: 'community', name: '企微社群运营', ready: true },
];

export default {
  id: 'report',
  title: '通报中心',
  render(view, _data, ctx) {
    const date = ctx.date;
    const q = (kind) => (date ? `?date=${encodeURIComponent(date)}` : '');
    let kind = (location.hash.split('/')[2] || 'online');
    let payload = null;

    view.innerHTML = `
      <div class="page-head">
        <div><h1>通报中心</h1><p>选日期 → 表格与文案 → 复制 / 下载</p></div>
        <div class="spacer"></div>
        <span class="chip">${date ? '所选 ' + fmt.date(date) : '最新一期'}</span>
      </div>

      <div class="card rep-head">
        <div class="rep-tabs" id="tabs">
          ${LINES.map((l) => `<button class="rep-tab ${l.id === kind ? 'on' : ''}" data-k="${l.id}" ${l.ready ? '' : 'disabled'}>
            ${l.name}${l.ready ? '' : '<em>待做</em>'}</button>`).join('')}
        </div>
        <div class="rep-actions">
          <button class="btn btn-primary" id="copyText">${icon('file', 14)} 复制文案</button>
          <a class="btn" id="dlExcel" href="#">${icon('arrow', 14)} 下载 Excel</a>
          <button class="btn" id="copyImg">${icon('spark', 14)} 复制图片</button>
          <button class="btn" id="saveImg">${icon('down', 14)} 导出图片</button>
        </div>
      </div>

      <div id="reportBody"><div class="empty">加载中…</div></div>`;

    const body = view.querySelector('#reportBody');
    view.querySelectorAll('.rep-tab').forEach((b) => {
      b.onclick = () => {
        if (b.disabled) return;
        view.querySelectorAll('.rep-tab').forEach((x) => x.classList.remove('on'));
        b.classList.add('on');
        kind = b.dataset.k;
        load();
      };
    });

    async function load() {
      body.innerHTML = '<div class="card"><div class="empty">加载中…</div></div>';
      const r = await fetch(`/api/report/${kind}${q(kind)}`).then((x) => x.json());
      if (!r.ok) {
        body.innerHTML = `<div class="card"><div class="empty"><b>该日期没有这份通报</b>${r.error || ''}</div></div>`;
        return;
      }
      payload = r;
      view.querySelector('#dlExcel').href = `/api/report/${kind}.xlsx${q(kind)}`;
      body.innerHTML = `
        <div class="card rep-text-card">
          <div class="card-head"><h3>通报文案</h3>
            <div class="right"><span class="chip">可直接粘贴到企微 / 邮件</span></div></div>
          <div class="rep-text">${escapeHTML(r.text).replace(/\n/g, '<br>')}</div>
        </div>
        ${r.tables.map((t, i) => tableCard(t, i)).join('')}`;

      view.querySelector('#copyText').onclick = async () => {
        try { await navigator.clipboard.writeText(r.text); toast('文案已复制'); }
        catch { fallbackCopy(r.text); }
      };
      view.querySelector('#saveImg').onclick = () => exportImage('download');
      view.querySelector('#copyImg').onclick = () => exportImage('copy');
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
