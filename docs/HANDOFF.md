# 交接文档（HANDOFF）

> 写给"完全没有本会话记忆"的接手者。只读这份 + 仓库，应能：理解项目、跑起来、知道现在卡在哪、接着干活、不重复踩坑。
> 最后更新：2026-10-29（**版本 0.1.8.2**｜经理队伍：页签修复 + 通报合并为一条 + 下载按钮统一）
>
> 历史节点：0.1.0 首版（口令+按模块时点）→ 0.1.2（SQLite、部署/U 盘、模块 skill、实用工具）
> → 0.1.3（降级挽回）→ 0.1.3.1（按正式成表对齐 + 映射内置）→ 0.1.3.2（修前三/后三取名次 + 网点明细按综合评价排序）
> → 0.1.4（使用指南、更新记录、顶栏精简、侧栏防误拖、薪管家老内核修复）
> → 0.1.4.1（更新日志独立成页、指南按钮改版、README 退回简介）
> → 0.1.4.2（标识换工商银行红金立体 logo、标题改「工商银行阜阳分行 / 经营驾驶舱」）
> → 0.1.5（一卡一户：社保卡 + 个人养老金，按日存累计值、三个时点自动拼成表）
> → 0.1.6（私人银行：达标客户/资产/产品销售；三个时点；`update.sh --with-data`）
> → 0.1.6.1（私银成表版式重做 + 修通报中心 undefined）
> → 0.1.6.2（**导出改为「官方成表原件当模板、只填数据格」**，格式与人工完全一致）
> → 0.1.6.3（红绿字色改黑、发展情况当前存量加红/黄、并列按名次、下载按钮回退为两个）
> → 0.1.7（**定期承接**：客编明细按到期日筛行聚合、任意区间、网点+支行双 sheet 成表）
> → 0.1.7.1（定期承接「手动编辑明细」；xlsx 图片在无 Pillow 运行时不再丢；支持 chunked 上传）
> → 0.1.8（**经理队伍**：财客 支行/网点/经理 三级、远维 支行/经理 两级）
> → 0.1.8.1（修页签第二次点不动；通报合并成一条 + 两个下载按钮）
> → 0.1.8.2（多份成表的下载按钮统一成红色主按钮，不再只有第一个标红）

---

## 1. 一句话说明

这是**阜阳分行个人金融条线的经营分析系统**：把原先散落在 5 个 `icbc-*` 技能里的"每天做通报"的活儿，升级成一个可浏览、可下钻、可按日期查、可上传、可导出通报的 Web 系统（FastAPI 不用，纯 Python 标准库 + 原生前端 + ECharts）。
数据存在 **SQLite（`data/icbc.db`）**，不再是散落的 JSON 文件。
部署形态（内网机、U 盘更新、无 root）：见 **`docs/DEPLOY.md`**。

浏览不设门槛；**「导入数据」「通报中心」要口令**：五个大类各一个口令（额外送「重点项目」），
另有一个管理员口令（全量 + 重置口令）。详见 4.5。

- 前端：原生 ES Modules + ECharts（本地内置）+ html2canvas（本地内置），无构建步骤
- 后端：`http.server`，无第三方 Web 框架
- 数据：**SQLite**（`data/icbc.db`，一条线一天一行快照；元数据表化，见 4.1）
- 解析：直接复用 5 个 `icbc-*` 技能的 `classify()/compute()`（代码已 vendor 进仓库，不再依赖 `~/.dsh/skills`）

---

## 2. 快速上手

### 2.1 环境

| 项 | 值 |
|---|---|
| 代码目录（WSL） | `/home/isee/projects/icbc-dashboard` |
| Python | `/home/isee/.venvs/data-tools/bin/python`（3.12；依赖见 `requirements.txt`，另有 `vendor/pylib` 随包用） |
| 开发数据 | `/home/isee/projects/icbc-dashboard/data`（`viz.ROOT`，可用 `--root` / `ICBC_ROOT` 覆盖） |
| 生产部署 | 内网麒麟机 `~/icbc-dashboard`（`releases/` + `current` + `shared/data`，无 root） |
| 主库 | `data/icbc.db`（SQLite，WAL；schema 版本见 `PRAGMA user_version`） |
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
> 改 **`VERSION`** 也要重启才生效（`version.app_version()` 进程内缓存）。

> **端口被占时 `nohup` 会静默失败**：旧进程没杀干净 → 新进程 `Address already in use`，
> 但 `nohup ... &` 照样返回、`curl` 打到的还是**旧进程**（看到的现象是"改了没生效"）。
> 起之前先 `ss -ltnp | grep 8766` 确认为空；必要时 `pkill -f "run.py --port 8766"` 再起。

### 2.3 自检（改完通报必跑）

```bash
/home/isee/.venvs/data-tools/bin/python scripts/check_report_parity.py     # 与技能成表逐格对账
/home/isee/.venvs/data-tools/bin/python scripts/migrate_to_sqlite.py --db-info   # 库现状（条数/最新/大小）
/home/isee/.venvs/data-tools/bin/python scripts/backup_db.py               # 热备份（不用停服务）
```

期望输出（当前基线）：

```
online   2026-10-17  1 处差异   ← 仅标题日期（成表用发信日 10.19，系统用数据日 10.17）
salary   2026-10-21  OK
wallet   2026-10-19  OK
deposit  2026-10-15  OK
community 2026-10-19 OK
```

> `downgrade`（降级挽回）**不在对账用例里**：目前只有"正式成表"本身、没有可用于回归的第二份，
> 已用 `scripts/check_report_parity.py` 之外的方式核对过——把导出的 xlsx 与
> `D:\Downloads\降级挽回营销先锋（0914-0920）.xlsx` **逐格比对，两个 sheet 零差异**。
> 以后拿到第二期成表，把用例补进脚本的 `CASES` 即可。

---

## 3. 仓库结构

```
icbc-dashboard/
├─ run.py                    启动入口（把 src 塞进 sys.path）
├─ requirements.txt          openpyxl / xlrd
├─ README.md                 只作入口简介，**不随版本更新**（以此文件为准）
├─ VERSION                   版本号；CHANGELOG 在 src/web/assets/js/changelog.js
├─ .gitignore                data/ 已忽略
├─ src/
│  ├─ xlsx_keep.py           保存工作簿时保住母版图片（无 Pillow 也行，见 8.12）
│  ├─ store.py               SQLite 存储层：schema/迁移/快照读写/台账/备份
│  ├─ compat.py              Python 3.8 垫片（补 zoneinfo，目标机回退路径用）
│  ├─ version.py             读 VERSION（打包时写入）
│  ├─ viz.py                 导入适配层：解析器分发、归档、assemble
│  ├─ server/
│  │  ├─ app.py              HTTP：静态资源 + 全部 /api/*（约 260 行）
│  │  ├─ auth.py             口令：六个身份组、会话、pbkdf2 哈希落盘
│  │  ├─ api.py              视图模型：每条线一个 build_xxx()
│  │  └─ report.py           通报：表格/文案/Excel（11 条线）
│  ├─ domain/catalog.py      唯一的目录配置（导航/首页/上传/路由都读它）
│  ├─ ingest/
│  │  ├─ readers.py          多格式读取（xlsx/xls/csv，按内容嗅探）
│  │  ├─ payroll.py          代发明细解析（月度多 sheet）
│  │  ├─ fivecards.py        五卡汇总表解析
│  │  ├─ downgrade.py        降级挽回解析（客编明细 + 内置映射，口径写在文件头）
│  │  ├─ yika.py             一卡一户解析（社保卡 + 养老金，按日累计值）
│  │  ├─ pbs.py              私人银行解析（客编明细 → 支行/网点，日期靠文件名）
│  │  ├─ jiepan.py           定期承接解析（客编明细按到期日筛行，窗口在单份快照内切）
│  │  └─ team.py             经理队伍解析（财客/远维列映射 + 三行表头校验 + 双块合并）
│  ├─ parsers/               vendor 进来的 5 个 icbc-* 技能（解析逻辑）
│  │  └─ icbc-{dqzz,xsfw,sbqb,xgj,qwsq}/{*.py, assets/}
│  ├─ report/assets/         10 个"样式母版" xlsx（从正式成表清数据得到）+ 若干内置配置
│  │  ├─ {online,salary,wallet,deposit,community,downgrade}_base.xlsx
│  │  ├─ downgrade_map.json  客编 → 支行/网点（1749 条，固定映射）
│  │  ├─ yika_base.xlsx      一卡一户样式母版（通报/社保卡/养老金 三 sheet）
│  │  ├─ yika_targets.json   网点顺序 / 支行 / 当日目标（固定值 4 或 6）
│  │  ├─ pbs_base.xlsx       私银定稿母版（**原件转 xlsx 后清数据**，列结构与隐藏列原样保留）
│  │  ├─ pbs_dev_base.xlsx   私银网点发展情况母版（同上，含横幅图片）
│  │  ├─ pb_nets.json        私银 40 网点 / 网点→支行 / 上年末存量
│  │  ├─ jiepan_base.xlsx / jiepan_nets.json / jiepan_exclude.json  定期承接母版与配置
│  │  ├─ ck_base.xlsx        经理队伍·财客母版（通报 + 明细 双 sheet）
│  │  └─ yw_base.xlsx        经理队伍·远维母版（同上）
│  └─ web/
│     ├─ index.html
│     ├─ assets/css/app.css  全部设计变量在 :root
│     ├─ assets/img/logo.png 工商银行标识（透明底 PNG 384²）
│     ├─ assets/js/{app.js,auth.js,ui.js,charts.js,pages/*}
│     │  ├─ guide-content.js  使用指南正文（纯数据，改文案只动这里）
│     │  └─ changelog.js      更新日志（独立页 #/changelog，发版必加一条）
│     └─ pages: home jg deposit online wallet salary community payroll fivecards jiepan
│               downgrade yika tool report import guide placeholder
├─ scripts/
│  ├─ bootstrap.py           一次性把 automations 历史灌进库
│  ├─ migrate_to_sqlite.py   旧 JSON → SQLite（一次性，可重跑）
│  ├─ backup_db.py           热备份 data/icbc.db → data/backups/
│  ├─ export_db.py           对外导出 .db + 清单
│  ├─ selftest.py            解释器/依赖/数据库自检（install/update 都调它）
│  ├─ check_modules.py       模块接线自检 + 生成 docs/MODULES.md
│  ├─ package_release.py     打 U 盘发布包（VERSION + SHA256SUMS，可带 runtime）
│  ├─ check_report_parity.py 与技能成表逐格对账（11 条线）
│  ├─ merge_seed.py          把发布包 seed/ 合并进生产库（只补缺不覆盖）
│  ├─ build_yika_assets.py   从成表生成一卡一户母版与目标表（改口径时重跑）
│  └─ build_team_bases.py    从官方成表生成 ck/yw 母版（换版式时重跑）
├─ data/                     运行时数据（git 忽略）
│  ├─ icbc.db                 主库（+ -wal / -shm；备份要连 wal 一起，或用 backup_db.py）
│  ├─ imports/<line>/<stamp>/  上传原件留档
│  ├─ backups/                热备份（icbc-<时间戳>.db + auth-<时间戳>.json）
│  ├─ legacy_json_<ts>/       迁移前的 JSON 快照留档（只读，确认后可删）
│  └─ auth.json                口令哈希（pbkdf2，首次访问自动生成；删掉=恢复初始口令）
├─ deploy/                   部署脚本：install / update + bin/{start,stop,status,backup,export-db,supervise}
├─ vendor/pylib/             纯 Python 依赖（openpyxl / xlrd / PyYAML），随包走，与架构无关
├─ legacy/                   v1 单文件版（build_v1.py + 旧 HTML + README 说明），只作留档
├─ docs/
│  ├─ HANDOFF.md              本文件（唯一权威的现状说明，改代码必同步）
│  ├─ DEPLOY.md               部署形态与运维 runbook（内网机/U 盘/更新/回滚/导出）
│  ├─ MODULES.md              模块总表（自动生成，别手改）
│  ├─ modules/<id>.md         每个模块的数据源/口径/坑（新增模块必写）
│  ├─ skills/dashboard-new-module/  新增模块的标准流程（也是 ~/.dsh/skills 里的同名 skill）
│  ├─ screenshots/            当前页面截图（home / jg / report-salary / upload）
│  └─ archive/PLAN-20261021.md  初版规划，已过时，勿作依据
```

