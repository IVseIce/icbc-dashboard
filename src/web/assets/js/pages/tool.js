/* pages/tool.js —— 实用工具：工具类模块的统一外壳（当前内容留空）。
   工具不是数据页：没有 as_of、没有条线、也没有导入；只按模块名占位，
   以后往里填具体功能时，把 <div class="tool-body"> 换成真正的实现即可。 */
import { icon } from '../ui.js';

const HINTS = {
  'tool-date-diff': '计划：算两个日期之间的天数 / 工作日差',
  'tool-deviation': '计划：算实际值与基准值的偏离度',
};

export default {
  id: 'tool',
  render(view, _data, ctx) {
    const id = (location.hash.split('/')[2] || '').trim();
    let hit = null;
    for (const p of ctx.catalog.professionals) {
      for (const g of p.groups) {
        for (const m of g.modules || []) {
          if (m.id === id) hit = { prof: p, group: g, module: m };
        }
      }
    }
    if (!hit) {
      view.innerHTML = '<div class="card"><div class="empty"><b>工具不存在</b></div></div>';
      return;
    }
    const { prof, module } = hit;

    view.innerHTML = `
      <div class="page-head">
        <div><h1>${module.name}</h1>
          <p>${prof.name} · 工具</p></div>
        <div class="spacer"></div>
        <span class="chip">待实现</span>
      </div>

      <div class="card tool-shell">
        <div class="tool-empty">
          <div class="tool-ico">${icon('spark', 22)}</div>
          <b>${module.name}</b>
          <p>${HINTS[module.id] || '这里先留空，后续实现具体功能。'}</p>
          <span class="chip">内容待补充</span>
        </div>
      </div>`;
  },
};
