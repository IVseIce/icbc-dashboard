# 阜阳分行 · 个人金融经营驾驶舱（v2）

> v1（单文件 HTML，`legacy/` 里保留）→ v2：SPA 多页 + ECharts + 导入服务。
> 目标：**好看**（现代、克制、有动效）、**好用**（总览 → 下钻）、**好改**（三层解耦，加条线只动三个地方）。

## 跑起来

```bash
python run.py                              # 默认 127.0.0.1:8766
python run.py --host 0.0.0.0 --port 8766   # 局域网可访问
# 打开 http://127.0.0.1:8766/
```

依赖只有 `openpyxl` / `xlrd`（见 `requirements.txt`），其余全部标准库。

```
icbc-dashboard/
├─ src/                  全部代码
│  ├─ server/            HTTP + API（app.py / api.py）
│  ├─ viz.py             数据层：导入适配器、快照、台账
│  ├─ parsers/           五个 icbc-* 解析器（已内置，不依赖外部技能目录）
│  └─ web/               前端（index.html / assets / vendor/echarts）
├─ data/                 运行时数据（.gitignore 已排除）
│  ├─ imports/<条线>/<时间戳>/     每次导入的原件
│  ├─ snapshots/<条线>/<日期>.json 归一化后的每期数据
│  └─ ledger.jsonl                 导入台账
├─ scripts/bootstrap.py  一次性把历史 automations 灌进来
├─ legacy/               v1 存档（build_v1.py + 旧页面）
├─ docs/screenshots/     页面截图
├─ run.py                启动入口
├─ requirements.txt
└─ .gitignore
```

数据根目录默认 `./data`，可用 `--root` 指向别处（例如把数据放到独立磁盘）。

## v3 进展（M1 已完成）

- 六大板块目录：`src/domain/catalog.py`（导航/首页/上传/路由的唯一来源）
- 首页按板块聚合，个金拆增存/增客/增收/增贷，网金含线上服务/数币/企微，重点项目单列
- 全局日期选择：`/api/all?date=YYYY-MM-DD`，语义为「取该日期之前最近一期」
- 未接入模块统一占位页（来源/颗粒度/频率一目了然）
- 旧 5 个模块页已挂到新导航下（`#/m/<moduleId>`）

## v3 · M2 进展

- **代发明细**已接入：`src/ingest/payroll.py`（9 期月度 → 网点维度快照 `data/snapshots/dfmx/`）
- 新增模块页 `#/m/jg-customer-pay`：客户/企业/当月与全年代发/新增/流失预警 + 月度走势 + 分层 + 网点与支行排行
- 金额用「全年代发金额」年累计，月度值 = 相邻两期相减（跨年重置）
- 导航新增「总览」入口

## v3 · M2 进展（续）

- **五卡唤醒**已接入：`src/ingest/fivecards.py`（支行维度，5 卡 × 各指标）
- 页面 `#/m/jg-customer-card`，重点项目「五卡唤醒方案」共用同一份数据
- 长尾率、未激活/未缴存/睡眠、未交易等口径按源表列名自适应（信用卡无长尾列则显示 —）

## v3 · M2 进展（通报中心）

- 通报中心先做「网点线上服务能力」：表格（40 网点 + 合计）+ 文案自动生成 + 复制 + 下载 Excel + 打印/存 PDF
- 接口：`GET /api/report/online?date=`、`GET /api/report/online.xlsx?date=`
- 顶栏新增「日 / 月」切换：选月时取该月内最新一期

## 通报中心（v2）

- Excel 导出改为**套用技能模板**：版式、列宽、合并表头、数字格式与正式通报一致
- 每列**前 5 名标红、后 5 名标绿**（与定稿同规则），网页与 Excel 同步
- 页面布局：页签 + 操作按钮置顶，文案卡片在表格之上
- 接口：`/api/report/online?date=`、`/api/report/online.xlsx?date=`

## 多格式读取（src/ingest/readers.py）

- 按**文件内容**判断真实格式（zip→xlsx、OLE→xls、否则文本），不信任扩展名
- 导入时自动纠正扩展名：`CSV 存成 .xlsx` → 按 .csv 识别；`xlsx 存成 .csv` → 按 .xlsx 识别
- 仍认不出时兜底：把文本内容转成真正的 xlsx 再试一次
- 给解析器用：`read_table()` / `sheets()` 统一返回二维表 / [(sheet, rows)]，xlsx、xls、csv 同码
- 已接入：上传导入链路、代发明细、五卡汇总；其余模块可逐步切换

## 上传（两级选择）

- `#/upload`：先选**专业/大类**，再选**模块**（只有配了 `as_line` 的模块可上传，其余灰显“暂不支持”）
- 提交后走 `/api/import`：按模块口径识别角色 → 归档 → 落快照 → 回写台账
- 新增可上传模块 = catalog 里给该模块加 `as_line` + 在 `viz.IMPORTERS` 注册解析器
- 代发明细、五卡唤醒已接入上传（代发按多 sheet 逐月入库；五卡日期取“日期”或文件名）

## 页面逻辑