---

## 4. 数据模型（SQLite）

### 4.1 库结构（`src/store.py`，schema v1）

`data/icbc.db`，四张表：

| 表 | 作用 | 关键字段 |
|---|---|---|
| `snapshot` | **事实层**：一条线一天一行 | `line`+`as_of` 唯一；`month`、`partial`、`rows`、`payload`(JSON)、`payload_hash`、`source`、`created_at`/`updated_at` |
| `source_file` | 上传原件台账 | `snapshot_id`、`name`、`sha256`、`bytes`、`path`、`archive` |
| `import_log` | 导入台账（替代 `ledger.jsonl`） | `ts`、`line`、`data_date`、`ok`、`error`、`files`(JSON)、`snapshot_id` |
| `setting` | 键值设置 | `key`、`value`(JSON)、`updated_at`（例如 `legacy_json_imported`） |

**为什么事实层还是"文档"而不是宽表**：所有指标都是 as-of 语义，解析器已经把一份源表算成一个完整快照；
而各线结构差异极大（数币=网点×4 等级、定期=支行×余额、代发=网点×十几列、五卡=支行×卡×指标），
拆宽表会让"加一条线"变成改三次 schema。元数据（台账/原件）才是真表。
将来要按指标做 SQL 分析，再加 v2 的 fact 表从 `payload` 派生，**本层接口不变**。

约定：

- 重复导入同一天 = **upsert**（覆盖 payload，保留 `created_at`），不会产生两行
- `partial=1` 的历史回填快照只用于画趋势，详情页跳过（`store.latest(..., partial_ok=False)`）
- 读多写少：WAL + 线程本地连接 + 3 秒 TTL 缓存（`store.load_snapshots` 返回的是缓存里的同一批 dict，**只读**）
- 换数据目录：`viz.use_root(dir)`（会同步 `store`；`--root` 现在真的生效了）
- schema 升级：改 `store.SCHEMA_VERSION` 并在 `init()` 里补升级分支；旧库会自动 `CREATE IF NOT EXISTS` 补表

### 4.2 条线与日期基线

| line | 含义 | 视图模型 | 数据日期基线 |
|---|---|---|---|
| `dqzz` | 定期存款 | `build_deposit` | 2026-10-15 |
| `xsfw` | 网点线上服务 | `build_online` | 2026-10-21 |
| `sbqb` | 数币钱包 | `build_wallet` | 2026-10-22 |
| `xgj` | 薪管家 | `build_salary` | 2026-10-22 |
| `qwsq` | 企微社群 | `build_community` | 2026-10-19 |
| `dfmx` | 代发明细（月） | `build_payroll` | 2026-09-30（即 26.09 期） |
| `wk` | 五卡唤醒 | `build_fivecards` | 2026-09-09 |
| `jjwh` | 降级挽回（旬） | `build_downgrade` | 2026-09-13（基期） |
| `jp` | 定期承接（周） | `build_jiepan` | 2026-10-25（取数日） |
| `ykh` | 一卡一户（日） | `build_yika` | 2026-10-25 |
| `pbs` | 私人银行（旬） | `build_pbs` | 2026-10-24 |
| `team` | 经理队伍（累计） | `build_team` | 2026-10-21 |
| `ykh_sb` / `ykh_yl` | 一卡一户的**按日累计值**（辅助条线，不出页面） | — | — |

- 带 `partial: true` 的快照只用于画趋势，**详情页会跳过**（`api._latest` 里过滤）
- 金额单位：存款/代发为万元，钱包为户；比率一律存**小数**（0.5578 而非 55.8）
- **`jp`（定期承接）的特殊性**：`as_of` 是取数日（表里 `最近到期日期` 的最大值），
  `coverage` 是 `[最早到期日, 取数日]`（固定 31 天）。payload 存客编级明细（按到期日偏移），
  **一次导入就能出该 31 天内任意区间的成表**——因为 `定期余额变化`/`时点资产变化` 是可加的。
  **绝不跨快照合并**（见 8.11）。见 `src/ingest/jiepan.py`。
- **`jjwh` 与别的线不同**：它不是"截至某日的一期"，而是**基期+末期两个时点**（间隔 6 天）。
  `as_of` 存的是**基期日期**，`period.start/end` 是通报口径（基期+1 天 ~ 基期+7 天）。
  页面/通报里的期间一律用 `period`，别用 `as_of` 直接当"本旬起始"。
- **`team`（经理队伍）是一份快照两块内容**：payload 里 `ck`（财客）与 `yw`（远维）各一棵子树，
  `blocks` 记录这块有哪些。**可以只导一块**（`team.merge` 从同日旧快照带过来），
  `as_of` 来自文件名（源表内没有日期）。见 `src/ingest/team.py`、HANDOFF 8.13
- **精度**：快照里比率保留 6 位（`round(x, 6)`），代发/五卡/企微的 ytd、rate 均为原始值；报表层**不要再四舍五入**，否则对账必挂。
  **`team` 是个例外：一律存 double 原值**，`round` 会让成表对账差最后几位（8.13-84）

### 4.3 组装与视图

- `viz.assemble()` 把最新快照拼成 `data/data/dashboard_data.json`（v1 兼容产物，v3 页面基本不用）
- v3 页面走 `api.build_all(date)`：`date=None` 取最新；传日期则每条线取"**不晚于该日**的最新一期"
- 每个 build_xxx 返回**扁平结构**（kpi/trend/rows），前端不关心计算
- `/api/state` 的"数据时点/最近导入"直接查 `store.line_stats()` / `store.recent_imports()`，
  不再解析全部 payload（日期选择器同理，只查 `as_of` 列）

### 4.4 导入台账 / 原始文件

- 每次导入写一条 `import_log`（成功/失败都写），`files` 存原始文件名数组；上传页"最近导入"读它
- 成功时把上传原件登记进 `source_file`（sha256 + 归档路径），可追溯"这期数据来自哪个文件"
- 原件仍在 `data/imports/<line>/<stamp>/`，台账与磁盘文件一一对应

---

### 4.5 口令与权限（大类准入）

不是账号体系，**只有"一组一个口令"**，登录即"本次打开网页内有效"。

| 身份组 | 初始口令 | 能看 |
|---|---|---|
| 个金 `jg` | `gejin2026` | 个金 + 重点项目 |
| 网金 `wj` | `wangjin2026` | 网金 + 重点项目 |
| 个贷 `loan` | `gedai2026` | 个贷 + 重点项目 |
| 银行卡 `card` | `yinhangka2026` | 银行卡 + 重点项目 |
| 私银 `pbs` | `siyin2026` | 私银 + 重点项目 |
| 管理员 `admin` | `admin2026` | 全部七个板块 + 管理口令 |

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

