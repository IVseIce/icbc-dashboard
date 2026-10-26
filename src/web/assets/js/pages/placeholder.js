/* 占位页：模块/板块还没接数据时的统一展示 */
import { icon, empty } from '../ui.js';

export function modulePlaceholder(view, { prof, group, module }) {
  view.innerHTML = `
    <div class="page-head">
      <div><h1>${module.name}</h1>
        <p>${prof.name} · ${group?.name || ''} · ${module.kind === 'planned' ? '待接入' : '待建设'}</p></div>
      <div class="spacer"></div>
      <span class="chip">框架已预留</span>
    </div>
    <div class="card">
      <div class="empty" style="padding:56px 20px">
        <div style="width:52px;height:52px;border-radius:16px;background:var(--blue-soft);color:var(--blue);
          display:grid;place-items:center;margin:0 auto 14px">${icon('spark', 24)}</div>
        <b style="font-size:15px">${module.name} · 数据待接入</b>
        <p style="margin:8px 0 0;color:var(--ink-3)">${module.desc || '该模块尚未接入数据源'}</p>
        <div style="display:flex;gap:8px;justify-content:center;margin-top:16px;flex-wrap:wrap">
          ${module.source ? `<span class="chip">来源：${module.source}</span>` : ''}
          ${module.level ? `<span class="chip">颗粒度：${module.level}</span>` : ''}
          ${module.freq ? `<span class="chip">频率：${module.freq}</span>` : ''}
        </div>
        <div style="margin-top:18px;color:var(--ink-3);font-size:12px">
          需要的数据准备好后，在「导入数据」里选择该模块即可上线
        </div>
      </div>
    </div>`;
}

const toolsOnly = (mods) => mods.length > 0 && mods.every((m) => m.kind === 'tool');

export function browse(view, { prof, group, catalog }) {
  const groups = group ? [group] : prof.groups;
  const mods = groups.flatMap((g) => (g.modules || []).map((m) => ({ ...m, _group: g.name })));
  view.innerHTML = `
    <div class="page-head">
      <div><h1>${prof.name}${group ? ' · ' + group.name : ''}</h1>
        <p>${prof.desc || ''} · ${mods.length ? mods.length + ' 个模块' : '暂时留空'}</p></div>
      <div class="spacer"></div>
      <span class="chip ${mods.length && prof.status === 'active' && !toolsOnly(mods) ? 'green' : ''}">${
        !mods.length ? '待补充'
        : toolsOnly(mods) ? '工具'
        : (prof.status === 'active' ? '已接入' : '框架预留')}</span>
    </div>
    ${mods.length ? `<div class="grid g2">
      ${mods.map((m) => `
        <div class="card clickable" data-go="#/m/${m.id}">
          <div class="card-head">
            <h3>${m.name}</h3>
            <div class="right"><span class="chip ${m.kind === 'metric' ? 'green' : ''}">
              ${m.kind === 'metric' ? '已接入' : m.kind === 'tool' ? '开发中' : '待接入'}</span></div>
          </div>
          <div style="color:var(--ink-2);font-size:12.5px;min-height:38px">${m.desc || ''}</div>
          <div style="display:flex;gap:6px;margin-top:8px;flex-wrap:wrap">
            ${m._group && m._group !== prof.name ? `<span class="chip">${m._group}</span>` : ''}
            ${m.level ? `<span class="chip">${m.level}</span>` : ''}
            ${m.freq ? `<span class="chip">${m.freq}</span>` : ''}
          </div>
        </div>`).join('')}
    </div>` : `<div class="card"><div class="empty" style="padding:56px 20px">
        <b style="font-size:15px">${prof.name} · 先留空</b>
        <p style="margin:8px 0 0;color:var(--ink-3)">
          这一块暂时没有模块，后续把常用的小工具放进来即可（在 catalog.py 里加模块）。
        </p>
      </div></div>`}`;
  view.querySelectorAll('[data-go]').forEach((el) => { el.onclick = () => { location.hash = el.dataset.go; }; });
}
