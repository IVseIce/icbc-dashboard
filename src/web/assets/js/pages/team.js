/* 经理队伍：财客 / 远维 两块（同一个模块，页签切换）
   - 财客：支行 8 → 网点 40 → 客户经理 49 三级
   - 远维：支行 8 → 客户经理 10 两级（远维没有网点）
   数据来自 api.build_team，金额单位是**原始万元**（财客成表把理财换成亿元、远维不换，
   页面上统一按「亿元 / 万元 / 户」各自标注，不再二次换算成别的口径）。 */
import { fmt, countUp, empty, icon, table, bigTable, toast } from '../ui.js';
import { mount, disposeAll, C, barRank, splitRank } from '../charts.js';

const RED = '#e11d48', GREEN = '#0f9f6e';
const BLOCK_LABEL = { ck: '财客', yw: '远维' };

/** 万元 → 亿元 */
const yi = (v) => (v == null ? null : v / 10000);
const signed = (v, nd = 2) => `${Number(v) > 0 ? '+' : ''}${fmt.n(v, nd)}`;

function tile(label, value, suffix, foot, color) {
  return `<div class="card kpi" style="--accent:${color}">
    <div class="heroline"></div>
    <div class="k-label">${label}</div>
    <div class="k-value">${value}<small>${suffix}</small></div>
    <div class="k-foot">${foot}</div>
  </div>`;
}

/** 成表红绿规则：前二红、后二绿（按名次，不按正负） */
function rankColor(rank, n) {
  if (rank == null) return C.blue;
  if (rank <= 2) return RED;
  if (rank > n - 2) return GREEN;
  return C.blue;
}

function tabBar(blocks, active) {
  if (blocks.length < 2) return '';
  const one = (id) => `<button class="tm-tab${active === id ? ' on' : ''}" data-block="${id}">
      ${BLOCK_LABEL[id]}</button>`;
  return `<div class="tm-tabs">${blocks.map(one).join('')}</div>`;
}

export default {
  id: 'team',
  title: '经理队伍',

  render(view, data, ctx) {
    const d = data.team;
    const blocks = (d?.blocks || []).filter((b) => d[b]);
    if (!d?.ok || !blocks.length) {
      view.innerHTML = `<div class="card">${empty('经理队伍暂无数据',
        '导入「财富客户经理经营业绩通报」或「远维经理营销PK赛通报」的明细表（可只导一个）')}</div>`;
      return;
    }

    // 当前看哪一块：地址栏 ?b=yw 优先；否则默认第一个
    const q = new URL(location.href).searchParams.get('b');
    const active = blocks.includes(q) ? q : blocks[0];

    // 切块 = 整页重画，所以页签不能只绑一次：
    // renderBlock 每次都会重建 DOM，绑定必须放在它里面（踩过：第二次点没反应）
    const paint = (block) => renderBlock(view, data, ctx, block, blocks, paint);
    paint(active);
  },
};

