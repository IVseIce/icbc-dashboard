/* 基保理（理财 / 基金 / 保险）：三条产品线用页签切换，每条线都是「支行 + 网点」两层。
   数据来自 api.build_jbl（三条线各存各的快照 jbl_lc / jbl_fund / jbl_bx）。

   数都是**源表成表里的原值**（万元），页面不重算、不换算，
   只是把「本期 / 历史各期 / 达成率」排出来看。
   期数不固定：这期 39/40/41，下期 41/42/43 —— 一切按快照里的 `period` / `periods`。 */
import { fmt, countUp, empty, icon, table, bigTable } from '../ui.js';
import { mount, disposeAll, C, barRank, splitRank, lineTrend,
  base, xAxis, yAxis, PALETTE } from '../charts.js';

const RED = '#c8102e', GREEN = '#0f9f6e';
const KIND_ORDER = ['lc', 'fund', 'bx'];
const KIND_LABEL = { lc: '理财', fund: '基金', bx: '保险' };
const KIND_HINT = {
  lc: '理财产品实时通报',
  fund: '基金通报',
  bx: '保险通报',
};

const shortNet = (n) => String(n || '').replace('阜阳', '');

function tile(label, value, suffix, foot, color) {
  return `<div class="card kpi" style="--accent:${color}">
    <div class="heroline"></div>
    <div class="k-label">${label}</div>
    <div class="k-value">${value}<small>${suffix}</small></div>
    <div class="k-foot">${foot}</div>
  </div>`;
}

/** 三个页签**始终都在**（理财/基金/保险），还没导入的置灰并标「未导入」——
    这样同事一眼能看出这个模块将来会有三块，而不是"怎么只有理财"。 */
function tabBar(avail, active, labels) {
  return `<div class="tm-tabs">${KIND_ORDER.map((k) => {
    const on = !!avail.includes(k);
    const cls = active === k ? ' on' : (on ? '' : ' off');
    const tag = on ? '' : '<em class="tm-tab-tag">未导入</em>';
    return `<button class="tm-tab${cls}" data-kind="${k}"${on ? '' : ' disabled'}>
      ${labels[k] || KIND_LABEL[k]}${tag}</button>`;
  }).join('')}</div>`;
}

export default {
  id: 'jbl',
  title: '基保理',

  render(view, data, ctx) {
    const d = data.jbl;
    // kinds 一定是数组；但保险起见再兜一层（接口异常时别让整页炸掉）
    const kinds = Array.isArray(d?.kinds) ? d.kinds : [];
    const avail = kinds.filter((k) => d && d[k] && d[k].ok);
    if (!d?.ok || !avail.length) {
      view.innerHTML = `
        <div class="page-head">
          <div><h1>基保理</h1><p>理财 / 基金 / 保险三条产品线，各自「支行 + 网点」两层</p></div>
        </div>
        ${tabBar([], null, (d && d.labels) || KIND_LABEL)}
        <div class="card">${empty(
          d?.nearest ? `所选日期之前没有数据（最近一期 ${fmt.short(d.nearest)}）` : '基保理暂无数据',
          d?.nearest ? '把日期调到该日之后，或点顶栏「回到最新」'
            : '导入「理财产品实时通报」工作簿即可（只读其中的支行通报 / 网点通报两张子表）')}</div>`;
      return;
    }
    // 当前看哪条线：地址栏 ?k=fund 优先，其次第一条有数据的
    const q = new URL(location.href).searchParams.get('k');
    const active = avail.includes(q) ? q : avail[0];

    // 切产品线 = 整页重画，绑定必须放在重画函数里（经理队伍踩过"第二次点不动"）
    const paint = (k) => renderKind(view, data, ctx, k, avail, paint);
    paint(active);
  },
};

