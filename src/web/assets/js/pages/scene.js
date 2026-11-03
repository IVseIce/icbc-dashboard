/* pages/scene.js —— 全量客户场景攻坚（支行 × 6 场景）
   数据是「文字项目」，不是数值指标，所以这一页的核心是**把内容排清楚**：
     · 顶部 KPI 四格（场景 / 已落地 / 推进中 / 覆盖支行）+ 本期变化
     · 场景泳道：每个场景一条卡，左边「已落地」，右边「推进中」，条目按支行分组
     · 本期有变化的条目**黄底高亮**（源表里是红色字体，成图里是黄色标注）
     · 支行矩阵：8 行 × 6 列，一眼看出谁在哪块有进展、谁还空着
   页面与「导出图片」用同一份 payload、同一套 DOM，保证图与页面一致。 */
import { fmt, empty, toast, icon } from '../ui.js';

const SCENE_ABBR = { 养老代发: '养', 薪管家代发: '薪', 智慧校园: '校', 支付即开票: '票', 政务民生: '政', 数币: '数' };
const SCENE_TONE = {
  养老代发: '#c8102e', 薪管家代发: '#e8960c', 智慧校园: '#2563eb',
  支付即开票: '#7c5cff', 政务民生: '#0ea5a5', 数币: '#12a06a',
};

export default {
  id: 'scene',
  title: '全量客户场景攻坚',

  render(view, data, ctx) {
    const d = data.scene;
    if (!d?.ok) {
      view.innerHTML = `<div class="card">${empty('全量客户场景攻坚暂无数据',
        '导入《全量客户场景攻坚成效图 MM.DD.xlsx》（日期从文件名识别）')}</div>`;
      return;
    }
    const k = d.kpi;
    const scenes = d.scenes || [];
    const branches = d.branches || [];
    const order = d.branch_order || [];
    const changed = k.changed || 0;

    view.innerHTML = `
      <div class="page-head">
        <div><h1>全量客户场景攻坚</h1>
          <p>${fmt.date(d.as_of)} · ${k.scenes} 大场景 · ${branches.length} 家支行 · 文字台账</p></div>
        <div class="spacer"></div>
        ${changed ? `<span class="chip sc-chg">本期变化 ${changed} 项</span>` : ''}
        <button class="btn btn-sm" id="scShot">${icon('expand', 14)} 导出图片</button>
        <button class="btn btn-sm" id="scCopy">${icon('file', 14)} 复制图片</button>
      </div>

      <div class="sc-board" id="scBoard">
        <div class="sc-head">
          <div>
            <h2>全量客户场景攻坚成效</h2>
            <p>截至 ${fmt.date(d.as_of)} · 六大重点场景 · 各支行项目推进情况一览</p>
          </div>
          <div class="sc-head-kpi">
            ${[['场景', k.scenes], ['已落地', k.landed], ['推进中', k.ongoing], ['覆盖支行', k.branches]]
              .map(([lab, val]) => `<div><b>${val}</b><span>${lab}</span></div>`).join('')}
          </div>
        </div>

        ${changed ? `<div class="sc-chgbar">
          <i>${icon('spark', 13)}</i>
          <span>本期进度有变化 <b>${changed}</b> 项，下表已用<em>黄色</em>标出</span>
        </div>` : ''}

        <div class="sc-legend">
          ${scenes.map((s) => `<span class="sc-lg" style="--t:${SCENE_TONE[s.name] || '#c8102e'}">
            ${s.name}<b>${s.landed}</b><small>/${s.landed + s.ongoing}</small></span>`).join('')}
        </div>

        ${scenes.map((s) => sceneLane(s, branches, order)).join('')}

        <div class="sc-matrix-wrap">
          <h3>支行 × 场景 总览</h3>
          <div class="sc-matrix">
            <table>
              <thead><tr><th>支行</th>${scenes.map((s) => `<th style="--t:${SCENE_TONE[s.name] || '#c8102e'}">${s.name}</th>`).join('')}<th>合计</th></tr></thead>
              <tbody>${order.map((b) => matrixRow(b, scenes, branches)).join('')}</tbody>
              <tfoot><tr><td>全行</td>${scenes.map((s) => `<td><b>${s.landed}</b>/${s.landed + s.ongoing}</td>`).join('')}
                <td><b>${k.landed}</b>/${k.landed + k.ongoing}</td></tr></tfoot>
            </table>
          </div>
        </div>

        <div class="sc-foot">注：<em>黄色</em>标注为本期进度有变化的项目 · 各支行持续推进，场景攻坚全面发力、全量客户深耕见效</div>
      </div>`;

    view.querySelector('#scShot').onclick = () => shoot(false);
    view.querySelector('#scCopy').onclick = () => shoot(true);

    view.querySelectorAll('[data-scene]').forEach((el) => {
      el.onclick = () => {
        const t = view.querySelector(`#lane-${el.dataset.scene}`);
        if (t) t.scrollIntoView({ behavior: 'smooth', block: 'center' });
      };
    });

    async function shoot(copy) {
      const node = view.querySelector('#scBoard').cloneNode(true);
      node.classList.add('sc-shooting');           // 截图时去掉圆角阴影，白底更干净
      const box = document.createElement('div');
      box.className = 'sc-shotbox';
      box.appendChild(node);
      document.body.appendChild(box);
      try {
        const canvas = await window.html2canvas(node, {
          scale: 2, backgroundColor: '#f4f6fa', useCORS: true, logging: false,
        });
        const blob = await new Promise((res) => canvas.toBlob(res, 'image/png'));
        if (copy) {
          try {
            await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
            toast('图片已复制，可直接粘贴');
            return;
          } catch { /* 降级为下载 */ }
        }
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `全量客户场景攻坚成效图${(d.as_of || '').slice(5).replace('-', '.')}.png`;
        a.click();
        setTimeout(() => URL.revokeObjectURL(a.href), 3000);
        toast('图片已导出');
      } catch (err) {
        toast(`导出失败：${err.message}`, 'err');
      } finally {
        box.remove();
      }
    }
  },
};