七大板块：个金、网金、个贷、银行卡、私银、**实用工具**、重点项目。
模块全表见 `docs/MODULES.md`（自动生成），新增模块的固定流程见 `docs/skills/dashboard-new-module/`。

> 「实用工具」是**工具板块**（`tool`），不是数据条线：`upload: False`（导入页不出现）、
> 模块 `kind: 'tool'`（侧栏标"开发中"、没有 as_of、走 `pages/tool.js` 渲染）。
> 当前两个模块：`tool-date-diff` 时日差计算、`tool-deviation` 偏离度计算，**内容待实现**。
> 加工具：`catalog.py` 的 `tool-main` 分组里加一条 `page: 'tool', kind: 'tool'`。

```
个金（nested=True，三级）
 ├ 增存：定期存款✓ | 定期承接✓ | 行外吸金 | 降级挽回✓ | 经理队伍✓
 ├ 增客：全量客户 | 代发工资✓ | 薪管家✓ | 一卡一户 | 五卡唤醒✓
 └ 增收：基保理 | 三方支付
网金（平铺）：线上服务✓ | 数币钱包✓ | 企微社群✓
个贷 / 银行卡 / 私银：各 1 个占位模块
实用工具（工具类，`upload: False`）：时日差计算 待实现 | 偏离度计算 待实现
重点项目（平铺）：网点争先 | 全量客户拓展 | 企微社群运营✓ | 五卡唤醒✓ | 挑战回访100位客户
```

✓ = `kind: "metric"`，有页面、可上传；`kind: "tool"` 是工具（无数据、标"开发中"）；
其余为 `placeholder`（灰、不可点）或 `planned`（可点但进占位页）。

**当前 25 个模块：数据 14 / 工具 2 / 占位 9**（`python scripts/check_modules.py` 会打印）。

模块 id（路由 `#/m/<id>`）：

- 个金：`jg-deposit-time` `jg-deposit-jiepan` `jg-deposit-waihang` `jg-deposit-jiangji` `jg-deposit-team`
  `jg-customer-all` `jg-customer-pay` `jg-customer-xgj` `jg-customer-yika` `jg-customer-card`
  `jg-income-jbl` `jg-income-pay`
- 网金：`wj-online-svc` `wj-wallet` `wj-wecom-social`
- 项目：`pj-contend` `pj-allcustomer` `pj-wecom` `pj-fivecards` `pj-100`
- 私银：`pbs-cust`（原名 `pbs-todo` / 「私银客户与 AUM」，0.1.6 起改成「私人银行」）
- 其他：`loan-todo` `card-todo`

**关键字段**：`as_line` 决定该模块能不能上传（有 `as_line` 且 `kind=metric` → 可上传）、`page` 决定用哪个前端渲染器。

路由（前端 `app.js`）：

```
#/                 首页（六板块总览）
#/p/<profId>       板块页（个金走专用 jg.js，其余通用 browse）
#/g/<prof>/<group> 分组页（只有个金有）
#/m/<moduleId>     模块页（按 page 分发到 RENDERERS）
#/report[/<kind>]  通报中心（kind: online/salary/wallet/deposit/community/downgrade/
                   yika/pbs/jiepan/ck/yw）
#/m/jg-deposit-jiepan?…   定期承接页；统计区间放地址栏 ?s=2026-10-01&e=2026-10-25
                   （/api/all 与 /api/report/jiepan 都认 start/end 两个参数）
#/upload           上传（两级选择，默认落到自己大类）
#/upload/<moduleId> 上传并预选该模块（模块页右上角"导入数据"就跳这里）
#/guide            使用指南（不过口令，所有人可看）
#/guide/<section>  指南里的某一节；section 通常=模块 id（模块页右上角"使用指南"跳这里）
#/changelog        更新日志（与指南并行的独立页，左上角两个页签互切）
```

---

## 6. 后端 API（`src/server/app.py`）

| 方法 | 路径 | 验口令 | 说明 |
|---|---|---|---|
| GET | `/`、`/assets/*`、`/vendor/*` | — | SPA 与静态资源 |
| GET | `/api/catalog` | — | 目录 + 可选日期 + latest/earliest + `line_keys`（条线→视图 key）+ `roles` + `version`/`build` |
| GET | `/api/all?date=YYYY-MM-DD` | — | 全量视图模型（首屏一次拉完） |
| GET | `/api/line/<line>` | — | 单条线 |
| POST | `/api/auth/login` | — | `{password}` → `{token, role, label, admin, scope}`；错口令 401 |
| POST | `/api/auth/password` | 管理员 | `{role, password}` 重置某个身份组 |
| POST | `/api/auth/logout` | token | 注销当前 token |
| GET | `/api/report/<kind>` | ✅ | 通报数据（表格 + 文案） |
| GET | `/api/report/<kind>.xlsx` | ✅ | 通报 Excel（按样式母版填） |
| GET | `/api/state` | ✅ | 各线时点、期数、最近导入台账（含 `db` 统计） |
| POST | `/api/import` | ✅ | multipart：`line`、`date?`、`files[]` |

口令不对或过期时，这几个接口回 `401 {"ok":false,"auth":true}`；前端据此弹口令框。

`/api/health` 不验口令，返回 `{ok, root, version, build, schema, sqlite}`——排查"跑的是哪一版"先看它。

导入走 `viz.do_import(line, files, data_date)`：
`归档原件 → readers.normalize（纠扩展名）→ 技能 classify/compute（dfmx/wk 是自写解析）→ 写快照 → assemble → 记台账`。
文本内容被误命名成 xlsx 且识别失败时，会**自动转成真 xlsx 重试一次**。

---

## 7. 通报中心（`src/server/report.py`）

**9 条线**：`online / salary / wallet / deposit / community / downgrade / yika / pbs / pbs_dev`
（`pbs_dev` 不是独立通报，是私银的第二张表，只提供 Excel、不单独出现在页签里）。

- 每条线一个 `build_xxx()` 产出 `{title, as_of, tables:[{name, columns, rows, totals}], text}`
- 每条线一个 `xxx_xlsx()`：**加载 `src/report/assets/<line>_base.xlsx` 后填数**
- 样式母版来源：把 `automations/*/out/*.xlsx` 正式成表**清空数据区**后另存（保留字体/边框/列宽/合并/数字格式）
  - online：微软雅黑 11；salary：仿宋_GB2312（支行/网点双 sheet）；wallet：等线 11（A 列支行分组）；
    deposit：方正黑体_GBK；community：宋体 11（支行/网点双 sheet）；
    **downgrade：微软雅黑，深红双层表头 + 黄/绿底色 + 右下备注区（通报/网点明细 双 sheet）**
- 降级挽回的文案由 `report._signed()` 生成措辞：**`+` 说"增长"、`−` 说"下降"**（数字本身不带符号）；
  三段固定格式（整体情况 / 支行排名 / 营销先锋），见 `build_downgrade()['text']`
- 红绿：online 每列前 5 红 / 后 5 绿（`annotate()`）；**私银用母版自带的条件格式**，代码不干预
- **私银导出是单独一套做法，别按其他线的方式改**（见 `docs/modules/pbs-cust.md`）：
  母版就是官方成表原件（`soffice --convert-to xlsx` 转一份、公式换静态值、删掉下方手工区），
  导出时**只写数据格**。不删列、不重排、不动隐藏列、不重建样式。
  - `pbs_xlsx` → 核心指标通报（定稿页，13 个可见列 + 一批隐藏列）
  - `pbs_dev_xlsx` → 网点私人银行客户发展情况表（Sheet1 + 横幅图片）
  - 前端 `report.js` 对 `pbs` 多渲染一个「下载发展情况表」按钮
    （**曾经试过打包成一个 zip 由一个按钮下载，出问题已回退**，见 8.1-12）
- 前端：`pages/report.js`，页签 → 取 `/api/report/<kind>`；支持复制文案、下载 Excel、复制图片、导出图片（html2canvas）
- **按口令过滤大类**：`LINES` 里每条通报带 `cat`（jg / wj），页面只渲染 `auth.can(cat)` 的通报；
  可见大类 >1 时顶部出现大类胶囊（管理员能看到「个金 2 / 网金 3」，单一身份组不显示胶囊）
- Excel 现在走 `fetch` + blob 下载（`<a href>` 带不了 token）；新增通报别忘了登记 `cat`
- 新增一条线：写 `build_xxx` + `xxx_xlsx`，登记 `BUILDERS` / `XLSX` / `CAT_OF`，
  再在 `report.js` 的 `LINES` 加 `{id, name, cat}`（少登记一处 `check_modules.py` 会报）
- **登记顺序有坑**：`BUILDERS` 在 `report.py` 中部，`build_xxx` 必须定义在它前面，
  否则 `NameError: build_xxx is not defined`（插入代码块时要挪位置）

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
9b. **要跟某个 Excel 长得一模一样时，别重画——直接拿原件当母版**：
    `soffice --convert-to xlsx` 转一份 → 公式换成静态值 → 删掉下方手工计算区 → 当模板，
    导出时只往数据格写值。私银就是这么做的，细节与三次翻车记录见 **8.10**。

### 8.2 数据 / 解析

