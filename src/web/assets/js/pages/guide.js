/* pages/guide.js —— 使用指南（正文在 guide-content.js，更新记录在 changelog.js）
   路由：#/guide            打开指南顶部
        #/guide/<section>  直接落到某一节（模块页右上角的"使用指南"就跳这里）
   左侧目录常驻、右侧正文分节；底部有"回到最上边"。 */
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

function tocHTML() {
  const main = GROUPS.filter((g) => g !== '其他').map((g) => ({ group: g, items: GUIDE_SECTIONS.filter((s) => s.group === g) }))
    .filter((x) => x.items.length);
  const other = GUIDE_SECTIONS.filter((s) => s.group === '其他');
  return `<div class="gn-title">目录</div>`
    + main.map((g) => `
    <div class="gn-title" style="padding-top:10px">${g.group}</div>
    ${g.items.map((s) => `<a href="#/guide/${s.id}" data-sec="${s.id}">${s.title}</a>`).join('')}`).join('')
    + `<div class="gn-title" style="padding-top:10px">其他</div>
       ${other.map((s) => `<a href="#/guide/${s.id}" data-sec="${s.id}">${s.title}</a>`).join('')}
       <a href="#/guide/changelog" data-sec="changelog">更新记录</a>`;
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

function changelogHTML() {
  const items = CHANGELOG.map((c, i) => `
    <div class="g-log-item${i === 0 ? ' new' : ''}">
      <h4><span class="g-ver">${c.version}</span>${c.title}${c.date ? `<span class="g-day">${c.date}</span>` : ''}</h4>
      <ul>${c.items.map((t) => `<li>${t}</li>`).join('')}</ul>
    </div>`).join('');
  return `<section class="g-sec" id="g-changelog">
    <h2><span class="g-num">${GUIDE_SECTIONS.length + 1}</span>更新记录</h2>
    <p class="g-sum">每次升级都记在这里：新功能、口径调整、修掉的问题。</p>
    <div class="g-log">${items}</div>
  </section>`;
}

export default {
  id: 'guide',
  title: '使用指南',

  render(view, { catalog, section }) {
    killScrollHandler();
    const ver = catalog?.version || '';
    const build = catalog?.build || '';
    view.innerHTML = `
      <div class="guide-wrap">
        <nav class="guide-nav" id="gNav">${tocHTML()}</nav>
        <div class="guide-body">
          <div class="g-hero">
            <h1>使用指南</h1>
            <p>这份指南按"先看什么、怎么操作、每个模块看什么"的顺序写。不熟悉的话，从第一节往后看一遍大约十分钟；
              只想查某个按钮，用左边目录直接跳。</p>
            <div class="g-meta">
              <span>共 ${GUIDE_SECTIONS.length} 节 + 更新记录</span>
              ${ver ? `<span>当前版本 v${ver}</span>` : ''}
              ${build ? `<span>构建 ${build}</span>` : ''}
            </div>
          </div>
          ${GUIDE_SECTIONS.map(secHTML).join('')}
          ${changelogHTML()}
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
      mark(section === 'changelog' ? 'changelog' : null);
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