function renderKind(view, data, ctx, kind, avail, paint) {
  disposeAll();                       // 先销毁上一块图表实例，别挂在已移除的节点上
  const d = data.jbl;
  const b = d[kind];
  const labels = d.labels || {};
  const k = b.kpi || {};
  const brs = (b.branches || []).slice();
  const nets = (b.nets || []).slice();
  const trend = b.trend || [];
  const period = b.period;
  const periods = b.periods || [];
  const nBr = brs.length;

  // 历史期数（不含本期）：用来画"各支行按期"的走势与对比
  const hist = periods.filter((p) => p !== period);
  const r = (v, nd = 2) => fmt.n(v, nd);

  view.innerHTML = `
    <div class="page-head">
      <div><h1>基保理 · ${b.label}</h1>
        <p>${fmt.date(b.as_of)}${period != null ? ` · 第 ${period} 期` : ''} ·
           ${nBr} 家支行${nets.length ? ` / ${nets.length} 个网点` : ''} · 单位：万元</p></div>
      <div class="spacer"></div>
      <span class="chip red">本期 ${r(k.current)} 万</span>
      <span class="chip">每期目标 ${r(k.target)} 万</span>
      <span class="chip ${(k.rate || 0) >= 1 ? 'green' : 'amber'}">达成率 ${fmt.pct(k.rate, 1)}</span>
    </div>

    ${tabBar(avail, kind, labels)}

    <div class="grid g4">
      ${tile('本期销量', r(k.current), '万元',
        period != null ? `第 ${period} 期` : '本期', C.red)}
      ${tile('每期目标', r(k.target), '万元',
        `达成率 ${fmt.pct(k.rate, 1)}`, C.blue)}
      ${tile('重点基金', r(k.fund), '万元',
        k.total != null ? `合计（源表列）${r(k.total)} 万` : '源表合计列', C.teal)}
      ${tile('有销量支行', `${k.hit || 0}`, `/ ${nBr} 家`,
        (k.best && k.best.current > 0) ? `最高 ${k.best.name} ${r(k.best.current)} 万` : '本期暂无报数', C.amber)}
    </div>

    <div class="grid g-7-5" style="margin-top:16px">
      <div class="card"><div class="card-head"><h3>按期销量走势</h3>
        <div class="right"><span class="chip amber">本期还在走</span>
          <span class="chip">${trend.length} 期</span></div></div>
        <div class="chart-box chart-md" id="jbTrend"></div></div>
      <div class="card"><div class="card-head"><h3>本期支行排行</h3>
        <div class="right"><span class="chip">单位：万元</span></div></div>
        <div class="chart-box chart-md" id="jbRank"></div></div>
    </div>

    <div class="grid g2" style="margin-top:16px">
      <div class="card"><div class="card-head"><h3>各期支行对比</h3>
        <div class="right"><span class="chip">最近 ${Math.min(6, hist.length + 1)} 期</span></div></div>
        <div class="chart-box chart-lg" id="jbStack"></div></div>
      <div class="card"><div class="card-head"><h3>支行达成率</h3>
        <div class="right"><span class="chip">本期 / 每期目标</span></div></div>
        <div class="chart-box chart-lg" id="jbRate"></div></div>
    </div>

    ${nets.length ? `
    <div class="grid g-7-5" style="margin-top:16px">
      <div class="card"><div class="card-head"><h3>网点头尾 · 本期</h3>
        <div class="right"><span class="chip">前 6 / 后 6</span></div></div>
        <div class="chart-box chart-lg" id="jbNet"></div></div>
      <div class="card"><div class="card-head"><h3>本期零销量网点</h3>
        <div class="right"><span class="chip red">需督办</span></div></div>
        <div id="jbZero" class="tm-list"></div></div>
    </div>` : ''}

    <div class="card" style="margin-top:16px"><div class="card-head"><h3>支行明细</h3>
      <div class="right"><span class="chip">按期销量 + 本期 + 达成率</span>
        <button class="btn btn-sm" id="jbBrExpand" style="margin-left:8px">${icon('expand', 14)} 全屏</button></div></div>
      <div id="jbBrTable"></div></div>

    ${nets.length ? `
    <div class="card" style="margin-top:16px"><div class="card-head"><h3>网点明细</h3>
      <div class="right"><span class="chip">前 15 个</span>
        <button class="btn btn-sm" id="jbNetExpand" style="margin-left:8px">${icon('expand', 14)} 全屏</button></div></div>
      <div id="jbNetTable"></div></div>` : ''}

    ${(!b.has.branches || !b.has.nets) ? `<div class="card" style="margin-top:16px">
      <div class="card-head"><h3>导入说明</h3></div>
      <div class="tm-notes">
        <div>· 本次只导入了 ${b.has.branches ? '支行通报' : '网点通报'}，
          另一张表的图表与明细为空；同一天再导一次缺的那张会自动合并。</div>
      </div></div>` : ''}

    ${(b.notes || []).length ? `<div class="card" style="margin-top:16px">
      <div class="card-head"><h3>识别说明</h3></div>
      <div class="tm-notes">${b.notes.map((x) => `<div>· ${x}</div>`).join('')}</div></div>` : ''}`;

  view.querySelectorAll('[data-count]').forEach((el) =>
    countUp(el, Number(el.dataset.count), { decimals: Number(el.dataset.dec || 0) }));

  // ---- 趋势：按期销量。本期是"还在走"的期，用不同颜色区分，
  // 否则折线看上去像"从 774 暴跌到 41"（其实是本期才过了一两天）
  mount(view.querySelector('#jbTrend'), {
    ...base(),
    grid: { left: 10, right: 16, top: 16, bottom: 6, containLabel: true },
    tooltip: { ...base().tooltip, trigger: 'axis' },
    xAxis: xAxis(trend.map((t) => `第${t.period}期`)),
    yAxis: yAxis({ axisLabel: { color: C.ink3, fontSize: 10 } }),
    series: [{
      name: '销量', type: 'bar', barMaxWidth: 34,
      label: { show: true, position: 'top', color: C.ink2, fontSize: 10,
        formatter: (o) => (o.value == null ? '' : Number(o.value).toFixed(0)) },
      data: trend.map((t) => ({
        value: t.value,
        itemStyle: {
          color: t.period === period ? C.amber : C.red,
          borderRadius: [4, 4, 0, 0],
        },
      })),
    }],
  });

  // ---- 支行本期排行（红前三 / 绿后三，按名次）
  const byCur = brs.slice().sort((x, y) => (y.current || 0) - (x.current || 0));
  mount(view.querySelector('#jbRank'), barRank(
    byCur.map((x, i) => ({
      name: x.name, value: +(x.current || 0).toFixed(4),
      color: i < 3 ? RED : (i >= byCur.length - 3 ? GREEN : C.blue),
    })), { unit: ' 万', decimals: 2 }));

  // ---- 各期支行对比：只取最近几期，横向 grouped bar 太多会看不清，用堆叠柱
  const recent = [period, ...hist.slice().sort((x, y) => y - x)].filter((p) => p != null).slice(0, 6).reverse();
  const histByBr = {};
  (b.branch_hist || []).forEach((h) => { histByBr[h.name] = h.metric || {}; });
  mount(view.querySelector('#jbStack'), {
    ...base(),
    legend: { top: 0, right: 0, icon: 'roundRect', itemWidth: 8, itemHeight: 8,
      textStyle: { color: C.ink3, fontSize: 11 } },
    grid: { left: 10, right: 16, top: 34, bottom: 6, containLabel: true },
    xAxis: xAxis(brs.map((x) => x.name)),
    yAxis: yAxis({ axisLabel: { color: C.ink3, fontSize: 10 } }),
    series: recent.map((p, i) => ({
      name: `第${p}期`, type: 'bar', barMaxWidth: 26, stack: 'p',
      itemStyle: { color: PALETTE[i % PALETTE.length], borderRadius: [3, 3, 0, 0] },
      data: brs.map((x) => {
        const v = (x.metric || {})[String(p)];
        return v == null ? null : +Number(v).toFixed(4);
      }),
    })),
  });

  // ---- 支行达成率
  mount(view.querySelector('#jbRate'), barRank(
    brs.filter((x) => (x.target || 0) > 0)
      .map((x) => ({ name: x.name, value: +((x.rate || 0) * 100).toFixed(2) }))
      .sort((a, c) => c.value - a.value),
    { unit: ' %', decimals: 1, color: C.teal }));

  // ---- 网点头尾
  if (nets.length) {
    const byNet = nets.slice().sort((x, y) => (y.current || 0) - (x.current || 0));
    mount(view.querySelector('#jbNet'), barRank(
      splitRank(byNet.map((x) => ({ name: shortNet(x.name), value: +(x.current || 0).toFixed(4) })),
        { top: 6, bottom: 6, unit: '个网点' }),
      { unit: ' 万', decimals: 2, color: C.violet }));

    const zero = nets.filter((x) => !(x.current > 0));
    view.querySelector('#jbZero').innerHTML = zero.length
      ? zero.slice(0, 12).map((x) => `
        <div class="tm-row">
          <span class="tm-nm">${shortNet(x.name)}</span>
          <span class="tm-sub">${x.branch || ''}</span>
          <b>0</b>
        </div>`).join('') + (zero.length > 12 ? `<div class="tm-row"><span class="tm-sub">还有 ${zero.length - 12} 个…</span></div>` : '')
      : '<div class="empty">本期所有网点都有销量</div>';
  }

  // ---- 支行明细
  const brCols = [
    { key: 'name', title: '支行', rank: false },
    ...recent.map((p) => ({
      key: `p${p}`, title: p === period ? `第${p}期（本期）` : `第${p}期`, unit: '万', decimals: 2,
      value: (row) => (row.metric || {})[String(p)],
    })),
    { key: 'target', title: '每期目标', unit: '万', decimals: 2 },
    { key: 'rate', title: '达成率', render: (v) => (v == null ? '—' : `${(v * 100).toFixed(2)}%`) },
    { key: 'fund', title: '重点基金', unit: '万', decimals: 2 },
    { key: 'total', title: '合计', unit: '万', decimals: 2 },
  ];
  view.querySelector('#jbBrTable').appendChild(table(brCols, brs, { sortBy: `p${period}` }));
  view.querySelector('#jbBrExpand').onclick = () => bigTable({
    title: `基保理 · ${b.label} · 支行明细`,
    subtitle: `${fmt.date(b.as_of)}${period != null ? ` · 第 ${period} 期` : ''} · ${nBr} 家支行 · 单位：万元`,
    columns: brCols, rows: brs,
  });

  // ---- 网点明细
  if (nets.length) {
    const netCols = [
      { key: 'name', title: '网点', rank: false, render: (v) => shortNet(v) },
      { key: 'branch', title: '支行' },
      ...recent.map((p) => ({
        key: `p${p}`, title: p === period ? `第${p}期（本期）` : `第${p}期`, unit: '万', decimals: 2,
        value: (row) => (row.metric || {})[String(p)],
      })),
      { key: 'fund', title: '重点基金', unit: '万', decimals: 2 },
      { key: 'total', title: '合计', unit: '万', decimals: 2 },
    ];
    const netRows = nets.map((x) => ({ ...x, name: shortNet(x.name) }));
    view.querySelector('#jbNetTable').appendChild(table(netCols, netRows, { sortBy: `p${period}`, limit: 15 }));
    view.querySelector('#jbNetExpand').onclick = () => bigTable({
      title: `基保理 · ${b.label} · 网点明细`,
      subtitle: `${fmt.date(b.as_of)} · ${nets.length} 个网点 · 单位：万元`,
      columns: netCols, rows: netRows,
    });
  }

  // ---- 页签：每次重画都要重新绑（DOM 是新的）
  view.querySelectorAll('.tm-tab').forEach((btn) => {
    btn.onclick = () => {
      const next = btn.dataset.kind;
      if (next === kind) return;
      const u = new URL(location.href);
      u.searchParams.set('k', next);
      history.replaceState(null, '', u.pathname + u.search + u.hash);
      paint(next);
    };
  });
}
