/* 通报中心：线上服务（表格 + 文案）——操作与文案在上，表格在下 */
import { icon, toast, fmt } from '../ui.js';

const LINES = [
  { id: 'online', name: '网点线上服务能力', ready: true },
  { id: 'deposit', name: '定期存款增长', ready: false },
  { id: 'wallet', name: '数字人民币钱包', ready: false },
  { id: 'salary', name: '薪管家聚薪行动', ready: false },
  { id: 'community', name: '企微社群运营', ready: false },
];

export default {
  id: 'report',
  title: '通报中心',
  render(view, _data, ctx) {
    const date = ctx.date;
    view.innerHTML = `
      <div class="page-head">
        <div><h1>通报中心</h1><p>选日期 → 表格与文案 → 复制 / 下载</p></div>
        <div class="spacer"></div>
        <span class="chip">${date ? '所选 ' + fmt.date(date) : '最新一期'}</span>
      </div>
      <div id="reportBody"><div class="empty">加载中…</div></div>`;
    load(date, view);

    async function load(on, root) {
      const host = root.querySelector('#reportBody');
      const q = on ? `?date=${encodeURIComponent(on)}` : '';
      const r = await fetch(`/api/report/online${q}`).then((x) => x.json());
      if (!r.ok) {
        host.innerHTML = `<div class="card"><div class="empty"><b>该日期没有线上服务通报</b>${r.error || ''}</div></div>`;
        return;
      }
      const cols = r.columns;
      const rows = [...r.rows, r.totals];
      host.innerHTML = `
        <div class="card rep-head">
          <div class="rep-tabs">
            ${LINES.map((l, i) => `<button class="rep-tab ${i === 0 ? 'on' : ''}" ${l.ready ? '' : 'disabled'}>
              ${l.name}${l.ready ? '' : '<em>待做</em>'}</button>`).join('')}
          </div>
          <div class="rep-actions">
            <button class="btn btn-primary" id="copyText">${icon('file', 14)} 复制文案</button>
            <a class="btn" href="/api/report/online.xlsx${q}">${icon('arrow', 14)} 下载 Excel</a>
            <button class="btn" id="copyImg">${icon('spark', 14)} 复制图片</button>
            <button class="btn" id="saveImg">${icon('down', 14)} 导出图片</button>
          </div>
        </div>

        <div class="card rep-text-card">
          <div class="card-head">
            <h3>通报文案</h3>
            <div class="right"><span class="chip">可直接粘贴到企微 / 邮件</span></div>
          </div>
          <div class="rep-text">${escapeHTML(r.text).replace(/\n/g, '<br>')}</div>
        </div>

        <div class="card">
          <div class="card-head">
            <h3>${r.title}</h3>
            <div class="right">
              <span class="chip hl-red">红：该列前 5 名</span>
              <span class="chip hl-green">绿：该列后 5 名</span>
            </div>
          </div>
          <div class="tbl-wrap" style="max-height:none">
            <table class="tbl rep">
              <thead><tr>${cols.map((c) => `<th>${c.title}</th>`).join('')}</tr></thead>
              <tbody>${rows.map((row, i) => {
                const sum = i === rows.length - 1;
                return `<tr class="${sum ? 'sum' : ''}">${cols.map((c) => {
                  const v = row[c.key];
                  if (c.type === 'text') return `<td class="strong">${String(v ?? '—').replace('阜阳', '')}</td>`;
                  if (v === null || v === undefined) return '<td class="muted">—</td>';
                  const hl = sum ? null : (row._hl || {})[c.key];
                  const cls = hl === 'red' ? 'hl-red' : hl === 'green' ? 'hl-green' : '';
                  const txt = c.type === 'pct' ? `${(v * 100).toFixed(2)}%` : fmt.n(v);
                  return `<td class="${cls}">${txt}</td>`;
                }).join('')}</tr>`;
              }).join('')}</tbody>
            </table>
          </div>
        </div>`;

      root.querySelector('#copyText').onclick = async () => {
        try { await navigator.clipboard.writeText(r.text); toast('文案已复制'); }
        catch (e) {
          const ta = document.createElement('textarea');
          ta.value = r.text; document.body.appendChild(ta); ta.select();
          document.execCommand('copy'); ta.remove(); toast('文案已复制');
        }
      };
      // ---------- 图片导出（与 Excel 观感一致：微软雅黑、细边框、居中）
      document.querySelectorAll('.sheet').forEach((n) => n.remove());
      const exportNode = document.createElement('div');
      exportNode.className = 'sheet';
      exportNode.innerHTML = `<h4>${r.title}</h4>${buildSheetTable(cols, rows)}`;
      document.body.appendChild(exportNode);

      const toBlob = () => window.html2canvas(exportNode, { scale: 2, backgroundColor: '#ffffff' })
        .then((canvas) => new Promise((res) => canvas.toBlob(res, 'image/png')));

      root.querySelector('#saveImg').onclick = async () => {
        const blob = await toBlob();
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `${r.title}.png`;
        a.click();
        setTimeout(() => URL.revokeObjectURL(a.href), 3000);
        toast('图片已导出');
      };

      root.querySelector('#copyImg').onclick = async () => {
        try {
          const blob = await toBlob();
          await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
          toast('图片已复制，可直接粘贴');
        } catch (e) {
          const blob = await toBlob();
          const a = document.createElement('a');
          a.href = URL.createObjectURL(blob); a.download = `${r.title}.png`; a.click();
          toast('浏览器不支持直接复制，已改为下载');
        }
      };
    }
  },
};

function buildSheetTable(cols, rows) {
  const head = `<tr>${cols.map((c) => `<th>${c.title}</th>`).join('')}</tr>`;
  const body = rows.map((row, i) => {
    const sum = i === rows.length - 1;
    return `<tr class="${sum ? 'sum' : ''}">${cols.map((c) => {
      const v = row[c.key];
      if (c.type === 'text') return `<td>${String(v ?? '—').replace('阜阳', '')}</td>`;
      if (v === null || v === undefined) return '<td>—</td>';
      const hl = sum ? null : (row._hl || {})[c.key];
      const cls = hl === 'red' ? 'hl-red' : hl === 'green' ? 'hl-green' : '';
      const txt = c.type === 'pct' ? `${(v * 100).toFixed(2)}%` : fmt.n(v);
      return `<td class="${cls}">${txt}</td>`;
    }).join('')}</tr>`;
  }).join('');
  return `<table><thead>${head}</thead><tbody>${body}</tbody></table>`;
}

function escapeHTML(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}
