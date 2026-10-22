/* 代发明细（月度 · 网点维度）：客户/企业/金额/新增/流失预警 */
import { fmt, countUp, empty, table, bigTable, icon } from '../ui.js';
import { mount, base, xAxis, yAxis, C, barRank, lineTrend, splitRank } from '../charts.js';

const COLS = [
  { key: 'name', title: '网点', rank: false, render: (v) => String(v).replace('阜阳', '') },
  { key: 'branch', title: '支行' },
  { key: 'comps', title: '代发企业', unit: '户', decimals: 0 },
  { key: 'cust', title: '代发客户', unit: '人', decimals: 0 },
  { key: 'ytd', title: '全年累计', unit: '万', decimals: 2 },
  { key: 'new_year', title: '当年新增', unit: '户', decimals: 0 },
  { key: 'lost', title: '流失', unit: '户', decimals: 0 },
  { key: 'warn', title: '预警', unit: '户', decimals: 0 },
];

export default {
  id: 'payroll',
  title: '代发明细',
  render(view, data) {
    const d = data.payroll;
    if (!d?.ok) {
      view.innerHTML = `<div class="card">${empty('代发明细暂无数据', '该日期之前没有月度数据')}</div>`;
      return;
    }
    const k = d.kpi;
    const nets = d.nets || [];
    const months = d.trend || [];
    view.innerHTML = `
      <div class="page-head">
        <div><h1>代发明细</h1>
          <p>${d.month} 月度数据 · ${k.nets} 个网点 · 共 ${fmt.n(k.comps)} 户代发企业</p></div>
        <div class="spacer"></div>
        <span class="chip amber">月度口径</span>
        <span class="chip">${d.as_of} 时点</span>
      </div>

      <div class="grid g6">
        ${tile('代发客户', fmt.n(k.cust), '人', '代发工资客户', C.blue)}
        ${tile('代发企业', fmt.n(k.comps), '户', `当年新增 ${k.new_year} 户`, C.teal)}
        ${tile('当月代发', fmt.n(k.month), '万元', '较上月', C.red)}
        ${tile('全年累计', fmt.n(k.ytd), '万元', '年累计代发', C.violet)}
        ${tile('流失预警', fmt.n((k.lost || 0) + (k.warn || 0)), '户', `流失 ${k.lost} · 预警 ${k.warn}`, C.amber)}
        ${tile('网点覆盖', `${k.nets}`, '个', '全部有代发数据', C.green)}
      </div>

      <div class="grid g-7-5" style="margin-top:16px">
        <div class="card"><div class="card-head"><h3>月度代发走势</h3>
          <div class="right"><span class="chip">柱=当月（万元）</span><span class="chip">线=客户数</span></div></div>
          <div class="chart-box chart-md" id="payTrend"></div></div>
        <div class="card"><div class="card-head"><h3>代发分层</h3>
          <div class="right"><span class="chip">按企业代发规模</span></div></div>
          <div class="chart-box chart-md" id="payTier"></div></div>
      </div>

      <div class="grid g-7-5" style="margin-top:16px">
        <div class="card"><div class="card-head"><h3>网点排行</h3>
          <div class="right"><span class="chip">全年累计代发</span></div></div>
          <div class="chart-box chart-lg" id="payRank"></div></div>
        <div class="card"><div class="card-head"><h3>支行汇总</h3>
          <div class="right"><span class="chip">全年累计（万元）</span></div></div>
          <div class="chart-box chart-lg" id="payBranch"></div></div>
      </div>

      <div class="card" style="margin-top:16px">
        <div class="card-head"><h3>网点明细</h3>
          <div class="right"><button class="btn btn-sm" id="payExpand">${icon('expand', 14)} 全屏</button></div></div>
        <div id="payTable"></div>
      </div>`;

    view.querySelectorAll('[data-count]').forEach((el) =>
      countUp(el, Number(el.dataset.count), { decimals: Number(el.dataset.dec || 0) }));

    // 趋势：柱=当月金额，线=客户数
    mount(view.querySelector('#payTrend'), base({
      legend: { top: 0, right: 0, icon: 'roundRect', itemWidth: 8, itemHeight: 8, textStyle: { color: C.ink3, fontSize: 11 } },
      grid: { left: 10, right: 16, top: 34, bottom: 6, containLabel: true },
      tooltip: { ...base().tooltip },
      xAxis: xAxis(months.filter((m) => m.amount !== null).map((m) => m.month.slice(2))),
      yAxis: [yAxis({ name: '', axisLabel: { color: C.ink3, fontSize: 10 } }),
        yAxis({ position: 'right', splitLine: { show: false }, axisLabel: { color: C.blue, fontSize: 10 } })],
      series: [
        { name: '当月代发(万)', type: 'bar', barWidth: '46%', data: months.filter((m) => m.amount !== null).map((m) => m.amount),
          itemStyle: { borderRadius: [4, 4, 0, 0], color: '#f2b3bd' } },
        { name: '代发客户', type: 'line', yAxisIndex: 1, smooth: 0.3, data: months.filter((m) => m.amount !== null).map((m) => m.cust),
          lineStyle: { width: 2, color: C.blue }, itemStyle: { color: C.blue }, symbolSize: 5 },
      ],
    }));

    // 分层
    const tiers = Object.entries(k.tier || {}).map(([name, value]) => ({ name, value }));
    mount(view.querySelector('#payTier'), base({
      tooltip: { ...base().tooltip, trigger: 'item', formatter: (p) => `${p.name}<br/><b>${p.value}</b> 户（${p.percent}%）` },
      legend: { orient: 'vertical', right: 0, top: 'middle', icon: 'circle', itemWidth: 8, itemHeight: 8,
        textStyle: { color: C.ink3, fontSize: 11 } },
      color: ['#2563eb', '#0ea5a5', '#7c5cff', '#e8960c'],
      series: [{ type: 'pie', radius: ['52%', '76%'], center: ['36%', '52%'],
        itemStyle: { borderColor: '#fff', borderWidth: 2, borderRadius: 4 },
        label: { show: false }, labelLine: { show: false },
        data: tiers }],
    }));

    mount(view.querySelector('#payRank'), barRank(
      splitRank(nets.map((n) => ({ name: n.name.replace('阜阳', ''), value: n.ytd })), { top: 6, bottom: 5 }),
      { color: C.red, unit: ' 万', decimals: 0 }));

    mount(view.querySelector('#payBranch'), barRank(
      d.branches.map((b) => ({ name: b.name, value: b.ytd })), { color: C.blue, unit: ' 万', decimals: 0 }));

    view.querySelector('#payTable').appendChild(table(COLS, nets, { sortBy: 'ytd' }));
    view.querySelector('#payExpand').onclick = () => bigTable({
      title: '代发明细 · 网点',
      subtitle: `${d.month} · 月度口径 · ${nets.length} 个网点`,
      columns: COLS, rows: nets,
    });
  },
};

function tile(label, value, unit, foot, color) {
  return `<div class="card kpi" style="--accent:${color}"><div class="heroline"></div>
    <div class="k-label">${label}</div>
    <div class="k-value"><span data-count="${String(value).replace(/,/g, '')}" data-dec="${String(value).includes('.') ? 2 : 0}">0</span><small>${unit}</small></div>
    <div class="k-foot">${foot}</div></div>`;
}
