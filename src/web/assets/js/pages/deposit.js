/* 定期存款（重点）：余额结构、增量排名、增幅、瀑布、支行明细抽屉 */
import { fmt, countUp, deltaHTML, empty, table, drawer, bigTable, icon } from '../ui.js';
import { mount, base, xAxis, yAxis, C, barRank, waterfall, PALETTE } from '../charts.js';

export default {
  id: 'deposit',
  title: '定期存款',
  nav: '定期存款',
  icon: 'deposit',
  tag: '重点',
  render(view, data) {
    const d = data.deposit;
    if (!d?.ok) { view.innerHTML = `<div class="card">${empty('定期存款暂无数据', '导入《分品种、期限时点报表》本月+上月')}</div>`; return; }
    const k = d.kpi;
    const br = d.branches || [];
    const incSorted = [...br].sort((a, b) => b.inc - a.inc);

    view.innerHTML = `
      <div class="page-head">
        <div>
          <h1>定期存款</h1>
          <p>${fmt.date(d.as_of)} · 较上月（${fmt.date(d.prev_as_of)}） · ${br.length} 家支行 · 单位：万元</p>
        </div>
        <div class="spacer"></div>
        <button class="btn" id="btnTable">明细表 ${icon('arrow', 14)}</button>
      </div>

      <div class="grid g4">
        ${kpiTile('定期存款余额', fmt.n(k.balance_yi, 2), '亿元', `上月 ${fmt.n(k.prev_balance / 10000, 2)} 亿`, 'violet')}
        ${kpiTile('当月增量', fmt.n(k.inc, 2), '万元', `户均 ${fmt.n(k.avg_inc_per_branch, 0)} 万/支行`, 'red')}
        ${kpiTile('当月增幅', (k.rate * 100).toFixed(2), '%', `上月基数 ${fmt.n(k.prev_balance, 0)} 万`, 'blue')}
        <div class="card kpi" style="--accent:${C.teal}"><div class="heroline"></div>
          <div class="k-label">增长面</div>
          <div class="k-value">${k.positive}<small>/ ${br.length} 家正增长</small></div>
          <div class="k-foot">负增长 ${k.negative} 家 · 最高 ${k.best.name}</div>
        </div>
      </div>

      <div class="grid g-7-5" style="margin-top:16px">
        <div class="card">
          <div class="card-head">
            <h3>支行余额与增幅</h3>
            <div class="right"><span class="chip">柱=余额（万元）</span><span class="chip red">线=增幅（%）</span></div>
          </div>
          <div class="chart-box chart-lg" id="depMain"></div>
        </div>
        <div class="card">
          <div class="card-head"><h3>余额结构</h3><div class="right"><span class="chip">各支行占比</span></div></div>
          <div class="chart-box chart-lg" id="depPie"></div>
        </div>
      </div>

      <div class="grid g2" style="margin-top:16px">
        <div class="card">
          <div class="card-head"><h3>当月增量排名</h3><div class="right"><span class="chip red">红=正 / 绿=负</span></div></div>
          <div class="chart-box chart-md" id="depRank"></div>
        </div>
        <div class="card">
          <div class="card-head"><h3>支行卡片</h3><div class="right"><span class="chip">点击查看明细</span></div></div>
          <div class="grid g2" style="gap:10px" id="depCards"></div>
        </div>
      </div>`;

    view.querySelectorAll('[data-count]').forEach((el) => countUp(el, Number(el.dataset.count), { decimals: Number(el.dataset.dec || 0) }));

    // 主图：余额柱 + 增幅线
    mount(view.querySelector('#depMain'), base({
      legend: { top: 0, right: 0, icon: 'roundRect', itemWidth: 9, itemHeight: 9, textStyle: { color: C.ink3, fontSize: 11 } },
      grid: { left: 10, right: 16, top: 36, bottom: 6, containLabel: true },
      tooltip: { ...base().tooltip, formatter: (ps) => {
        const b = ps[0];
        const line = ps.find((p) => p.seriesName === '增幅');
        const row = br.find((x) => x.name === b.name) || {};
        return `<b>${b.name}</b><br/>余额 ${fmt.n(row.cur, 2)} 万<br/>增量 ${fmt.sign(row.inc, 2)} 万<br/>增幅 ${row.rate >= 0 ? '+' : ''}${(row.rate * 100).toFixed(2)}%`;
      } },
      xAxis: xAxis(br.map((b) => b.name)),
      yAxis: [yAxis({ name: '', axisLabel: { color: C.ink3, fontSize: 10 } }),
        yAxis({ position: 'right', splitLine: { show: false }, axisLabel: { color: C.red, fontSize: 10, formatter: '{value}%' } })],
      series: [
        {
          name: '余额', type: 'bar', barWidth: '52%', data: br.map((b) => b.cur),
          itemStyle: {
            borderRadius: [6, 6, 0, 0],
            color: new window.echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: '#8ea7f0' }, { offset: 1, color: '#c9d7f9' }]),
          },
        },
        {
          name: '增幅', type: 'line', yAxisIndex: 1, smooth: 0.35, symbolSize: 6,
          data: br.map((b) => +(b.rate * 100).toFixed(2)),
          lineStyle: { width: 2, color: C.red }, itemStyle: { color: C.red },
          label: { show: true, position: 'top', color: C.red, fontSize: 10, formatter: (p) => `${p.value}%` },
        },
      ],
    }));

    // 余额结构环形图
    mount(view.querySelector('#depPie'), base({
      tooltip: { ...base().tooltip, trigger: 'item', formatter: (p) => `${p.name}<br/><b>${fmt.n(p.value, 0)}</b> 万（${p.percent}%）` },
      legend: { orient: 'vertical', right: 0, top: 'middle', icon: 'circle', itemWidth: 8, itemHeight: 8,
        textStyle: { color: C.ink3, fontSize: 11 }, formatter: (n) => n.replace('支行', '') },
      series: [{
        type: 'pie', radius: ['52%', '76%'], center: ['38%', '50%'], avoidLabelOverlap: true,
        itemStyle: { borderColor: '#fff', borderWidth: 2, borderRadius: 4 },
        color: ['#2563eb', '#0ea5a5', '#7c5cff', '#e8960c', '#0891b2', '#64748b', '#ec4899', '#12a06a'],
        label: { show: false }, labelLine: { show: false },
        emphasis: { scale: true, scaleSize: 6, itemStyle: { shadowBlur: 16, shadowColor: 'rgba(13,27,49,.2)' } },
        data: br.map((b) => ({ name: b.name, value: b.cur })),
      }],
      graphic: [{ type: 'text', left: '32%', top: '46%', style: {
        text: `${(br.reduce((a, b) => a + b.cur, 0) / 10000).toFixed(1)} 亿`, fill: C.ink, fontSize: 18, fontWeight: 700 } },
        { type: 'text', left: '34%', top: '56%', style: { text: '合计余额', fill: '#8494ab', fontSize: 11 } }],
    }));

    // 增量排名（正负发散）
    mount(view.querySelector('#depRank'), base({
      grid: { left: 10, right: 48, top: 10, bottom: 6, containLabel: true },
      tooltip: { ...base().tooltip, formatter: (p) => `${p[0].name}<br/><b>${fmt.sign(p[0].value, 2)}</b> 万` },
      xAxis: yAxis({ show: false, min: (v) => Math.min(0, v.min * 1.08), max: (v) => Math.max(0, v.max * 1.06) }),
      yAxis: xAxis(incSorted.map((b) => b.name), { axisLine: { show: false } }),
      series: [{
        type: 'bar', barWidth: '56%',
        data: incSorted.map((b) => ({
          value: b.inc,
          itemStyle: { borderRadius: b.inc >= 0 ? [0, 5, 5, 0] : [5, 0, 0, 5], color: b.inc >= 0 ? C.red : C.green },
        })),
        label: { show: true, position: 'right', color: C.ink2, fontSize: 10.5, formatter: (p) => fmt.sign(p.value, 0) },
        markLine: {
          silent: true, symbol: 'none', lineStyle: { color: '#d6deea', width: 1 }, label: { show: false },
          data: [{ xAxis: 0 }],
        },
      }],
    }));

    // 支行卡片
    const cards = view.querySelector('#depCards');
    cards.innerHTML = br.map((b) => `
      <div class="card clickable" style="padding:12px;box-shadow:none;border-color:var(--line)" data-b="${b.name}">
        <div style="display:flex;align-items:center;gap:6px">
          <b style="font-size:13px">${b.name}</b>
          <span class="chip" style="margin-left:auto;font-size:10px">${(b.share * 100).toFixed(1)}%</span>
        </div>
        <div style="font-size:19px;font-weight:700;letter-spacing:-.4px;margin-top:4px">${fmt.n(b.cur, 0)}<small style="font-size:11px;color:var(--ink-3)"> 万</small></div>
        <div style="font-size:11.5px;display:flex;gap:8px;margin-top:2px">
          ${deltaHTML(b.inc, fmt.sign(b.inc, 0) + ' 万')}
          <span style="color:var(--ink-3)">${b.rate >= 0 ? '+' : ''}${(b.rate * 100).toFixed(2)}%</span>
        </div>
      </div>`).join('');
    cards.querySelectorAll('[data-b]').forEach((el) => {
      el.onclick = () => showBranch(br.find((x) => x.name === el.dataset.b), k, br);
    });

    // 明细表（全屏）
    view.querySelector('#btnTable').onclick = () => bigTable({
      title: '定期存款 · 支行明细',
      subtitle: `${fmt.date(d.as_of)} · 较上月 ${fmt.date(d.prev_as_of)} · 单位：万元`,
      columns: DEP_COLS, rows: br,
    });
  },
};

