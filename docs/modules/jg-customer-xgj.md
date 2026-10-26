# 薪管家（jg-customer-xgj）

| 项 | 值 |
|---|---|
| 板块 / 分组 | 个人金融 / 增客 |
| 类型 | 数据模块（metric） |
| 数据源 | 工银薪管家增量表 ×4：支行·全年、支行·当月、网点·全年、网点·当月（xlsx） |
| 粒度 | 支行（12 行含合计）+ 网点（40 个） |
| 频率 | 日 |
| as_of | 导入时传入的 `data_date`；不传则取"昨天" |
| 导入 | `viz.import_xgj` → `IMPORTERS['xgj']` |
| 视图 | `api.build_salary` → `BUILDERS['salary']`、`LINE_OF['salary']='xgj'` |
| 页面 | `pages/salary.js`，路由 `#/m/jg-customer-xgj` |
| 通报 | `report.build_salary` / `salary_xlsx`；`CAT_OF['salary']='jg'`；母版 `salary_base.xlsx`（支行/网点双 sheet） |
| 口令可见 | 个金口令、管理员 |

## 字段映射

| 源表位置 | 快照字段 | 说明 |
|---|---|---|
| 增量表 `K` 列 | `year` / `month` | 薪酬代发金额（万元）；按表是"年"还是"月"累加到对应字段 |
| 增量表 `F` 列 | `ent_year` / `ent_month` | 有效使用企业数（户），取整 |
| sheet 名 / 表头 | `period` | 决定这份表进 `year` 还是 `month` |

## 口径

- 全年 = 四张表里 `period='年'` 的两张求和；当月 = `period='月'` 的两张求和
- 支行名会去掉"阜阳"与"支行"后缀；网点名保留原样
- `虚拟`、`电话银行` 这类非实体网点在导入时被剔除
- 报表行序以**母版行名**为准，缺的补 0（导入时会把 0 网点过滤掉，不能直接用快照列表）

## 已知坑

1. **0 网点被过滤**：`import_xgj` 只保留有数据的网点，所以报表必须按模板行名补齐，否则少行/错位
2. 网点是 **4..43 行（含 43）**，支行是 4..11、合计第 12 行；早期写成 `range(4, 43)` 漏了最后一个
3. 母版字体是 **仿宋_GB2312**，不能拿空白模板顶替（会变宋体）
4. 金额保留 2 位小数，比率不要二次四舍五入（对账会挂）

## 改这个模块时先看

1. `src/viz.py::import_xgj`（列名与周期判断）
2. `src/server/report.py::salary_xlsx`（行区间 4..11 / 4..43）
3. `src/report/assets/salary_base.xlsx`
4. `scripts/check_report_parity.py` 里 salary 的用例（2026-10-21）
