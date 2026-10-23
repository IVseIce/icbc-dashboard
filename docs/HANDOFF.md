# 交接文档（HANDOFF）

> 写给"完全没有本会话记忆"的接手者。只读这份 + 仓库，应能：理解项目、跑起来、知道现在卡在哪、接着干活、不重复踩坑。
> 最后更新：2026-10-23（对应 commit `0821eef`）

---

## 1. 一句话说明

这是**阜阳分行个人金融条线的经营分析系统**：把原先散落在 5 个 `icbc-*` 技能里的"每天做通报"的活儿，升级成一个可浏览、可下钻、可按日期查、可上传、可导出通报的 Web 系统（FastAPI 不用，纯 Python 标准库 + 原生前端 + ECharts）。

- 前端：原生 ES Modules + ECharts（本地内置）+ html2canvas（本地内置），无构建步骤
- 后端：`http.server`，无第三方 Web 框架
- 数据：JSON 快照（按日期、按条线），暂未上 SQLite
- 解析：直接复用 5 个 `icbc-*` 技能的 `classify()/compute()`（代码已 vendor 进仓库，不再依赖 `~/.dsh/skills`）

---

## 2. 快速上手

### 2.1 环境

| 项 | 值 |
|---|---|
| 代码目录（WSL） | `/home/isee/projects/icbc-dashboard` |
| Python | `/home/isee/.venvs/data-tools/bin/python`（openpyxl、xlrd 已装） |
| 运行时数据 | `/home/isee/projects/icbc-dashboard/data`（`viz.ROOT`，可用 `--root` 覆盖） |
| 原始资料（Windows） | `/mnt/d/资料/ICBC/...` |
| Chrome（截图/PDF） | `/mnt/c/Program Files/Google/Chrome/Application/chrome.exe` |
| GitHub | `git@github.com:IVseIce/icbc-dashboard.git`（私有，master） |
| SSH key | `~/.ssh/id_ed25519_icbc`，仓库已配 `core.sshCommand`，直接 `git push` 即可 |

### 2.2 启动

```bash
cd /home/isee/projects/icbc-dashboard
nohup /home/isee/.venvs/data-tools/bin/python run.py --port 8766 --host 0.0.0.0 \
  >> /tmp/viz-v2.log 2>&1 &
```

验证：

```bash
curl -s http://127.0.0.1:8766/api/health          # {"ok":true,...}
curl -s http://127.0.0.1:8766/api/catalog | head  # 板块/模块目录
open http://127.0.0.1:8766/                       # 浏览器
```

> 改 **Python** 必须重启进程；改 **前端 JS/CSS** 不用重启、不用构建，刷新页面即可（服务对 assets 设了 no-store）。

### 2.3 自检（改完通报必跑）

```bash
/home/isee/.venvs/data-tools/bin/python scripts/check_report_parity.py
```

期望输出（当前基线）：

```
online   2026-10-17  1 处差异   ← 仅标题日期（成表用发信日 10.19，系统用数据日 10.17）
salary   2026-10-21  OK
wallet   2026-10-19  OK
deposit  2026-10-15  OK
community 2026-10-19 OK
```

---

## 3. 仓库结构

```
icbc-dashboard/
├─ run.py                    启动入口（把 src 塞进 sys.path）
├─ requirements.txt          openpyxl / xlrd
├─ .gitignore                data/ 已忽略
├─ src/
│  ├─ viz.py                 数据层：导入适配器、快照读写、台账、assemble
│  ├─ server/
│  │  ├─ app.py              HTTP：静态资源 + 全部 /api/*（约 200 行）
│  │  ├─ api.py              视图模型：每条线一个 build_xxx()
│  │  └─ report.py           通报：表格/文案/Excel（5 条线）
│  ├─ domain/catalog.py      唯一的目录配置（导航/首页/上传/路由都读它）
│  ├─ ingest/
│  │  ├─ readers.py          多格式读取（xlsx/xls/csv，按内容嗅探）
│  │  ├─ payroll.py          代发明细解析（月度多 sheet）
│  │  └─ fivecards.py        五卡汇总表解析
│  ├─ parsers/               vendor 进来的 5 个 icbc-* 技能（解析逻辑）
│  │  └─ icbc-{dqzz,xsfw,sbqb,xgj,qwsq}/{*.py, assets/}
│  ├─ report/assets/         5 个"样式母版" xlsx（从正式成表清数据得到）
│  │  └─ {online,salary,wallet,deposit,community}_base.xlsx
│  └─ web/
│     ├─ index.html
│     ├─ assets/css/app.css  全部设计变量在 :root
│     └─ assets/js/{app.js,ui.js,charts.js,pages/*}
├─ scripts/
│  ├─ bootstrap.py           一次性把 automations 历史灌进 data/
│  └─ check_report_parity.py 与技能成表逐格对账
├─ data/                     运行时数据（git 忽略）
│  ├─ snapshots/<line>/<date>.json
│  ├─ imports/<line>/<stamp>/  上传原件留档
│  └─ ledger.jsonl             导入台账
├─ legacy/                   v1 单文件版（build_v1.py + 旧 HTML），只作留档
└─ docs/{PLAN.md,HANDOFF.md,screenshots/}
```

