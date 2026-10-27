/* pages/guide.js —— 「帮助」两个页面：使用指南 / 更新日志
   路由：#/guide             指南顶部
        #/guide/<section>   指南里的某一节（模块页右上角的"使用指南"就跳这里）
        #/changelog         更新日志（与指南并行，用页面左上角的页签切换）
   两个页面共用同一个外壳（doc-head 页签 + 正文），互切只换内容不换布局。 */
import { GUIDE_SECTIONS } from '../guide-content.js';
import { CHANGELOG } from '../changelog.js';
import { icon } from '../ui.js';

const GROUPS = ['开始', '看数据', '管数据', '各模块', '其他'];
const SECTION_IDS = new Set(GUIDE_SECTIONS.map((s) => s.id));

/** 给 app.js 用：模块页 → 指南里对应那一节（没有专门的节就回指南首页） */
export function guideHref(moduleId) {
  return moduleId && SECTION_IDS.has(moduleId) ? `#/guide/${moduleId}` : '#/guide';
}

let scrollHandler = null;

function killScrollHandler() {
  if (scrollHandler) {
    window.removeEventListener('scroll', scrollHandler);
    scrollHandler = null;
  }
}

/* ---------------------------------------------------------------- 外壳 */
/** 页面左上角的两个页签：使用指南 / 更新日志 */
function tabsHTML(mode) {
  return `<div class="doc-tabs">
    <a href="#/guide" class="doc-tab${mode === 'guide' ? ' on' : ''}">${icon('overview', 13)} 使用指南</a>
    <a href="#/changelog" class="doc-tab${mode === 'log' ? ' on' : ''}">${icon('spark', 13)} 更新日志</a>
  </div>`;
}

function headHTML({ mode, title, desc, meta }) {
  return `<div class="g-hero${mode === 'log' ? ' log' : ''}">
    ${tabsHTML(mode)}
    <h1>${title}</h1>
    <p>${desc}</p>
    ${meta ? `<div class="g-meta">${meta}</div>` : ''}
  </div>`;
}

/* ---------------------------------------------------------------- 使用指南 */
function tocHTML() {
  const main = GROUPS.filter((g) => g !== '其他')
    .map((g) => ({ group: g, items: GUIDE_SECTIONS.filter((s) => s.group === g) }))
    .filter((x) => x.items.length);
  const other = GUIDE_SECTIONS.filter((s) => s.group === '其他');
  return `<div class="gn-title">目录</div>`
    + main.map((g) => `
    <div class="gn-title" style="padding-top:10px">${g.group}</div>
    ${g.items.map((s) => `<a href="#/guide/${s.id}" data-sec="${s.id}">${s.title}</a>`).join('')}`).join('')
    + `<div class="gn-title" style="padding-top:10px">其他</div>
       ${other.map((s) => `<a href="#/guide/${s.id}" data-sec="${s.id}">${s.title}</a>`).join('')}
       <a href="#/changelog">更新日志 →</a>`;
}

function secHTML(s, i) {
  return `<section class="g-sec" id="g-${s.id}">
    <h2><span class="g-num">${i + 1}</span>${s.title}</h2>
    ${s.summary ? `<p class="g-sum">${s.summary}</p>` : ''}
    <div class="g-body">${s.body}</div>
    ${relatedHTML(s)}
  </section>`;
}

/** 模块章节底部给"去那个页面看看 / 去导入"两个出口 */
function relatedHTML(s) {
  if (s.group !== '各模块') return '';
  const links = [`<a href="#/m/${s.id}">打开「${s.title}」</a>`];
  if (s.id.indexOf('tool-') === 0) links.push('<a href="#/p/tool">实用工具</a>');
  else links.push(`<a href="#/upload/${s.id}">导入这个模块的数据</a>`);
  return `<div class="g-links">${links.join('')}<a href="#/report">通报中心</a></div>`;
}

/* ---------------------------------------------------------------- 更新日志 */
function logHTML() {
  return CHANGELOG.map((c, i) => `
    <div class="g-log-item${i === 0 ? ' new' : ''}" id="v-${c.version}">
      <h4><span class="g-ver">${c.version}</span>${c.title}${c.date ? `<span class="g-day">${c.date}</span>` : ''}</h4>
      <ul>${c.items.map((t) => `<li>${t}</li>`).join('')}</ul>
    </div>`).join('');
}

/** 日志页的左侧索引：按版本跳转（和指南的目录占同样的宽度，两个页签切换时不跳位） */
function versionIndexHTML() {
  return `<div class="gn-title">版本</div>`
    + CHANGELOG.map((c, i) => `<a href="#/changelog" data-ver="${c.version}"
        class="${i === 0 ? 'on' : ''}">${c.version}<em>${c.date || ''}</em></a>`).join('');
}

