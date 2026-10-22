/* 企微社群：群/客户/交互 三口径对比 + 熟识率 + 网点明细 */
import { fmt, countUp, empty, table, bigTable, icon } from '../ui.js';
import { mount, base, xAxis, yAxis, C, barRank } from '../charts.js';

export default {
  id: 'community',
  title: '企微社群',
  nav: '企微社群',
  icon: 'community',
  render(view, data) {
    const d = data.community;
    if (!d?.ok) { view.innerHTML = `<div class="card">${empty('企微社群暂无数据', '导入本周 + 上周的成员群聊数据统计')}</div>`; return; }
    const k = d.kpi;
    const brs = d.branches || [];
    view.innerHTML = `
      <div class="page-head">
        <div><h1>企业微信社群运营</h1>
          <p>${fmt.date(d.as_of)} · 周频对比（较上周） · ${brs.length} 家支行</p></div>
        <div class="spacer"></div>
        <span class="chip amber">群 ${k.groups}（+${k.groups_d}）</span>
        <span class="chip green">客户 ${fmt.n(k.cust)}（+${fmt.n(k.cust_d)}）</span>
      </div>
      <div class="grid g4">
        ${tile('群数量', fmt.n(k.groups), '个', `较上周 +${k.groups_d}`, C.amber)}
        ${tile('群客户数', fmt.n(k.cust), '户', `较上周 +${fmt.n(k.cust_d)}`, C.blue)}
        ${tile('交互数', fmt.n(k.inter), '条', `较上周 +${fmt.n(k.inter_d)}`, C.teal)}
        ${tile('客户熟识率', fmt.pct(k.rate, 2), '', `较上周 ${k.rate_d >= 0 ? '+' : ''}${(k.rate_d * 100).toFixed(2)} 个百分点`, C.violet)}
      </div>
      <div class="grid g-7-5" style="margin-top:16px">
        <div class="card"><div class="card-head"><h3>支行客户数</h3>
          <div class="right"><span class="chip">较上周增量标签</span></div></div>
          <div class="chart-box chart-md" id="qwBar"></div></div>
        <div class="card"><div class="card-head"><h3>交互与熟识率</h3></div>
          <div class="chart-box chart-md" id="qwRate"></div></div>
      </div>
      <div class="card" style="margin-top:16px"><div class="card-head"><h3>网点明细</h3>
        <div class="right"><span class="chip red">${k.empty_nets} 个网点尚未建群</span>
          <button class="btn btn-sm" id="qwExpand" style="margin-left:8px">${icon('expand', 14)} 全屏</button></div></div>
        <div id="qwTable"></div></div>`;
    view.querySelectorAll('[data-count]').forEach((el) => countUp(el, Number(el.dataset.count), { decimals: Number(el.dataset.dec || 0) }));

    mount(view.querySelector('#qwBar'), barRank(
      brs.map((b) => ({ name: b.name.replace('支行', ''), value: b.cust })), { color: C.amber, unit: ' 户' }));

    mount(view.querySelector('#qwRate'), base({
      tooltip: { ...base().tooltip },
      legend: { top: 0, right: 0, icon: 'roundRect', itemWidth: 8, itemHeight: 8, textStyle: { color: C.ink3, fontSize: 11 } },
      grid: { left: 10, right: 16, top: 34, bottom: 6, containLabel: true },
      xAxis: xAxis(brs.map((b) => b.name.replace('支行', ''))),
      yAxis: [
        yAxis({ axisLabel: { color: C.ink3, formatter: '{value}%' }, max: (v) => Math.max(5, Math.ceil(v.max * 1.2)) }),
        yAxis({ position: 'right', splitLine: { show: false }, axisLabel: { color: C.teal, fontSize: 10 } }),
      ],
      series: [
        { name: '熟识率(%)', type: 'bar', barWidth: '46%', data: brs.map((b) => +(b.rate * 100).toFixed(2)),
          itemStyle: { borderRadius: [5, 5, 0, 0], color: '#b9a9ff' } },
        { name: '交互数(条)', type: 'line', yAxisIndex: 1, smooth: 0.35, data: brs.map((b) => b.inter),
          lineStyle: { color: C.teal, width: 2 }, itemStyle: { color: C.teal }, symbolSize: 6 },
      ],
    }));

    view.querySelector('#qwTable').appendChild(table(QW_COLS, d.nets, {}));
    view.querySelector('#qwExpand').onclick = () => bigTable({
      title: '企微社群 · 网点明细', subtitle: `${fmt.date(d.as_of)} · 共 ${d.nets.length} 个网点`,
      columns: QW_COLS, rows: d.nets,
    });
  },
};

const QW_COLS = [
  { key: 'name', title: '网点', rank: false, render: (v) => String(v).replace('阜阳', '') },
  { key: 'groups', title: '群数', decimals: 0 },
  { key: 'groups_d', title: '较上周', decimals: 0, render: (v) => `<span class="delta ${v > 0 ? 'up' : v < 0 ? 'down' : 'flat'}">${fmt.sign(v, 0)}</span>` },
  { key: 'cust', title: '客户数', decimals: 0 },
  { key: 'cust_d', title: '较上周', decimals: 0, render: (v) => `<span class="delta ${v > 0 ? 'up' : v < 0 ? 'down' : 'flat'}">${fmt.sign(v, 0)}</span>` },
  { key: 'inter', title: '交互数', decimals: 0 },
  { key: 'rate', title: '熟识率', render: (v) => fmt.pct(v, 2) },
];

function tile(label, value, unit, foot, color) {
  return `<div class="card kpi" style="--accent:${color}"><div class="heroline"></div>
    <div class="k-label">${label}</div>
    <div class="k-value"><span data-count="${String(value).replace(/[,%]/g, '')}" data-dec="${String(value).includes('.') ? 2 : 0}">0</span><small>${unit}</small></div>
    <div class="k-foot">${foot}</div></div>`;
}