---

## 4. 数据模型

### 4.1 快照

`data/snapshots/<line>/<YYYY-MM-DD>.json`，一条线一天一个文件。

| line | 含义 | 视图模型 | 数据日期基线 |
|---|---|---|---|
| `dqzz` | 定期存款 | `build_deposit` | 2026-10-15 |
| `xsfw` | 网点线上服务 | `build_online` | 2026-10-21 |
| `sbqb` | 数币钱包 | `build_wallet` | 2026-10-22 |
| `xgj` | 薪管家 | `build_salary` | 2026-10-22 |
| `qwsq` | 企微社群 | `build_community` | 2026-10-19 |
| `dfmx` | 代发明细（月） | `build_payroll` | 2026-09-30（即 26.09 期） |
| `wk` | 五卡唤醒 | `build_fivecards` | 2026-09-09 |

- 带 `partial: true` 的快照只用于画趋势，**详情页会跳过**（`api._latest` 里过滤）
- 金额单位：存款/代发为万元，钱包为户；比率一律存**小数**（0.5578 而非 55.8）
- **精度**：快照里比率保留 6 位（`round(x, 6)`），代发/五卡/企微的 ytd、rate 均为原始值；报表层**不要再四舍五入**，否则对账必挂

### 4.2 组装与视图

- `viz.assemble()` 把最新快照拼成 `data/data/dashboard_data.json`（v1 兼容产物，v3 页面基本不用）
- v3 页面走 `api.build_all(date)`：`date=None` 取最新；传日期则每条线取"**不晚于该日**的最新一期"
- 每个 build_xxx 返回**扁平结构**（kpi/trend/rows），前端不关心计算

### 4.3 导入台账

`data/ledger.jsonl` 每行一条：`{ts, line, data_date, files, ok, error, archive}`。上传页"最近导入"就是读它。

---

## 5. 目录 / 导航结构（`src/domain/catalog.py`）

六大板块：个金、网金、个贷、银行卡、私银、重点项目。

```
个金（nested=True，三级）
 ├ 增存：定期存款✓ | 定期承接 | 行外吸金 | 降级挽回 | 经理队伍
 ├ 增客：全量客户 | 代发工资✓ | 薪管家✓ | 一卡一户 | 五卡唤醒✓
 └ 增收：基保理 | 三方支付
网金（平铺）：线上服务✓ | 数币钱包✓ | 企微社群✓
个贷 / 银行卡 / 私银：各 1 个占位模块
重点项目（平铺）：网点争先 | 全量客户拓展 | 企微社群运营✓ | 五卡唤醒✓ | 挑战回访100位客户
```

✓ = `kind: "metric"`，有页面、可上传；其余为 `placeholder`（灰、不可点）或 `planned`（可点但进占位页）。

模块 id（路由 `#/m/<id>`）：

- 个金：`jg-deposit-time` `jg-deposit-jiepan` `jg-deposit-waihang` `jg-deposit-jiangji` `jg-deposit-team`
  `jg-customer-all` `jg-customer-pay` `jg-customer-xgj` `jg-customer-yika` `jg-customer-card`
  `jg-income-jbl` `jg-income-pay`
- 网金：`wj-online-svc` `wj-wallet` `wj-wecom-social`
- 项目：`pj-contend` `pj-allcustomer` `pj-wecom` `pj-fivecards` `pj-100`
- 其他：`loan-todo` `card-todo` `pbs-todo`

**关键字段**：`as_line` 决定该模块能不能上传（有 `as_line` 且 `kind=metric` → 可上传）、`page` 决定用哪个前端渲染器。

路由（前端 `app.js`）：

```
#/                 首页（六板块总览）
#/p/<profId>       板块页（个金走专用 jg.js，其余通用 browse）
#/g/<prof>/<group> 分组页（只有个金有）
#/m/<moduleId>     模块页（按 page 分发到 RENDERERS）
#/report[/<kind>]  通报中心（kind: online/salary/wallet/deposit/community）
#/upload           上传
```

---