| 路由 | 页面 | 说明 |
|---|---|---|
| `#/` | 总览 | 定期存款、网点线上服务两大重点卡（含量/mini 图），数币/薪管家/企微三张小卡，数据时点 |
| `#/deposit` | 定期存款 ★ | KPI → 支行余额×增幅双轴 → 余额结构环形 → 增量排名（红正绿负）→ 支行卡片（点开抽屉）→ 明细表 |
| `#/online` | 网点线上服务 ★ | 6 KPI → 动户率分布 → 八支行雷达 → 动户率×签约率散点 → 网点排行 → 可按支行筛选的明细 |
| `#/wallet` | 数字人民币 | 累计走势、等级结构、网点 Top12、当日零新增清单 |
| `#/salary` | 薪管家 | 累计代发走势、支行排行、有报数网点明细 |
| `#/community` | 企微社群 | 群/客户/交互 + 周环比、熟识率双轴、网点明细 |
| `#/import` | 数据导入 | 选大类 → 拖文件 → 识别归属 → 归档重算 → 跳转该条线 |

交互：侧栏切换、卡片点击下钻、表头排序、网点行点开抽屉、导入后自动刷新。

## 交互细节

- **头尾排行**：网点多的图（线上服务、数币）用 `splitRank()` 只画前 N + 后 N，中间折叠成 `⋯ 中间 N 个 ⋯`；
  前排实色、后排淡色，一眼看清“谁在领跑、谁在拖后”。
- **全屏大表**：每个条线底部的明细表点「全屏」，弹出无内滚的大表（自动 2–3 栏排版），支持搜索与点表头排序。
- 表格行可点开右侧抽屉看单点详情；导入成功后自动刷新并可一键跳到该条线。

## 三层架构（为了以后好改）

```
server/app.py      HTTP：静态资源 + /api/all + /api/line/<id> + /api/import
server/api.py      视图模型：每个条线一个 build_xxx()，只做取数+派生，不碰样式
viz.py             数据层：导入适配器、快照、台账（解析逻辑见 parsers/）
parsers/           五个 icbc-* 技能的解析代码已随项目打包（不再依赖 ~/.dsh/skills）
web/assets/js/     SPA：app.js 壳 + pages/*.js 页面 + charts.js 图型 + ui.js 组件
web/assets/css/    app.css：全部设计变量在 :root，配色/圆角/阴影改一处即可
web/vendor/        echarts.min.js（本地内置，内网/断网可用）
```

`viz.SKILLS` 默认指向项目内 `parsers/`，找不到时才回退 `~/.dsh/skills`；部署时只拷这个目录即可。

### 加一个新条线要动哪三处

1. `server/api.py`：写 `build_xxx()`，返回扁平结构，登记进 `BUILDERS`；
2. `web/assets/js/pages/xxx.js`：`export default { id, title, nav, icon, render(view,data) }`；
3. `web/assets/js/app.js`：`import` 后加进 `PAGES`（导航自动出现）。

要接新的源表格式，只在 `viz.py` 里加一个 `import_xxx()` 并登记到 `IMPORTERS`/`LINES`，页面层不用动。

### 常用调整点

| 想改 | 改哪里 |
|---|---|
| 主色/圆角/阴影/间距 | `web/assets/css/app.css` 的 `:root` |
| 图表配色 | `web/assets/js/charts.js` 的 `PALETTE` 与 `C` |
| 某个图换成别的形式 | 对应 `pages/*.js` 里换成 `charts.js` 的另一个图型 |
| 加一列数据 | `server/api.py` 里加字段 + 页面表格列配置加一项 |
| 首页重点卡顺序 | `server/api.py` 的 `build_overview()['priority']` |

## 数据放哪里（代码 vs 数据）

工程惯例是**代码与数据分离**：代码可整体替换/回滚，数据要单独备份、单独扩容、通常不进版本库。
三种典型布局：

| 布局 | 形态 | 适用 | 风险 |
|---|---|---|---|
| 包含其中 | `project/data/`（.gitignore） | 单机、演示、便携 | 部署/回滚容易误伤数据；多人不能共享 |
| **并列同级（推荐）** | `apps\viz\` + `data\viz\` + `config\viz.yaml` | 一台服务器长期跑 | 需要 `--root` 指对路径 |
| 独立服务 | Postgres / MinIO / 对象存储 | 多实例、要审计/并发 | 运维成本高 |

本项目已经支持并列：`python server/app.py --root D:\资料\ICBC\Visualizations`。
若想“一个文件夹全带走”，把 `--root` 指向项目内 `data\` 即可，代码不用改。

## 部署到服务器

- 无第三方 Python 依赖（openpyxl / xlrd 除外），`server/app.py` 可直接起；
- 前端是纯静态资源，将来换 Nginx + 反向代理 `/api` 也不用改代码；
- `serve_static` 目前由 app.py 代劳，QPS 上去后建议前置 Nginx；
- 若换机器：把 `viz.SKILLS` 指向随包携带的 5 个 `icbc-*` 目录即可（解析逻辑在那边）。

## 代码与数据放哪

当前采用 **src/ + data/ 同仓布局**（Python 项目的 src layout 变体）：

- 代码全在 `src/`，可整体替换升级；
- 数据在 `data/`，已在 `.gitignore` 中排除，只增不改、可单独备份；
- 数据根可配置（`--root`），将来要迁到独立磁盘或 docker volume，不用改代码。

约定：**升级只替换 `src/`、`run.py`，绝不动 `data/`**；备份只备 `data/`。

## 已知取舍

- 数币/薪管家/企微目前只有「最新一期 + 历史快照」两种粒度，没有网点级历史，后续可加；
- 定期存款 `trend` 依赖多期导入，只有一期时不画趋势；
- 企微「上周」基准取最接近「本周 −7 天」的备份，与正式通报口径一致。