10. **扩展名不可信**：曾出现 CSV 被另存成 `.xlsx`。`ingest/readers.py` 按文件头判断（PK→xlsx、D0CF11E0→xls、否则文本），导入时自动改回正确扩展名。
11. **企微"上周"不是上一份备份**，而是"最接近 本周−7 天"的备份（否则 +30 变 +4）。
12. **企微"交互数"= 群聊消息总数（x）**，不是"发过消息的成员数（msg）"；熟识率分子用 msg。
13. **代发明细的"当月代发"列不可靠**（26.07 那期混进了累计值/重复行，用户明确说不改数据）：月度金额用**年累计相邻两期相减**，跨年重置。
14. **代发明细 26.07 sheet 有 2,847 行（其他约 2,265）**，疑似重复导出；已知问题，用户接受。
15. **薪管家导入时会把 0 网点过滤掉**（`viz.import_xgj`），所以报表必须用模板行名补齐，不能直接用快照列表。
16. 数币网点名在快照里是短名（无"阜阳"），报表匹配要归一。
17. **`datetime` 是 `date` 的子类**：openpyxl 读日期得到 datetime，`isinstance(v, date)` 会先命中，
    于是 `isoformat()` 变成 `2026-09-13T00:00:00`。判断顺序必须 `datetime` 在前（降级挽回踩过）。
18. **映射表里 `XX支行营业室` 是网点、不是支行**：按"以支行结尾"过滤会把 8 家营业室全排除，
    网点数从 40 变 32、所有网均值都错。判实体网点的正确写法：以「支行」**或**「营业室」结尾，
    并显式排除「…运行管理部」（`ingest/downgrade.py::is_entity_net`）。
19. **明细表数值列混有字符串**（`'780.76'`，175 行）：必须 `float(str(v).replace(',',''))`，
    直接 `float(v)` 会抛异常或静默丢数。
20. **成表数字用 1 位小数显示、原始值存 4 位**：`number_format='#,##0.0'` 只影响显示；
    页面用同样的 1 位，别在 JS 里再四舍五入一次造成两处不一致。
21. **"前三/后三"按名次取，别按数值正负筛**：降级挽回 1020-1026 期只有两家评分为正，
    老写法 `[b for b in branches if b['score'] > 0][:3]` 只取到两个，文案变成"两家位居前三"。
    正确写法见 `report.build_downgrade()`：先按 `rank` 排序，再 `[:3]` / `[-3:][::-1]`。
    **凡是"前 N / 后 N"、榜单、头尾，一律按排序后的名次切片，不要先按正负/阈值过滤再切。**

### 8.3 前端

22. **截图/录屏要用 `--force-prefers-reduced-motion`**，否则动画停在中间帧（数字显示成 267.87 之类的假值）。`countUp` 已尊重该设置。
23. **平铺板块要遍历所有分组**（曾只取 `groups[0]`，网金少了两个模块）。
24. 图表统一在 `charts.js`（`barRank` 支持负值向左+绿色、`splitRank` 做"头尾突出"、`bigTable` 做全屏大表）。
25. 抽屉、全屏表、提示都在 `ui.js`；新增页面照 `pages/*.js` 的默认导出结构写。
26. **阵列新方法一律不要用**：`Array.prototype.at`（Chromium 92+）、`Object.hasOwn`、
    `structuredClone`、`replaceAll`、`findLast`、`toSorted` 在老内核上直接抛
    `TypeError: xxx is not a function`，整页白掉（薪管家 `tr.at(-1)` 踩过，报错行号指向别处，很难认）。
    统一写法：下标 `arr[arr.length-1]`、`indexOf`、手写 `JSON.parse(JSON.stringify())`。
    查法：`grep -rn "\.at(-\|replaceAll\|Object.hasOwn\|structuredClone" src/web/assets/js/`
27. **点击事件里别用 `e.currentTarget` 做延时闭包**：事件回调结束后 `currentTarget` 会被置空，
    `setTimeout(() => e.currentTarget.style...)` 就是 `Cannot read property 'style' of null`。
    按钮动效改成**切 class**（`btn.classList.add('spinning')`），不要存 `currentTarget`。
28. **侧栏导航要拦"误拖"**：按住导航项手一抖，浏览器按拖动链接处理 → 直接新开窗口。
    三道防线都在 `app.js::guardSidebarDrag()`：锚点 `draggable="false"` + 侧栏内拦 `dragstart` +
    按下到松手位移 >6px 就不认这次 click。CSS 另有 `-webkit-user-drag:none`。
    新增侧栏链接（含板块/分组入口）必须带 `draggable="false"`，否则又会冒出"点了新开一个网页"。

### 8.4 口令 / 权限

29. **权限只存在内存**：`auth.js` 的模块变量 + 服务端 `_sessions`。刷新即失效是需求；不要改 `sessionStorage`/`localStorage`。
    口令框有三个结束态，别混：`true`=通过、`false`=用户取消、`null`=被换页关掉（`cancelGate()`）。
    `render()` 开头会 `cancelGate()`，所以**切页时口令框自动关**；`startGate()` 拿到 `null` 必须直接 return，
    否则会把用户从刚点开的页面拽回口令页。
30. **带 token 才有数据**：`/api/report/*`、`/api/state`、`/api/import` 全部要 `X-Auth`。页面里一律用 `authFetch()`，
    别直接 `fetch`；Excel 下载也必须 `fetch`+blob（`<a href>` 带不上 header，会 401 却"看起来没反应"）。
31. **401 的统一处理**：`authFetch` 清权限 → 派发 `dash:auth-lost` → `app.js` 重渲染并重新弹口令框。
    页面自己的 `catch` 里遇到 `err.auth` 要**安静返回**，别再往已经被销毁的 DOM 写错误。
32. **新增通报/模块要挂大类**：`report.js` 的 `LINES[].cat`；不挂就是"哪个口令都看不到"。导入页的大类权限靠 `auth.can(prof)`。
33. **管理口令只有管理员能改**（`POST /api/auth/password` 会校验 `sess.admin`）；忘记管理员口令的兜底是删 `data/auth.json`（回到初始口令）。

### 8.5 存储（SQLite）

34. **别在业务代码里直接写文件快照**：一律 `viz.save_snapshot()`（内部走 `store`）。
   早期 `ingest/payroll.py`、`ingest/fivecards.py` 直接往 `data/snapshots/` 写 JSON，迁移时已改掉。
35. **备份要连 WAL**：`cp icbc.db` 可能丢最近的写入。用 `scripts/backup_db.py`（SQLite 在线备份 API），
   或整包打包时把 `icbc.db-wal` 一起带上。
36. **`store.load_snapshots()` 返回缓存里的同一个 list**：只读，要改先 `dict()` 拷一份。
   缓存 TTL 3 秒，**本进程写入会立刻失效**，别的进程（CLI 脚本）写入最多 3 秒后可见。
37. **旧 JSON 只读一次**：`store.import_legacy()` 靠 `setting.legacy_json_imported` 幂等；
   挪走 `legacy_json_*` 后不会再灌。别把 `snapshots/` 手工放回 `data/`，否则空库启动会自动导入一遍。

### 8.6 环境

38. WSL 下 Node 的 `--check` 可用来快速验 JS 语法：`node --input-type=module --check < file.js`。
39. 本机 LibreOffice 宏不可靠（见 AGENTS.md），但**转换/重算**可用；不要在自动化里依赖宏。
40. 服务进程重启：`fuser -k 8766/tcp` 再起；日志 `/tmp/viz-v2.log`。

### 8.7 老浏览器兼容（内网机踩过）

41. **不要用 `inset` 简写**：目标机有一台的 Chromium 内核在 84–86 之间，不认 `inset`，
   所有 `position:fixed` 浮层会掉到文档流末尾（看不见、点不到）。已改成
   `top/right/bottom/left` 四边；新增浮层也照这个写。
42. **浮层可见性不要依赖"JS 加 `.on` + opacity 动画"**：动画/合成层没跑起来时会出现
   "遮罩透明但仍挡住点击"的假死（症状：按钮点了没反应）。口令框现在默认不透明，
   动效只做卡片位移；添加浮层时按同样方式。
43. 快速判断：`getComputedStyle(mask).opacity === '0'` 且 rect 覆盖全屏 = 假死；
   rect 为 0 或在视口外 = 布局没生效（`inset` 这类问题）。左下角版本号悬停能看到
   `build` 与 `navigator.userAgent`，让对方发个截图即可定位内核。

### 8.8 使用指南 / 更新日志（0.1.4 新增，改版必看）

44. **四个文件各有分工**：`pages/guide.js`（两个页面的渲染）、`guide-content.js`（指南正文）、
    `changelog.js`（更新日志）、`app.js`（`#/guide` 与 `#/changelog` 两条路由）。
    **指南和更新日志是两个页面**，用页面左上角的页签（`.doc-tabs`）互切，不要再塞回指南正文里。
    正文是纯数据（`GUIDE_SECTIONS`），渲染器只认 `id/group/title/summary/body` 五个字段，
    `body` 里**只允许** `p/ul/ol/li/b/strong/em/code/kbd/table.g-tbl/thead/tbody/tr/th/td/br`，
    不要 inline style、不要 div、不要标题标签（标题由渲染器统一加序号）。
45. **章节 id 就是模块 id**：`#/guide/<模块id>` 能直达，模块页右上角「使用指南」按钮靠这个跳
    （`guide.js::guideHref`，找不到对应节就回 `#/guide`）。新增模块时记得补一节，
    否则 `check_modules.py` 会 WARN。占位模块不必写（它们没有"怎么用"可讲）。
46. **发版必须往 `changelog.js` 最前面插一条**，版本号与 `VERSION` 一致（`check_modules.py` 会 WARN）。
    写"使用者能看到什么变化"，不写函数名/文件名/表名。这条同时是给用户看的发版说明。
