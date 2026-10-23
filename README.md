# 阜阳分行 · 个人金融经营驾驶舱

把各条线每天的 Excel 通报，做成一个可浏览、可下钻、按日期查询、可上传、可导出的 Web 系统。

> **接手开发先读 [docs/HANDOFF.md](docs/HANDOFF.md)**：项目全貌、数据结构、踩过的坑、当前卡点、自检命令都在那里。
> `docs/archive/` 下是历史规划稿，**已过时，不要据此判断现状**。

![首页](docs/screenshots/home.png)

## 快速开始

```bash
cd /home/isee/projects/icbc-dashboard
python run.py                                   # 本机 127.0.0.1:8766
python run.py --host 0.0.0.0 --port 8766        # 局域网可访问
```

依赖只有 `openpyxl` / `xlrd`；前端零构建（原生 ES Modules + 本地内置的 ECharts / html2canvas）。

改完通报逻辑，跑一遍对账：

```bash
python scripts/check_report_parity.py
```

## 目录结构

```
src/
  viz.py               数据层：导入适配器、快照、台账
  server/              app.py（HTTP+路由）/ auth.py（口令）/ api.py（视图模型）/ report.py（通报）
  domain/catalog.py    目录配置：板块→分组→模块（导航/首页/上传/路由都读它）
  ingest/              readers.py（多格式读取）/ payroll.py / fivecards.py
  parsers/             5 个 icbc-* 技能的解析代码（vendor，含 assets）
  report/assets/       5 份通报的"样式母版"xlsx
  web/                 前端（index.html + assets/{css,js} + vendor/；auth.js 管口令与权限）
data/                  运行时数据：snapshots / imports / ledger.jsonl（git 忽略）
scripts/               bootstrap.py（历史回填）、check_report_parity.py（对账）
legacy/                v1 单文件版，仅存档，不再维护
```

## 现在能做什么

- **六个板块**：个金（增存/增客/增收，三级导航）、网金、个贷、银行卡、私银、重点项目
- **7 条数据线**：定期存款、网点线上服务、数币钱包、薪管家、企微社群、代发工资、五卡唤醒
  —— 均有支行/网点下钻、日/月切换（"取该日之前最近一期"）
- **上传**：两级选择（大类 → 模块），支持 xlsx/xls/csv（内容识别，扩展名错了也能认）；
  从模块页右上角「导入数据」进入会自动预选该模块
- **口令准入**：「导入数据」「通报中心」要口令。五个大类各一个口令（都能看「重点项目」），
  另有管理员口令（全量 + 重置口令）。口令只在本次打开网页内有效，刷新即失效；
  详见 [docs/HANDOFF.md 4.4](docs/HANDOFF.md)（含初始口令）
- **通报中心**：线上服务 / 薪管家 / 数币 / 定期 / 企微 五条线，表格 + 文案 + Excel + 图片，与正式成表逐格对齐
- **未接入的模块**：统一占位页（写明需要什么数据），见 HANDOFF 的待办表

![个金总览](docs/screenshots/jg.png)

![身份验证](docs/screenshots/login.png)

## 约定

- 数字以**正式通报成表**为准；页面、图片、Excel 三处同源同值
- 顶栏"数据截至"= 当前页面那个模块自己的时点，不是全局最新日期
- 口令只拦「导入数据 / 通报中心」两个管理模块；板块浏览仍然不设门槛
- 快照按 `data/snapshots/<line>/<date>.json` 存放，比率存小数、保留 6 位
- `data/` 不进版本库；整包备份见 HANDOFF 第 9 节