/* ---------------------------------------------------------------- 拼装 */
/** 一个场景一条泳道：左「已落地」右「推进中」，条目按支行分组 */
function sceneLane(sc, branches, order) {
  const tone = SCENE_TONE[sc.name] || '#c8102e';
  const abbr = SCENE_ABBR[sc.name] || String(sc.name)[0];
  const landed = pick(branches, sc.name, 'landed', order);
  const ongoing = pick(branches, sc.name, 'ongoing', order);
  const empty = !landed.length && !ongoing.length;

  return `<section class="sc-lane" id="lane-${sc.name}" style="--tone:${tone}">
    <div class="sc-lane-head" data-scene="${sc.name}">
      <span class="sc-abbr">${abbr}</span>
      <h3>${sc.name}场景</h3>
      <div class="sc-lane-stat">
        <span class="ok">已落地 <b>${sc.landed}</b></span>
        <span class="go">推进中 <b>${sc.ongoing}</b></span>
        <span class="cv">覆盖 <b>${sc.branches}</b>/${order.length}</span>
        ${sc.changed ? `<span class="ch">本期变化 <b>${sc.changed}</b></span>` : ''}
      </div>
    </div>
    ${empty ? '<div class="sc-lane-empty">本期这一场景没有项目记录</div>' : `
    <div class="sc-cols">
      <div class="sc-col">
        <div class="sc-col-head ok">✓ 已落地</div>
        ${landed.length ? colHTML(landed) : '<div class="sc-none">—</div>'}
      </div>
      <div class="sc-col">
        <div class="sc-col-head go">→ 推进中</div>
        ${ongoing.length ? colHTML(ongoing) : '<div class="sc-none">—</div>'}
      </div>
    </div>`}
  </section>`;
}

/** 把「支行 → 条目」摊平成 [{branch, items}]，顺序按 branch_order */
function pick(branches, scene, key, order) {
  const idx = new Map(order.map((b, i) => [b, i]));
  return branches
    .map((b) => ({ branch: b.name, items: ((b.scenes || {})[scene] || {})[key] || [] }))
    .filter((x) => x.items.length)
    .sort((a, b) => (idx.get(a.branch) ?? 99) - (idx.get(b.branch) ?? 99));
}

