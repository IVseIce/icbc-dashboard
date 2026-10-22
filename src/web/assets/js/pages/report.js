/* 通报中心（M3 实现）：先列出现有 5 条线的通报与规划 */
import { icon } from '../ui.js';

const LINES = [
  ['定期存款增长', '个金 · 增存', '表格 + 文案', '已具备数据'],
  ['数字人民币钱包', '网金 · 数币', '表格 + 文案', '已具备数据'],
  ['薪管家聚薪行动', '个金 · 增客', '表格 + 文案', '已具备数据'],
  ['网点线上服务能力', '网金 · 线上服务', '表格 + 文案', '已具备数据'],
  ['企微社群运营', '网金 · 企微', '表格 + 文案', '已具备数据'],
];

export default {
  id: 'report', title: '通报中心',
  render(view) {
    view.innerHTML = `
      <div class="page-head">
        <div><h1>通报中心</h1><p>选日期 → 生成表格与文案 → 复制 / 下载 Excel · PDF · PNG</p></div>
        <div class="spacer"></div>
        <span class="chip">规划中 · M3</span>
      </div>
      <div class="card">
        <div class="card-head"><h3>已有通报</h3><div class="right"><span class="chip">版式沿用现有定稿</span></div></div>
        <div class="tbl-wrap" style="max-height:none">
          <table class="tbl">
            <thead><tr><th>通报</th><th>归属</th><th>产出</th><th>数据</th><th>操作</th></tr></thead>
            <tbody>${LINES.map(([n, g, o, s]) => `<tr>
              <td class="strong">${n}</td><td>${g}</td><td>${o}</td>
              <td><span class="chip green">${s}</span></td>
              <td style="color:var(--ink-3)">待开放</td></tr>`).join('')}
            </tbody>
          </table>
        </div>
        <div style="margin-top:14px;color:var(--ink-3);font-size:12px">
          ${icon('spark', 13)} 下一步：先做「表格预览 + 文案复制」，再接 Excel / PDF / PNG 导出。
        </div>
      </div>`;
  },
};
