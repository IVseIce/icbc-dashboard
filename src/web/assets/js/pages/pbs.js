/* 私人银行：支行核心指标 + 网点发展情况（重点看头尾） */
import { fmt, countUp, empty, icon, table, bigTable } from '../ui.js';
import { mount, C, barRank, splitRank } from '../charts.js';

const num = (v, nd = 0) => fmt.n(v, nd);
const signed = (v, nd = 0) => `${Number(v) > 0 ? '+' : ''}${fmt.n(v, nd)}`;
const cls = (v) => (v > 0 ? 'up' : v < 0 ? 'down' : '');

function tile(label, value, suffix, foot, color) {
  return `<div class="card kpi" style="--accent:${color}">
    <div class="heroline"></div>
    <div class="k-label">${label}</div>
    <div class="k-value">${value}<small>${suffix}</small></div>
    <div class="k-foot">${foot}</div>
  </div>`;
}

const BR_COLS = [
  { key: 'name', title: '支行', rank: false },
  { key: 'cust', title: '客户数', unit: '户', decimals: 0 },
  { key: 'cust_vs_year', title: '比上年', unit: '户', decimals: 0, cls: 'num' },
  { key: 'cust_vs_quarter', title: '比上季末', unit: '户', decimals: 0, cls: 'num' },
  { key: 'asset', title: '资产', unit: '万', decimals: 2 },
  { key: 'asset_vs_year', title: '资产比上年', unit: '万', decimals: 2, cls: 'num' },
  { key: 'asset_vs_quarter', title: '资产比上季末', unit: '万', decimals: 2, cls: 'num' },
  { key: 'dep', title: '日均存款', unit: '万', decimals: 2 },
  { key: 'xl_bal', title: '遴选余额', unit: '万', decimals: 0 },
  { key: 'xl_q4', title: '遴选季度增量', unit: '万', decimals: 0 },
  { key: 'kd_amt', title: '快贷提款', unit: '万', decimals: 0 },
  { key: 'xt_out', title: '信托已出单', unit: '万', decimals: 0 },
  { key: 'bx_sold', title: '保险已销售', unit: '万', decimals: 0 },
];

const NET_COLS = [
  { key: 'name', title: '网点', rank: false, render: (v) => String(v).replace('阜阳', '') },
  { key: 'branch', title: '支行' },
  { key: 'cust', title: '当前存量', unit: '户', decimals: 0 },
  { key: 'prev_cust', title: '上年末', unit: '户', decimals: 0 },
  { key: 'cust_vs_year', title: '较年初', unit: '户', decimals: 0, cls: 'num' },
];

