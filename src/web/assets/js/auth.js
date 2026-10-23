/* auth.js —— 口令准入：五个大类 + 管理员
   会话只存在这个模块的内存里：导航/切换页面不丢，刷新页面或关掉网页即失效（这是需求）。
   服务端另有一份内存会话（12 小时闲置过期），这里只负责带 token 与弹口令框。 */
import { toast } from './ui.js';

const S = { token: null, role: null, label: '', admin: false, scope: [] };

export const auth = {
  get ok() { return !!S.token; },
  get token() { return S.token; },
  get role() { return S.role; },
  get label() { return S.label; },
  get admin() { return S.admin; },
  get scope() { return S.scope; },
  /** 该大类能不能看（管理员全开；其余 = 自己 + 重点项目） */
  can(prof) { return S.admin || S.scope.includes(prof); },
  reset() { S.token = null; S.role = null; S.label = ''; S.admin = false; S.scope = []; },
};

/* ---------------------------------------------------------------- 请求 */
export async function authFetch(url, opts = {}) {
  const headers = new Headers(opts.headers || {});
  if (S.token) headers.set('X-Auth', S.token);
  const res = await fetch(url, { ...opts, headers });
  if (res.status === 401) {
    auth.reset();
    window.dispatchEvent(new CustomEvent('dash:auth-lost'));
    throw Object.assign(new Error('需要验证口令'), { auth: true });
  }
  return res;
}

export async function login(password) {
  const res = await fetch('/api/auth/login', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  });
  const r = await res.json().catch(() => ({}));
  if (!res.ok || !r.ok) return null;
  Object.assign(S, { token: r.token, role: r.role, label: r.label, admin: !!r.admin, scope: r.scope || [] });
  return r;
}

/* ---------------------------------------------------------------- 图标 */
const ICON_LOCK = (s = 22) => `<svg viewBox="0 0 24 24" width="${s}" height="${s}" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><rect x="4.5" y="10" width="15" height="10.5" rx="3"/><path d="M8 10V7.5a4 4 0 0 1 8 0V10"/><circle cx="12" cy="15" r="1.6" fill="currentColor" stroke="none"/></svg>`;

/* ---------------------------------------------------------------- 口令框 */
let maskEl = null;

/**
 * 弹口令框；返回 Promise<boolean>（true = 验证通过）。
 * @param {{title?:string, sub?:string, note?:string}} opts
 */
export function askPassword({ title = '身份验证', sub = '', note = '' } = {}) {
  if (maskEl) {                          // 不叠两个框：先把上一个取消掉（否则它的 Promise 会一直挂着）
    if (maskEl._cancel) maskEl._cancel();
    else maskEl.remove();
  }
  return new Promise((resolve) => {
    const mask = document.createElement('div');
    mask.className = 'gate-mask';
    mask.innerHTML = `
      <div class="gate-card" role="dialog" aria-modal="true">
        <button class="gate-x" title="取消">✕</button>
        <div class="gate-emblem">${ICON_LOCK(24)}</div>
        <h3>${title}</h3>
        <p class="gate-sub">${sub || '输入分管大类的口令进入'}</p>
        <form class="gate-form" autocomplete="off">
          <input type="password" id="gateInput" placeholder="请输入口令" autocomplete="current-password" spellcheck="false">
          <button class="btn btn-primary" type="submit" id="gateGo">进入</button>
        </form>
        <div class="gate-msg" id="gateMsg"></div>
        <div class="gate-note">${note || '五大类口令 → 对应大类，均可看「重点项目」<br>管理员口令 → 全部大类'}</div>
      </div>`;
    document.body.appendChild(mask);
    maskEl = mask;
    requestAnimationFrame(() => mask.classList.add('on'));

    const input = mask.querySelector('#gateInput');
    const go = mask.querySelector('#gateGo');
    const msg = mask.querySelector('#gateMsg');
    let done = false;

    const close = (ok) => {
      if (done) return;
      done = true;
      document.removeEventListener('keydown', esc);
      mask.classList.remove('on');
      setTimeout(() => mask.remove(), 220);
      if (maskEl === mask) maskEl = null;
      resolve(ok);
    };
    mask._cancel = () => close(false);
    mask.querySelector('.gate-x').onclick = () => close(false);
    mask.onclick = (e) => { if (e.target === mask) close(false); };
    const esc = (e) => { if (e.key === 'Escape') { close(false); document.removeEventListener('keydown', esc); } };
    document.addEventListener('keydown', esc);

    mask.querySelector('.gate-form').onsubmit = async (e) => {
      e.preventDefault();
      const pw = input.value;
      if (!pw) { input.focus(); return; }
      go.disabled = true;
      input.disabled = true;
      msg.textContent = '';
      msg.className = 'gate-msg';
      try {
        const r = await login(pw);
        if (!r) {
          msg.textContent = '口令不正确，请重试';
          msg.className = 'gate-msg bad';
          mask.querySelector('.gate-card').classList.add('shake');
          setTimeout(() => mask.querySelector('.gate-card')?.classList.remove('shake'), 420);
          input.value = '';
          input.disabled = false;
          go.disabled = false;
          input.focus();
          return;
        }
        document.removeEventListener('keydown', esc);
        close(true);
      } catch (err) {
        msg.textContent = `无法连接服务：${err.message}`;
        msg.className = 'gate-msg bad';
        input.disabled = false;
        go.disabled = false;
      }
    };
    setTimeout(() => input.focus(), 60);
  });
}

