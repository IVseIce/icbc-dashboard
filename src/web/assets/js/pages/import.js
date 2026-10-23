/* 数据导入：两级选择（大类 → 模块）→ 上传 → 识别 → 入库
   能进这一步说明口令已通过；没权限的大类置灰、不可点（管理员全开）。 */
import { fmt, toast, icon, empty } from '../ui.js';
import { auth, authFetch } from '../auth.js';

const LOCK = '<svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="4.5" y="10" width="15" height="10.5" rx="3"/><path d="M8 10V7.5a4 4 0 0 1 8 0V10"/></svg>';

export default {
  id: 'import',
  title: '数据导入',
  render(view, _data, ctx) {
    const cat = ctx.catalog;
    const files = [];
    let prof = null;
    let mod = null;
    let ledger = [];

    const canSee = (p) => auth.can(p.id);
    const who = auth.admin ? '管理员 · 全部板块' : `${auth.label} · 含重点项目`;

    view.innerHTML = `
      <div class="page-head">
        <div><h1>数据导入</h1>
          <p>选大类 → 选模块 → 放源表；系统按模块口径识别、归档、入库</p></div>
        <div class="spacer"></div>
        <span class="chip ${auth.admin ? 'red' : 'green'}" id="impWho">${who}</span>
        <span class="chip" id="impStatus">读取中…</span>
      </div>

      <div class="card">
        <div class="card-head"><h3>① 选择大类</h3>
          <div class="right"><span class="chip">灰色 = 当前口令无权访问</span></div></div>
        <div class="import-grid" id="profGrid"></div>
      </div>

      <div class="card" style="margin-top:14px">
        <div class="card-head"><h3>② 选择模块</h3>
          <div class="right" id="modHint"><span class="chip">先选大类</span></div></div>
        <div class="mod-grid" id="modGrid"><div class="empty" style="padding:26px">先选上面的模块</div></div>
      </div>

      <div class="grid g-7-5" style="margin-top:14px">
        <div class="card">
          <div class="card-head"><h3>③ 放入源表</h3>
            <div class="right">
              <label class="chip" style="cursor:pointer">数据日期
                <input type="date" id="impDate" style="border:0;background:transparent;font-family:inherit;font-size:11px">
              </label>
            </div></div>
          <div class="dropzone" id="drop">
            <div class="dz-icon">${icon('import', 22)}</div>
            <b>点击选择，或把文件拖进来</b>
            <p>支持 xlsx / xls / csv；扩展名与内容不符也能识别</p>
          </div>
          <input type="file" id="fileInput" multiple accept=".xlsx,.xls,.csv" hidden>
          <ul class="filelist" id="fileList"></ul>
          <div id="result"></div>
          <div style="display:flex;gap:10px;margin-top:14px">
            <button class="btn" id="btnClear">清空</button>
            <button class="btn btn-primary" id="btnSubmit" disabled style="margin-left:auto">
              ${icon('arrow', 15)} 开始导入
            </button>
          </div>
        </div>

        <div class="card">
          <div class="card-head"><h3>数据时点</h3>
            <div class="right"><span class="chip">仅显示有权限的条线</span></div></div>
          <div class="timeline" id="impTimeline"></div>
        </div>
      </div>

      <div class="card" style="margin-top:14px">
        <div class="card-head"><h3>最近导入</h3>
          <div class="right"><span class="chip" id="ledgerCount"></span></div></div>
        <div id="ledger"></div>
      </div>`;

    const profGrid = view.querySelector('#profGrid');
    const modGrid = view.querySelector('#modGrid');

    // 有权限的条线（用于过滤"数据时点"和"最近导入"）
    const allowedLines = new Set(cat.professionals.filter(canSee)
      .flatMap((p) => p.groups).flatMap((g) => g.modules || [])
      .map((m) => m.as_line).filter(Boolean));

    // ---------- ① 大类
    profGrid.innerHTML = cat.professionals.map((p) => {
      const ok = canSee(p);
      return `<div class="line-pick ${ok ? '' : 'locked'}" data-id="${p.id}">
        <b>${p.short || p.name}${ok ? '' : ` <em class="lp-lock">${LOCK}</em>`}</b>
        <small>${ok ? (p.desc || '') : '需要该大类的口令'}</small>
        <span class="asof" ${ok ? `data-asof="${p.id}"` : ''}>${ok ? '—' : '未授权'}</span>
      </div>`;
    }).join('');

    profGrid.querySelectorAll('.line-pick').forEach((el) => {
      el.onclick = () => {
        if (el.classList.contains('locked')) { toast('该大类需要对应的口令', 'err'); return; }
        selectProf(cat.professionals.find((p) => p.id === el.dataset.id));
      };
    });

    // ---------- ② 模块
    function selectProf(p, pick) {
      prof = p;
      mod = null;
      profGrid.querySelectorAll('.line-pick').forEach((x) => x.classList.toggle('on', x.dataset.id === p.id));
      renderModules();
      if (pick?.as_line) pickModule(pick);
    }

    function renderModules() {
      if (!prof) return;
      const groups = prof.groups || [];
      const mods = groups.flatMap((g) => (g.modules || []).map((m) => ({ ...m, _group: g.name })));
      view.querySelector('#modHint').innerHTML =
        `<span class="chip">${prof.short || prof.name} · ${mods.length} 个模块</span>`;
      modGrid.innerHTML = mods.map((m) => {
        const ok = !!m.as_line;
        return `<div class="mod-pick ${ok ? '' : 'off'}" data-id="${m.id}">
          <div class="mp-top"><b>${m.name}</b>
            <span class="chip ${ok ? 'green' : ''}" style="font-size:9.5px">${ok ? '可上传' : '暂不支持'}</span></div>
          <small>${m._group || ''}${m.source ? ' · ' + m.source : ''}</small>
        </div>`;
      }).join('');
      modGrid.querySelectorAll('.mod-pick').forEach((el) => {
        const m = mods.find((x) => x.id === el.dataset.id);
        if (!m?.as_line) return;
        el.onclick = () => pickModule(m);
      });
    }

    function pickModule(m) {
      mod = m;
      modGrid.querySelectorAll('.mod-pick').forEach((x) => x.classList.toggle('on', x.dataset.id === m.id));
      sync();
    }

    // ---------- ③ 文件
    const input = view.querySelector('#fileInput');
    const drop = view.querySelector('#drop');
    const list = view.querySelector('#fileList');
    const addFiles = (fl) => {
      for (const f of fl) {
        if (!/\.(xlsx|xls|csv)$/i.test(f.name)) { toast('只支持 xlsx / xls / csv', 'err'); continue; }
        if (!files.some((x) => x.name === f.name && x.size === f.size)) files.push(f);
      }
      sync();
    };
    drop.onclick = () => input.click();
    input.onchange = (e) => { addFiles(e.target.files); e.target.value = ''; };
    ['dragenter', 'dragover'].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add('over'); }));
    ['dragleave', 'drop'].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove('over'); }));
    drop.addEventListener('drop', (e) => addFiles(e.dataTransfer.files));

    function sync() {
      list.innerHTML = files.map((f, i) => `<li><span class="nm">${f.name}</span>
        <span class="sz">${(f.size / 1024).toFixed(0)} KB</span>
        <span class="rm" data-i="${i}">✕</span></li>`).join('');
      list.querySelectorAll('.rm').forEach((el) => {
        el.onclick = () => { files.splice(+el.dataset.i, 1); sync(); };
      });
      view.querySelector('#btnSubmit').disabled = !(mod && files.length);
    }
    view.querySelector('#btnClear').onclick = () => { files.length = 0; sync(); view.querySelector('#result').innerHTML = ''; };

    // ---------- 提交
    view.querySelector('#btnSubmit').onclick = async (e) => {
      const btn = e.currentTarget;
      btn.disabled = true;
      const box = view.querySelector('#result');
      box.innerHTML = `<div class="result"><h4>正在识别与计算…</h4>
        <p style="color:var(--ink-3);margin:4px 0 0">${prof.name} / ${mod.name} · ${files.length} 个文件</p></div>`;
      const fd = new FormData();
      fd.append('line', mod.as_line);
      fd.append('module', mod.id);
      const dt = view.querySelector('#impDate').value;
      if (dt) fd.append('date', dt);
      files.forEach((f) => fd.append('files', f, f.name));
      try {
        const res = await authFetch('/api/import', { method: 'POST', body: fd });
        const r = await res.json();
        if (r.ok) {
          box.innerHTML = `<div class="result ok">
            <h4>导入成功 · ${mod.name} · 数据日期 ${fmt.date(r.data_date)}</h4>
            <ul>${(r.files || []).map((f) => `<li><b>${f.name}</b> → <span style="color:var(--blue)">${f.role}</span></li>`).join('')}
              ${(r.notes || []).filter(Boolean).map((n) => `<li style="color:var(--ink-3)">${n}</li>`).join('')}</ul>
            <div style="margin-top:10px"><a class="btn btn-primary" href="#/m/${mod.id}">查看模块 ${icon('arrow', 14)}</a></div>
          </div>`;
          toast('导入成功');
          files.length = 0; sync();
          if (ctx.reloadData) await ctx.reloadData();
          paint();
        } else {
          box.innerHTML = `<div class="result bad"><h4>导入失败</h4><p>${r.error || '未知错误'}</p></div>`;
          btn.disabled = false;
        }
      } catch (err) {
        if (err.auth) return;                       // 口令失效：全局会弹口令框
        box.innerHTML = `<div class="result bad"><h4>请求失败</h4><p>${err.message}</p></div>`;
        btn.disabled = false;
      }
    };

    // ---------- 状态
    async function paint() {
      let st = null;
      try {
        st = await authFetch('/api/state', { cache: 'no-store' }).then((r) => r.json());
      } catch (err) {
        if (err.auth) return;
      }
      if (!st?.ok) { view.querySelector('#impStatus').textContent = '服务未连接'; return; }
      view.querySelector('#impStatus').textContent =
        `已连接 ${st.root.replace(/^\/mnt\/([a-z])\//, (m, d) => d.toUpperCase() + ':\\\\').replace(/\//g, '\\\\')}`;
      const by = Object.fromEntries(st.lines.map((l) => [l.id, l]));
      view.querySelectorAll('[data-asof]').forEach((el) => {
        const p = cat.professionals.find((x) => x.id === el.dataset.asof);
        const lines = (p?.groups || []).flatMap((g) => (g.modules || []).map((m) => m.as_line)).filter(Boolean);
        const dates = lines.map((l) => by[l]?.as_of).filter(Boolean).sort();
        el.textContent = dates.length ? `最新 ${dates[dates.length - 1].slice(5)}` : '尚未导入';
      });
      const lines = st.lines.filter((l) => allowedLines.has(l.id));
      view.querySelector('#impTimeline').innerHTML = lines.map((l) => `<div class="tl-item" style="--accent:#2563eb"><i class="tl-dot"></i>
        <span class="tl-name">${l.label}</span>
        <span class="chip ${l.as_of ? 'green' : 'red'}" style="font-size:10px">${l.as_of ? '已就绪' : '待导入'}</span>
        <span class="tl-sub">${l.as_of ? fmt.date(l.as_of) : '—'} · ${l.snapshots} 期</span></div>`).join('');

      ledger = (st.ledger || []).filter((r) => allowedLines.has(r.line));
      view.querySelector('#ledgerCount').textContent = `${ledger.length} 条`;
      view.querySelector('#ledger').innerHTML = ledger.length ? `
        <div class="tbl-wrap" style="max-height:220px"><table class="tbl" style="table-layout:fixed;width:100%">
          <thead><tr><th style="width:92px">时间</th><th style="width:120px">条线</th>
            <th style="width:92px">数据日期</th><th>文件</th><th style="width:80px">结果</th></tr></thead>
          <tbody>${ledger.map((r) => `<tr>
            <td style="text-align:left">${(r.ts || '').slice(5, 16)}</td>
            <td>${r.label || r.line}</td>
            <td>${r.data_date ? fmt.date(r.data_date) : '—'}</td>
            <td style="text-align:left;color:var(--ink-3);overflow:hidden;text-overflow:ellipsis">${(r.files || []).join('、')}</td>
            <td>${r.ok ? '<span class="chip green">成功</span>' : '<span class="chip red">失败</span>'}</td>
          </tr>`).join('')}</tbody></table></div>` : empty('还没有导入记录');
    }

    // 预选：优先「从模块页点导入」带过来的模块，否则落到自己有权限的大类
    const locate = (id) => {
      for (const p of cat.professionals) {
        for (const g of p.groups) {
          for (const m of g.modules || []) {
            if (m.id === id) return { prof: p, group: g, module: m };
          }
        }
      }
      return null;
    };
    const wanted = ctx.moduleId ? locate(ctx.moduleId) : null;
    const own = cat.professionals.find((p) => p.id === auth.role && canSee(p));
    if (wanted && canSee(wanted.prof)) selectProf(wanted.prof, wanted.module);
    else if (own) selectProf(own);

    paint();
    sync();
  },
};
