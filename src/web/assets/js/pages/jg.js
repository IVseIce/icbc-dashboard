/* 个金总览：基础数据 + 增存/增客/增收 三类，全部模块一览（不折叠） */
import { fmt, icon, countUp, empty } from '../ui.js';

const KIND = { metric: 'green', planned: '', placeholder: '' };

export default {
  id: 'jg',
  render(view, data, ctx) {
    const cat = ctx.catalog;
    const prof = cat.professionals.find((p) => p.id === 'jg');
    const d = data.deposit?.kpi, s = data.salary?.kpi, pay = data.payroll?.kpi;
    const five = data.fivecards?.totals;

    view.innerHTML = `
      <div class="page-head">
        <div><h1>个人金融</h1>
          <p>增存 · 增客 · 增收 · ${prof.groups.reduce((n, g) => n + g.modules.length, 0)} 个模块</p></div>
        <div class="spacer"></div>
        <span class="chip ${prof.status === 'active' ? 'green' : ''}">已接入 ${countMetric(prof)}/${countAll(prof)}</span>
      </div>

      <div class="card jg-base">
        <div class="card-head"><h3>基础数据</h3>
          <div class="right"><span class="chip">未接入的先留空</span></div></div>
        <div class="jg-base-grid">
          ${baseTile('定期存款余额', d ? fmt.n(d.balance_yi, 2) : null, '亿元', d ? '当月 ' + fmt.sign(d.inc, 0) + ' 万' : '待接入', 'violet')}
          ${baseTile('当月增量', d ? fmt.n(d.inc, 0) : null, '万元', d ? (d.rate * 100).toFixed(2) + '%' : '', 'red')}
          ${baseTile('代发客户', pay ? fmt.n(pay.cust) : null, '人', pay ? '企业 ' + fmt.n(pay.comps) + ' 户' : '待接入', 'blue')}
          ${baseTile('薪管家代发', s ? fmt.n(s.year, 0) : null, '万元', s ? '当月 ' + fmt.n(s.month, 2) : '', 'teal')}
          ${baseTile('五卡存量', five ? fmt.n(five.stock) : null, '户', five ? '长尾率 ' + fmt.pct(five.long_rate, 1) : '', 'amber')}
          ${baseTile('全量客户', null, '户', '待接入', 'green')}
        </div>
      </div>

      ${prof.groups.map((g) => section(g, data)).join('')}`;

    view.querySelectorAll('[data-count]').forEach((el) =>
      countUp(el, Number(el.dataset.count), { decimals: Number(el.dataset.dec || 0) }));
  },
};

function countMetric(p) { return p.groups.flatMap((g) => g.modules).filter((m) => m.kind === 'metric').length; }
function countAll(p) { return p.groups.flatMap((g) => g.modules).length; }

function baseTile(label, value, unit, foot, color) {
  return `<div class="jg-bt" style="--accent:${color}">
    <div class="jg-bt-l">${label}</div>
    <div class="jg-bt-v">${value === null ? '<span class="muted">—</span>' : `${value}<small>${unit}</small>`}</div>
    <div class="jg-bt-f">${foot || ''}</div>
  </div>`;
}

function section(g, data) {
  return `
  <section class="card jg-sec" style="margin-top:16px">
    <div class="card-head">
      <h3>${g.name}</h3>
      <div class="right"><span class="chip">${g.modules.length} 个模块 · 已接入 ${g.modules.filter((m) => m.kind === 'metric').length}</span></div>
    </div>
    <div class="jg-grid">
      ${g.modules.map((m) => moduleCard(m, g, data)).join('')}
    </div>
  </section>`;
}

function moduleCard(m, g, data) {
  const stat = statsFor(m.id, data);
  const clickable = m.kind === 'metric' || m.kind === 'planned';
  return `
  <div class="jg-mod ${clickable ? '' : 'off'}" ${clickable ? `data-go="#/m/${m.id}"` : ''}>
    <div class="jg-mod-top">
      <b>${m.name}</b>
      <span class="chip ${m.kind === 'metric' ? 'green' : ''}" style="font-size:9.5px">
        ${m.kind === 'metric' ? '已接入' : m.kind === 'planned' ? '待结构化' : '待接入'}</span>
    </div>
    ${stat ? `<div class="jg-mod-stats">${stat}</div>` : `<div class="jg-mod-empty">${icon('spark', 12)} 暂无数据</div>`}
  </div>`;
}

function statsFor(id, data) {
  const d = data;
  const out = [];
  const push = (v, l) => out.push(`<div><i>${v}</i><span>${l}</span></div>`);
  if (id === 'jg-deposit-time' && d.deposit?.kpi) {
    const k = d.deposit.kpi;
    push(fmt.n(k.balance_yi, 2) + '<small>亿</small>', '余额');
    push(fmt.sign(k.inc, 0), '当月增量(万)');
    push((k.rate * 100).toFixed(2) + '<small>%</small>', '增幅');
  } else if (id === 'jg-customer-pay' && d.payroll?.kpi) {
    const k = d.payroll.kpi;
    push(fmt.n(k.cust), '代发客户');
    push(fmt.n(k.month, 0), '当月(万)');
    push(fmt.n(k.comps), '企业');
  } else if (id === 'jg-customer-xgj' && d.salary?.kpi) {
    const k = d.salary.kpi;
    push(fmt.n(k.year, 0), '全年(万)');
    push(fmt.n(k.month, 2), '当月(万)');
    push(fmt.n(k.ent_year), '有效单位');
  } else if (id === 'jg-customer-card' && d.fivecards?.totals) {
    const t = d.fivecards.totals;
    push(fmt.n(t.stock), '存量');
    push(fmt.pct(t.long_rate, 1), '长尾率');
    push(fmt.n(t.long), '长尾户');
  } else if (id === 'pj-wecom' && d.community?.kpi) {
    const k = d.community.kpi;
    push(fmt.n(k.groups), '群');
    push(fmt.n(k.cust), '客户');
    push(fmt.pct(k.rate, 2), '熟识率');
  }
  return out.length ? out.join('') : null;
}