export default {
  id: 'guide',
  title: '使用指南',

  render(view, { catalog, section }) {
    killScrollHandler();
    const ver = catalog?.version || '';
    const build = catalog?.build || '';
    const meta = [`共 ${GUIDE_SECTIONS.length} 节`];
    if (ver) meta.push(`当前版本 v${ver}`);
    if (build) meta.push(`构建 ${build}`);

    view.innerHTML = `
      <div class="guide-wrap">
        <nav class="guide-nav" id="gNav">${tocHTML()}</nav>
        <div class="guide-body">
          ${headHTML({
            mode: 'guide',
            title: '使用指南',
            desc: '按"先看什么、怎么操作、每个模块看什么"的顺序写。不熟悉的话，从第一节往后看一遍大约十分钟；'
              + '只想查某个按钮，用左边目录直接跳。',
            meta: meta.map((x) => `<span>${x}</span>`).join(''),
          })}
          ${GUIDE_SECTIONS.map(secHTML).join('')}
          <div class="g-top"><button id="gTop">${icon('up', 13)} 回到最上边</button></div>
        </div>
      </div>`;
  },

  /** 渲染收尾（app.js 在 paintTop 之后调）：定位到指定小节 + 高亮目录 */
  after(view, section) {
    const nav = view.querySelector('#gNav');
    const btn = view.querySelector('#gTop');
    if (btn) btn.onclick = () => { window.scrollTo(0, 0); };

    const links = nav ? Array.from(nav.querySelectorAll('a[data-sec]')) : [];
    const mark = (id) => links.forEach((a) => a.classList.toggle('on', a.dataset.sec === id));

    // 顶栏按钮进来时直接落到对应小节；锚点在粘性顶栏下面，用 scrollIntoView 的边距处理不了，
    // 这里手动算偏移（顶栏 62px + 16px 余量）
    const target = section ? view.querySelector(`#g-${section}`) : null;
    if (target) {
      const y = target.getBoundingClientRect().top + window.pageYOffset - 78;
      window.scrollTo(0, Math.max(0, y));
      mark(section);
    } else {
      mark(null);
    }

    scrollHandler = () => {
      let cur = null;
      for (const el of view.querySelectorAll('.g-sec')) {
        if (el.getBoundingClientRect().top <= 110) cur = el.id.replace(/^g-/, '');
      }
      mark(cur);
    };
    window.addEventListener('scroll', scrollHandler, { passive: true });
    scrollHandler();
  },
};

/* ---------------------------------------------------------------- 更新日志页
   与指南并行的独立页面（不是指南里的一节）：
   页面左上角同样是两个页签，切过去再切回来都在。 */
export const changelogPage = {
  id: 'changelog',
  title: '更新日志',

  render(view, { catalog }) {
    killScrollHandler();
    const cur = CHANGELOG[0] || {};
    const ver = catalog?.version || '';
    const meta = [];
    if (cur.version) meta.push(`最新 ${cur.version}${cur.date ? ' · ' + cur.date : ''}`);
    if (ver) meta.push(`当前版本 v${ver}`);
    meta.push(`共 ${CHANGELOG.length} 次更新`);

    view.innerHTML = `
      <div class="guide-wrap">
        <nav class="guide-nav" id="gNav">${versionIndexHTML()}</nav>
        <div class="guide-body">
          ${headHTML({
            mode: 'log',
            title: '更新日志',
            desc: '每次升级都记在这里：新增了什么、口径有没有调整、修掉了哪些问题。'
              + '最新的在最上面，想确认手上这个版本有没有某功能，对着版本号找。',
            meta: meta.map((x) => `<span>${x}</span>`).join(''),
          })}
          <section class="g-sec log-sec" id="g-changelog">
            <div class="g-log">${logHTML()}</div>
          </section>
          <div class="g-top"><button id="gTop">${icon('up', 13)} 回到最上边</button></div>
        </div>
      </div>`;
  },

  after(view) {
    killScrollHandler();
    const btn = view.querySelector('#gTop');
    if (btn) btn.onclick = () => { window.scrollTo(0, 0); };

    // 左侧版本索引：点一下滚到那一版（不是换页，只滚）
    const nav = view.querySelector('#gNav');
    const links = nav ? Array.from(nav.querySelectorAll('a[data-ver]')) : [];
    const mark = (v) => links.forEach((a) => a.classList.toggle('on', a.dataset.ver === v));
    links.forEach((a) => {
      a.onclick = (e) => {
        e.preventDefault();
        // 版本号里带点（0.1.2），不能用 querySelector('#v-0.1.2')：点会被当成 class 分隔符
        const el = view.querySelector('.g-log-item') && [...view.querySelectorAll('.g-log-item')]
          .find((x) => x.id === `v-${a.dataset.ver}`);
        if (!el) return;
        window.scrollTo(0, Math.max(0, el.getBoundingClientRect().top + window.pageYOffset - 88));
        mark(a.dataset.ver);
      };
    });

    // 日志一共八九条，一屏基本看得见，不做滚动联动高亮（滚动联动会跟点击打架，
    // 点 0.1.2 后立刻被"当前可见的那条"覆盖）。点谁就标谁，够用。
  },
};