const DEP_COLS = [
  { key: 'name', title: '支行', rank: false },
  { key: 'prev', title: '上月余额', decimals: 2 },
  { key: 'cur', title: '本月余额', decimals: 2 },
  { key: 'inc', title: '当月增量', decimals: 2, render: (v) => `<span class="delta ${v >= 0 ? 'up' : 'down'}">${fmt.sign(v, 2)}</span>` },
  { key: 'rate', title: '增幅', render: (v) => `${v >= 0 ? '+' : ''}${(v * 100).toFixed(2)}%` },
  { key: 'share', title: '余额占比', render: (v) => `${(v * 100).toFixed(2)}%` },
  { key: 'rank_bal', title: '余额排名' },
  { key: 'rank_inc', title: '增量排名' },
];

function kpiTile(label, value, unit, foot, accent) {
  const map = { violet: C.violet, red: C.red, blue: C.blue, teal: C.teal };
  return `<div class="card kpi" style="--accent:${map[accent] || C.blue}">
    <div class="heroline"></div>
    <div class="k-label">${label}</div>
    <div class="k-value"><span data-count="${String(value).replace(/,/g, '')}" data-dec="${String(value).includes('.') ? 2 : 0}">0</span><small>${unit}</small></div>
    <div class="k-foot">${foot}</div>
  </div>`;
}

