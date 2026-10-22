/* 网点线上服务（重点）：分布、散点、雷达、排行、明细（可按支行筛选） */
import { fmt, countUp, empty, table, icon, drawer, bigTable } from '../ui.js';
import { mount, base, xAxis, yAxis, C, histogram, scatter, radar, barRank, splitRank, PALETTE } from '../charts.js';

export default {
  id: 'online',
  title: '网点线上服务',
  nav: '网点线上服务',
  icon: 'online',
  tag: '重点',
  render(view, data) {
    const d = data.online;
    if (!d?.ok) { view.innerHTML = `<div class="card">${empty('网点线上服务暂无数据', '导入动户率×2 + 企微明细×3 + 营销授权')}</div>`; return; }
    const k = d.kpi, nets = d.nets || [], brs = d.branches || [];

    view.innerHTML = `
      <div class="page-head">
        <div>
          <h1>网点线上服务能力</h1>
          <p>${fmt.date(d.as_of)} · ${k.nets} 个网点 · 动户率 = 当日手机银行动户 / 到店客群</p>
        </div>
        <div class="spacer"></div>
        <span class="chip ${k.above55 >= 20 ? 'green' : 'amber'}">达标(≥55%) ${k.above55} 个网点</span>
        <span class="chip red">低于45% ${k.below45} 个</span>
      </div>

      <div class="grid g6">
        ${tile('当日动户率', (k.day_rate * 100).toFixed(2), '%', `网点均值 ${(k.avg_day_rate * 100).toFixed(1)}%`, C.red)}
        ${tile('当月动户率', (k.month_rate * 100).toFixed(2), '%', '到店客群加权', C.violet)}
        ${tile('当月添客', fmt.n(k.add_month), '户', `当日 ${fmt.n(k.add_today)} 户`, C.blue)}
        ${tile('添客实名率', (k.real_rate * 100).toFixed(1), '%', '企微添客口径', C.teal)}
        ${tile('签约率', (k.sign_rate * 100).toFixed(1), '%', '营销授权', C.amber)}
        ${tile('管户签约率', (k.kh_rate * 100).toFixed(1), '%', '签约/管户', C.green)}
      </div>

      <div class="grid g-7-5" style="margin-top:16px">
        <div class="card">
          <div class="card-head"><h3>动户率分布</h3><div class="right"><span class="chip">按 40 个网点分档</span></div></div>
          <div class="chart-box chart-md" id="onHist"></div>
        </div>
        <div class="card">
          <div class="card-head"><h3>支行多维对比</h3><div class="right"><span class="chip">归一化 0–100</span></div></div>
          <div class="chart-box chart-md" id="onRadar"></div>
        </div>
      </div>

      <div class="grid g-7-5" style="margin-top:16px">
        <div class="card">
          <div class="card-head">
            <h3>动户率 × 签约率</h3>
            <div class="right"><span class="chip">气泡=到店客群</span><span class="chip red">右上=双优</span></div>
          </div>
          <div class="chart-box chart-lg" id="onScatter"></div>
        </div>
        <div class="card">
          <div class="card-head"><h3>网点排行 · 头尾</h3><div class="right"><span class="chip">当日动户率</span></div></div>
          <div class="chart-box chart-lg" id="onRank"></div>
        </div>
      </div>

      <div class="card" style="margin-top:16px">
        <div class="card-head">
          <h3>网点明细</h3>
          <div class="right" id="brFilter"></div>
          <button class="btn btn-sm" id="onExpand" style="margin-left:8px">${icon('expand', 14)} 全屏</button>
        </div>
        <div id="onTable"></div>
      </div>`;

    view.querySelectorAll('[data-count]').forEach((el) => countUp(el, Number(el.dataset.count), { decimals: Number(el.dataset.dec || 0) }));

    mount(view.querySelector('#onHist'), histogram(
      (d.hist?.labels || []).map((s) => s.replace('~', '–')),
      d.hist?.counts || [], { unit: '%', markValue: null }));

    // 雷达：全行 + 前二 + 后二
    const inds = [
      { name: '当日动户率', max: 100 },
      { name: '当月动户率', max: 100 },
      { name: '添客实名率', max: 100 },
      { name: '签约率', max: 100 },
      { name: '管户签约率', max: 100 },
    ];
    const norm = (b) => [b.day_rate * 90, b.month_rate * 100, b.real_rate * 100, b.sign_rate * 100, b.kh_rate * 100].map((v) => +v.toFixed(1));
    const sorted = [...brs].sort((a, b) => b.day_rate - a.day_rate);
    const avg = inds.map((_, i) => +(brs.reduce((s, b) => s + norm(b)[i], 0) / Math.max(1, brs.length)).toFixed(1));
    mount(view.querySelector('#onRadar'), radar(inds, [
      { name: '全行平均', value: avg, color: C.ink3, opacity: 0.06 },
      ...sorted.slice(0, 2).map((b, i) => ({ name: b.name, value: norm(b), color: [C.red, C.amber][i], opacity: 0.12 })),
      ...sorted.slice(-2).map((b, i) => ({ name: b.name, value: norm(b), color: [C.blue, C.teal][i], opacity: 0.08 })),
    ]));

    mount(view.querySelector('#onScatter'), scatter(d.scatter || [], { xName: '当日动户率 %', yName: '签约率 %' }));

    const sortedAll = [...nets].sort((a, b) => b.day_rate - a.day_rate);
    const picked = splitRank(sortedAll.map((n) => ({
      name: n.name.replace('阜阳', '').replace('支行营业室', '营业室'), value: n.day_rate,
    })), { top: 6, bottom: 6, unit: '个' });
    mount(view.querySelector('#onRank'), barRank(picked, { color: C.red, unit: '%', decimals: 1 }));

    // 明细 + 支行筛选
    const filterBox = view.querySelector('#brFilter');
    filterBox.innerHTML = `<span class="chip" data-b="">全部 ${nets.length}</span>` +
      brs.map((b) => `<span class="chip" data-b="${b.name}" style="margin-left:4px">${b.name} ${b.nets}</span>`).join('');
    filterBox.querySelectorAll('[data-b]').forEach((c) => {
      c.style.cursor = 'pointer';
      c.onclick = () => {
        filterBox.querySelectorAll('[data-b]').forEach((x) => { x.style.background = ''; x.style.color = ''; });
        c.style.background = 'var(--red-soft)'; c.style.color = '#a80d26';
        renderTable(c.dataset.b);
      };
    });

    view.querySelector('#onExpand').onclick = () => bigTable({
      title: '网点线上服务 · 明细',
      subtitle: `${fmt.date(d.as_of)} · 共 ${nets.length} 个网点`,
      columns: ON_COLS, rows: nets,
    });

    function renderTable(branch = '') {
      const rows = nets.filter((n) => !branch || n.branch === branch);
      const cols = ON_COLS;
      const host = view.querySelector('#onTable');
      host.innerHTML = '';
      host.appendChild(table(cols, rows, {
        onRow: (r) => drawer(r.name.replace('阜阳', ''), `
          <div class="kv"><span>所属支行</span><b>${r.branch}</b></div>
          <div class="kv"><span>当日动户率</span><b style="color:${r.day_rate >= 55 ? 'var(--red)' : 'var(--ink)'}">${r.day_rate.toFixed(2)}%</b></div>
          <div class="kv"><span>当月动户率</span><b>${r.month_rate.toFixed(2)}%</b></div>
          <div class="kv"><span>到店客群</span><b>${fmt.n(r.cust)} 户</b></div>
          <div class="kv"><span>当日添客 / 当月</span><b>${r.add_today} / ${r.add_month} 户</b></div>
          <div class="kv"><span>添客实名率</span><b>${r.real_rate.toFixed(1)}%</b></div>
          <div class="kv"><span>营销授权签约率</span><b>${r.sign_rate.toFixed(1)}%</b></div>
          <div class="kv"><span>管户签约率</span><b>${r.kh_rate.toFixed(1)}%</b></div>`,
        `${fmt.date(d.as_of)} · 点击表格行可查看更多`)}));
    }
    renderTable('');
  },
};