function renderBlock(view, data, ctx, block, blocks, paint) {
  disposeAll();                       // 先销毁上一块的图表实例，别让它们挂在已移除的节点上
  const d = data.team;
  const b = d[block];
  const meta = { ck: { who: '财客', cust: '50万元以上客户', ins: '期缴保险' },
    yw: { who: '远维', cust: '10万元以上客户', ins: null } }[block];
  const brs = (b.branches || []).slice().sort((x, y) => (x.rank || 99) - (y.rank || 99));
  const nets = b.nets || [];
  const mgrs = (b.mgr_rows || []).slice().sort((x, y) => (y.score || 0) - (x.score || 0));
  const t = b.total || {};
  const nBr = brs.length;

  view.innerHTML = `
    <div class="page-head">
      <div><h1>经理队伍</h1>
        <p>${fmt.date(d.as_of)} · ${meta.who}客户经理 ${b.n || 0} 人 ·
           ${nBr} 家支行${b.has_net ? ` / ${nets.length} 个网点` : '（无网点维度）'}
           · 累计口径（较年初）</p></div>
      <div class="spacer"></div>
      <span class="chip">平均总得分 ${fmt.n(t.score, 2)}</span>
      <span class="chip red">存款增量 ${fmt.n(yi(t.dep_inc), 2)} 亿</span>
      <span class="chip blue">非存增量 ${fmt.n(yi(t.nstock_inc), 2)} 亿</span>
    </div>

    ${tabBar(blocks, block)}

    <div class="grid g6">
      ${tile('管户日均存款', fmt.n(yi(t.dep_stock), 2), '亿元',
        `较年初 ${signed(yi(t.dep_inc), 2)} 亿`, C.violet)}
      ${tile('管户日均非存', fmt.n(yi(t.nstock_stock), 2), '亿元',
        `较年初 ${signed(yi(t.nstock_inc), 2)} 亿`, C.blue)}
      ${tile(meta.cust, fmt.n(t.c50_inc, 0), '户',
        `存量 ${fmt.n(t.c50_stock, 0)} 户`, C.teal)}
      ${tile('融e借', fmt.n(t.rej_inc, 0), '万元',
        `余额 ${fmt.n(t.rej_stock, 0)} 万`, C.red)}
      ${tile('卡分期', fmt.n(t.kp_inc, 0), '万元',
        `余额 ${fmt.n(t.kp_stock, 0)} 万`, C.amber)}
      ${tile('企业微信净增', fmt.n(t.wx_net, 0), '户',
        `好友 ${fmt.n(t.wx_friends, 0)} 户`, C.green)}
    </div>

    <div class="grid g-7-5" style="margin-top:16px">
      <div class="card"><div class="card-head"><h3>支行总得分</h3>
        <div class="right"><span class="chip red">红=前二</span><span class="chip green">绿=后二</span></div></div>
        <div class="chart-box chart-md" id="tmBrScore"></div></div>
      <div class="card"><div class="card-head"><h3>支行存款增量</h3>
        <div class="right"><span class="chip">单位：亿元</span></div></div>
        <div class="chart-box chart-md" id="tmBrDep"></div></div>
    </div>

    ${b.has_net ? `
    <div class="grid g-7-5" style="margin-top:16px">
      <div class="card"><div class="card-head"><h3>网点总得分 · 头尾</h3>
        <div class="right"><span class="chip">前 6 / 后 6</span></div></div>
        <div class="chart-box chart-lg" id="tmNet"></div></div>
      <div class="card"><div class="card-head"><h3>网点最差的 6 个</h3>
        <div class="right"><span class="chip green">重点帮扶</span></div></div>
        <div id="tmNetTail" class="tm-list"></div></div>
    </div>` : ''}

    <div class="grid g-7-5" style="margin-top:16px">
      <div class="card"><div class="card-head"><h3>客户经理 · 头尾</h3>
        <div class="right"><span class="chip">按总得分，前 6 / 后 6</span></div></div>
        <div class="chart-box chart-lg" id="tmMgr"></div></div>
      <div class="card"><div class="card-head"><h3>客户经理 · 前五名</h3>
        <div class="right"><span class="chip red">通报表扬</span></div></div>
        <div id="tmMgrTop" class="tm-list"></div></div>
    </div>

    <div class="card" style="margin-top:16px"><div class="card-head"><h3>支行明细</h3>
      <div class="right"><span class="chip">按总得分排序 · 金额单位见列名</span>
        <button class="btn btn-sm" id="tmBrExpand" style="margin-left:8px">${icon('expand', 14)} 全屏</button></div></div>
      <div id="tmBrTable"></div></div>

    ${b.has_net ? `
    <div class="card" style="margin-top:16px"><div class="card-head"><h3>网点明细</h3>
      <div class="right"><span class="chip">前 15 个</span>
        <button class="btn btn-sm" id="tmNetExpand" style="margin-left:8px">${icon('expand', 14)} 全屏</button></div></div>
      <div id="tmNetTable"></div></div>` : ''}

    <div class="card" style="margin-top:16px"><div class="card-head"><h3>客户经理明细</h3>
      <div class="right"><span class="chip">前 15 人</span>
        <button class="btn btn-sm" id="tmMgrExpand" style="margin-left:8px">${icon('expand', 14)} 全屏</button></div></div>
      <div id="tmMgrTable"></div></div>

    ${(d.notes || []).length ? `<div class="card" style="margin-top:16px">
      <div class="card-head"><h3>导入说明</h3></div>
      <div class="tm-notes">${d.notes.map((x) => `<div>· ${x}</div>`).join('')}</div></div>` : ''}`;

  view.querySelectorAll('[data-count]').forEach((el) =>
    countUp(el, Number(el.dataset.count), { decimals: Number(el.dataset.dec || 0) }));

  // 支行总得分：红前二 / 绿后二
  mount(view.querySelector('#tmBrScore'), barRank(
    brs.map((x) => ({ name: x.name, value: +(x.score || 0).toFixed(4),
      text: `${(x.score || 0).toFixed(2)} 分`,
      color: rankColor(x.rank, nBr) })),
    { unit: ' 分', decimals: 2 }));

  // 支行存款增量：红涨绿跌
  mount(view.querySelector('#tmBrDep'), barRank(
    brs.slice().sort((a, c) => (c.dep_inc || 0) - (a.dep_inc || 0)).map((x) => ({
      name: x.name, value: +(yi(x.dep_inc) || 0).toFixed(4),
      color: (x.dep_inc || 0) >= 0 ? RED : GREEN })),
    { unit: ' 亿', decimals: 2 }));

  // 网点头尾
  if (b.has_net && nets.length) {
    mount(view.querySelector('#tmNet'), barRank(
      splitRank(nets.map((x) => ({ name: shortNet(x.name), value: +(x.score || 0).toFixed(4) })),
        { top: 6, bottom: 6, unit: '个网点' }),
      { unit: ' 分', decimals: 2, color: C.teal }));

    const tail = nets.slice().sort((x, y) => (x.score || 0) - (y.score || 0)).slice(0, 6);
    view.querySelector('#tmNetTail').innerHTML = tail.map((x) => `
      <div class="tm-row">
        <span class="tm-nm">${shortNet(x.name)}</span>
        <span class="tm-sub">${(x.branch || '').replace('支行', '')} · ${x.mgrs} 人</span>
        <b>${(x.score || 0).toFixed(2)}</b>
      </div>`).join('') || '<div class="empty">暂无</div>';
  }

  // 客户经理头尾
  mount(view.querySelector('#tmMgr'), barRank(
    splitRank(mgrs.map((x) => ({ name: `${x.mgr}`, value: +(x.score || 0).toFixed(4) })),
      { top: 6, bottom: 6, unit: '人' }),
    { unit: ' 分', decimals: 2, color: C.violet }));

  view.querySelector('#tmMgrTop').innerHTML = mgrs.slice(0, 5).map((x, i) => `
    <div class="tm-row">
      <span class="rank-badge ${i < 3 ? 'top' : ''}">${i + 1}</span>
      <span class="tm-nm">${x.mgr}</span>
      <span class="tm-sub">${shortNet(x.net || x.branch)}</span>
      <b>${(x.score || 0).toFixed(2)}</b>
    </div>`).join('') || '<div class="empty">暂无</div>';

  // ---- 明细表
  const brCols = brColumns(block, nBr);
  const brRows = brs.map((x) => ({ ...x, _net: undefined }));
  view.querySelector('#tmBrTable').appendChild(table(brCols, brRows, { sortBy: 'rank', sortDir: 1 }));
  view.querySelector('#tmBrExpand').onclick = () => bigTable({
    title: `经理队伍 · ${meta.who}支行明细`,
    subtitle: `${fmt.date(d.as_of)} · ${nBr} 家支行 · 累计口径（较年初）`,
    columns: brCols, rows: brRows,
  });

  if (b.has_net && nets.length) {
    const netCols = netColumns(block);
    const netRows = nets.map((x) => ({ ...x, name: shortNet(x.name) }));
    view.querySelector('#tmNetTable').appendChild(table(netCols, netRows, { sortBy: 'score', limit: 15 }));
    view.querySelector('#tmNetExpand').onclick = () => bigTable({
      title: `经理队伍 · ${meta.who}网点明细`,
      subtitle: `${fmt.date(d.as_of)} · ${nets.length} 个网点 · 按总得分排序`,
      columns: netCols, rows: netRows,
    });
  }

  const mgrCols = mgrColumns(block);
  const mgrRows = mgrs.map((x) => ({ ...x, net: shortNet(x.net || ''), branch: (x.branch || '').replace('支行', '') }));
  view.querySelector('#tmMgrTable').appendChild(table(mgrCols, mgrRows, { sortBy: 'score', limit: 15 }));
  view.querySelector('#tmMgrExpand').onclick = () => bigTable({
    title: `经理队伍 · ${meta.who}客户经理明细`,
    subtitle: `${fmt.date(d.as_of)} · ${mgrRows.length} 人 · 按总得分排序`,
    columns: mgrCols, rows: mgrRows,
  });

  // 页签：每次重画都要重新绑（DOM 是新的）
  view.querySelectorAll('.tm-tab').forEach((btn) => {
    btn.onclick = () => {
      const next = btn.dataset.block;
      if (next === block) return;
      const u = new URL(location.href);
      u.searchParams.set('b', next);
      history.replaceState(null, '', u.pathname + u.search + u.hash);
      paint(next);
    };
  });
}