/* ---------------------------------------------------------------- 管理密码 */
const FALLBACK_ROLES = [
  { id: 'jg', name: '个金', full: '个人金融' },
  { id: 'wj', name: '网金', full: '网络金融' },
  { id: 'loan', name: '个贷', full: '个人贷款' },
  { id: 'card', name: '银行卡', full: '银行卡' },
  { id: 'pbs', name: '私银', full: '私人银行' },
  { id: 'admin', name: '管理员', full: '系统管理员' },
];

/** 管理员：重置六个身份组的口令 */
export function openPasswordManager(roles) {
  if (maskEl) {                          // 同上：不叠框
    if (maskEl._cancel) maskEl._cancel();
    else maskEl.remove();
  }
  const list = (roles && roles.length ? roles : FALLBACK_ROLES);
  const mask = document.createElement('div');
  mask.className = 'gate-mask';
  mask.innerHTML = `
    <div class="gate-card wide" role="dialog" aria-modal="true">
      <button class="gate-x" title="关闭">✕</button>
      <div class="gate-head-row">
        <div class="gate-emblem sm">${ICON_LOCK(18)}</div>
        <div><h3>管理密码</h3>
          <p class="gate-sub">六个身份组各一个口令，重置后立即生效；已登录的会话不受影响</p></div>
      </div>
      <div class="pw-list">
        ${list.map((r) => `
          <div class="pw-row" data-role="${r.id}">
            <div class="pw-name"><b>${r.full}</b><small>${r.name}</small></div>
            <input type="password" placeholder="新口令（至少 6 位）" autocomplete="new-password" spellcheck="false">
            <button class="btn btn-sm" data-reset>重置</button>
          </div>`).join('')}
      </div>
      <div class="gate-msg" id="pwMsg"></div>
    </div>`;
  document.body.appendChild(mask);
  maskEl = mask;
  requestAnimationFrame(() => mask.classList.add('on'));

  const close = () => {
    document.removeEventListener('keydown', esc);
    mask.classList.remove('on');
    setTimeout(() => mask.remove(), 220);
    if (maskEl === mask) maskEl = null;
  };
  mask.querySelector('.gate-x').onclick = close;
  mask.onclick = (e) => { if (e.target === mask) close(); };
  const esc = (e) => { if (e.key === 'Escape') { close(); document.removeEventListener('keydown', esc); } };
  document.addEventListener('keydown', esc);

  const msg = mask.querySelector('#pwMsg');
  mask.querySelectorAll('.pw-row').forEach((row) => {
    const input = row.querySelector('input');
    const btn = row.querySelector('[data-reset]');
    const submit = async () => {
      const pw = input.value.trim();
      if (pw.length < 6) { msg.textContent = '口令至少 6 位'; msg.className = 'gate-msg bad'; input.focus(); return; }
      btn.disabled = true;
      input.disabled = true;
      try {
        const res = await authFetch('/api/auth/password', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ role: row.dataset.role, password: pw }),
        });
        const r = await res.json();
        if (!r.ok) throw new Error(r.error || '重置失败');
        input.value = '';
        const name = row.querySelector('.pw-name b').textContent;
        toast(`${name} 的口令已更新`);
        msg.textContent = '已更新，请牢记新口令';
        msg.className = 'gate-msg ok';
      } catch (err) {
        if (!err.auth) { msg.textContent = err.message; msg.className = 'gate-msg bad'; }
        else close();
      } finally {
        btn.disabled = false;
        input.disabled = false;
      }
    };
    btn.onclick = submit;
    input.onkeydown = (e) => { if (e.key === 'Enter') { e.preventDefault(); submit(); } };
  });
  setTimeout(() => mask.querySelector('.pw-row input')?.focus(), 80);
}