const ON_COLS = [
  { key: 'name', title: '网点', rank: false, render: (v) => String(v).replace('阜阳', '') },
  { key: 'branch', title: '支行' },
  { key: 'day_rate', title: '当日动户率', render: (v) => `<b style="color:${v >= 55 ? 'var(--red)' : 'var(--ink-2)'}">${v.toFixed(2)}%</b>` },
  { key: 'month_rate', title: '当月动户率', render: (v) => `${v.toFixed(2)}%` },
  { key: 'cust', title: '到店客群', decimals: 0 },
  { key: 'add_today', title: '当日添客', decimals: 0 },
  { key: 'add_month', title: '当月添客', decimals: 0 },
  { key: 'real_rate', title: '实名率', render: (v) => `${v?.toFixed(1)}%` },
  { key: 'sign_rate', title: '签约率', render: (v) => `${v?.toFixed(1)}%` },
  { key: 'kh_rate', title: '管户签约率', render: (v) => `${v?.toFixed(1)}%` },
];

function tile(label, value, unit, foot, color) {
  return `<div class="card kpi" style="--accent:${color}">
    <div class="heroline"></div>
    <div class="k-label">${label}</div>
    <div class="k-value"><span data-count="${String(value).replace(/,/g, '')}" data-dec="${String(value).includes('.') ? 2 : 0}">0</span><small>${unit}</small></div>
    <div class="k-foot">${foot}</div>
  </div>`;
}