47. **指南里不要写死会变的东西**：具体日期（"9.13/9.19"）只能当例子且要标明是例子；
    某个模块"要准备几份文件"来自 `viz.XGJ_ROLE` / `XSFW_ROLE` 等常量，改导入器时要回来改文案。
48. **指南是公开页面**（不过口令），所以不能写初始口令、内部路径、服务器地址、姓名工号。
    口令相关只写"找管理员在「管理密码」里重置"。
49. **回到最上边**用的是 `window.scrollTo(0,0)`，深链定位用 `scrollIntoView` 会顶到粘性顶栏下面，
    所以 `guide.after()` 里手动减 78px；`render()` 末尾已统一 `window.scrollTo(0,0)`，
    新增页面不需要自己处理换页滚动。
50. **带点的 id 不能用 `querySelector('#v-0.1.2')`**：点号在 CSS 选择器里是 class 分隔符，
    直接抛 `SyntaxError: '#v-0.1.2' is not a valid selector`（更新日志的版本索引踩过）。
    用 `[].find(x => x.id === 'v-' + ver)` 或 `getElementById`。
51. **顶栏按钮别让它们换行**：`.crumbs` 要 `white-space:nowrap`、`.topbar-right` 要 `flex:none`；
    窄屏靠媒体查询降级——`<1240px` 数据截止胶囊收窄并省略，`<1100px` 指南按钮换短标签「指南」。
    「数据截至」是业务信息，优先砍装饰性文字，别先砍它。
52. **`e.currentTarget` 之外，`@media` 里的 `content:"…"` 也别用来替文字**（部分老内核不重排宽度）；
    要长短两种标签就直接放两个 `<span>`，用 `display` 切。
53. **用户给的 logo 原图是深色底 JPG**（`Snipaste_2026-10-27_11-08-16.png` 实为 jpeg，246×246，底 `#0b1324`）：
    直接放上去会在侧栏渐变上出现一块方底色。处理：按四角色差做**软阈值抠透明**
    （距离 <18 全透、18~46 线性过渡、>46 保留），裁到 `getbbox()`，补成正方形，输出 384² PNG。
    原图在 `D:\资料\ICBC\Snipaste_2026-10-27_11-08-16.png`，重做时照这个流程。

### 8.9 一卡一户（0.1.5 新增）

54. **「累计」不是户数**：社保卡取 `柜台新增卡数量（本年累计）+ 批量开户新增卡（本年累计）`，
    养老金取 `本年新增`。**不要用养老金的「累计开户数」**——那是存量（含去年及以前），相减跨年就错。
55. **成表合计行公式是 `/2`**：`阜阳分行` 行是 `=SUM(C4:C51)/2`，因为上面 8 行小计已加过一遍。
    换算成"40 个网点之和"即可，**别真的去掉那个 2 再算一次**。
56. **清母版不能整段清空**：社保卡 `F/J`、养老金 `Q/R` 是公式，养老金 `G/M` 列是网点名。
    第一版整段清了，辅助 sheet 全成空白（`scripts/build_yika_assets.py` 里已按列清）。
57. **日期块规则要按"周"算**：周五~周日是一个块（周日代表三天合计），前一日 = 上一块的末日
    （周日 → 周四）；上周末 = 本周开始前的周日（周日 → −7 天，周一 → 前一天）。
    周一时前一日与上周末重合，只用 2 天数据。**周五、周六不出通报**。
58. **网点名三种写法**：成表/养老金 `界首支行营业室`；社保卡源表 `阜阳界首支行营业室`。
    社保卡源表还有 `安徽阜阳分行运行管理部` —— **不是网点**，别算进 40 个。
    归一用 `ingest/yika.py::_norm()`，匹配用 `_lookup()`（精确 → 去前缀 → 后缀唯一）。
59. **源表「合计」行不等于 40 网点之和**：它含运行管理部（多 2 张）。导出成表的合计行要用
    快照里的 `grand`，用网点求和会少 2。
60. **`read_table()` 只读第一个 sheet**：成表文件里带 通报/社保卡/养老金 三张表，
    必须用 `readers.sheets()` 遍历，否则只会看到"通报"那张然后判定"未识别"。
61. **对账要两边都重算**：一卡一户的成表两侧都留了公式（F/J、Q/R），
    `check_report_parity.py` 现在会检测我方文件里有没有公式并自动重算，别只重算参考文件。

62. **`splitRank` 只做"头尾切片"，返回的仍是 rows，必须再包一层 `barRank`**：
    `mount(el, splitRank(...))` 少了 `barRank` 会让 echarts 收到裸数组，
    报 `t.split is not a function`（栈全在 echarts 内部，看不出是自己的错）。
    正确写法：`mount(el, barRank(splitRank(rows, {...}), {...}))`。
63. **源表里的"归属支行"可能不是你要的分行**：私银源表有 12 个值，其中 4 个（牡丹/文峰/城建/汇通）
    要映射到 8 家支行，而且是**对着成表验算**出来的（牡丹→颍泉、文峰→颍州、城建→颍州、汇通→颍东）。
    用户口述与成表不一致时，**以成表为准**并当场确认。
64. **源表可能没有日期列**：私银明细只有客编和金额，日期只能从文件名来。
    `ingest/pbs.py::date_from_name` 覆盖 `20261024` / `2026-10-24` / `2026.10.24` / `10.24` / `1024` / `202512`；
    认不出**必须报错让用户手填**，不要默认今天。

### 8.10 复制官方成表那几次翻车（0.1.6.1~0.1.6.3，成本很高，必读）

65. **「照着成表的样子重新画一个表」必然对不上**：字体分区、字号、隐藏列、条件格式、
    合并区、行高列宽、内嵌图片，靠截图猜一定漏。0.1.6.1 我重画了三轮还是错，
    最后换成 **「原件当母版、只写数据格」** 一次就对。
    **以后凡是"要跟某个 Excel 长得一模一样"，一律先问自己能不能直接拿原件当母版。**
66. **隐藏列不能删，只能让它继续隐藏**：私银定稿里 C~N 之间夹着一批"缩到看不见"的列
    （签约率、渗透率、异地等），是靠 `column_dimensions[..].hidden` 实现的。
    一旦 `delete_cols`，后面列号整体前移，条件格式的 sqref 和公式里的列引用全部错位
    （症状：红绿标到了别的列、表头挤成一团、需要的数据列消失）。
    → 保留原列结构，数据只往**原始列号**写；用户要的是"最后看不见"，不是"物理删除"。
67. **LibreOffice 转换会丢条件格式**：`.xls → .xlsx` 时，某些 CF 规则会消失
    （私银发展情况表 E 列的红绿就是这么丢的，转换后只剩一条无关的 M36 规则）。
    核对"原件到底有什么格式"时，**不能只看转换后的文件**，
    要用 `olefile` 读原始 BIFF 记录：`CONDFMT(0x01B0)` / `CF(0x01B1)` / `DXF(0x00E0)`。
    也可以把原件直接转 PDF 渲染出来看——能立刻分清"哪些颜色是静态涂的、哪些是条件格式算的"。
68. **条件格式的 dxf 可能自带字体色**：私银定稿里 44 条规则的 dxf 字体都是 `00FFFFFF`
    （alpha=0 的白），Excel 渲染成**白字**，红底上根本看不清。
    要"只上底色"就重建 `DifferentialStyle(fill=...)`，别保留原 dxf 的 font。
69. **openpyxl 无法跨工作簿保格式复制 sheet**：`_style` 是索引号，跨工作簿会错位
    （底色串行、标题溢出、`####` 一堆）。要么同簿 `copy_worksheet`，
    要么两个文件分别导出。**别把两张不同母版的表硬塞进一个工作簿。**
70. **"一键下载两个文件"用 zip 打包试过，出了问题**（0.1.6.3 已回退成两个按钮）。
    当时表现是下载打不开/不对。要重做先复现并查清：是 `Content-Type`、文件名编码，
    还是前端 blob 下载的 `download` 属性问题。**在查清前保持两个按钮。**
71. **"前 N / 后 N + 并列全标"要按名次取值，不是按去重值**：
    `1 1 1 2 3 4` 的第 3 小是 **1** → 只标那三个 1；
    `1 1 1 1 1 2` 的第 3 小还是 **1** → 五个 1 全标。
    用"去重后第 3 个"（即 2）会把不该标的也标上。


### 8.11 定期承接（0.1.7 新增，改这条线必看）

72. **口径全在这里，别再自己推**（`src/ingest/jiepan.py` 文件头也写了一遍）：
    - 定期承接率 = (近30天到期金额 + 定期余额变化) / **近30天到期金额**
    - 资金承接率 = (近30天到期金额 + 时点资产变化) / **近30天到期金额**
    - **分母是到期金额，不是「30 天前定期余额」**。两者差很大（本例 8.98 亿 vs 22.73 亿，
      合计承接率 0.8054 vs 0.9231）。2026-10-28 用成表的活公式逐格核实过。
    - 网均未承接 = 支行 `定期余额变化` 合计 ÷ 该支行网点数（元 → 万元）
    - 综合评价 = 网均名次×0.4 + 定期率名次×0.4 + 资金率名次×0.2，三项都是**降序**名次，
      总分**升序**排前；**并列取同一名次并跳号**（Excel RANK 语义）。
      阜南与颍泉可以是**并列第 1**，下一个是第 3，不是第 2。
    - 优秀先锋 = 网点定期承接率降序前 **8**（不是前 10，也不看资金承接率）
    - 网点只算实体网点：以「支行」或「营业室」结尾，排除「…运行管理部」→ 40 个