export default {
  id: 'pbs',
  title: '私人银行',
  render(view, data, ctx) {
    const d = data.pbs;
    if (!d?.ok) {
      view.innerHTML = `<div class="card">${empty('私人银行暂无数据',
        '导入「客编日均资产明细」；顺带把上年末、上季度末两份也放进去，才能算对比')}</div>`;
      return;
    }
    const k = d.kpi, per = d.period || {};
    const brs = d.branches || [];
    const nets = d.nets || [];
    const zero = d.zero_nets || [];
    const q = per.quarter ? `${Number(per.quarter.slice(5, 7))}月末` : '上季末';

    view.innerHTML = `
      <div class="page-head">
        <div><h1>私人银行</h1>
          <p>${d.as_of_cn || fmt.date(d.as_of)} · ${k.nets} 个网点（有数 ${k.active_nets}）·
             月日均 600 万元以上客户</p></div>
        <div class="spacer"></div>
        ${k.has_year_end ? '' : '<span class="chip amber">缺上年末数据</span>'}
        ${k.has_quarter ? '' : `<span class="chip amber">缺${q}数据</span>`}
        <span class="chip ${(k.cust_vs_year || 0) >= 0 ? 'red' : 'green'}">
          较年初 ${signed(k.cust_vs_year)} 户</span>
      </div>

      <div class="grid g6">
        ${tile('达标客户', num(k.cust), '户',
          `较年初 ${signed(k.cust_vs_year)} · 较${q} ${signed(k.cust_vs_quarter)}`, C.red)}
        ${tile('达标客户资产', fmt.money(k.asset), '', `较年初 ${signed(k.asset_vs_year)} 万`, C.violet)}
        ${tile('日均存款', fmt.money(k.dep), '', `较年初 ${signed(k.asset_vs_quarter)} 万`, C.blue)}
        ${tile('有数网点', `${k.active_nets}`, `/ ${k.nets}`,
          `零客户 ${k.zero_net_count} 个`, C.teal)}
        ${tile('遴选余额', num(k.xl_bal), '万',
          `季度增量 ${signed(k.xl_q4)} 万`, C.amber)}
        ${tile('重点产品', num(k.xt_out), '万信托',
          `快贷 ${num(k.kd_amt)} 万 · 保险 ${num(k.bx_sold)} 万`, C.green)}
      </div>

      <div class="grid g-7-5" style="margin-top:16px">
        <div class="card"><div class="card-head"><h3>支行客户数（较年初增量）</h3>
          <div class="right"><span class="chip">红=增 / 绿=减</span></div></div>
          <div class="chart-box chart-md" id="pbCust"></div></div>
        <div class="card"><div class="card-head"><h3>支行资产规模</h3>
          <div class="right"><span class="chip">达标客户资产（万元）</span></div></div>
          <div class="chart-box chart-md" id="pbAsset"></div></div>
      </div>

      <div class="grid g-7-5" style="margin-top:16px">
        <div class="card"><div class="card-head"><h3>支行资产较年初增量</h3>
          <div class="right"><span class="chip">万元</span></div></div>
          <div class="chart-box chart-md" id="pbAssetYoy"></div></div>
        <div class="card"><div class="card-head"><h3>网点头尾（较年初）</h3>
          <div class="right"><span class="chip">前 6 / 后 5</span></div></div>
          <div class="chart-box chart-md" id="pbNetRank"></div></div>
      </div>

      <div class="card" style="margin-top:16px">
        <div class="card-head"><h3>支行核心指标</h3>
          <div class="right"><span class="chip">与成表一致</span>
            <button class="btn btn-sm" id="pbBrExpand" style="margin-left:8px">${icon('expand', 14)} 全屏</button></div></div>
        <div id="pbBrTable"></div></div>

      <div class="card" style="margin-top:16px">
        <div class="card-head"><h3>网点发展情况</h3>
          <div class="right">${zero.length ? `<span class="chip red">${zero.length} 个网点零客户</span>` : ''}
            <button class="btn btn-sm" id="pbNetExpand" style="margin-left:8px">${icon('expand', 14)} 全屏</button></div></div>
        <div id="pbNetTable"></div></div>`;

    view.querySelectorAll('[data-count]').forEach((el) =>
      countUp(el, Number(el.dataset.count), { decimals: Number(el.dataset.dec || 0) }));

    // 支行客户数：按较年初增量，正红负绿
    const byYoy = [...brs].filter((b) => b.cust_vs_year !== null)
      .sort((a, b) => (b.cust_vs_year || 0) - (a.cust_vs_year || 0));
    mount(view.querySelector('#pbCust'), barRank(
      byYoy.map((b) => ({ name: b.name, value: b.cust_vs_year, color: b.cust_vs_year >= 0 ? C.red : C.green })),
      { unit: ' 户', decimals: 0 }));

    mount(view.querySelector('#pbAsset'), barRank(
      [...brs].sort((a, b) => (b.asset || 0) - (a.asset || 0))
        .map((b) => ({ name: b.name, value: b.asset })),
      { color: C.violet, unit: ' 万', decimals: 0 }));

    const byAssetYoy = [...brs].filter((b) => b.asset_vs_year !== null)
      .sort((a, b) => (b.asset_vs_year || 0) - (a.asset_vs_year || 0));
    mount(view.querySelector('#pbAssetYoy'), barRank(
      byAssetYoy.map((b) => ({ name: b.name, value: b.asset_vs_year, color: b.asset_vs_year >= 0 ? C.red : C.green })),
      { unit: ' 万', decimals: 0 }));

    // splitRank 只负责"头尾切片"，返回值仍要交给 barRank 变成图表配置
    mount(view.querySelector('#pbNetRank'), barRank(
      splitRank(
        nets.filter((n) => n.cust_vs_year !== null)
          .sort((a, b) => (b.cust_vs_year || 0) - (a.cust_vs_year || 0))
          .map((n) => ({ name: String(n.name).replace('阜阳', ''), value: n.cust_vs_year })),
        { top: 6, bottom: 5 }),
      { unit: ' 户', decimals: 0 }));

    view.querySelector('#pbBrTable').appendChild(table(BR_COLS, brs, {}));
    view.querySelector('#pbNetTable').appendChild(table(NET_COLS, nets, {}));

    view.querySelector('#pbBrExpand').onclick = () => bigTable({
      title: '私人银行 · 支行核心指标',
      subtitle: `${d.as_of_cn} · 单位：万元 / 户`, columns: BR_COLS, rows: brs,
    });
    view.querySelector('#pbNetExpand').onclick = () => bigTable({
      title: '私人银行 · 网点发展情况',
      subtitle: `${d.as_of_cn} · ${nets.length} 个网点 · 上年末对比`,
      columns: NET_COLS, rows: nets,
    });
  },
};