/* ---------------------------------------------------------------- 工具 */
function shortNet(n) {
  if (!n) return '';
  return String(n).replace('阜阳', '').replace('支行营业室', '营业室');
}

const scoreCell = (v, rank, n) =>
  `<b style="color:${rankColor(rank, n)}">${(v || 0).toFixed(2)}</b>`;

const deltaCell = (v, nd = 2) =>
  `<span class="delta ${(v || 0) > 0 ? 'up' : (v || 0) < 0 ? 'down' : 'flat'}">${signed(v, nd)}</span>`;

/** 支行明细的列（两块共用，只是"期缴保险"财客才有） */
function brColumns(block, n) {
  const cols = [
    { key: 'rank', title: '排名', decimals: 0, rank: false, strong: true },
    { key: 'name', title: '支行', sortable: false, render: (v) => String(v).replace('支行', '') },
    { key: 'score', title: '总得分', render: (v, r) => scoreCell(v, r.rank, n) },
    { key: 'mgrs', title: '经理数', decimals: 0 },
    { key: 'dep_stock', title: '存款存量', unit: '亿', render: (v) => fmt.n(yi(v), 2) },
    { key: 'dep_inc', title: '存款增量', unit: '亿', render: (v) => deltaCell(yi(v), 2) },
    { key: 'nstock_stock', title: '非存存量', unit: '亿', render: (v) => fmt.n(yi(v), 2) },
    { key: 'nstock_inc', title: '非存增量', unit: '亿', render: (v) => deltaCell(yi(v), 2) },
    { key: 'c50_inc', title: '50万以上客户增量', unit: '户', render: (v) => deltaCell(v, 0) },
    { key: 'rej_inc', title: '融e借增量', unit: '万', render: (v) => deltaCell(v, 0) },
    { key: 'kp_inc', title: '卡分期增量', unit: '万', render: (v) => deltaCell(v, 1) },
    { key: 'mobile_inc', title: '手机银行净增', unit: '户', render: (v) => deltaCell(v, 0) },
    { key: 'sb_inc', title: '社保卡净增', unit: '户', render: (v) => deltaCell(v, 0) },
    { key: 'yl_inc', title: '养老金净增', unit: '户', render: (v) => deltaCell(v, 0) },
    { key: 'debit_inc', title: '借记卡绑卡净增', unit: '户', render: (v) => deltaCell(v, 0) },
    { key: 'cc_inc', title: '贷记卡绑卡消费净增', unit: '户', render: (v) => deltaCell(v, 0) },
    { key: 'cp_inc', title: '信用卡纯消费净增', unit: '户', render: (v) => deltaCell(v, 0) },
  ];
  if (block === 'ck') cols.push({ key: 'ins_year', title: '期缴保险销量', unit: '万', decimals: 2 });
  cols.push({ key: 'fund_year', title: '非货币基金销量', unit: '万', decimals: 2 });
  cols.push({
    key: 'licai_year',
    title: block === 'ck' ? '个人理财销量' : '个人理财销量',
    unit: block === 'ck' ? '亿' : '万',
    render: (v) => fmt.n(block === 'ck' ? yi(v) : v, 2),
  });
  cols.push({ key: 'wx_net', title: '企业微信净增', unit: '户', render: (v) => deltaCell(v, 0) });
  cols.push({ key: 'mkt_norm', title: '营销通常态化', render: (v) => fmt.pct(v, 1) });
  return cols;
}

