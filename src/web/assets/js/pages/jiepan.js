/* 定期承接（到期承接率）：支行综合评价 + 网点头尾 + 任意时间段切换
   数据来自 api.build_jiepan（客编明细按「最近到期日期」筛行求和，窗口只在单份快照内切）。 */
import { fmt, countUp, empty, icon, table, bigTable, toast } from '../ui.js';
import { mount, C, barRank, splitRank, scatter } from '../charts.js';
import { authFetch } from '../auth.js';

const pct = (v) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`);
const num = (v, nd = 2) => fmt.n(v, nd);
const signed = (v, nd = 1) => `${Number(v) > 0 ? '+' : ''}${fmt.n(v, nd)}`;
/** 承接率上色：≥100% 红（超额承接），<80% 绿（需帮扶），其余正常 */
const rateCls = (v) => (v == null ? '' : v >= 1 ? 'up' : v < 0.8 ? 'down' : '');

function tile(label, value, suffix, foot, color, cls = '') {
  return `<div class="card kpi" style="--accent:${color}">
    <div class="heroline"></div>
    <div class="k-label">${label}</div>
    <div class="k-value ${cls}">${value}<small>${suffix}</small></div>
    <div class="k-foot">${foot}</div>
  </div>`;
}

/** 区间控件：默认「上周」，可改成取数日往前一个月内任意区间 */
function rangeBar(d) {
  const cov = d.coverage || [d.as_of, d.as_of];
  const per = d.period || {};
  const days = per.start && per.end
    ? Math.round((Date.parse(per.end) - Date.parse(per.start)) / 86400000) + 1 : 0;
  return `<div class="jp-range">
    <span class="jp-lab">统计区间</span>
    <input type="date" id="jpStart" value="${per.start || ''}" min="${cov[0]}" max="${cov[1]}">
    <span class="jp-tilde">至</span>
    <input type="date" id="jpEnd" value="${per.end || ''}" min="${cov[0]}" max="${cov[1]}">
    <button class="btn btn-sm" id="jpApply">查看</button>
    <button class="btn btn-sm" id="jpWeek">上周</button>
    <span class="jp-hint">可选范围 ${fmt.date(cov[0])}–${fmt.date(cov[1])}（本次数据取自 ${fmt.date(d.as_of)}）· 当前 ${days} 天</span>
  </div>`;
}

export default {
  id: 'jiepan',
  title: '定期承接',
  render(view, data, ctx) {
    const d = data.jiepan;
    if (!d?.ok) {
      const why = d?.out_of_range
        ? `<div class="card">${empty('所选区间超出这份数据的取数范围', d.reason || '')}</div>`
        : `<div class="card">${empty('定期承接暂无数据',
          '导入「客编明细」（含 归属支行/机构名称/最近到期日期/定期余额变化），每次导出都覆盖取数日往前一个月')}</div>`;
      view.innerHTML = why;
      return;
    }
    const k = d.kpi, per = d.period;
    const brs = [...(d.branches || [])].sort((a, b) => (a.rank || 99) - (b.rank || 99));
    const nets = d.nets || [];
    const top = d.top_nets || [];
    const tail = d.tail_nets || [];

    view.innerHTML = `
      <div class="page-head">
        <div><h1>定期承接</h1>
          <p>${fmt.date(per.start)}–${fmt.date(per.end)} · ${k.nets} 个网点 / ${k.branches} 家支行 ·
             到期金额 ${fmt.n(k.due_amt / 10000, 0)} 万元</p></div>
        <div class="spacer"></div>
        <span class="chip ${k.unpicked >= 0 ? 'red' : 'green'}">未承接 ${signed(k.unpicked)} 万</span>
        <span class="chip">定期承接率 ${pct(k.rate)}</span>
        <span class="chip">资金承接率 ${pct(k.frate)}</span>
      </div>

      ${rangeBar(d)}

      <div class="grid g5">
        ${tile('定期未承接金额', signed(k.unpicked), '万元',
          `到期金额 ${fmt.n(k.due_amt / 10000, 0)} 万`, k.unpicked >= 0 ? C.red : C.green)}
        ${tile('网均未承接', signed(k.avg_unpicked), '万元/网点',
          `共 ${k.nets} 个实体网点`, k.avg_unpicked >= 0 ? C.red : C.green)}
        ${tile('定期承接率', pct(k.rate), '', '（到期金额+定期变化）÷到期金额', C.violet)}
        ${tile('资金承接率', pct(k.frate), '', '（到期金额+资产变化）÷到期金额', C.blue)}
        ${tile('涉及客编', fmt.n(k.custs), '户', `正向支行 ${k.positive} / ${k.branches} 家`, C.amber)}
      </div>

      <div class="grid g-7-5" style="margin-top:16px">
        <div class="card"><div class="card-head"><h3>支行综合评价</h3>
          <div class="right"><span class="chip">网均未承接 · 定期承接率 · 资金承接率 4:4:2</span></div></div>
          <div class="chart-box chart-lg" id="jpBr"></div></div>
        <div class="card"><div class="card-head"><h3>网均未承接金额</h3>
          <div class="right"><span class="chip amber">黄=前三</span><span class="chip green">绿=后三</span></div></div>
          <div class="chart-box chart-lg" id="jpAvg"></div></div>
      </div>

      <div class="grid g-7-5" style="margin-top:16px">
        <div class="card"><div class="card-head"><h3>网点头尾 · 定期承接率</h3>
          <div class="right"><span class="chip">前 8 / 后 8</span></div></div>
          <div class="chart-box chart-lg" id="jpNet"></div></div>
        <div class="card"><div class="card-head"><h3>优秀先锋（前 8）</h3>
          <div class="right"><span class="chip red">本期通报表扬</span></div></div>
          <div id="jpTop" class="jp-toplist"></div></div>
      </div>

      <div class="grid g-7-5" style="margin-top:16px">
        <div class="card"><div class="card-head"><h3>网均 × 承接率</h3>
          <div class="right"><span class="chip">右上=既省又稳，左下=需帮扶</span></div></div>
          <div class="chart-box chart-lg" id="jpScatter"></div></div>
        <div class="card"><div class="card-head"><h3>后五名网点</h3>
          <div class="right"><span class="chip green">重点帮扶</span></div></div>
          <div id="jpTail" class="jp-toplist"></div></div>
      </div>

      <div class="card" style="margin-top:16px"><div class="card-head"><h3>支行明细</h3>
        <div class="right"><span class="chip">按综合评价排序 · 单位：万元</span></div></div>
        <div id="jpBrTable"></div></div>

      <div class="card" style="margin-top:16px"><div class="card-head"><h3>网点明细 · 前 15</h3>
        <div class="right"><button class="btn btn-sm" id="jpExpand">${icon('expand', 14)} 全屏</button></div></div>
        <div id="jpNetTable"></div></div>`;

    view.querySelectorAll('[data-count]').forEach((el) =>
      countUp(el, Number(el.dataset.count), { decimals: Number(el.dataset.dec || 0) }));

    // 支行综合评价：条形长度用「9 − 名次」（名次越靠前条越长），右侧标注加权分。
    // 不能拿分数直接当长度：1 分和 7.4 分差 7 倍，视觉上会歪成"倍数关系"。
    const N = brs.length;
    mount(view.querySelector('#jpBr'), barRank(
      brs.map((b) => ({
        name: b.name,
        value: N + 1 - (b.rank || N),
        text: `${b.rank} 名 · ${b.score.toFixed(1)} 分`,
        color: b.rank <= 3 ? '#e8b60c' : b.rank >= 6 ? C.green : C.blue,
      })),
      { unit: '', decimals: 0 }));
    // 网均未承接：负数向左，红=好、绿=差按名次
    mount(view.querySelector('#jpAvg'), barRank(
      brs.slice().sort((a, b) => b.avg_unpicked - a.avg_unpicked).map((b) => ({
        name: b.name,
        value: b.avg_unpicked,
        color: b.rank <= 3 ? '#e8b60c' : b.rank >= 6 ? C.green : C.blue,
      })),
      { unit: ' 万元', decimals: 1 }));

    // 网点头尾：按承接率降序，splitRank 取头 8 尾 8
    const netRows = nets.filter((n) => n.rate != null)
      .map((n) => ({ name: n.short || n.name.replace('阜阳', ''), value: +(n.rate * 100).toFixed(2) }));
    mount(view.querySelector('#jpNet'), barRank(
      splitRank(netRows, { top: 8, bottom: 8, unit: '个网点' }),
      { unit: ' %', decimals: 1, color: C.teal }));

    // 散点：横轴网均未承接、纵轴承接率（每点一个网点）
    mount(view.querySelector('#jpScatter'), scatter(
      nets.filter((n) => n.rate != null).map((n) => ({
        name: n.short || n.name.replace('阜阳', ''),
        x: n.bal_d / 10000,
        y: +(n.rate * 100).toFixed(2),
        size: Math.abs(n.bal_d) / 100000 + 6,
        branch: n.branch,
      })),
      { xName: '未承接金额', yName: '定期承接率', xUnit: ' 万', yUnit: '%', showSize: false, yFmt: '%' }));

    // 网点名次（按承接率降序，与明细表一致），头尾列表要用
    const netRanked = nets.map((n, i) => ({ ...n, rank: i + 1 }));
    const row = (n, isTop) => `
      <div class="jp-row">
        <span class="rank-badge ${isTop ? 'top' : ''}">${n.rank || ''}</span>
        <span class="jp-nm">${n.short || n.name.replace('阜阳', '')}</span>
        <span class="jp-br">${n.branch.replace('支行', '')}</span>
        <b class="${rateCls(n.rate)}">${pct(n.rate)}</b>
      </div>`;
    view.querySelector('#jpTop').innerHTML = top.map((n, i) => row({ ...n, rank: i + 1 }, true)).join('')
      || '<div class="empty">暂无</div>';
    // tail_nets 已经是「最差排最后」的五家；倒过来让最差的排在最上面，一眼看到
    const netRankOf = new Map(netRanked.map((n) => [n.name, n.rank]));   
    view.querySelector('#jpTail').innerHTML = [...tail].reverse()
      .map((n) => row({ ...n, rank: netRankOf.get(n.name) }, false)).join('')
      || '<div class="empty">暂无</div>';

    const brCols = [
      { key: 'rank', title: '综合评价', decimals: 0, rank: false, strong: true },
      { key: 'name', title: '支行', sortable: false },
      { key: 'nets', title: '网点数', decimals: 0 },
      { key: 'unpicked', title: '未承接金额', unit: '万', decimals: 2 },
      { key: 'avg_unpicked', title: '网均未承接', unit: '万', decimals: 2 },
      { key: 'rate', title: '定期承接率', render: (v) => `<b class="${rateCls(v)}">${pct(v)}</b>` },
      { key: 'frate', title: '资金承接率', render: (v) => `<b class="${rateCls(v)}">${pct(v)}</b>` },
    ];
    view.querySelector('#jpBrTable').appendChild(table(brCols, brs, { sortBy: 'rank', sortDir: 1 }));

    const netCols = [
      { key: 'rank', title: '排名', decimals: 0, rank: false },
      { key: 'name', title: '网点', sortable: false, render: (v) => String(v).replace('阜阳', '') },
      { key: 'branch', title: '支行', sortable: false, render: (v) => String(v).replace('支行', '') },
      { key: 'bal_d', title: '未承接金额', unit: '万', decimals: 2,
        render: (v) => signed((v || 0) / 10000, 2) },
      { key: 'rate', title: '定期承接率', render: (v) => `<b class="${rateCls(v)}">${pct(v)}</b>` },
      { key: 'frate', title: '资金承接率', render: (v) => `<b class="${rateCls(v)}">${pct(v)}</b>` },
    ];
    view.querySelector('#jpNetTable').appendChild(table(netCols, netRanked, { sortBy: 'rank', sortDir: 1, limit: 15 }));
    view.querySelector('#jpExpand').onclick = () => bigTable({
      title: '定期承接 · 全部网点',
      subtitle: `${fmt.date(per.start)}–${fmt.date(per.end)} · 按定期承接率降序`,
      columns: netCols, rows: netRanked,
    });

    // ---- 区间切换：把 s/e 放到地址栏（app.js 的 loadData 会带上），然后重载数据重画
    const go = async (start, end) => {
      const u = new URL(location.href);
      if (start && end) { u.searchParams.set('s', start); u.searchParams.set('e', end); }
      else { u.searchParams.delete('s'); u.searchParams.delete('e'); }
      history.replaceState(null, '', u.pathname + u.search + u.hash);
      await ctx.reload();
    };
    const st = view.querySelector('#jpStart');
    const en = view.querySelector('#jpEnd');
    view.querySelector('#jpApply').onclick = () => {
      if (!st.value || !en.value) return toast('请把起止日期都选上', 'err');
      go(st.value, en.value);
    };
    view.querySelector('#jpWeek').onclick = () => go(null, null);
  },
};
