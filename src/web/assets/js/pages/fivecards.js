/* 五卡唤醒（支行维度）：社保卡/退役军人/养老金/信用卡/薪金卡 */
import { fmt, countUp, empty, table, bigTable, icon } from '../ui.js';
import { mount, base, xAxis, yAxis, C, stackedBar, barRank } from '../charts.js';

const CARD_COLORS = { 社保卡: '#2563eb', 退役军人优待证: '#0ea5a5', 养老金: '#7c5cff', 信用卡: '#e8960c', 薪金卡: '#c8102e' };

export default {
  id: 'fivecards',
  title: '五卡唤醒',
  render(view, data) {
    const d = data.fivecards;
    if (!d?.ok) { view.innerHTML = `<div class="card">${empty('五卡唤醒暂无数据', '导入五卡汇总表')}</div>`; return; }
    const cards = d.cards || [];
    const brs = d.branches || [];
    const cols = [
      { key: 'name', title: '支行', rank: false },
      ...cards.map((c) => ({ key: c.name, title: c.name, unit: '存量', decimals: 0,
        value: (r) => r.cards?.[c.name]?.stock, render: (_, r) => fmt.n(r.cards?.[c.name]?.stock ?? 0) })),
      ...cards.map((c) => ({ key: `${c.name}-rate`, title: `${c.name}长尾率`, sortable: false,
        value: (r) => r.cards?.[c.name]?.long_rate ?? 0,
        render: (_, r) => {
          const v = r.cards?.[c.name]?.long_rate;
          return v === null || v === undefined ? '—' : `<b style="color:${v >= 0.8 ? 'var(--red)' : 'var(--ink-2)'}">${(v * 100).toFixed(1)}%</b>`;
        } })),
    ];

    view.innerHTML = `
      <div class="page-head">
        <div><h1>五卡唤醒</h1>
          <p>${d.as_of} · 支行维度 · 存量、长尾、未激活 / 未交易</p></div>
        <div class="spacer"></div>
        <span class="chip amber">支行粒度</span>
        <button class="btn" id="fiveExpand">${icon('expand', 14)} 明细</button>
      </div>

      <div class="grid g5">
        ${cards.map((c) => cardTile(c)).join('')}
      </div>

      <div class="grid g-7-5" style="margin-top:16px">
        <div class="card"><div class="card-head"><h3>各支行五卡存量</h3>
          <div class="right"><span class="chip">堆叠</span></div></div>
          <div class="chart-box chart-md" id="fiveStack"></div></div>
        <div class="card"><div class="card-head"><h3>长尾率对比</h3>
          <div class="right"><span class="chip">越高越需要唤醒</span></div></div>
          <div class="chart-box chart-md" id="fiveRate"></div></div>
      </div>

      <div class="card" style="margin-top:16px">
        <div class="card-head"><h3>支行 × 五卡</h3>
          <div class="right"><span class="chip">存量 / 长尾率</span></div></div>
        <div id="fiveTable"></div>
      </div>`;

    view.querySelectorAll('[data-count]').forEach((el) =>
      countUp(el, Number(el.dataset.count), { decimals: Number(el.dataset.dec || 0) }));

    mount(view.querySelector('#fiveStack'), stackedBar(
      brs.map((b) => b.name),
      cards.map((c) => ({ name: c.name, color: CARD_COLORS[c.name],
        data: brs.map((b) => b.cards?.[c.name]?.stock ?? 0) }))));

    mount(view.querySelector('#fiveRate'), barRank(
      cards.filter((c) => c.long_rate !== null).map((c) => ({ name: c.name, value: +(c.long_rate * 100).toFixed(1) })),
      { color: C.red, unit: '%', decimals: 1, max: 100 }));

    view.querySelector('#fiveTable').appendChild(table(cols, brs, {}));
    view.querySelector('#fiveExpand').onclick = () => bigTable({
      title: '五卡唤醒 · 支行明细', subtitle: `${d.as_of} · 单位：户`,
      columns: cols, rows: brs,
    });
  },
};

function cardTile(c) {
  const color = CARD_COLORS[c.name] || C.blue;
  const extra = c.idle_label
    ? `${c.idle_label} ${fmt.n(c.idle)}（${fmt.pct(c.idle_rate, 1)}）`
    : (c.trade_rate !== null && c.trade_rate !== undefined
      ? `近一年未交易 ${fmt.pct(c.trade_rate, 1)}`
      : '—');
  return `<div class="card kpi" style="--accent:${color}"><div class="heroline"></div>
    <div class="k-label">${c.name}</div>
    <div class="k-value"><span data-count="${c.stock || 0}" data-dec="0">0</span><small>户</small></div>
    <div class="k-foot">长尾率 <b style="color:${(c.long_rate ?? 0) >= 0.8 ? 'var(--red)' : 'var(--ink)'}">
      ${c.long_rate === null ? '—' : fmt.pct(c.long_rate, 1)}</b> · ${extra}</div>
  </div>`;
}
