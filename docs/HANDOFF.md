# 交接文档（HANDOFF）

> 写给"完全没有本会话记忆"的接手者。只读这份 + 仓库，应能：理解项目、跑起来、知道现在卡在哪、接着干活、不重复踩坑。
> 最后更新：2026-10-23（口令准入 + 按模块显示数据时点）

---

## 1. 一句话说明

这是**阜阳分行个人金融条线的经营分析系统**：把原先散落在 5 个 `icbc-*` 技能里的"每天做通报"的活儿，升级成一个可浏览、可下钻、可按日期查、可上传、可导出通报的 Web 系统（FastAPI 不用，纯 Python 标准库 + 原生前端 + ECharts）。

浏览不设门槛；**「导入数据」「通报中心」要口令**：五个大类各一个口令（额外送「重点项目」），
另有一个管理员口令（全量 + 重置口令）。详见 4.4。

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
│  │  ├─ app.py              HTTP：静态资源 + 全部 /api/*（约 260 行）
│  │  ├─ auth.py             口令：六个身份组、会话、pbkdf2 哈希落盘
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
│  ├─ ledger.jsonl             导入台账
│  └─ auth.json                口令哈希（pbkdf2，首次访问自动生成；删掉=恢复初始口令）
├─ legacy/                   v1 单文件版（build_v1.py + 旧 HTML + README 说明），只作留档
├─ docs/
│  ├─ HANDOFF.md              本文件（唯一权威的现状说明）
│  ├─ screenshots/            当前页面截图（home / jg / report-salary / upload）
│  └─ archive/PLAN-20261021.md  初版规划，已过时，勿作依据
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

### 4.4 口令与权限（大类准入）

不是账号体系，**只有"一组一个口令"**，登录即"本次打开网页内有效"。

| 身份组 | 初始口令 | 能看 |
|---|---|---|
| 个金 `jg` | `gejin2026` | 个金 + 重点项目 |
| 网金 `wj` | `wangjin2026` | 网金 + 重点项目 |
| 个贷 `loan` | `gedai2026` | 个贷 + 重点项目 |
| 银行卡 `card` | `yinhangka2026` | 银行卡 + 重点项目 |
| 私银 `pbs` | `siyin2026` | 私银 + 重点项目 |
| 管理员 `admin` | `admin2026` | 全部六个板块 + 管理口令 |

- 初始口令写在 `src/server/auth.py` 的 `DEFAULTS`；**上线后让管理员在「管理密码」里改掉**
- 哈希存 `data/auth.json`（salt + pbkdf2-120k，`chmod 600`，git 忽略）；文件损坏会改名 `.json.bad` 后回落到初始口令
- **会话只活在两处内存**：服务端 `_sessions`（闲置 12h 过期）+ 前端 `auth.js` 的模块变量。
  刷新页面 / 关掉标签页 / 重启服务 → 都要重新验证。这是需求，不要"优化"成 localStorage
- 前端：`auth.js` 提供 `auth.can(prof)`、`authFetch()`（自动带 `X-Auth`，401 时清权限并广播 `dash:auth-lost`）、
  `askPassword()`（口令框）、`openPasswordManager()`（管理员改口令）
- 后端：`/api/auth/login|password|logout`；`/api/report/*`、`/api/state`、`/api/import` 必须带 `X-Auth`
  （也接受 `?token=`，方便调试）。其余接口（`/api/catalog`、`/api/all`、`/api/line/*`）不设门槛
- 界面：进这两个模块先弹口令框（背景是带锁的占位卡）；通过后右上角出现身份胶囊，
  五大类点它=重新验证，管理员点它=下拉「管理密码 / 重新验证」

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
#/upload           上传（两级选择，默认落到自己大类）
#/upload/<moduleId> 上传并预选该模块（模块页右上角"导入数据"就跳这里）
```

---

## 6. 后端 API（`src/server/app.py`）

| 方法 | 路径 | 验口令 | 说明 |
|---|---|---|---|
| GET | `/`、`/assets/*`、`/vendor/*` | — | SPA 与静态资源 |
| GET | `/api/catalog` | — | 目录 + 可选日期 + latest/earliest + `line_keys`（条线→视图 key）+ `roles` |
| GET | `/api/all?date=YYYY-MM-DD` | — | 全量视图模型（首屏一次拉完） |
| GET | `/api/line/<line>` | — | 单条线 |
| POST | `/api/auth/login` | — | `{password}` → `{token, role, label, admin, scope}`；错口令 401 |
| POST | `/api/auth/password` | 管理员 | `{role, password}` 重置某个身份组 |
| POST | `/api/auth/logout` | token | 注销当前 token |
| GET | `/api/report/<kind>` | ✅ | 通报数据（表格 + 文案） |
| GET | `/api/report/<kind>.xlsx` | ✅ | 通报 Excel（按样式母版填） |
| GET | `/api/state` | ✅ | 各线时点、期数、最近导入台账 |
| POST | `/api/import` | ✅ | multipart：`line`、`date?`、`files[]` |

口令不对或过期时，这几个接口回 `401 {"ok":false,"auth":true}`；前端据此弹口令框。

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
- **按口令过滤大类**：`LINES` 里每条通报带 `cat`（jg / wj），页面只渲染 `auth.can(cat)` 的通报；
  可见大类 >1 时顶部出现大类胶囊（管理员能看到「个金 2 / 网金 3」，单一身份组不显示胶囊）
- Excel 现在走 `fetch` + blob 下载（`<a href>` 带不了 token）；新增通报别忘了登记 `cat`
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

### 8.4 口令 / 权限

21. **权限只存在内存**：`auth.js` 的模块变量 + 服务端 `_sessions`。刷新即失效是需求；不要改 `sessionStorage`/`localStorage`。
22. **带 token 才有数据**：`/api/report/*`、`/api/state`、`/api/import` 全部要 `X-Auth`。页面里一律用 `authFetch()`，
    别直接 `fetch`；Excel 下载也必须 `fetch`+blob（`<a href>` 带不上 header，会 401 却"看起来没反应"）。
23. **401 的统一处理**：`authFetch` 清权限 → 派发 `dash:auth-lost` → `app.js` 重渲染并重新弹口令框。
    页面自己的 `catch` 里遇到 `err.auth` 要**安静返回**，别再往已经被销毁的 DOM 写错误。
24. **新增通报/模块要挂大类**：`report.js` 的 `LINES[].cat`；不挂就是"哪个口令都看不到"。导入页的大类权限靠 `auth.can(prof)`。
25. **管理口令只有管理员能改**（`POST /api/auth/password` 会校验 `sess.admin`）；忘记管理员口令的兜底是删 `data/auth.json`（回到初始口令）。

### 8.5 环境

26. WSL 下 Node 的 `--check` 可用来快速验 JS 语法：`node --input-type=module --check < file.js`。
27. 本机 LibreOffice 宏不可靠（见 AGENTS.md），但**转换/重算**可用；不要在自动化里依赖宏。
28. 服务进程重启：`fuser -k 8766/tcp` 再起；日志 `/tmp/viz-v2.log`。

---

## 9. 当前状态 / 卡在哪

### 已完成

- 六大板块框架、个金三级导航、首页总览、个金总览页（基础数据 + 三分类模块卡带数）
- 7 条线接入：定期、线上服务、数币、薪管家、企微、代发工资、五卡唤醒（页面 + 上传 + 日期 as-of）
- 上传两级（专业→模块）+ 多格式读取 + 台账
- 通报中心 5 条线（表格/文案/Excel/图片），对账脚本全绿（1 处标题日期差异）
- 日/月切换；红涨绿跌；头尾突出排行；全屏大表
- 顶栏"数据截至"改为**按当前页面模块自己的时点**（模块取 `as_of`，板块取该板块各模块最大值；
  选日期筛选时显示"数据截至 X · 所选 ≤Y"），日期控件的值也跟着本页时点走
- 口令准入：六个身份组、大类过滤（导入页灰掉无权大类、通报中心不显示无权通报）、
  管理员改口令、右上角身份胶囊（五大类=重新验证，管理员=管理密码/重新验证）

### 未完成 / 待定

| 事项 | 现状 | 需要的输入 |
|---|---|---|
| 网点争先、挑战回访100位客户 | 占位页 | 名单/排名/积分口径 |
| 全量客户拓展 | 占位页（`planned`） | 现在是文字进度表，需要结构化字段 |
| 定期承接、行外吸金、降级挽回、经理队伍、一卡一户、全量客户 | 占位 | 数据源 |
| 基保理、三方支付（增收） | 占位 | 数据源；基保理=基金/保险/理财 |
| 个贷、银行卡、私银 | 占位 | 数据源 |
| 账号级身份 | 未做：只有"一组一口令"，不记谁导的 | 需要追责时再加姓名/工号 |
| 导航级权限 | 未做：侧栏仍可浏览所有板块（口令只拦两个管理模块） | 若要求"没口令连板块都不给看"，需在 `render()` 前置门槛 |
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
| 口令 / 身份组 | `src/server/auth.py` 的 `ROLES`/`DEFAULTS`；前端表现看 `auth.js`、`app.js` 的 `paintTop()/startGate()` |
| 某模块的"数据截至" | 自动取该模块 `as_line` 的 `as_of`；要改文案看 `app.js` 的 `asofFor()` |

---

## 11. 交接检查清单

1. `git log --oneline -5` 看到 `0821eef` 或更新
2. 起服务 → `curl /api/health` 返回 ok
3. `python scripts/check_report_parity.py` → 除 online 标题外全 OK
4. 打开 `#/`、`#/p/jg`、`#/m/jg-deposit-time` 各看一眼（顶栏"数据截至"应分别是 10/22、10/22、10/15）
5. `#/report` 应弹口令框；输 `gejin2026` 只看到「定期存款增长 / 薪管家」两项；刷新页面应重新要口令
6. `#/upload` 输 `wangjin2026` 后网金可选、其余灰掉；从 `#/m/wj-wallet` 点右上角"导入数据"应预选到「数币钱包」
7. 改动前先读本文件第 8 节（坑）与第 9 节（现状/待办）；`docs/archive/` 是过时规划，不要作为依据

> 约定：所有数据数字以"正式通报成表"为准；页面/图片/Excel 三处必须同源同值；改完必跑对账。
