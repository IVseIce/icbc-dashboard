/* 总览：重点条线（定期/线上服务）大卡 + 其余三条线小卡 + 数据时点 */
import { fmt, countUp, deltaHTML, empty, icon } from '../ui.js';
import { mount, barRank, lineTrend, sparkline, C } from '../charts.js';

export default {
  id: 'overview',
  title: '总览',
  nav: '总览',
  icon: 'overview',
  render(view, data) {
    const o = data.overview || {};
    const L = o.lines || {};
    const ok = (k) => L[k]?.ok;
    const d = L.deposit || {};
    const on = L.online || {};

    view.innerHTML = `
      <div class="page-head">
        <div>
          <h1>今日经营概览</h1>
          <p>五条线最新一期数据 · 点击任一卡片进入多维度分析</p>
        </div>
        <div class="spacer"></div>
        <span class="chip">生成于 ${o.generated_at || '—'}</span>
      </div>

      <div class="grid g2">
        ${heroDeposit(d, data.deposit)}
        ${heroOnline(on, data.online)}
      </div>

      <div class="grid g3" style="margin-top:16px">
        ${miniWallet(L.wallet, data.wallet)}
        ${miniSalary(L.salary, data.salary)}
        ${miniCommunity(L.community, data.community)}
      </div>

      <div class="grid g-8-4" style="margin-top:16px">
        ${timeline(L)}
        ${noteCard()}
      </div>`;

    // 动画数字
    view.querySelectorAll('[data-count]').forEach((el) => {
      countUp(el, Number(el.dataset.count), { decimals: Number(el.dataset.dec || 0) });
    });

    // 企微：前三支行客户数小条形
    const qb = (data.community?.branches || []).slice(0, 3);
    mount(view.querySelector('#ovQwChart'), barRank(
      qb.map((b) => ({ name: b.name.replace('支行', ''), value: b.cust })),
      { color: C.amber, unit: ' 户', hideLabel: true }));

    // 重点卡片内的小图
    const dep = data.deposit?.branches || [];
    mount(view.querySelector('#ovDepositChart'), barRank(
      dep.map((b) => ({ name: b.name, value: b.inc })).sort((a, b) => b.value - a.value),
      { color: C.red, unit: ' 万', decimals: 0, hideLabel: true }));

    const tr = (data.online?.trend || []).slice(-12);
    mount(view.querySelector('#ovOnlineChart'), lineTrend(
      tr.map((t) => fmt.short(t.d)), [{ name: '当日动户率', data: tr.map((t) => +(t.day_rate * 100).toFixed(2)), color: C.red }],
      { unit: '%' }));

  },
};

/* ------------------------------------------------------------------ 块 */
function heroDeposit(d, detail) {
  const k = d.kpi;
  if (!d.ok || !k) return `<div class="card hero-card">${empty('定期存款暂无数据')}</div>`;
  return `
  <div class="card hero-card clickable" style="--accent:${C.violet}" onclick="location.hash='#/deposit'">
    <div class="heroline"></div>
    <div class="top">
      <div class="title">${icon('deposit', 18)} 定期存款 <span class="chip blue" style="margin-left:4px">重点</span></div>
      <div class="go">查看分析 ${icon('arrow', 14)}</div>
    </div>
    <div class="sub" style="color:var(--ink-3);font-size:12px;margin-top:4px">
      ${fmt.date(d.as_of)} · 较 ${fmt.date(d.prev_as_of)} 增减
    </div>
    <div class="hero-kpis">
      <div class="hero-kpi">
        <div class="v"><span data-count="${k.balance_yi}" data-dec="2">0</span><small>亿元</small></div>
        <div class="l">定期存款余额</div>
      </div>
      <div class="hero-kpi">
        <div class="v"><span data-count="${k.inc}" data-dec="2">0</span><small>万</small></div>
        <div class="l">当月增量</div>
      </div>
      <div class="hero-kpi">
        <div class="v" style="color:var(--red)">${(k.rate * 100).toFixed(2)}<small>%</small></div>
        <div class="l">当月增幅</div>
      </div>
    </div>
    <div class="chart" id="ovDepositChart"></div>
  </div>`;
}

function heroOnline(o, detail) {
  const k = o.kpi;
  if (!o.ok || !k) return `<div class="card hero-card">${empty('网点线上服务暂无数据')}</div>`;
  return `
  <div class="card hero-card clickable" style="--accent:${C.red}" onclick="location.hash='#/online'">
    <div class="heroline"></div>
    <div class="top">
      <div class="title">${icon('online', 18)} 网点线上服务 <span class="chip red" style="margin-left:4px">重点</span></div>
      <div class="go">查看分析 ${icon('arrow', 14)}</div>
    </div>
    <div class="sub" style="color:var(--ink-3);font-size:12px;margin-top:4px">
      ${fmt.date(o.as_of)} · ${k.nets} 个网点 · 当日添客 ${fmt.n(k.add_today)} 户
    </div>
    <div class="hero-kpis">
      <div class="hero-kpi">
        <div class="v"><span data-count="${(k.day_rate * 100).toFixed(2)}" data-dec="2">0</span><small>%</small></div>
        <div class="l">当日动户率</div>
      </div>
      <div class="hero-kpi">
        <div class="v"><span data-count="${k.add_month}" data-dec="0">0</span><small>户</small></div>
        <div class="l">当月添客</div>
      </div>
      <div class="hero-kpi">
        <div class="v">${(k.sign_rate * 100).toFixed(1)}<small>%</small></div>
        <div class="l">营销授权签约率</div>
      </div>
    </div>
    <div class="chart" id="ovOnlineChart"></div>
  </div>`;
}

