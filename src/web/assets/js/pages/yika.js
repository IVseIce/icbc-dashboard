/* 一卡一户：支行 + 网点两层，重点看"好的几个"和"差的几个"
   —— 支行看当日合计完成率排行；网点看达标的（红榜）与两项都挂零的（黑榜）。 */
import { fmt, countUp, empty, icon, table, bigTable } from '../ui.js';
import { mount, C, barRank, splitRank } from '../charts.js';

const pct = (v, nd = 1) => (v === null || v === undefined ? '—' : `${(Number(v) * 100).toFixed(nd)}%`);
/** 网点叫法 = 支行名 + 网点名，各去掉「阜阳」「支行」。
    和通报文案一致（`阜阳城建支行` → `颍州城建`），否则「城建」不知道是哪个支行。 */
const shortName = (name, branch) => {
  let s = String(name || '').replace('阜阳', '');
  if (s.endsWith('支行')) s = s.slice(0, -2);
  const b = String(branch || '').trim();
  return b && !s.startsWith(b) ? b + s : s;
};

function tile(label, value, suffix, foot, color) {
  return `<div class="card kpi" style="--accent:${color}">
    <div class="heroline"></div>
    <div class="k-label">${label}</div>
    <div class="k-value"><span data-count="${String(value).replace(/,/g, '')}"
      data-dec="${String(value).includes('.') ? 0 : 0}">0</span><small>${suffix}</small></div>
    <div class="k-foot">${foot}</div>
  </div>`;
}

function periodText(per) {
  if (!per) return '';
  const s = per.start, e = per.end;
  if (s === e) return `${fmt.date(s)}`;
  const sameMonth = s.slice(5, 7) === e.slice(5, 7);
  return sameMonth ? `${fmt.date(s)}–${Number(e.slice(8, 10))}日` : `${fmt.date(s)}–${fmt.date(e)}`;
}

