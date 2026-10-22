/* 通报中心：先做「网点线上服务能力」——表格 + 文案 + 复制 / Excel
   其余条线先占位，复用同一套渲染即可扩展。 */
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
        <div><h1>通报中心</h1>
          <p>选日期 → 生成表格与文案 → 复制 / 下载</p></div>
        <div class="spacer"></div>
        <span class="chip">${date ? '所选 ' + fmt.date(date) : '最新一期'}</span>
      </div>

      <div class="card">
        <div class="card-head">
          <h3>选择通报</h3>
          <div class="right"><span class="chip">表格版式沿用现有定稿</span></div>
        </div>
        <div class="tabs">
          ${LINES.map((l, i) => `<button class="${i === 0 ? 'on' : ''}" ${l.ready ? '' : 'disabled style="opacity:.45;cursor:not-allowed"'}>${l.name}${l.ready ? '' : ' · 待做'}</button>`).join('')}
        </div>
        <div id="reportBody"><div class="empty">加载中…</div></div>
      </div>`;

    load(date);

    async function load(on) {
      const host = view.querySelector('#reportBody');
      host.innerHTML = '<div class="empty">加载中…</div>';
      const q = on ? `?date=${encodeURIComponent(on)}` : '';
      const r = await fetch(`/api/report/online${q}`).then((x) => x.json());
      if (!r.ok) {
        host.innerHTML = `<div class="empty"><b>该日期没有线上服务通报</b>${r.error || ''}</div>`;
        return;
      }
      const cols = r.columns;
      const rows = [...r.rows, r.totals];
      host.innerHTML = `
        <div class="report-title">${r.title}</div>
        <div class="tbl-wrap" style="max-height:none">
          <table class="tbl rep">
            <thead><tr>${cols.map((c) => `<th>${c.title}</th>`).join('')}</tr></thead>
            <tbody>${rows.map((row, i) => `<tr class="${i === rows.length - 1 ? 'sum' : ''}">
              ${cols.map((c) => {
                const v = row[c.key];
                if (c.type === 'text') return `<td class="strong">${String(v ?? '—').replace('阜阳', '')}</td>`;
                if (v === null || v === undefined) return '<td class="muted">—</td>';
                if (c.type === 'pct') return `<td>${(v * 100).toFixed(2)}%</td>`;
                return `<td>${fmt.n(v)}</td>`;
              }).join('')}
            </tr>`).join('')}</tbody>
          </table>
        </div>

        <div class="report-actions">
          <button class="btn btn-primary" id="copyText">${icon('file', 14)} 复制文案</button>
          <a class="btn" href="/api/report/online.xlsx${q}">${icon('arrow', 14)} 下载 Excel</a>
          <button class="btn" id="printBtn">打印 / 存 PDF</button>
          <span class="chip" style="margin-left:auto">PNG 导出待接</span>
        </div>

        <div class="report-text">${escapeHTML(r.text).replace(/\n/g, '<br>')}</div>`;

      view.querySelector('#copyText').onclick = async () => {
        try {
          await navigator.clipboard.writeText(r.text);
          toast('文案已复制');
        } catch (e) {
          const ta = document.createElement('textarea');
          ta.value = r.text; document.body.appendChild(ta); ta.select();
          document.execCommand('copy'); ta.remove();
          toast('文案已复制');
        }
      };
      view.querySelector('#printBtn').onclick = () => window.print();
    }
  },
};

function escapeHTML(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}