/** 条目开头如果重复了支行名就去掉（"颍上养老代发…" → "养老代发…"），
    否则左列已经有支行标签，读起来会「颍上 颍上养老代发」 */
function stripBranch(text, branch) {
  const t = String(text || '').trim();
  if (branch && t.indexOf(branch) === 0) {
    const rest = t.slice(branch.length).replace(/^[：:、，,\s]+/, '');
    return rest || t;
  }
  return t;
}

/** 同一场景里多家支行的条目文字完全一样时（例如 8 家都写「已落地数币代发」），
    堆 8 行纯粹是噪声 —— 合成一行：文字 + 支行胶囊。>=4 家才合并，太少还是分行清楚。 */
function compactGroups(groups) {
  const byText = new Map();
  for (const g of groups) {
    for (const it of g.items) {
      const key = stripBranch(it.text, g.branch);
      const rec = byText.get(key) || { text: key, branches: [], changed: false };
      rec.branches.push(g.branch);
      rec.changed = rec.changed || !!it.changed;
      byText.set(key, rec);
    }
  }
  const shared = [];
  const rest = [];
  for (const rec of byText.values()) {
    if (rec.branches.length >= 4) shared.push(rec);
    else rest.push(rec);
  }
  if (!shared.length) return null;
  // 剩下的零散条目按原支行顺序还原
  const order = groups.map((g) => g.branch);
  const restGroups = [];
  for (const rec of rest) {
    for (const br of rec.branches) {
      const g = restGroups.find((x) => x.branch === br) || { branch: br, items: [] };
      g.items.push({ text: rec.text, changed: rec.changed && rec.branches.length === 1 });
      if (!restGroups.includes(g)) restGroups.push(g);
    }
  }
  restGroups.sort((a, b) => order.indexOf(a.branch) - order.indexOf(b.branch));
  return { shared, restGroups };
}

function sharedHTML(rec) {
  return `<div class="sc-group sc-group-wide">
    <div class="sc-items">
      <p class="sc-item sc-item-shared${rec.changed ? ' chg' : ''}">${esc(rec.text)}
        <span class="sc-chips">${rec.branches.map((b) => `<i>${b}</i>`).join('')}</span>
        <span class="sc-cnt">${rec.branches.length} 家</span></p>
    </div>
  </div>`;
}

function groupHTML(g, kind) {
  return `<div class="sc-group">
    <span class="sc-br">${g.branch}</span>
    <div class="sc-items">${g.items.map((it) =>
      `<p class="sc-item${it.changed ? ' chg' : ''}">${esc(stripBranch(it.text, g.branch))}</p>`).join('')}</div>
  </div>`;
}

/** 一列条目：能合并的合并，剩下的照常按支行分组 */
function colHTML(groups) {
  const c = compactGroups(groups);
  if (!c) return groups.map((g) => groupHTML(g)).join('');
  return c.shared.map(sharedHTML).join('') + c.restGroups.map((g) => groupHTML(g)).join('');
}

function matrixRow(b, scenes, branches) {
  const rec = branches.find((x) => x.name === b);
  const cells = scenes.map((s) => {
    const cell = ((rec?.scenes || {})[s.name]) || { landed: [], ongoing: [] };
    const l = cell.landed.length;
    const o = cell.ongoing.length;
    const chg = [...cell.landed, ...cell.ongoing].filter((x) => x.changed).length;
    if (!l && !o) return `<td class="sc-mx-empty">—</td>`;
    // 落地数用大字、推进中用 +n 小字；有本期变化的整格淡黄
    const lead = l ? `<b>${l}</b>` : '<span class="z">0</span>';
    const rest = o ? `<small>+${o}</small>` : '';
    return `<td class="sc-mx${chg ? ' chg' : ''}">${lead}${rest}</td>`;
  }).join('');
  const tot = rec ? `<b>${rec.landed}</b>${rec.ongoing ? `<small>+${rec.ongoing}</small>` : ''}` : '—';
  return `<tr><th>${b}</th>${cells}<td class="sc-mx-tot">${tot}</td></tr>`;
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}
