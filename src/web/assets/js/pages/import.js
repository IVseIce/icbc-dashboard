/* 数据导入：大类 → 源表 → 识别 → 归档 → 刷新（导入后可直接跳到该条线） */
import { fmt, toast, icon, empty } from '../ui.js';

const LINES = {
  dqzz: { label: '定期存款', hint: '分品种、期限时点报表：本月 + 上月（可一个 xls 多 sheet）', page: '#/deposit', accent: 'violet' },
  xsfw: { label: '网点线上服务', hint: '动户率×2 + 企微明细×3 + 营销授权（模板可缺）', page: '#/online', accent: 'red' },
  sbqb: { label: '数字人民币钱包', hint: '钱包开立明细表（含网点号/钱包等级/注册日期）', page: '#/wallet', accent: 'blue' },
  xgj: { label: '工银薪管家', hint: '四张增量表：支行/网点 × 年度/月度', page: '#/salary', accent: 'teal' },
  qwsq: { label: '企微社群', hint: '成员群聊数据统计：本周 + 上周', page: '#/community', accent: 'amber' },
};
const ORDER = ['dqzz', 'xsfw', 'sbqb', 'xgj', 'qwsq'];

export default {
  id: 'import',
  title: '数据导入',
  nav: '导入数据',
  icon: 'import',
  render(view, data, ctx) {
    const files = [];
    let line = '';
    let lastResult = null;

    view.innerHTML = `
      <div class="page-head">
        <div><h1>导入源数据</h1>
          <p>选大类 → 放源表 → 自动识别归属、归档、重算并刷新看板</p></div>
        <div class="spacer"></div>
        <span class="chip" id="impStatus">读取中…</span>
      </div>

      <div class="card">
        <div class="card-head"><h3>① 选择大类</h3>
          <div class="right"><span class="chip">识别按该类口径，选错会明确报错</span></div></div>
        <div class="import-grid" id="lineGrid"></div>
      </div>

      <div class="grid g-7-5" style="margin-top:16px">
        <div class="card">
          <div class="card-head"><h3>② 放入源表</h3>
            <div class="right">
              <label class="chip" style="cursor:pointer">数据日期 <input type="date" id="impDate"
                style="border:0;background:transparent;font-family:inherit;font-size:11px;color:var(--ink-2)"></label>
            </div></div>
          <div class="dropzone" id="drop">
            <div class="dz-icon">${icon('import', 22)}</div>
            <b>点击选择，或把文件拖进来</b>
            <p>支持 xlsx / xls / csv，可一次多选</p>
          </div>
          <input type="file" id="fileInput" multiple accept=".xlsx,.xls,.csv" hidden>
          <ul class="filelist" id="fileList"></ul>
          <div id="result"></div>
          <div style="display:flex;gap:10px;margin-top:14px">
            <button class="btn" id="btnClear">清空</button>
            <button class="btn btn-primary" id="btnSubmit" disabled style="margin-left:auto">
              ${icon('upload', 15)} 开始导入
            </button>
          </div>
        </div>

        <div class="card">
          <div class="card-head"><h3>数据时点</h3>
            <div class="right"><span class="chip">导入后自动更新</span></div></div>
          <div class="timeline" id="impTimeline"></div>
        </div>
      </div>

      <div class="card" style="margin-top:16px">
        <div class="card-head"><h3>最近导入</h3>
          <div class="right"><span class="chip" id="ledgerCount"></span></div></div>
        <div id="ledger"></div>
      </div>`;

    const grid = view.querySelector('#lineGrid');
    grid.innerHTML = ORDER.map((id) => `
      <div class="line-pick" data-id="${id}">
        <b>${LINES[id].label}</b>
        <small>${LINES[id].hint}</small>
        <span class="asof">—</span>
      </div>`).join('');

    grid.querySelectorAll('.line-pick').forEach((el) => {
      el.onclick = () => {
        grid.querySelectorAll('.line-pick').forEach((x) => x.classList.remove('on'));
        el.classList.add('on');
        line = el.dataset.id;
        sync();
      };
    });

    /* ---------------------------------------------------------- 文件 */
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

    const sync = () => {
      list.innerHTML = files.map((f, i) => `
        <li><span class="nm">${f.name}</span><span class="sz">${(f.size / 1024).toFixed(0)} KB</span>
        <span class="rm" data-i="${i}">✕</span></li>`).join('');
      list.querySelectorAll('.rm').forEach((el) => {
        el.onclick = () => { files.splice(+el.dataset.i, 1); sync(); };
      });
      view.querySelector('#btnSubmit').disabled = !(line && files.length);
    };
    view.querySelector('#btnClear').onclick = () => { files.length = 0; sync(); view.querySelector('#result').innerHTML = ''; };

    /* ---------------------------------------------------------- 提交 */
    view.querySelector('#btnSubmit').onclick = async (e) => {
      const btn = e.currentTarget;
      btn.disabled = true;
      const box = view.querySelector('#result');
      box.innerHTML = `<div class="result"><h4>正在识别与计算…</h4><p style="color:var(--ink-3);margin:4px 0 0">${files.length} 个文件</p></div>`;
      const fd = new FormData();
      fd.append('line', line);
      const dt = view.querySelector('#impDate').value;
      if (dt) fd.append('date', dt);
      files.forEach((f) => fd.append('files', f, f.name));
      try {
        const r = await fetch('/api/import', { method: 'POST', body: fd }).then((x) => x.json());
        lastResult = r;
        if (r.ok) {
          box.innerHTML = `<div class="result ok">
            <h4>导入成功 · ${LINES[line].label} · 数据日期 ${fmt.date(r.data_date)}</h4>
            <ul>${(r.files || []).map((f) => `<li><b>${f.name}</b> → <span style="color:var(--blue)">${f.role}</span></li>`).join('')}
              ${(r.notes || []).filter(Boolean).map((n) => `<li style="color:var(--ink-3)">${n}</li>`).join('')}</ul>
            <div style="margin-top:10px;display:flex;gap:8px">
              <a class="btn btn-primary" href="${LINES[line].page}">查看${LINES[line].label} ${icon('arrow', 14)}</a>
              <button class="btn" onclick="location.reload()">刷新页面</button>
            </div>
          </div>`;
          toast('导入成功，看板已更新');
          files.length = 0; sync();
          await ctx.reload();
          paintState();
        } else {
          box.innerHTML = `<div class="result bad"><h4>导入失败</h4><p>${r.error || '未知错误'}</p></div>`;
          toast('导入失败：' + (r.error || '').slice(0, 40), 'err');
          btn.disabled = false;
        }
      } catch (err) {
        box.innerHTML = `<div class="result bad"><h4>请求失败</h4><p>${err.message}</p></div>`;
        btn.disabled = false;
      }
    };

    /* ---------------------------------------------------------- 状态 */
    async function paintState() {
      const st = await fetch('/api/state', { cache: 'no-store' }).then((r) => r.json()).catch(() => null);
      if (!st?.ok) { view.querySelector('#impStatus').textContent = '服务未连接'; return; }
      view.querySelector('#impStatus').textContent = `已连接 ${st.root.replace(/^\/mnt\/([a-z])\//, (m, d) => d.toUpperCase() + ':\\').replace(/\//g, '\\')}`;
      const byId = Object.fromEntries(st.lines.map((l) => [l.id, l]));
      grid.querySelectorAll('.line-pick').forEach((el) => {
        const l = byId[el.dataset.id];
        el.querySelector('.asof').textContent = l?.as_of ? `最新 ${l.as_of} · ${l.snapshots} 期` : '尚未导入';
      });
      const tl = view.querySelector('#impTimeline');
      tl.innerHTML = st.lines.map((l) => {
        const c = LINES[l.id]?.accent || 'blue';
        const color = { violet: '#7c5cff', red: '#c8102e', blue: '#2563eb', teal: '#0ea5a5', amber: '#e8960c' }[c];
        return `<div class="tl-item" style="--accent:${color}"><i class="tl-dot"></i>
          <span class="tl-name">${l.label}</span>
          <span class="chip ${l.as_of ? 'green' : 'red'}" style="font-size:10px">${l.as_of ? '已就绪' : '待导入'}</span>
          <span class="tl-sub">${l.as_of ? fmt.date(l.as_of) : '—'} · ${l.snapshots} 期</span></div>`;
      }).join('');
      const led = st.ledger || [];
      view.querySelector('#ledgerCount').textContent = `${led.length} 条`;
      view.querySelector('#ledger').innerHTML = led.length ? `
        <div class="tbl-wrap" style="max-height:240px"><table class="tbl" style="table-layout:fixed;width:100%">
          <thead><tr><th style="width:92px">时间</th><th style="width:110px">大类</th><th style="width:92px">数据日期</th><th style="width:auto">文件</th><th style="width:82px">结果</th></tr></thead>
          <tbody>${led.map((r) => `<tr>
            <td style="text-align:left">${(r.ts || '').slice(5, 16)}</td>
            <td>${LINES[r.line]?.label || r.line}</td>
            <td>${r.data_date ? fmt.date(r.data_date) : '—'}</td>
            <td style="text-align:left;color:var(--ink-3);max-width:320px;overflow:hidden;text-overflow:ellipsis">${(r.files || []).join('、')}</td>
            <td>${r.ok ? '<span class="chip green">成功</span>' : `<span class="chip red">失败</span>`}</td>
          </tr>`).join('')}</tbody></table></div>`
        : empty('还没有导入记录');
    }

    paintState();
    sync();
  },
};
