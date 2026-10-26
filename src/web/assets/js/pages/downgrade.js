/* 降级挽回：支行评价排行 + 营销先锋 + 网点表现（重点看头尾） */
import { fmt, countUp, empty, icon, table, bigTable } from '../ui.js';
import { mount, C, barRank, splitRank } from '../charts.js';

const num = (v, nd = 1) => fmt.n(v, nd);
const signed = (v, nd = 1) => `${Number(v) > 0 ? '+' : ''}${fmt.n(v, nd)}`;

function tile(label, value, suffix, foot, color, cls = '') {
  return `<div class="card kpi" style="--accent:${color}">
    <div class="heroline"></div>
    <div class="k-label">${label}</div>
    <div class="k-value ${cls}">${value}<small>${suffix}</small></div>
    <div class="k-foot">${foot}</div>
  </div>`;
}

export default {
  id: 'downgrade',
  title: '降级挽回',
  render(view, data) {
    const d = data.downgrade;
    if (!d?.ok) {
      view.innerHTML = `<div class="card">${empty('降级挽回暂无数据',
        '导入「客编资产明细 + 客编→支行/网点映射」两份表')}</div>`;
      return;
    }
    const k = d.kpi, per = d.period;
    const brs = [...(d.branches || [])].sort((a, b) => a.rank - b.rank);
    const nets = [...(d.nets || [])].sort((a, b) => a.rank - b.rank);

    view.innerHTML = `
      <div class="page-head">
        <div><h1>降级挽回</h1>
          <p>${per.label_cn} · ${k.nets} 个网点 · ${fmt.n(k.customers)} 个降级客编</p></div>
        <div class="spacer"></div>
        <span class="chip">数据日 ${fmt.date(d.as_of)}</span>
        <span class="chip ${k.asset >= 0 ? 'red' : 'green'}">资产 ${signed(k.asset)} 万</span>
        <span class="chip ${k.dep >= 0 ? 'red' : 'green'}">存款 ${signed(k.dep)} 万</span>
      </div>

      <div class="grid g5">
        ${tile('本旬资产提升', signed(k.asset), '万元', `网均 ${signed(k.asset_avg)} 万元`, k.asset >= 0 ? C.red : C.green)}
        ${tile('本旬存款提升', signed(k.dep), '万元', `网均 ${signed(k.dep_avg)} 万元`, k.dep >= 0 ? C.red : C.green)}
        ${tile('综合评价', signed(k.score), '', '网均资产 + 网均存款，1:1', C.violet)}
        ${tile('正向支行', `${k.up}`, '/ 8 家', `下降 ${k.down} 家`, C.blue)}
        ${tile('降级客编', fmt.n(k.customers), '人', `覆盖 ${k.nets} 个实体网点`, C.amber)}
      </div>

      <div class="grid g-7-5" style="margin-top:16px">
        <div class="card"><div class="card-head"><h3>支行综合评价</h3>
          <div class="right"><span class="chip amber">黄=前二</span><span class="chip green">绿=后二</span></div></div>
          <div class="chart-box chart-lg" id="dgBr"></div></div>
        <div class="card"><div class="card-head"><h3>网均资产提升</h3>
          <div class="right"><span class="chip">万元 / 网点</span></div></div>
          <div class="chart-box chart-lg" id="dgAvg"></div></div>
      </div>

      <div class="grid g-7-5" style="margin-top:16px">
        <div class="card"><div class="card-head"><h3>营销先锋 · 网点头尾</h3>
          <div class="right"><span class="chip">资产 + 存款 提升额</span></div></div>
          <div class="chart-box chart-lg" id="dgNet"></div></div>
        <div class="card"><div class="card-head"><h3>后五名网点</h3>
          <div class="right"><span class="chip green">重点帮扶</span></div></div>
          <div id="dgBottom" style="display:flex;flex-direction:column;gap:7px;padding-top:4px"></div></div>
      </div>

      <div class="card" style="margin-top:16px"><div class="card-head"><h3>支行明细</h3>
        <div class="right"><span class="chip">单位：万元</span></div></div>
        <div id="dgBrTable"></div></div>

      <div class="card" style="margin-top:16px"><div class="card-head"><h3>网点明细 · 前 15</h3>
        <div class="right"><button class="btn btn-sm" id="dgExpand">${icon('expand', 14)} 全屏</button></div></div>
        <div id="dgNetTable"></div></div>`;

    view.querySelectorAll('[data-count]').forEach((el) =>
      countUp(el, Number(el.dataset.count), { decimals: Number(el.dataset.dec || 0) }));

    // 支行综合评价：红黄绿按 hl 上色
    mount(view.querySelector('#dgBr'), barRank(
      brs.slice().map((b) => ({
        name: b.name,
        value: b.score,
        color: b.hl === 'yellow' ? '#e8b60c' : b.hl === 'green' ? C.green : C.blue,
      })),
      { unit: ' 分', decimals: 1 }));

    mount(view.querySelector('#dgAvg'), barRank(
      brs.slice().sort((a, b) => a.asset_avg - b.asset_avg)
        .map((b) => ({ name: b.name, value: b.asset_avg, color: b.asset_avg >= 0 ? C.red : C.green })),
      { unit: ' 万元', decimals: 1 }));

    // 网点头尾：全部 40 个，用 splitRank 截成 头8 + 省略号 + 尾8
    const netRows = nets.map((n) => ({ name: n.name.replace('阜阳', ''), value: n.sum,
                                       branch: n.branch, customers: n.customers }));
    mount(view.querySelector('#dgNet'), barRank(
      splitRank(netRows, { top: 8, bottom: 8, unit: '个网点' }),
      { unit: ' 万元', decimals: 1 }));

    const bottom5 = nets.slice(-5).reverse();
    view.querySelector('#dgBottom').innerHTML = bottom5.map((n) => `
      <div style="display:flex;align-items:center;gap:8px;padding:7px 9px;border-radius:9px;background:#fbfcfe">
        <span class="rank-badge">${n.rank}</span>
        <span style="font-size:12px;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
          ${n.name.replace('阜阳', '')}</span>
        <span style="font-size:11px;color:var(--ink-3)">${n.branch}</span>
        <b style="font-size:12px;color:var(--green)">${fmt.n(n.sum, 1)}</b>
      </div>`).join('');

    const brCols = [
      { key: 'rank', title: '排序', decimals: 0, rank: false },
      { key: 'name', title: '支行', sortable: false },
      { key: 'nets', title: '网点数', decimals: 0 },
      { key: 'score', title: '综合评价', decimals: 1, strong: true },
      { key: 'asset', title: '本旬资产提升', unit: '万', decimals: 1 },
      { key: 'asset_avg', title: '网均资产', unit: '万', decimals: 1 },
      { key: 'dep', title: '本旬存款提升', unit: '万', decimals: 1 },
      { key: 'dep_avg', title: '网均存款', unit: '万', decimals: 1 },
      { key: 'customers', title: '降级客编', decimals: 0 },
    ];
    view.querySelector('#dgBrTable').appendChild(table(brCols, brs, { sortBy: 'score' }));

    // 网点按综合评价（资产+存款 各 50%）降序，与导出表一致
    const netByScore = [...nets]
      .map((n) => ({ ...n, score: Math.round((((n.asset || 0) + (n.dep || 0)) / 2) * 10000) / 10000 }))
      .sort((a, b) => b.score - a.score)
      .map((n, i) => ({ ...n, score_rank: i + 1 }));
    const netCols = [
      { key: 'score_rank', title: '排名', decimals: 0, rank: false },
      { key: 'name', title: '网点', sortable: false },
      { key: 'branch', title: '支行', sortable: false },
      { key: 'customers', title: '客户数', decimals: 0 },
      { key: 'asset', title: '资产提升', unit: '万', decimals: 1 },
      { key: 'dep', title: '存款提升', unit: '万', decimals: 1 },
      { key: 'score', title: '综合评价', unit: '万', decimals: 1, strong: true },
    ];
    view.querySelector('#dgNetTable').appendChild(table(netCols, netByScore, { sortBy: 'score', limit: 15 }));

    view.querySelector('#dgExpand').onclick = () => bigTable({
      title: '降级挽回 · 全部网点',
      subtitle: `${per.label_cn} · 单位：万元`,
      columns: netCols,
      rows: netByScore,
    });
  },
};