73. **窗口只能在单份快照内切，绝不跨快照合并**。这是这条线最容易做错的地方：
    每份源表都是"取数日往前一个月"，`30天前定期余额` 的基准日**跟着导出日滚动**
    （10.25 的表基准 9.25，10.19 的表基准 9.19）。同一个客户在两份表里的四个余额列
    数值都不一样，跨批次拼数据在数学上就是错的。`aggregate()` 会用 `coverage` 挡住越界请求。

74. **一次导入能出任意子区间**，因为 `定期余额变化` / `时点资产变化` 是**每客编这一期**的变化量，
    与窗口无关；按 `最近到期日期` 筛行求和就得到该区间的结果。payload 存客编级明细
    （`nets` + `rows`，每行 7 个字段），不要只存聚合结果，否则切不了窗口。

75. **「大额整体流失户」是人工在源表里改的，不是规则算出来的**。10.25 那期有 3 户
    （阜南胜利路 ×2、太和华源 ×1，各 600~700 万）到期后资产近乎清零，
    人工处理方式是**把源表该行的「定期余额变化」和「时点资产变化」两列都改成 0**，
    「当前余额」列还是 0（所以会出现"变化 ≠ 当前 − 30天前"的行，共 3 行）。
    影响 2002 万，占合计 10%　——**不要试图用金额阈值自动判定**，那只是巧合。
    `jiepan.parse(exclude=[客编...])` 留了接口，默认不排除；用户说以后在导入前处理。

76. **成表母版直接取「清空数据的成表」**（`src/report/assets/jiepan_base.xlsx`），
    里面 A 列（支行）和 C 列（元）本来是**隐藏**的，Sheet7 的 J 列（网点负责人）也隐藏。
    用户截图确认"只看 B/D/E/F 四列"，所以导出沿用母版的隐藏状态，不要取消隐藏。
    Sheet6 原来 43-85 行是隐藏的"按承接率降序副本"、Sheet7 13-33 行是排名计算区，
    已在母版里**删掉**（我们直接按名次写数，不需要这些中间行）。

77. **`net_short()` 的简称规则要对得上人话**：`XX支行营业室`→`XX营业室`（不是 `XX`），
    `临泉政务新区`→`临泉政务`，结果不含支行短名时补上（牡丹支行 属 颍泉 → `颍泉牡丹`），
    已含支行名的不重复补（太和大桥支行 → `太和大桥`）。

78. **官方的 G12 那格是错的**：公式范围写成 `E2:E4902`（只覆盖 7816 行里的 4901 行），
    所以官方合计资金承接率 0.9135 是"前半段"的值，全量应为 **0.9058**。
    我们按全量算，导出比官方大 0.0076——**这是修 bug，不是不一致**。
    另外官方 Sheet7 的 C 列（综合评价）在重排后又引用固定行号（`=I16`…），整体错位，
    我们用 `RANK` 语义重算，与官方的**并列第 1**一致。


### 8.13 经理队伍（0.1.8 新增，改这条线必看）

81. **只读明细子表，别碰中间表**。一份工作簿里有 `财客明细` + `计算１` + `ＶＬＯＯＫ` + `Sheet3`：
    `计算１` 是 `财客明细` **换了表头的同一份数据**（49×88 逐格一致），`ＶＬＯＯＫ` 是按支行聚合的
    透视结果。我们的聚合自己做，读中间表只会把官方那套 VLOOKUP 序号错误一起抄进来。
82. **两块可以只导一块**，`ingest/team.py::merge()` 从**同一天**的旧快照里把另一块带过来；
    页面「导入说明」会写清是"沿用"还是"本次只导了X"。别把"只导一块"当成覆盖整条线。
83. **源表没有日期**，`as_of` 从文件名认（复用 `ingest.pbs.date_from_name`）：
    `20261021` / `2026.10.21` / `2026-10-21` / `10.21` / `1021` / `10-21` / `10月21(日)` 都认，
    不带年按今年。认不出**必须让用户手填**（`DATE_ARG_LINES` 里加了 `team`）。
84. **绝不要 `round()`**：成表对账是逐格比 double。当初按惯例 `round(x, 6)`，
    ck 差 63 处、yw 差 59 处，全是 `92.2885807957933` vs `92.288581` 这种末位差异。
    `team` 的聚合与导出**一律存原值**（其他条线的 6 位约定不适用这里）。
85. **官方远维成表的 R~V 五列取错了字段**（透视表比财客多一列「社保卡存量」，VLOOKUP 序号没跟着改）：
    R=社保卡存量、S=社保卡增量、T=养老金增量、U=借记卡绑卡增量、V=贷记卡绑卡消费增量；
    「贷记卡纯消费增量」压根没被引用。**用户 2026-10-29 拍板按表头取数（与财客对齐）**，
    所以这 5 列与官方原件不同，对账用 `SKIP_CELLS['yw']` 跳过，**别"修回去"对齐官方**。
86. **远维明细末尾有隐藏的临时名单区**（15 行起，只有姓名 + 网点名、没有支行）：
    解析按"支行列为空"跳过；母版里已删掉这些行。对账用 `SKIP_DETAIL_ROWS = {'yw': 15}`。
87. **表头校验不能省**：`CK_COLS` / `YW_COLS` 是「字段→列号」的硬映射，导入时用**三行表头
    合并后的路径**逐列核对（`CHECK`）。源表哪天加了列，直接报错，不会静默取错数。
88. **成表母版由脚本生成**：`scripts/build_team_bases.py` 拿官方成表 → 只留两个子表 →
    清掉数据格、保留 B 列机构名/表头/合并/条件格式/隐藏列 J。**换版式要重跑这个脚本**，
    不要手改 xlsx。清数据时 `A13` 的 `－` 是固定标签，要留住。
89. **汇总规则**：`总得分` + 两个营销通执行率取**平均**，其余**求和**；单位换算只在导出/页面做
    （财客理财转亿元，远维理财留万元）；「50万以上客户」表头写"万户"但值其实是**户**。
90. **通报中心里是"一条通报 + 两个下载按钮"，不是两条通报**（用户 2026-10-29 明确要求）：
    builder 是 `build_team()`，返回 `downloads: [{key:'ck',…},{key:'yw',…}]`，
    前端 `report.js` 按 `downloads` **动态渲染按钮**（`paintDownloads`），
    `XLSX` 里仍然是 `ck_xlsx` / `yw_xlsx` 两个 key。
    以后再有"一条通报多份成表"的，照这个来：**在 `BASES_OF` 登记母版、在 builder 里给 `downloads`**，
    别拆成两条（私银也是这个模式：`pbs` + `pbs_dev`）。
91. **切页签这类"局部重画"必须每次重新绑事件**：`pages/team.js` 的财客/远维页签第一次能点、
    第二次点不动 —— 因为 `renderBlock()` 重建了 DOM，而事件只在外层绑了一次。
    正确写法：把绑定放**重画函数里面**，并先 `disposeAll()` 销毁上一块的 ECharts 实例。
    **凡是"重画自己"的交互，都按这个检查一遍**。

### 8.12 两个"本机正常、到内网就坏"的坑（0.1.7.1）

79. **openpyxl 读写 xlsx 里的图片依赖 Pillow，而内网运行时没有 Pillow**。
    `vendor/pylib` 只放纯 Python 包（openpyxl / xlrd / PyYAML，与架构无关），
    所以 `load_workbook()` 读出来 `ws._images` 是 **0**，`save()` 之后
    `xl/media/*`、`xl/drawings/*` **全没了** —— 私银「发展情况表」的表头横幅就是这么丢的。
    本机虚拟环境装了 Pillow，**永远复现不出来**；`dist/` 里的母版本身是有图的（能验证）。
    修法：`src/xlsx_keep.py` 的 `save_like(tpl, wb)` —— 先正常保存，再把母版有、产物没有的
    图片部件原样补回，并补齐 `[Content_Types].xml`、`<drawing r:id>`、sheet rels 三处引用。
    **只在产物没有 media/drawing 时才动手**，所以本机（有 Pillow）走原路径、不会重复注入。
    ⚠️ 补 `<drawing>` 时必须**就地声明 `xmlns:r`**（母版是这么写的）；只写 `r:id` 会让
    严格的解析器报 `ParseError: unbound prefix`，而 openpyxl 自己重读就会炸。
    ⚠️ 以后任何"母版里带图片/图表"的导出，都要走 `save_like(母版路径, wb)`，别直接 `wb.save()`。

80. **Chrome 传大文件会用 `Transfer-Encoding: chunked`，服务端原来只认 `Content-Length`**。
    原来 `do_POST` 直接 `self.rfile.read(Content-Length or 0)`：分块上传时读到 **0 字节**，
    于是"没有收到文件"或提前回包，连接被判为损坏，前端只看到
    `TypeError: Failed to fetch`（Chrome 报 `ERR_ALPN_NEGOTIATION_FAILED`），
    **服务端日志里连一行都没有**。已改成 `_read_body()` 两种传输方式都认。
    排查提示：如果"导入偶发网络错误、服务端无日志"，先看浏览器 Network 里这条请求有没有
    `Content-Length`；没有就是分块上传。

---

## 9. 当前状态 / 卡在哪

### 已完成

- 七大板块框架（含实用工具）、个金三级导航、首页总览、个金总览页（基础数据 + 三分类模块卡带数）
- **10 条线接入**：定期、线上服务、数币、薪管家、企微、代发工资、五卡唤醒、降级挽回、一卡一户、**私人银行**（页面 + 上传 + 时点）
- 上传两级（专业→模块）+ 多格式读取 + 台账
- 通报中心 **10 条通报**（表格/文案/Excel/图片），对账脚本全绿（1 处标题日期差异）；
  私银、经理队伍都是"一条通报 + 两个下载按钮"