function showBranch(b, k, all) {
  if (!b) return;
  const share = all.reduce((s, x) => s + x.cur, 0);
  drawer(`${b.name}支行`, `
    <div class="kv"><span>本月余额</span><b>${fmt.n(b.cur, 2)} 万元</b></div>
    <div class="kv"><span>上月余额</span><b>${fmt.n(b.prev, 2)} 万元</b></div>
    <div class="kv"><span>当月增量</span><b class="delta ${b.inc >= 0 ? 'up' : 'down'}">${fmt.sign(b.inc, 2)} 万元</b></div>
    <div class="kv"><span>当月增幅</span><b>${b.rate >= 0 ? '+' : ''}${(b.rate * 100).toFixed(2)}%</b></div>
    <div class="kv"><span>全行占比</span><b>${(b.share * 100).toFixed(2)}%</b></div>
    <div class="kv"><span>余额排名</span><b>第 ${b.rank_bal} / ${all.length}</b></div>
    <div class="kv"><span>增量排名</span><b>第 ${b.rank_inc} / ${all.length}</b></div>
    <div style="margin-top:16px">
      ${miniCompare(b, all)}
    </div>
    <p style="color:var(--ink-3);font-size:11.5px;margin-top:14px">
      全行合计 ${fmt.n(k.cur_bal || k.balance, 0)} 万元，本支行贡献 ${((b.share || 0) * 100).toFixed(2)}%。
    </p>`, `${fmt.date(k.as_of)} · 数据来源：分品种、期限时点报表`);
}

function miniCompare(b, all) {
  const max = Math.max(...all.map((x) => x.inc), 1);
  const rows = [{ name: b.name, v: b.inc, me: true }]
    .concat(all.filter((x) => x.name !== b.name).sort((a, c) => c.inc - a.inc).slice(0, 4).map((x) => ({ name: x.name, v: x.inc })));
  return rows.map((r) => `
    <div style="display:flex;align-items:center;gap:8px;margin:6px 0;font-size:11.5px">
      <span style="width:34px;color:${r.me ? 'var(--ink)' : 'var(--ink-3)'};font-weight:${r.me ? 700 : 400}">${r.name}</span>
      <div style="flex:1;height:8px;background:#f1f4f9;border-radius:4px;overflow:hidden">
        <i style="display:block;height:100%;width:${Math.max(2, Math.abs(r.v) / max * 100)}%;border-radius:4px;background:${r.v >= 0 ? (r.me ? C.red : '#f2a5b2') : C.green}"></i>
      </div>
      <span style="width:64px;text-align:right;color:${r.v >= 0 ? 'var(--red)' : 'var(--green)'};font-weight:600">${fmt.sign(r.v, 0)}</span>
    </div>`).join('');
}