export default {
  id: 'yika',
  title: '一卡一户',
  render(view, data) {
    const d = data.yika;
    if (!d?.ok) {
      view.innerHTML = `<div class="card">${empty('一卡一户暂无数据',
        '导入「社保卡发卡统计报表」和「个人养老金开户表」，每天导当期即可')}</div>`;
      return;
    }
    const k = d.kpi;
    const per = d.period || {};
    const brs = d.branches || [];
    const nets = d.nets || [];
    const reached = d.top_nets || [];
    const zero = d.zero_nets || [];

    view.innerHTML = `
      <div class="page-head">
        <div><h1>“一卡一户”</h1>
          <p>${periodText(per)} · 社保卡 + 个人养老金 · ${k.nets} 个网点 · 单位：张 / 户</p></div>
        <div class="spacer"></div>
        <span class="chip">当日 ${fmt.date(per.cur)}</span>
        <span class="chip">前一日 ${fmt.date(per.prev)}</span>
        <span class="chip">上周末 ${fmt.date(per.week_end)}</span>
      </div>

      <div class="grid g6">
        ${tile('社保卡当日开户', fmt.n(k.sb_day), '张', `目标 ${k.sb_target} · 达成 ${pct(k.sb_rate)}`,
               k.sb_rate >= 1 ? C.red : C.blue)}
        ${tile('社保卡本周开户', fmt.n(k.sb_week), '张', `周完成率 ${pct(k.sb_rate)}`, C.blue)}
        ${tile('养老金当日开户', fmt.n(k.yl_day), '户', `目标 ${k.yl_target} · 达成 ${pct(k.yl_rate)}`,
               k.yl_rate >= 1 ? C.red : C.teal)}
        ${tile('养老金本周开户', fmt.n(k.yl_week), '户', `覆盖 ${k.yl_active} 个网点`, C.teal)}
        ${tile('当日合计完成率', (k.day_rate * 100).toFixed(1), '%',
               `任务 ${k.sb_target + k.yl_target} · 完成 ${fmt.n(k.sb_day + k.yl_day)}`, C.violet)}
        ${tile('周任务完成率', (k.week_rate * 100).toFixed(1), '%',
               `本周 ${fmt.n(k.sb_week + k.yl_week)} · 达标网点 ${k.reached} 个`, C.amber)}
      </div>

      <div class="grid g-7-5" style="margin-top:16px">
        <div class="card"><div class="card-head"><h3>支行当日合计完成率</h3>
          <div class="right"><span class="chip red">红=前二</span><span class="chip green">绿=后二</span></div></div>
          <div class="chart-box chart-lg" id="ykBr"></div></div>
        <div class="card"><div class="card-head"><h3>两项当日开户</h3>
          <div class="right"><span class="chip">社保卡 / 养老金</span></div></div>
          <div class="chart-box chart-lg" id="ykBrSplit"></div></div>
      </div>

      <div class="grid g-7-5" style="margin-top:16px">
        <div class="card"><div class="card-head"><h3>网点当日合计完成率 · 头尾</h3>
          <div class="right"><span class="chip">${nets.length} 个网点</span></div></div>
          <div class="chart-box chart-lg" id="ykNet"></div></div>
        <div class="card"><div class="card-head"><h3>已达标网点</h3>
          <div class="right"><span class="chip red">当日合计 ≥ 100%</span></div></div>
          <div id="ykReached" style="display:flex;flex-direction:column;gap:7px;padding-top:4px"></div>
          <div class="card-head" style="margin-top:14px">
            <h3 style="font-size:12.5px">两项均无业绩</h3>
            <div class="right"><span class="chip">需在群里反馈“0”</span></div></div>
          <div id="ykZero" style="display:flex;flex-wrap:wrap;gap:6px;padding-top:2px"></div>
        </div>
      </div>

      <div class="card" style="margin-top:16px"><div class="card-head"><h3>支行明细</h3>
        <div class="right"><span class="chip">按当日合计完成率排序</span></div></div>
        <div id="ykBrTable"></div></div>

      <div class="card" style="margin-top:16px"><div class="card-head"><h3>网点明细</h3>
        <div class="right"><span class="chip">共 ${nets.length} 个</span>
          <button class="btn btn-sm" id="ykExpand" style="margin-left:8px">${icon('expand', 14)} 全屏</button></div></div>
        <div id="ykNetTable"></div></div>`;

    view.querySelectorAll('[data-count]').forEach((el) =>
      countUp(el, Number(el.dataset.count), { decimals: 0 }));

    // 支行：按当日合计完成率，前二红后二绿（通报也是这么说的）
    const brsByDay = [...brs].sort((a, b) => b.day_rate - a.day_rate);
    mount(view.querySelector('#ykBr'), barRank(
      brsByDay.map((b, i) => ({
        name: b.name,
        value: +(b.day_rate * 100).toFixed(2),
        color: i < 2 ? C.red : (i >= brsByDay.length - 2 ? C.green : '#cbd6e8'),
      })),
      { unit: '%', decimals: 1 }));

    // 支行：两项当日开户对比（横向双条，看结构）
    mount(view.querySelector('#ykBrSplit'), barRank(
      brsByDay.flatMap((b) => ([
        { name: `${b.name} · 社保`, value: b.sb_day, color: C.blue },
        { name: `${b.name} · 养老`, value: b.yl_day, color: C.teal },
      ])),
      { unit: ' 户', decimals: 0 }));

    // 网点头尾
    const netRows = [...nets].sort((a, b) => b.day_rate - a.day_rate)
      .map((n) => ({ name: shortName(n.name, n.branch), value: +(n.day_rate * 100).toFixed(1),
                     _n: n }));
    mount(view.querySelector('#ykNet'), barRank(
      splitRank(netRows, { top: 8, bottom: 8, unit: '个网点' }),
      { unit: '%', decimals: 1 }));

    // 红榜：达标（当日合计 ≥ 100%）
    const rv = view.querySelector('#ykReached');
    rv.innerHTML = reached.length ? reached.map((n) => `
      <div style="display:flex;align-items:center;gap:8px;padding:7px 9px;border-radius:9px;background:#fdf3f4">
        <span class="rank-badge top">✓</span>
        <span style="font-size:12px;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
          ${shortName(n.name, n.branch)}</span>
        <span style="font-size:11px;color:var(--ink-3)">${n.branch}</span>
        <b style="font-size:12px;color:var(--red)">${pct(n.day_rate)}</b>
      </div>`).join('')
      : '<div style="font-size:12px;color:var(--ink-3);padding:6px 2px">本期还没有网点达标</div>';

    // 黑榜：社保、养老「日平台达成率都 ≤ 0」（一负一正不算）
    const zv = view.querySelector('#ykZero');
    zv.innerHTML = zero.length ? zero.map((n) =>
      `<span class="chip red">${shortName(n.name, n.branch)}</span>`).join('')
      : '<span style="font-size:12px;color:var(--ink-3)">本期没有两项都挂零的网点</span>';

    // 支行表
    const brCols = [
      { key: 'rank', title: '排名', decimals: 0, rank: false },
      { key: 'name', title: '支行', sortable: false },
      { key: 'nets', title: '网点', decimals: 0 },
      { key: 'sb_day', title: '社保卡当日', decimals: 0 },
      { key: 'sb_week', title: '社保卡本周', decimals: 0 },
      { key: 'yl_day', title: '养老金当日', decimals: 0 },
      { key: 'yl_week', title: '养老金本周', decimals: 0 },
      { key: 'day_rate', title: '当日合计完成率', render: (v) => pct(v), strong: true },
      { key: 'week_rate', title: '周任务完成率', render: (v) => pct(v) },
    ];
    view.querySelector('#ykBrTable').appendChild(table(brCols, brsByDay.map((b, i) => ({ ...b, rank: i + 1 })), {}));

    // 网点表
    const netCols = [
      { key: 'name', title: '网点', render: (v, r) => shortName(v, r.branch) },
      { key: 'branch', title: '支行', sortable: false },
      { key: 'sb_day', title: '社保当日', decimals: 0 },
      { key: 'sb_rate', title: '社保日达成', render: (v) => `<b style="color:${(v || 0) >= 1 ? 'var(--red)' : (v || 0) <= 0 ? 'var(--green)' : 'var(--ink-2)'}">${pct(v)}</b>` },
      { key: 'yl_day', title: '养老当日', decimals: 0 },
      { key: 'yl_rate', title: '养老日达成', render: (v) => `<b style="color:${(v || 0) >= 1 ? 'var(--red)' : (v || 0) <= 0 ? 'var(--green)' : 'var(--ink-2)'}">${pct(v)}</b>` },
      { key: 'sb_week', title: '社保本周', decimals: 0 },
      { key: 'yl_week', title: '养老本周', decimals: 0 },
      { key: 'day_rate', title: '当日合计', render: (v) => pct(v), strong: true },
      { key: 'week_rate', title: '周任务', render: (v) => pct(v) },
    ];
    view.querySelector('#ykNetTable').appendChild(table(netCols, nets, { sortBy: 'day_rate' }));

    view.querySelector('#ykExpand').onclick = () => bigTable({
      title: '“一卡一户” · 全部网点',
      subtitle: `${periodText(per)} · 社保卡 ${k.sb_day} 张 / 养老金 ${k.yl_day} 户`,
      columns: netCols,
      rows: nets,
    });
  },
};