- 日/月切换；红涨绿跌；头尾突出排行；全屏大表
- 顶栏"数据截至"改为**按当前页面模块自己的时点**（模块取 `as_of`，板块取该板块各模块最大值；
  选日期筛选时显示"数据截至 X · 所选 ≤Y"），日期控件的值也跟着本页时点走
- 口令准入：六个身份组、大类过滤（导入页灰掉无权大类、通报中心不显示无权通报）、
  管理员改口令、右上角身份胶囊（五大类=重新验证，管理员=管理密码/重新验证）
- **存储迁到 SQLite**：`data/icbc.db`（snapshot / source_file / import_log / setting），
  迁移脚本 + 对账脚本 + 热备份脚本齐备；旧的 `data/snapshots/*.json` 已挪到 `data/legacy_json_*`
- 侧栏下半区固定「通报中心 / 导入数据」，上方模块列表照常滚动
- **实用工具板块**（工具类，`upload:false`）：时日差计算 / 偏离度计算，页面是统一工具外壳，内容待实现
- **降级挽回**：客编明细单表导入（映射内置）、支行+网点双层页、通报文案（+增长/−下降）、
  Excel 与正式成表**逐格零差异**（双 sheet）
- **使用指南**（0.1.4）：右上角「导入数据」左边一个低调入口 + 每页可直达对应章节
  （`#/guide/<模块id>`）；正文 19 节分五组，左侧目录常驻、底部「回到最上边」；指南**不过口令**
- **更新日志**独立成页（`#/changelog`），与指南用页面左上角页签互切（0.1.4.1）
- **顶栏精简**（0.1.4）：原来「刷新」+「回到最新」两个按钮功能重叠，合并为一个
  （清筛选 + 重新取数）；动效改成切 class，不再碰 `e.currentTarget`
- **侧栏防误拖**（0.1.4）：`draggable=false` + 拦 `dragstart` + 位移>6px 不认点击
- **老内核修复**（0.1.4）：薪管家页 `tr.at(-1)` 在 Chromium<92 上整页报错，已换成下标
- **定期承接**（0.1.7）：客编明细单表导入 → 网点/支行两层；**一次导入可切任意区间**
  （默认上周，可取数日往前一个月内任选）；支行按综合评价（名次 4:4:2）排名、并列同名次；
  优秀先锋 = 承接率前 8；通报文案三段 + 双 sheet Excel **与成表逐格一致（32+120 项零差异）**
- **标识与品牌**（0.1.4.2）：侧栏换成工商银行红金立体 logo（透明底 PNG），标题「工商银行阜阳分行 / 经营驾驶舱」；
  浏览器标签、收藏夹图标、加载动画同步换掉
- **私人银行**（0.1.6 ~ 0.1.6.3）：客编明细单表导入（日期靠文件名识别，认不出让用户手填）；
  三个时点（当天 / 上年末 / 上季度末）拼表；产品销售 7 项做成导入页里的**可编辑表格**、
  存 setting、与文件共用提交按钮
  - **成表导出 = 官方成表原件当模板、只填数据格**（0.1.6.2 定下来的做法，见 8.1-12/13），
    字体、字号、底色、条件格式、隐藏列、横幅图片全部原样继承，与人工做的完全一致
  - 两个下载按钮：核心指标通报 / 网点发展情况表
  - 红绿：核心指标表用母版条件格式（**字色已改黑**，原来 dxf 里是白色导致看不清）；
    发展情况表 E 列（较年初）好 3 红/坏 3 绿、C 列（当前存量）**只红+黄不标绿**，
    判定按**名次**并列全标（`1 1 1 2 3 4` 只标那三个 1）
- **带数据升级**（0.1.6）：`update.sh --with-data` 用 `scripts/merge_seed.py` 把包内 seed **合并**进生产库
  （快照按 `(line, as_of)` 只补缺、setting 只补缺失键，绝不覆盖口令与手工维护的数据）
- **一卡一户**（0.1.5）：社保卡 + 个人养老金，支行/网点两层；导入按日存累计值（`ykh_sb`/`ykh_yl`），
  出通报自动拼「当日/前一日/上周末」三个时点；文案与用户模板**逐字一致**，Excel 三张 sheet
  与正式成表**逐格零差异**，已进对账用例

- **经理队伍**（0.1.8）：财客（支行 8 / 网点 40 / 经理 49）+ 远维（支行 8 / 经理 10）两块，
  页签切换；两个文件可只导一个；日期认文件名（7 种写法）。
  通报中心里是**一条**「客户经理经营业绩」：文案整篇一体，导出**两个按钮**（各带自己日期），
  Excel 版式与官方成表**逐格零差异**（远维 R~V 五列按用户要求修正了官方的取数错误）

### 未完成 / 待定

| 事项 | 现状 | 需要的输入 |
|---|---|---|
| 网点争先、挑战回访100位客户 | 占位页 | 名单/排名/积分口径 |
| 全量客户拓展 | 占位页（`planned`） | 现在是文字进度表，需要结构化字段 |
| 行外吸金、全量客户 | 占位 | 数据源 |
| 实用工具的两个工具（时日差 / 偏离度） | 页面是空壳 | 输入输出定义 |
| 基保理、三方支付（增收） | 占位 | 数据源；基保理=基金/保险/理财 |
| 个贷、银行卡 | 占位 | 数据源 |
| 私银两份成表合并下载 | 现在是两个按钮；打包成 zip 由一个按钮下载试过但出问题，已回退（0.1.6.3） | 要重做的话先查清当时失败原因 |
| 私银产品销售历史 | 只存当前值（`setting.pbs_sales`），没有按日留痕 | 需要看历史则改成按日快照 |
| 账号级身份 | 未做：只有"一组一口令"，不记谁导的 | 需要追责时再加姓名/工号 |
| 导航级权限 | 未做：侧栏仍可浏览所有板块（口令只拦两个管理模块） | 若要求"没口令连板块都不给看"，需在 `render()` 前置门槛 |
| 通报日期 vs 数据日期 | 线上服务标题差 1 处 | 导入时加"通报日期"字段即可 |
| 部署形态 | 已完成：releases+current+shared、install/update/回滚、热备份、导出 .db | 见 `docs/DEPLOY.md` |
| 内置运行时 | 机制就绪（自检+回退），arm64 二进制未实测 | 首次装完用 `bin/status.sh` 确认解释器 |
| Excel/CSV 批量导出 | 未做（通报中心可导单份 Excel；对外只导 .db） | 需要时定义表口径 |
| 降级挽回对账用例 | 未进 `check_report_parity`（缺第二期成表） | 拿到下一期成表后补 `CASES` |
| 经理队伍对账用例 | 已进 `CASES`（ck/yw 各一条），但只有这一期成表 | 下一期成表来了再加一条做回归 |
| 降级挽回映射更新 | 映射是固定 json（1749 条），客编新增需手工更新 | 需要时加"映射表覆盖导入" |
| 定期承接的「大额流失户」剔除 | **未做**：官方做法是人工在源表里把两列改成 0；`parse(exclude=…)` 留了接口 | 用户说以后在导入前处理，届时把客编传进来即可 |
| 定期承接的网点负责人 | **未做**（成表 J 列，用户确认最终不展示） | 无 |
| 定期承接的对账用例 | 未进 `check_report_parity`（成表是人工剔除后的口径，源表是原始口径） | 拿到下一期"源表 + 成表"成对文件后补 |
| 一卡一户的历史回填 | 养老金表一次能带 36 个日期进来；社保卡历史需逐天导（源表一天一张） | 无（源表限制） |
| 指南随版本演进 | 新模块/新按钮要手动补 `guide-content.js` 一节 + `changelog.js` 一条（`check_modules.py` 会 WARN 但不阻塞） | 无（流程性工作） |
| 指南里的"要准备几份文件" | 从 `viz.XGJ_ROLE` / `XSFW_ROLE` 等常量反推，不是自动生成 | 数据源角色变化时要回来改文案 |

### 备份

- 日常热备份：`python scripts/backup_db.py` → `data/backups/icbc-<时间戳>.db`（默认留最近 20 份）
- 迁移前留档：`data/legacy_json_<时间戳>/`（旧 JSON 快照 + ledger.jsonl，确认无误后可删）
- 发布包：`dist/icbc-dashboard-<版本>.tar.gz`（含 seed 种子数据 + arm64 运行时，见 `docs/DEPLOY.md`）
- 代码+数据整包：`/mnt/d/资料/ICBC/icbc-dashboard-备份-20261022.tar.gz`（9.3 MB，迁移前的版本）
- 更旧的保险副本：`/mnt/d/资料/ICBC/Visualizations.migrated-20261021`（可删）

---

## 10. 常见改动路径（改哪儿）

