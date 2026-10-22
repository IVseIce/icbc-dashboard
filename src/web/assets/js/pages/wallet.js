/* 数字人民币钱包：趋势、等级结构、支行与网点排行 */
import { fmt, countUp, empty, table, icon, bigTable } from '../ui.js';
import { mount, base, xAxis, yAxis, C, lineTrend, stackedBar, barRank, splitRank } from '../charts.js';

export default {
  id: 'wallet',
  title: '数字人民币钱包',
  nav: '数字人民币',
  icon: 'wallet',
  render(view, data) {
    const d = data.wallet;
    if (!d?.ok) { view.innerHTML = `<div class="card">${empty('数字人民币钱包暂无数据', '导入钱包开立明细表')}</div>`; return; }
    const k = d.kpi;
    const lvName = ['一类', '二类', '三类', '四类'];
    view.innerHTML = `
      <div class="page-head">
        <div><h1>数字人民币个人钱包</h1>
          <p>${fmt.date(d.as_of)} · ${k.nets} 个网点 · 累计开立 ${fmt.n(k.total)} 户</p></div>
        <div class="spacer"></div>
        <span class="chip green">当日 +${fmt.n(k.day)}</span>
        <span class="chip blue">当月 +${fmt.n(k.month)}</span>
        <span class="chip red">当日零开 ${k.zero_day} 个网点</span>
      </div>
      <div class="grid g4">
        ${tile('累计开立', fmt.n(k.total), '户', `网点均值 ${k.per_net} 户`, C.blue)}
        ${tile('当日新增', fmt.n(k.day), '户', k.dod ? `较前一日 ${fmt.sign(k.dod, 0)} 户` : '—', C.red)}
        ${tile('当月新增', fmt.n(k.month), '户', `占累计 ${((k.month / k.total) * 100).toFixed(1)}%`, C.violet)}
        ${tile('等级结构', `${k.lv[1]}`, '二类为主', `一类 ${k.lv[0]} · 三类 ${k.lv[2]} · 四类 ${k.lv[3]}`, C.teal)}
      </div>
      <div class="grid g-7-5" style="margin-top:16px">
        <div class="card"><div class="card-head"><h3>累计开立走势</h3>
          <div class="right"><span class="chip">${(d.trend || []).length} 个时点</span></div></div>
          <div class="chart-box chart-md" id="wlTrend"></div></div>
        <div class="card"><div class="card-head"><h3>支行等级结构</h3>
          <div class="right"><span class="chip">堆叠：一类–四类</span></div></div>
          <div class="chart-box chart-md" id="wlStack"></div></div>
      </div>
      <div class="grid g-7-5" style="margin-top:16px">
        <div class="card"><div class="card-head"><h3>网点排行 · 头尾</h3>
          <div class="right"><span class="chip">累计开立</span></div></div>
          <div class="chart-box chart-lg" id="wlRank"></div></div>
        <div class="card"><div class="card-head"><h3>当日零新增网点</h3>
          <div class="right"><span class="chip red">${k.zero_day} 个</span></div></div>
          <div id="wlZero" style="display:flex;flex-wrap:wrap;gap:6px;padding-top:6px"></div></div>
      </div>
      <div class="card" style="margin-top:16px"><div class="card-head"><h3>网点明细</h3>
        <div class="right"><button class="btn btn-sm" id="wlExpand">${icon('expand', 14)} 全屏</button></div></div>
        <div id="wlTable"></div></div>`;
    view.querySelectorAll('[data-count]').forEach((el) => countUp(el, Number(el.dataset.count), { decimals: Number(el.dataset.dec || 0) }));

    const tr = d.trend || [];
    mount(view.querySelector('#wlTrend'), lineTrend(tr.map((t) => fmt.short(t.d)),
      [{ name: '累计', data: tr.map((t) => t.total), color: C.blue }], { unit: ' 户' }));

    mount(view.querySelector('#wlStack'), stackedBar(d.branches.map((b) => b.name),
      lvName.map((n, i) => ({ name: n, data: d.branches.map((b) => b.lv[i]), color: ['#1d4ed8', '#3b82f6', '#60a5fa', '#bfdbfe'][i] }))));

    const wlRows = d.nets.map((n) => ({ name: n.name.replace('阜阳', '').replace('支行营业室', '营业室'), value: n.total }));
    mount(view.querySelector('#wlRank'), barRank(splitRank(wlRows, { top: 6, bottom: 5 }),
      { color: C.blue, unit: ' 户' }));

    const zero = d.nets.filter((n) => !n.day);
    view.querySelector('#wlZero').innerHTML = zero.length
      ? zero.map((n) => `<span class="chip red">${n.name.replace('阜阳', '')} · 累计 ${n.total}</span>`).join('')
      : `<span class="chip green">无零新增网点</span>`;

    view.querySelector('#wlTable').appendChild(table(WL_COLS, d.nets, { sortBy: 'total' }));
    view.querySelector('#wlExpand').onclick = () => bigTable({
      title: '数字人民币钱包 · 网点明细', subtitle: `${fmt.date(d.as_of)} · ${k.nets} 个网点`,
      columns: WL_COLS, rows: d.nets,
    });
  },
};

const WL_COLS = [
  { key: 'name', title: '网点', rank: false, render: (v) => String(v).replace('阜阳', '') },
  { key: 'branch', title: '支行' },
  { key: 'total', title: '累计', decimals: 0 },
  { key: 'month', title: '当月新增', decimals: 0 },
  { key: 'day', title: '当日新增', decimals: 0, render: (v) => `<b style="color:${v > 0 ? 'var(--red)' : 'var(--ink-3)'}">${v}</b>` },
];

function tile(label, value, unit, foot, color) {
  return `<div class="card kpi" style="--accent:${color}"><div class="heroline"></div>
    <div class="k-label">${label}</div>
    <div class="k-value"><span data-count="${String(value).replace(/,/g, '')}" data-dec="${String(value).includes('.') ? 2 : 0}">0</span><small>${unit}</small></div>
    <div class="k-foot">${foot}</div></div>`;
}
