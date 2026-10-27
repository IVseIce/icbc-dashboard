/* 工银薪管家：累计趋势、支行/网点排行 */
import { fmt, countUp, empty, table, bigTable, icon } from '../ui.js';
import { mount, base, xAxis, yAxis, C, lineTrend, barRank } from '../charts.js';

export default {
  id: 'salary',
  title: '工银薪管家',
  nav: '薪管家',
  icon: 'salary',
  render(view, data) {
    const d = data.salary;
    if (!d?.ok) { view.innerHTML = `<div class="card">${empty('薪管家暂无数据', '导入四张增量表')}</div>`; return; }
    const k = d.kpi;
    const tr = d.trend || [];
    // 老内核（Chromium < 92）没有 Array.prototype.at，且这里必须兼容 —— 用下标取末两期
    const last = tr.length ? tr[tr.length - 1] : null;
    const prev = tr.length > 1 ? tr[tr.length - 2] : null;
    const delta = (Number(last?.year) || 0) - (Number(prev?.year) || 0);
    view.innerHTML = `
      <div class="page-head">
        <div><h1>工银薪管家「聚薪行动」</h1>
          <p>${fmt.date(d.as_of)} · 全年累计新增代发 · 有效使用单位 ${k.ent_year} 户</p></div>
        <div class="spacer"></div>
        <span class="chip teal">当月 ${fmt.n(k.month, 2)} 万</span>
        <span class="chip">当月新增单位 ${k.ent_month} 户</span>
      </div>
      <div class="grid g4">
        ${tile('全年代发金额', fmt.n(k.year, 2), '万元', `较上一期 ${delta >= 0 ? '+' : ''}${fmt.n(delta, 2)} 万`, C.teal)}
        ${tile('当月代发金额', fmt.n(k.month, 2), '万元', `占全年 ${(k.year ? (k.month / k.year) * 100 : 0).toFixed(1)}%`, C.blue)}
        ${tile('有效使用单位', fmt.n(k.ent_year), '户', `当月新增 ${k.ent_month} 户`, C.violet)}
        ${tile('有产能支行', `${k.branches_active}`, '家', `有报数网点 ${k.nets_active} 个`, C.amber)}
      </div>
      <div class="grid g-7-5" style="margin-top:16px">
        <div class="card"><div class="card-head"><h3>累计代发走势</h3>
          <div class="right"><span class="chip">${tr.length} 期</span></div></div>
          <div class="chart-box chart-md" id="xgTrend"></div></div>
        <div class="card"><div class="card-head"><h3>支行全年排行</h3></div>
          <div class="chart-box chart-md" id="xgRank"></div></div>
      </div>
      <div class="card" style="margin-top:16px"><div class="card-head"><h3>网点明细（有报数）</h3>
        <div class="right"><span class="chip">按全年降序</span>
          <button class="btn btn-sm" id="xgExpand" style="margin-left:8px">${icon('expand', 14)} 全屏</button></div></div>
        <div id="xgTable"></div></div>`;
    view.querySelectorAll('[data-count]').forEach((el) => countUp(el, Number(el.dataset.count), { decimals: Number(el.dataset.dec || 0) }));

    mount(view.querySelector('#xgTrend'), lineTrend(tr.map((t) => fmt.short(t.d)),
      [{ name: '全年代发', data: tr.map((t) => t.year), color: C.teal }], { unit: ' 万' }));

    mount(view.querySelector('#xgRank'), barRank(
      d.branches.filter((b) => (b.year || 0) > 0).map((b) => ({ name: b.name, value: b.year })),
      { color: C.teal, unit: ' 万', decimals: 0 }));

    view.querySelector('#xgTable').appendChild(table(XG_COLS, d.nets, {}));
    view.querySelector('#xgExpand').onclick = () => bigTable({
      title: '工银薪管家 · 网点明细', subtitle: `${fmt.date(d.as_of)} · 有报数网点 ${d.nets.length} 个`,
      columns: XG_COLS, rows: d.nets,
    });
  },
};

const XG_COLS = [
  { key: 'name', title: '网点', rank: false, render: (v) => String(v).replace('阜阳', '') },
  { key: 'year', title: '全年', unit: '万', decimals: 2 },
  { key: 'month', title: '当月', unit: '万', decimals: 2 },
  { key: 'ent_year', title: '全年单位', unit: '户', decimals: 0 },
  { key: 'ent_month', title: '当月单位', unit: '户', decimals: 0 },
];

function tile(label, value, unit, foot, color) {
  return `<div class="card kpi" style="--accent:${color}"><div class="heroline"></div>
    <div class="k-label">${label}</div>
    <div class="k-value"><span data-count="${String(value).replace(/,/g, '')}" data-dec="${String(value).includes('.') ? 2 : 0}">0</span><small>${unit}</small></div>
    <div class="k-foot">${foot}</div></div>`;
}