| 想改 | 改哪里 |
|---|---|
| 板块/模块/名称/顺序 | `src/domain/catalog.py` |
| 导航层级（是否子目录） | 同上 `nested: True`；渲染在 `app.js` 的 `navSection()` |
| 某模块的数字卡 | 对应 `pages/*.js`（如 `jg.js` 的 `statsFor`） |
| 图表样式/配色 | `src/web/assets/css/app.css` 的 `:root`、`charts.js` 的 `PALETTE` |
| 顶栏标识 / 品牌文字 | `src/web/index.html` 的 `.brand` + `assets/img/logo.png`；页面标题在 `app.js` 的 `document.title` |
| 新增一个模块（完整流程） | 读 `docs/skills/dashboard-new-module/SKILL.md`，按 8 步接线（末步含使用指南+changelog），最后跑 `python scripts/check_modules.py --write` |
| 新增一条线上传 | catalog 加 `as_line` + `viz.IMPORTERS` 注册解析器（存库走 `viz.save_snapshot`，别写文件） |
| 查"哪个模块没接好" | `python scripts/check_modules.py`（id 重复/页面缺失/条线未注册/通报未登记都会报） |
| 新增一条通报 | `report.py` 加 `build_xxx`/`xxx_xlsx` + `report.js` 的 `LINES` |
| 报表样式 | 换 `src/report/assets/<line>_base.xlsx`（务必是"成表清数据"） |
| 部署/升级脚本 | `deploy/`（`install.sh` / `update.sh` / `bin/*.sh`），结构见 `docs/DEPLOY.md` |
| 依赖版本 | `requirements.txt` + `vendor/pylib/`（纯 Python，改版本要两个一起改） |
| 发布打包 | `python scripts/package_release.py`（版本号=日期+git sha） |
| 口令 / 身份组 | `src/server/auth.py` 的 `ROLES`/`DEFAULTS`；前端表现看 `auth.js`、`app.js` 的 `paintTop()/startGate()` |
| 表结构 / 加指标表 | `src/store.py`（`SCHEMA_SQL` + `SCHEMA_VERSION` + `init()` 升级分支） |
| 查库/排障 | `python scripts/migrate_to_sqlite.py --db-info`，或 `sqlite3 data/icbc.db "select line,max(as_of),count(*) from snapshot group by line"` |
| 某模块的"数据截至" | 自动取该模块 `as_line` 的 `as_of`；要改文案看 `app.js` 的 `asofFor()` |
| 降级挽回的口径 | `src/ingest/downgrade.py` 顶部常量（`REPORT_SHIFT` / `SPAN_DAYS` / `UNIT` / `EXCLUDE_SUFFIX`） |
| 一卡一户的口径 | `src/ingest/yika.py` 顶部常量（`WEEK_DAYS=6`、`SB_COLS`、`YL_SUB`）+ `plan_dates()` 日期块规则 |
| 一卡一户的网点/目标 | 改 `src/report/assets/yika_targets.json`，或改 `scripts/build_yika_assets.py` 后重跑 |
| 一卡一户的母版样式 | 换 `src/report/assets/yika_base.xlsx`（务必跑 `build_yika_assets.py` 生成，别手清） |
| 降级挽回的客编映射 | 换 `src/report/assets/downgrade_map.json`（`[[客编, 支行, 网点], …]`，改完重启） |
| 定期承接的口径 | `src/ingest/jiepan.py`（`COLS` 列名映射、`TOP_N`=8、`EXCLUDE_KEY`、`_rank_desc/_rank_asc`） |
| 定期承接的网点清单 | `src/report/assets/jiepan_nets.json`（支行 → 网点，改完重启） |
| 定期承接的成表版式 | 换 `src/report/assets/jiepan_base.xlsx`（**成表清空数据**，别取消 A/C 列隐藏） |
| 定期承接的手工改数 | `src/ingest/jiepan.py` 的 `EDIT_FIELDS`（开放哪几列）；前端在 `pages/import.js` |
| 带图片的 Excel 导出 | 一律走 `xlsx_keep.save_like(母版路径, wb)`（见 8.12 第 79 条） |
| 私银的网点清单 / 支行归属 | `src/report/assets/pb_nets.json`；支行别名在 `src/ingest/pbs.py::BRANCH_ALIAS` |
| 私银成表母版 | 就是官方原件转的 xlsx（`pbs_base.xlsx` / `pbs_dev_base.xlsx`），**别重新排**，见 8.10 |
| 私银红绿规则 | `report.py::_pbs_fill_dev` 的 `paint()`（按名次，C 列只红+黄、E 列红+绿）；核心指标表用母版条件格式 |
| 私银的产品销售初值 | 页面上改并保存，或直接写 `setting.pbs_sales`（`{支行: {7 个键}}`） |
| 私银成表列布局 | 换 `src/report/assets/pbs_base.xlsx` / `pbs_dev_base.xlsx`，改完同步 `_pbs_fill_report` 里的 `COLS/KEY_OF_COL` 列号 |
| 带数据升级 | `update.sh <包> --with-data`（调 `scripts/merge_seed.py`，只补缺不覆盖） |
| 经理队伍的列映射 | `src/ingest/team.py` 的 `CK_COLS`/`YW_COLS`/`CHECK`（改完跑一遍导入验证表头） |
| 经理队伍成表版式 | 重跑 `python scripts/build_team_bases.py`（不要手改母版 xlsx） |
| 一份通报多个成表 | `report.BASES_OF` 登记母版 key + builder 里给 `downloads`，前端自动渲染按钮（8.13-90） |
| 使用指南的正文 | `src/web/assets/js/guide-content.js`（纯数据；`body` 只许 p/ul/ol/li/b/code/kbd/table 等白名单标签） |
| 更新日志 | `src/web/assets/js/changelog.js`（发版往最前面插一条，版本号与 `VERSION` 一致）；页面在 `pages/guide.js` 的 `changelogPage` |
| 版本号 | 仓库根 `VERSION`；打包时写 `BUILD`（日期-git短sha） |
| 版本号怎么定 | `0.x`=重大重构/整体重写/需数天；`0.x.x`=新增模块或功能；`0.x.x.x`=小 bug 修复与体验优化（几分钟到一两小时） |

---

## 11. 交接检查清单

1. `git log --oneline -5` 能看到最近一次提交；`cat VERSION` 应为 `0.1.7.1` 或更高
2. 起服务 → `curl /api/health` 返回 `ok:true`，且 `version` 与 `VERSION` 一致
   （版本号有缓存：改完 `VERSION` 要**重启进程**才生效）
3. `python scripts/check_report_parity.py` → 除 online 标题外全 OK
   `python scripts/migrate_to_sqlite.py --db-info` → 13 条数据线、最新 2026-10-25、schema v1
4. 打开 `#/`、`#/p/jg`、`#/m/jg-deposit-time`、`#/m/jg-deposit-jiangji` 各看一眼
   （顶栏"数据截至"应分别是 10/22、10/22、10/15、9/13）
5. `#/report` 应弹口令框；输 `gejin2026` 只看到「定期存款增长 / 薪管家 / 降级挽回营销先锋」三项；
   刷新页面应重新要口令
6. `#/upload` 输 `wangjin2026` 后网金可选、其余灰掉；从 `#/m/wj-wallet` 点右上角"导入数据"应预选到「数币钱包」
7. `python scripts/selftest.py --root data` → OK；`python scripts/check_modules.py` → OK；
   打包前 `python scripts/package_release.py --seed` 能从干净提交出包
8. 打开 `#/guide` 能看到 20 节（含「一卡一户」「经理队伍」）；从 `#/m/jg-deposit-time` 点右上角「使用指南」
   应直接落到「定期存款」那一节；`#/changelog` 是独立一页，左上角两个页签能互切
9. `python scripts/check_report_parity.py` 里 yika 应 OK（三 sheet 零差异）；
   打开 `#/m/jg-customer-yika` 能看到 6 张数字卡、3 张图和两张表
10. 私银：`#/m/pbs-cust` 应显示 252 户 / 26.97 亿 / 40 网点；`#/report` 里「私人银行核心指标」
    有**两个下载按钮**（下载 Excel / 下载发展情况表），两份都应是真正的 xlsx（不是 zip）。
    核心指标页与 `D:\资料\ICBC\20261028私银\阜阳分行私人银行业务通报（2026.1024）.xls`
    定稿页 **13 列逐格一致**（合计 9989 / 160 / 1531 / 3900 / 320 / 3900 / 423）；
    发展情况页只允许 1 处差异（师范大学支行上年末，成表人工填 1、源表 0）
11. `#/m/jg-deposit-jiepan` → 默认显示「上周」（本例 10.19–10.25，未承接 -5351.86 万）；
    改区间到 10.01–10.25 后应为 -19488.54 万（原始表口径）；
    改到 9.01 之前应提示"超出这份数据的取数范围"。
    `#/report` 里「到期承接情况通报」文案三段与导出 Excel 双 sheet 都要有
12. 导入页选「定期承接」→ 出现「④ 手动编辑明细（可选）」；输客编能查到行、能改四列，
    改完提交时 `notes` 里应出现「导入前手工修改 N 行」；
13. `#/report` 里「私人银行核心指标」旁边点「下载发展情况表」→ 用解压工具看 xlsx 里
    应有 `xl/media/image1.jpeg`（**内网机同理，这是 0.1.7.1 修的那个坑**）；
14. `#/m/jg-deposit-team` 能看到「财客 / 远维」两个页签，**来回点四次都要能切**；
    财客 3 张图（含网点头尾）、远维 2 张；红绿按名次（前二红后二绿）。
    `#/report` 里是**一条**「客户经理经营业绩」：文案一整篇，导出两个按钮
    （「下载 财客 Excel（10.21）」「下载 远维 Excel（10.21）」），两份 Excel 都能下
15. 打开任意页，左侧栏应显示工商银行 logo + 「工商银行阜阳分行 / 经营驾驶舱」；
   浏览器标签标题形如「定期存款 · 阜阳分行经营驾驶舱」；`/assets/img/logo.png` 返回 200
16. 改动前先读本文件第 8 节（坑）与第 9 节（现状/待办）；`docs/archive/` 是过时规划，不要作为依据

> 约定：所有数据数字以"正式通报成表"为准；页面/图片/Excel 三处必须同源同值；改完必跑对账。
