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
    let sales = null;            // {支行: {键: 值}}：当前编辑中的值
    let salesSaved = null;       // 已保存的值（用于判断"有没有改"）
    let salesDirty = false;
    // 定期承接「手动编辑」：按客编查行、改四列，提交时随 overrides 一起回传
    let jpEdits = new Map();     // key=`客编|机构|到期日` → {custno, net, due, due_amt, bal_d, ast_d}
    let jpSearching = false;

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
        <div class="mod-grid" id="modGrid"><div class="empty" style="padding:26px">先选上面的分类</div></div>
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
              ${icon('arrow', 15)} 提交
            </button>
          </div>
        </div>

        <div class="card">
          <div class="card-head"><h3>数据时点</h3>
            <div class="right"><span class="chip">仅显示有权限的条线</span></div></div>
          <div class="timeline" id="impTimeline"></div>
        </div>
      </div>

      <div class="card" id="jpEditCard" style="margin-top:14px;display:none">
        <div class="card-head"><h3>④ 手动编辑明细（可选）</h3>
          <div class="right">
            <span class="chip" id="jpEditCount" style="display:none"></span>
            <span class="chip amber" id="jpEditHint">不填也行，直接提交即可</span>
          </div></div>
        <p style="margin:0 0 12px;color:var(--ink-3);font-size:12px">
          个别客户要先人工处理（比如到期后资产整体流失的，不算网点未承接），可以在这里按
          <b>客户编号</b> 找到那一行，把 <b>到期金额 / 定期余额变化 / 时点资产变化 / 最近到期日期</b>
          改成想要的值，再提交。<b>只改这一份数据，不动源文件</b>；不改就照原样导入。
        </p>
        <div class="jp-find">
          <input type="text" id="jpCustno" placeholder="输入客户编号，例如 131100038448885" autocomplete="off">
          <button class="btn btn-primary" id="jpFind">查找</button>
          <button class="btn btn-sm" id="jpClearEdits" style="margin-left:auto">清空已改</button>
        </div>
        <div id="jpEditBox" style="margin-top:12px"></div>
      </div>

      <div class="card" id="salesCard" style="margin-top:14px;display:none">
        <div class="card-head"><h3>④ 私银产品销售（人工维护）</h3>
          <div class="right"><span class="chip">单位：万元 / 户</span>
            <span class="chip amber" id="salesDirty" style="display:none">有未保存的修改</span></div></div>
        <p style="margin:0 0 10px;color:var(--ink-3);font-size:12px">
          这块是手工填的，**不用每次重填**：改哪个格子改哪个，提交后一直留着；
          导入当天明细时会一起合进通报，页面和 Excel 随即更新。</p>
        <div id="salesGrid"></div>
        <div style="display:flex;gap:10px;margin-top:12px">
          <button class="btn" id="btnSalesReset">还原为已保存</button>
          <button class="btn btn-primary" id="btnSalesSave" style="margin-left:auto">保存产品销售</button>
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

    // ---------- ① 大类（没有模块的板块，比如"实用工具"，不在这里出现）
    const uploadable = cat.professionals.filter((p) => p.upload !== false
      && (p.groups || []).some((g) => (g.modules || []).length));
    profGrid.innerHTML = uploadable.map((p) => {
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
      showSales(m.as_line === 'pbs');
      showJpEdit(m.as_line === 'jp');
      sync();
    }

    // ---------- ④ 私银产品销售（只有 pbs 模块才出现）
    const SALES_COLS = [
      ['xl_bal', '遴选余额'], ['xl_q4', '遴选季度增量'], ['kd_amt', '快贷提款'],
      ['xt_out', '信托已出单'], ['xt_sold', '信托已销售'],
      ['bx_out', '保险已出单'], ['bx_sold', '保险已销售'],
    ];
    const SALES_BR = ['颍州', '颍泉', '颍东', '界首', '临泉', '阜南', '颍上', '太和'];
    const salesCard = view.querySelector('#salesCard');
    const salesGrid = view.querySelector('#salesGrid');

    function emptySales() {
      const o = {};
      SALES_BR.forEach((b) => { o[b] = {}; SALES_COLS.forEach(([k]) => { o[b][k] = 0; }); });
      return o;
    }

    function showSales(on) {
      salesCard.style.display = on ? '' : 'none';
      if (!on) return;
      if (!sales) { sales = emptySales(); salesSaved = emptySales(); }
      paintSales();
    }

    function paintSales() {
      salesGrid.innerHTML = `<div class="tbl-wrap"><table class="tbl sales-tbl" style="table-layout:fixed;width:100%">
        <thead><tr><th style="width:64px">支行</th>
          ${SALES_COLS.map(([, n]) => `<th>${n}</th>`).join('')}</tr></thead>
        <tbody>${SALES_BR.map((b) => `<tr>
          <td class="strong" style="text-align:left">${b}</td>
          ${SALES_COLS.map(([k]) => `<td><input type="number" step="any" data-br="${b}" data-k="${k}"
            value="${sales[b][k] ?? 0}"></td>`).join('')}
        </tr>`).join('')}</tbody></table></div>`;
      salesGrid.querySelectorAll('input').forEach((el) => {
        el.oninput = () => {
          const v = Number(el.value);
          sales[el.dataset.br][el.dataset.k] = Number.isFinite(v) ? v : 0;
          checkDirty();
        };
      });
    }

    function checkDirty() {
      salesDirty = JSON.stringify(sales) !== JSON.stringify(salesSaved);
      view.querySelector('#salesDirty').style.display = salesDirty ? '' : 'none';
      sync();
    }

    async function loadSales() {
      try {
        const r = await authFetch('/api/pbs/sales', { cache: 'no-store' }).then((x) => x.json());
        if (r.ok) { sales = r.sales; salesSaved = JSON.parse(JSON.stringify(r.sales)); }
      } catch (err) {
        if (err.auth) return;
      }
      if (!sales) { sales = emptySales(); salesSaved = emptySales(); }
      checkDirty();
      if (mod?.as_line === 'pbs') paintSales();
    }

    view.querySelector('#btnSalesSave').onclick = async (e) => {
      const btn = e.currentTarget;
      btn.disabled = true;
      try {
        const res = await authFetch('/api/pbs/sales', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ sales }),
        });
        const r = await res.json();
        if (!r.ok) throw new Error(r.error || '保存失败');
        salesSaved = JSON.parse(JSON.stringify(sales));
        checkDirty();
        toast('产品销售已保存');
        if (ctx.reloadData) await ctx.reloadData();
      } catch (err) {
        if (!err.auth) toast(err.message, 'err');
      } finally {
        btn.disabled = false;
      }
    };
    view.querySelector('#btnSalesReset').onclick = () => {
      sales = JSON.parse(JSON.stringify(salesSaved));
      paintSales();
      checkDirty();
      toast('已还原为上次保存的值');
    };

    // ---------- ④ 定期承接：手动编辑明细（可选）
    const jpCard = view.querySelector('#jpEditCard');
    const jpBox = view.querySelector('#jpEditBox');
    const jpCount = view.querySelector('#jpEditCount');

    const JP_FIELDS = [
      ['due', '最近到期日期', 'date'],
      ['due_amt', '近30天到期金额（元）', 'number'],
      ['bal_d', '定期余额变化（元）', 'number'],
      ['ast_d', '时点资产变化（元）', 'number'],
    ];
    const jpKey = (o) => `${o.custno}|${o.net}|${o.due}`;

    function showJpEdit(on) {
      jpCard.style.display = on ? '' : 'none';
      if (on) paintJpEdits();
    }

    function paintJpEdits() {
      const n = jpEdits.size;
      jpCount.style.display = n ? '' : 'none';
      jpCount.textContent = `已手动改 ${n} 行`;
      sync();
    }

    function renderJpRows(rows) {
      // rows: 刚查出来的原始行；编辑框里显示"已改过就用改后的值"
      jpBox.innerHTML = rows.map((r) => {
        const cur = jpEdits.get(jpKey(r)) || {};
        const v = (k) => (cur[k] !== undefined ? cur[k] : r[k]);
        return `<div class="jp-edit-row" data-k="${jpKey(r)}">
          <div class="jp-edit-head">
            <b>${r.custno}</b>
            <span>${r.branch || '—'} / ${String(r.net || '').replace('阜阳', '')}</span>
            <span class="jp-edit-id" style="color:var(--ink-4);font-size:11px">
              30天前定期 ${fmt.n(r.bal30, 2)} → 当前 ${fmt.n(r.bal, 2)}</span>
          </div>
          <div class="jp-edit-grid">
            ${JP_FIELDS.map(([k, label, type]) => `
              <label>${label}
                <input type="${type}" ${type === 'number' ? 'step="0.01"' : ''}
                       data-f="${k}" value="${v(k)}">
              </label>`).join('')}
          </div>
          <div class="jp-edit-foot">
            <span class="jp-edit-warn" data-warn></span>
            <button class="btn btn-sm" data-act="reset">还原这一行</button>
          </div>
        </div>`;
      }).join('');

      jpBox.querySelectorAll('.jp-edit-row').forEach((box) => {
        const key = box.dataset.k;
        const orig = rows.find((r) => jpKey(r) === key);
        const mark = () => {
          const vals = {};
          box.querySelectorAll('input[data-f]').forEach((el) => {
            const k = el.dataset.f;
            vals[k] = el.type === 'number' ? Number(el.value) : el.value;
          });
          const changed = JP_FIELDS.some(([k]) => String(vals[k]) !== String(orig[k]));
          const rec = { custno: orig.custno, net: orig.net, ...vals };
          // net/due 用于定位，改过到期日时记住"原来是哪天"
          rec._origDue = orig.due;
          if (changed) jpEdits.set(key, rec); else jpEdits.delete(key);
          box.classList.toggle('edited', changed);
          const warn = box.querySelector('[data-warn]');
          // 变化 ≠ 当前 − 30天前 时提示：这正是"人工把变化改成 0"留下的特征
          const gap = Number(vals.due_amt) - Number(vals.bal_d);
          warn.textContent = changed ? '已修改，提交时生效' : '';
          paintJpEdits();
        };
        box.querySelectorAll('input[data-f]').forEach((el) => { el.oninput = mark; el.onchange = mark; });
        box.querySelector('[data-act="reset"]').onclick = () => {
          jpEdits.delete(key);
          renderJpRows(rows);
        };
        mark();       // 打开时先同步一次（可能是之前改过的）
      });
    }

    async function jpFind() {
      const custno = view.querySelector('#jpCustno').value.trim();
      if (!custno) return toast('请先输入客户编号', 'err');
      if (!files.length) return toast('请先把明细表放进来', 'err');
      if (jpSearching) return;
      jpSearching = true;
      const btn = view.querySelector('#jpFind');
      btn.disabled = true;
      jpBox.innerHTML = '<div class="result"><h4>正在查…</h4></div>';
      try {
        const fd = new FormData();
        fd.append('custno', custno);
        files.forEach((f) => fd.append('files', f, f.name));
        const res = await authFetch('/api/jiepan/find', { method: 'POST', body: fd });
        const r = await res.json();
        if (!r.ok) {
          jpBox.innerHTML = `<div class="result bad"><h4>没找到</h4><p>${r.error || ''}</p></div>`;
          return;
        }
        renderJpRows(r.rows);
      } catch (err) {
        if (err.auth) return;
        jpBox.innerHTML = `<div class="result bad"><h4>查询失败</h4><p>${err.message}</p></div>`;
      } finally {
        jpSearching = false;
        btn.disabled = false;
      }
    }
    view.querySelector('#jpFind').onclick = jpFind;
    view.querySelector('#jpCustno').onkeydown = (e) => { if (e.key === 'Enter') jpFind(); };
    view.querySelector('#jpClearEdits').onclick = () => {
      if (!jpEdits.size) return toast('还没有改过');
      jpEdits.clear();
      jpBox.innerHTML = '';
      paintJpEdits();
      toast('已清空手动修改');
    };

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
      // 只要有任意一边有内容就能提交：文件 或 产品销售
      view.querySelector('#btnSubmit').disabled = !(mod && (files.length || salesDirty));
    }
    view.querySelector('#btnClear').onclick = () => { files.length = 0; sync(); view.querySelector('#result').innerHTML = ''; };

    // ---------- 提交
    view.querySelector('#btnSubmit').onclick = async (e) => {
      const btn = e.currentTarget;
      btn.disabled = true;
      const box = view.querySelector('#result');

      // 只有产品销售有改动时：先保存，不必再导文件
      if (!files.length && salesDirty) {
        box.innerHTML = '<div class="result"><h4>正在保存产品销售…</h4></div>';
        try {
          const res = await authFetch('/api/pbs/sales', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sales }),
          });
          const r = await res.json();
          if (!r.ok) throw new Error(r.error || '保存失败');
          salesSaved = JSON.parse(JSON.stringify(sales));
          checkDirty();
          box.innerHTML = '<div class="result ok"><h4>产品销售已保存</h4>'
            + '<p style="margin:4px 0 0;color:var(--ink-3)">通报与页面已按新值更新</p></div>';
          toast('产品销售已保存');
          if (ctx.reloadData) await ctx.reloadData();
          paint();
        } catch (err) {
          if (!err.auth) box.innerHTML = `<div class="result bad"><h4>保存失败</h4><p>${err.message}</p></div>`;
        }
        btn.disabled = false;
        return;
      }
      box.innerHTML = `<div class="result"><h4>正在识别与计算…</h4>
        <p style="color:var(--ink-3);margin:4px 0 0">${prof.name} / ${mod.name} · ${files.length} 个文件</p></div>`;
      const fd = new FormData();
      fd.append('line', mod.as_line);
      fd.append('module', mod.id);
      const dt = view.querySelector('#impDate').value;
      if (dt) fd.append('date', dt);
      files.forEach((f) => fd.append('files', f, f.name));
      // 定期承接：把页面里手改过的行一起带上（服务端按 客编+机构+到期日 覆盖）
      if (mod.as_line === 'jp' && jpEdits.size) {
        const ov = [...jpEdits.values()].map((o) => ({
          custno: o.custno, net: o.net, due: o.due,
          due_amt: o.due_amt, bal_d: o.bal_d, ast_d: o.ast_d,
        }));
        fd.append('overrides', JSON.stringify(ov));
      }
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
          files.length = 0;
          jpEdits.clear();
          jpBox.innerHTML = '';
          if (mod?.as_line === 'jp') paintJpEdits();
          sync();
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
      const total = st.db?.imports;
      view.querySelector('#ledgerCount').textContent =
        total ? `最近 ${ledger.length} 条 · 共 ${total} 条` : `${ledger.length} 条`;
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
    loadSales();
  },
};