## 6. 后端 API（`src/server/app.py`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/`、`/assets/*`、`/vendor/*` | SPA 与静态资源 |
| GET | `/api/catalog` | 目录 + 各线可选日期 + latest/earliest |
| GET | `/api/all?date=YYYY-MM-DD` | 全量视图模型（首屏一次拉完） |
| GET | `/api/line/<line>` | 单条线 |
| GET | `/api/report/<kind>` | 通报数据（表格 + 文案） |
| GET | `/api/report/<kind>.xlsx` | 通报 Excel（按样式母版填） |
| GET | `/api/state` | 各线时点、期数、最近导入台账 |
| POST | `/api/import` | multipart：`line`、`date?`、`files[]` |

导入走 `viz.do_import(line, files, data_date)`：
`归档原件 → readers.normalize（纠扩展名）→ 技能 classify/compute（dfmx/wk 是自写解析）→ 写快照 → assemble → 记台账`。
文本内容被误命名成 xlsx 且识别失败时，会**自动转成真 xlsx 重试一次**。

---

## 7. 通报中心（`src/server/report.py`）

5 条线：`online / salary / wallet / deposit / community`。

- 每条线一个 `build_xxx()` 产出 `{title, as_of, tables:[{name, columns, rows, totals}], text}`
- 每条线一个 `xxx_xlsx()`：**加载 `src/report/assets/<line>_base.xlsx` 后填数**
- 样式母版来源：把 `automations/*/out/*.xlsx` 正式成表**清空数据区**后另存（保留字体/边框/列宽/合并/数字格式）
  - online：微软雅黑 11；salary：仿宋_GB2312（支行/网点双 sheet）；wallet：等线 11（A 列支行分组）；
    deposit：方正黑体_GBK；community：宋体 11（支行/网点双 sheet）
- 红绿：目前只有 online 做（每列前 5 红 / 后 5 绿，`annotate()`），前端与 Excel 同源
- 前端：`pages/report.js`，页签 → 取 `/api/report/<kind>`；支持复制文案、下载 Excel、复制图片、导出图片（html2canvas）
- 新增一条线：写 `build_xxx` + `xxx_xlsx`，登记 `BUILDERS` / `XLSX`，再在 `report.js` 的 `LINES` 里 `ready: true`

---

## 8. 已经踩过的坑（重要，别重犯）

### 8.1 报表 / Excel

1. **样式母版必须用"正式成表"清数据**，不能用技能里的空白模板：模板数据区是宋体 11，成表是微软雅黑 11，直接套会"字体不一致"。
2. **行序与补 0 必须按模板行名**：薪管家 40 个网点里约 30 个是 0，早期按数据过滤导致"0 没填上""顺序不对"。
3. **合并单元格写值会报 `MergedCell` read-only**：先 `ws.unmerge_cells()` 再写（数币 A 列支行）。
4. **循环 range 少一行**：网点是 4..43 含，早期写成 `range(4,43)` 漏了最后一个。
5. **网点名不统一**：模板是 `阜阳岳家湖支行`，数据里是 `颍东岳家湖支行`。匹配顺序：精确 → 去"阜阳" → **后缀唯一匹配**（`_match`/`_key`）。
6. **合计行别自己平均**：线上服务的合计率要取源表合计行（加权），不是各网点平均。
7. **比率精度**：快照 6 位 → 报表直出；`api` 层为页面显示四舍五入到 2 位，**报表不要用 api 的 `kpi`，要读快照**（`build_online/deposit/community` 已是读快照）。
8. **公式型成表**：定期/企微的成表里是公式，`data_only=True` 读到 None；对账脚本先用 LibreOffice 重算（`soffice --headless --convert-to xlsx`）。
9. 线上服务标题日期：成表用**发信日**（10.19），系统用**数据日**（10.17），这是唯一已知差异；要消掉得在导入时记录"通报日期"。

### 8.2 数据 / 解析

10. **扩展名不可信**：曾出现 CSV 被另存成 `.xlsx`。`ingest/readers.py` 按文件头判断（PK→xlsx、D0CF11E0→xls、否则文本），导入时自动改回正确扩展名。
11. **企微"上周"不是上一份备份**，而是"最接近 本周−7 天"的备份（否则 +30 变 +4）。
12. **企微"交互数"= 群聊消息总数（x）**，不是"发过消息的成员数（msg）"；熟识率分子用 msg。
13. **代发明细的"当月代发"列不可靠**（26.07 那期混进了累计值/重复行，用户明确说不改数据）：月度金额用**年累计相邻两期相减**，跨年重置。
14. **代发明细 26.07 sheet 有 2,847 行（其他约 2,265）**，疑似重复导出；已知问题，用户接受。
15. **薪管家导入时会把 0 网点过滤掉**（`viz.import_xgj`），所以报表必须用模板行名补齐，不能直接用快照列表。
16. 数币网点名在快照里是短名（无"阜阳"），报表匹配要归一。