function miniWallet(l, d) {
  const k = l?.kpi;
  if (!l?.ok || !k) return `<div class="card mini-card">${empty('数币钱包暂无数据')}</div>`;
  return `
  <div class="card mini-card clickable" style="--accent:${C.blue}" onclick="location.hash='#/wallet'">
    <div class="row">${icon('wallet', 16)}<span style="font-size:13px;font-weight:650">数字人民币钱包</span>
      <span class="go" style="margin-left:auto;color:var(--ink-3)">${icon('arrow', 13)}</span></div>
    <div class="row">
      <div class="v">${fmt.n(k.total)}<small>户</small></div>
      <span class="chip green" style="margin-left:auto">当日 +${fmt.n(k.day)}</span>
    </div>
    <div class="k-foot" style="font-size:11.5px;color:var(--ink-3)">
      当月新增 <b style="color:var(--ink)">${fmt.n(k.month)}</b> 户 · 网点 ${k.nets} 个 ·
      零新增 <b style="color:var(--red)">${k.zero_day}</b> 个
    </div>
    <div class="chart">${sparkline((d?.trend || []).slice(-12).map((t) => t.total), { color: C.blue, height: 64 })}</div>
  </div>`;
}

function miniSalary(l, d) {
  const k = l?.kpi;
  if (!l?.ok || !k) return `<div class="card mini-card">${empty('薪管家暂无数据')}</div>`;
  const tr = (d?.trend || []).slice(-12);
  return `
  <div class="card mini-card clickable" style="--accent:${C.teal}" onclick="location.hash='#/salary'">
    <div class="row">${icon('salary', 16)}<span style="font-size:13px;font-weight:650">工银薪管家</span>
      <span class="go" style="margin-left:auto;color:var(--ink-3)">${icon('arrow', 13)}</span></div>
    <div class="row">
      <div class="v">${fmt.n(k.year, 2)}<small>万元</small></div>
      <span class="chip blue" style="margin-left:auto">当月 ${fmt.n(k.month, 2)}</span>
    </div>
    <div class="k-foot" style="font-size:11.5px;color:var(--ink-3)">
      有效单位 <b style="color:var(--ink)">${k.ent_year}</b> 户 · 较上期
      <b style="color:var(--red)">+${fmt.n((k.year || 0) - (tr.length > 1 ? tr[tr.length - 2].year : k.year), 2)}</b> 万
    </div>
    <div class="chart">${sparkline(tr.map((t) => t.year), { color: C.teal, height: 64 })}</div>
  </div>`;
}

function miniCommunity(l, d) {
  const k = l?.kpi;
  if (!l?.ok || !k) return `<div class="card mini-card">${empty('企微社群暂无数据')}</div>`;
  return `
  <div class="card mini-card clickable" style="--accent:${C.amber}" onclick="location.hash='#/community'">
    <div class="row">${icon('community', 16)}<span style="font-size:13px;font-weight:650">企微社群</span>
      <span class="go" style="margin-left:auto;color:var(--ink-3)">${icon('arrow', 13)}</span></div>
    <div class="row">
      <div class="v">${fmt.n(k.cust)}<small>户客户</small></div>
      <span class="chip amber" style="margin-left:auto">${k.groups} 个群</span>
    </div>
    <div class="k-foot" style="font-size:11.5px;color:var(--ink-3)">
      较上周 <b>+${fmt.n(k.cust_d)}</b> 户 · 熟识率 <b style="color:var(--ink)">${fmt.pct(k.rate, 2)}</b> ·
      交互 ${fmt.n(k.inter)} 条
    </div>
    <div class="chart" id="ovQwChart" style="height:80px"></div>
  </div>`;
}

function timeline(L) {
  const rows = [
    ['deposit', '定期存款', C.violet],
    ['online', '网点线上服务', C.red],
    ['wallet', '数字人民币钱包', C.blue],
    ['salary', '工银薪管家', C.teal],
    ['community', '企微社群', C.amber],
  ];
  return `
  <div class="card">
    <div class="card-head"><h3>数据时点</h3><div class="right"><span class="chip">导入后自动更新</span></div></div>
    <div class="timeline">
      ${rows.map(([k, name, c]) => {
        const l = L[k] || {};
        const snaps = (window.__snapCount && window.__snapCount[k]) || '';
        return `<div class="tl-item" style="--accent:${c}">
          <i class="tl-dot"></i>
          <span class="tl-name">${name}</span>
          <span class="chip ${l.ok ? 'green' : 'red'}" style="font-size:10px">${l.ok ? '已就绪' : '待导入'}</span>
          <span class="tl-sub">${l.ok ? fmt.date(l.as_of) : '—'}${snaps ? ` · ${snaps} 期` : ''}</span>
        </div>`;
      }).join('')}
    </div>
  </div>`;
}

function noteCard() {
  return `
  <div class="card">
    <div class="card-head"><h3>口径与说明</h3></div>
    <div style="font-size:12px;color:var(--ink-2);line-height:1.9">
      <div>· 数字与各条线正式通报一致，未做人工改写</div>
      <div>· 期次以「数据日期」为准，补录历史不会顶掉最新一期</div>
      <div>· 跨条线只看排名与相对位置，不比绝对数大小</div>
      <div class="chip" style="margin-top:8px">红 = 增长 / 绿 = 下降（银行口径）</div>
    </div>
  </div>`;
}
