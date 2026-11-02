/* pages/admin.js —— 数据管理（管理员专用）
   路由 #/admin/data
   用途：导错了数据时，在这里把某一模块的某一期删掉，不用改数据库。
   删除是**软删除**（库里留痕、可恢复），删之前服务端会自动热备份一份。 */
import { fmt, toast, icon, empty } from '../ui.js';
import { auth, authFetch } from '../auth.js';

export default {
  id: 'admin',
  title: '数据管理',

  render(view, _data, ctx) {
    if (!auth.admin) {
      view.innerHTML = `<div class="card">${empty('需要管理员权限', '用管理员口令验证后从右上角身份菜单进入')}</div>`;
      return;
    }
    view.innerHTML = `
      <div class="page-head">
        <div><h1>数据管理</h1>
          <p>删除导错的数据 · 可以恢复 · 只影响本机库</p></div>
        <div class="spacer"></div>
        <button class="btn" id="admReload">${icon('arrow', 14)} 刷新</button>
      </div>
      <div class="card" id="admIntro">
        <div class="adm-note">
          <b>删除是软的</b>：数据只是标记成"已删除"，页面和通报立刻看不到，
          但库里还留着，随时能恢复。每次删除前系统会自动热备份一份数据库。
          <b>「原始数据」</b>那几项是内部线（按日存的原料），删了会让之后的拼装缺少对比基准，一般不用动。
        </div>
      </div>
      <div id="admBody"><div class="card"><div class="empty"><b>载入中…</b></div></div></div>`;

    const body = view.querySelector('#admBody');

    const load = async () => {
      body.innerHTML = '<div class="card"><div class="empty"><b>载入中…</b></div></div>';
      try {
        const res = await authFetch('/api/admin/data');
        const d = await res.json();
        if (!d.ok) throw new Error(d.error || '读取失败');
        body.innerHTML = d.lines.map((l) => lineCard(l)).join('');
        bind(d);
      } catch (err) {
        if (err.auth) return;
        body.innerHTML = `<div class="card"><div class="empty"><b>读取失败</b>${err.message}</div></div>`;
      }
    };

    const lineCard = (l) => {
      const pub = l.dates || [];
      const del = l.deleted || [];
      const chips = pub.length
        ? pub.slice().reverse().map((d) => `
            <button class="adm-date" data-line="${l.line}" data-asof="${d}">
              ${fmt.date(d).replace('月', '/').replace('日', '')}
            </button>`).join('')
        : '<span class="adm-none">暂无数据</span>';
      const delHTML = del.length ? `
        <div class="adm-del-row">
          <span class="adm-del-tag">已删 ${del.length} 期</span>
          ${del.map((x) => `<button class="adm-date del" data-restore="${l.line}" data-asof="${x.as_of}"
             title="删除于 ${x.deleted_at}，点击恢复">${fmt.date(x.as_of).replace('月', '/').replace('日', '')}</button>`).join('')}
        </div>` : '';
      return `
        <div class="card adm-line${l.internal ? ' internal' : ''}">
          <div class="adm-head">
            <b>${l.label}</b>
            <span class="chip">${l.count} 期</span>
            ${l.latest ? `<span class="chip">最新 ${fmt.date(l.latest)}</span>` : ''}
            ${l.internal ? '<span class="chip red">内部原始数据</span>' : ''}
            <span class="adm-hint">${l.hint || ''}</span>
          </div>
          <div class="adm-dates">${chips}</div>
          ${delHTML}
        </div>`;
    };

    const bind = (d) => {
      body.querySelectorAll('.adm-date[data-line]').forEach((b) => {
        b.onclick = () => askDelete(b.dataset.line, b.dataset.asof, d);
      });
      body.querySelectorAll('[data-restore]').forEach((b) => {
        b.onclick = () => doRestore(b.dataset.restore, b.dataset.asof);
      });
    };

    const labelOf = (line, d) => {
      const hit = (d.lines || []).find((x) => x.line === line);
      return hit ? hit.label : line;
    };

    /** 删除确认：写清"删什么、会影响什么、能不能恢复" */
    const askDelete = (line, asOf, d) => {
      document.querySelector('.adm-confirm')?.remove();
      const box = document.createElement('div');
      box.className = 'adm-confirm';
      const isLatest = (d.lines.find((x) => x.line === line) || {}).latest === asOf;
      box.innerHTML = `
        <div class="adm-cf-card">
          <h3>${icon('trash', 16)} 删除这一期？</h3>
          <div class="adm-cf-body">
            <div class="kv"><span>模块</span><b>${labelOf(line, d)}</b></div>
            <div class="kv"><span>数据日期</span><b>${asOf}</b></div>
            ${isLatest ? '<p class="adm-cf-warn">这是该模块<b>最新</b>的一期，删掉后页面会退回到上一期。</p>' : ''}
            <p class="adm-cf-ok">删除是<b>软删除</b>：库里还留着，随时能在「已删」里点一下恢复。
              删除前系统会自动备份一次数据库。</p>
          </div>
          <div class="adm-cf-acts">
            <button class="btn" data-cancel>取消</button>
            <button class="btn btn-primary" data-ok>确认删除</button>
          </div>
        </div>`;
      document.body.appendChild(box);
      const close = () => box.remove();
      box.onclick = (e) => { if (e.target === box) close(); };
      box.querySelector('[data-cancel]').onclick = close;
      box.querySelector('[data-ok]').onclick = async (e) => {
        const btn = e.currentTarget;
        btn.disabled = true;
        btn.textContent = '删除中…';
        try {
          const res = await authFetch('/api/admin/delete', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ line, as_of: asOf }),
          });
          const r = await res.json();
          if (!r.ok) throw new Error(r.error || '删除失败');
          close();
          toast(`已删除 ${labelOf(line, d)} ${asOf}`);
          if (r.warning && r.warning.text) toast(r.warning.text, 'err');
          await ctx.reloadData?.();
          await load();
        } catch (err) {
          if (err.auth) return;
          btn.disabled = false;
          btn.textContent = '确认删除';
          toast(err.message, 'err');
        }
      };
    };

    const doRestore = async (line, asOf) => {
      try {
        const res = await authFetch('/api/admin/restore', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ line, as_of: asOf }),
        });
        const r = await res.json();
        if (!r.ok) throw new Error(r.error || '恢复失败');
        toast(`已恢复 ${asOf}`);
        await ctx.reloadData?.();
        await load();
      } catch (err) {
        if (err.auth) return;
        toast(err.message, 'err');
      }
    };

    view.querySelector('#admReload').onclick = load;
    load();
  },
};