### 8.3 前端

17. **截图/录屏要用 `--force-prefers-reduced-motion`**，否则动画停在中间帧（数字显示成 267.87 之类的假值）。`countUp` 已尊重该设置。
18. **平铺板块要遍历所有分组**（曾只取 `groups[0]`，网金少了两个模块）。
19. 图表统一在 `charts.js`（`barRank` 支持负值向左+绿色、`splitRank` 做"头尾突出"、`bigTable` 做全屏大表）。
20. 抽屉、全屏表、提示都在 `ui.js`；新增页面照 `pages/*.js` 的默认导出结构写。

### 8.4 环境

21. WSL 下 Node 的 `--check` 可用来快速验 JS 语法：`node --input-type=module --check < file.js`。
22. 本机 LibreOffice 宏不可靠（见 AGENTS.md），但**转换/重算**可用；不要在自动化里依赖宏。
23. 服务进程重启：`fuser -k 8766/tcp` 再起；日志 `/tmp/viz-v2.log`。

---

## 9. 当前状态 / 卡在哪

### 已完成

- 六大板块框架、个金三级导航、首页总览、个金总览页（基础数据 + 三分类模块卡带数）
- 7 条线接入：定期、线上服务、数币、薪管家、企微、代发工资、五卡唤醒（页面 + 上传 + 日期 as-of）
- 上传两级（专业→模块）+ 多格式读取 + 台账
- 通报中心 5 条线（表格/文案/Excel/图片），对账脚本全绿（1 处标题日期差异）
- 日/月切换；红涨绿跌；头尾突出排行；全屏大表

### 未完成 / 待定

| 事项 | 现状 | 需要的输入 |
|---|---|---|
| 网点争先、挑战回访100位客户 | 占位页 | 名单/排名/积分口径 |
| 全量客户拓展 | 占位页（`planned`） | 现在是文字进度表，需要结构化字段 |
| 定期承接、行外吸金、降级挽回、经理队伍、一卡一户、全量客户 | 占位 | 数据源 |
| 基保理、三方支付（增收） | 占位 | 数据源；基保理=基金/保险/理财 |
| 个贷、银行卡、私银 | 占位 | 数据源 |
| 上传人/权限 | 未做（无账号体系） | 是否需要先记姓名 |
| SQLite | 未做（仍 JSON 快照） | 数据量大到需要再迁 |
| 通报日期 vs 数据日期 | 线上服务标题差 1 处 | 导入时加"通报日期"字段即可 |
| 自动启动/部署 | 手工 nohup | 上服务器时做服务化 |

### 备份

- 代码+数据整包：`/mnt/d/资料/ICBC/icbc-dashboard-备份-20261022.tar.gz`（9.3 MB，含当时 data/）
- 旧数据目录：`/mnt/d/资料/ICBC/Visualizations.migrated-20261021`（迁移到 `data/` 后的保险副本，可删）

---

## 10. 常见改动路径（改哪儿）

| 想改 | 改哪里 |
|---|---|
| 板块/模块/名称/顺序 | `src/domain/catalog.py` |
| 导航层级（是否子目录） | 同上 `nested: True`；渲染在 `app.js` 的 `navSection()` |
| 某模块的数字卡 | 对应 `pages/*.js`（如 `jg.js` 的 `statsFor`） |
| 图表样式/配色 | `src/web/assets/css/app.css` 的 `:root`、`charts.js` 的 `PALETTE` |
| 新增一条线上传 | catalog 加 `as_line` + `viz.IMPORTERS` 注册解析器 |
| 新增一条通报 | `report.py` 加 `build_xxx`/`xxx_xlsx` + `report.js` 的 `LINES` |
| 报表样式 | 换 `src/report/assets/<line>_base.xlsx`（务必是"成表清数据"） |

---

## 11. 交接检查清单

1. `git log --oneline -5` 看到 `0821eef` 或更新
2. 起服务 → `curl /api/health` 返回 ok
3. `python scripts/check_report_parity.py` → 除 online 标题外全 OK
4. 打开 `#/`、`#/p/jg`、`#/m/jg-deposit-time`、`#/report/salary`、`#/upload` 各看一眼
5. 需要改动前先读 `docs/PLAN.md`（更早的规划，部分已过时）和本文件第 8 节

> 约定：所有数据数字以"正式通报成表"为准；页面/图片/Excel 三处必须同源同值；改完必跑对账。