function netColumns(block) {
  return [
    { key: 'rank', title: '排名', decimals: 0, rank: false, strong: true },
    { key: 'name', title: '网点', sortable: false },
    { key: 'branch', title: '支行', sortable: false, render: (v) => String(v).replace('支行', '') },
    { key: 'mgrs', title: '经理数', decimals: 0 },
    { key: 'score', title: '总得分', render: (v, r) => `<b>${(v || 0).toFixed(2)}</b>` },
    { key: 'dep_inc', title: '存款增量', unit: '亿', render: (v) => deltaCell(yi(v), 2) },
    { key: 'nstock_inc', title: '非存增量', unit: '亿', render: (v) => deltaCell(yi(v), 2) },
    { key: 'c50_inc', title: '50万以上客户增量', unit: '户', render: (v) => deltaCell(v, 0) },
    { key: 'rej_inc', title: '融e借增量', unit: '万', render: (v) => deltaCell(v, 0) },
  ];
}

function mgrColumns(block) {
  const cols = [
    { key: 'rank', title: '排名', decimals: 0, rank: false, strong: true },
    { key: 'branch', title: '支行', sortable: false },
  ];
  if (block === 'ck') cols.push({ key: 'net', title: '网点', sortable: false });
  cols.push(
    { key: 'mgr', title: '客户经理', sortable: false },
    { key: 'score', title: '总得分', render: (v) => `<b>${(v || 0).toFixed(2)}</b>` },
    { key: 'dep_inc', title: '存款增量', unit: '亿', render: (v) => deltaCell(yi(v), 2) },
    { key: 'nstock_inc', title: '非存增量', unit: '亿', render: (v) => deltaCell(yi(v), 2) },
    { key: 'c50_inc', title: '50万以上客户增量', unit: '户', render: (v) => deltaCell(v, 0) },
    { key: 'rej_inc', title: '融e借增量', unit: '万', render: (v) => deltaCell(v, 0) },
    { key: 'kp_inc', title: '卡分期增量', unit: '万', render: (v) => deltaCell(v, 1) },
    { key: 'wx_net', title: '企业微信净增', unit: '户', render: (v) => deltaCell(v, 0) },
  );
  return cols;
}
