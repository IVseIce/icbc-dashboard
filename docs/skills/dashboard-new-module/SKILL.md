---
name: dashboard-new-module
description: 在「阜阳分行个人金融经营驾驶舱」里新增或修改一个业务模块的完整流程：确认数据源与口径 → 目录登记 → 导入解析 → 视图模型 → 页面 → 通报（含 Excel）→ 模块文档 → 自检打包。适用于从主会话 fork 出来的专项会话，按本文件就能做完，不需要主会话上下文。
whenToUse: 用户要求「新增一个模块 / 加一条线 / 把某个 Excel 做成页面 / 加一份通报 / 改现有模块的口径或页面」，或提到 `/dashboard-new-module` 时。也用于「这个模块哪里漏了」的排查——先跑第 6 节的 check_modules.py。
---

# 驾驶舱：新增 / 修改模块

**核心原则：所有数字都在快照里，页面、图片、Excel 三处同源同值。**
不要手算、不要在页面里重算、不要改硬盘上的 json（数据现在在 SQLite）。

仓库：`/home/isee/projects/icbc-dashboard`
先读：`docs/HANDOFF.md` 第 4/5/7/8 节、`docs/MODULES.md`（模块总表）、`docs/modules/`（已有模块的范例）。

---

## 1 开工前必须问清楚（缺一项就先问，别猜）

| 项 | 说明 |
|---|---|
| 模块名 / 所属板块 | 七大板块之一：个金 `jg` / 网金 `wj` / 个贷 `loan` / 银行卡 `card` / 私银 `pbs` / 实用工具 `tool` / 重点项目 `project` |
| 源数据 | 一份真实文件（或样例）+ 是日报/月报/周报；多份源表要说明各自角色 |
| 口径 | 每个指标：分子、分母、单位（万元/户/％）、比率是小数还是百分数、保留几位 |
| 粒度 | 支行（8 家）还是网点（约 40 个）；是否要同时给合计行 |
| 时点规则 | 用哪一列/哪个 sheet 定 `as_of`；"取该日之前最近一期"是否适用 |
| 是否出通报 | 要的话：标题格式、支行表 / 网点表、是否需要红绿标注、Excel 母版从哪来 |
| 页面要素 | KPI 卡要看哪几个数、趋势、排行、明细表 |

不确定的口径**必须回问**。历史上大多数返工都来自"想当然的口径"。

---

## 2 接线七步

### ① 目录登记 `src/domain/catalog.py`

在对应板块的分组里加一条：

```python
{'id': 'wj-xxx', 'name': '模块名', 'page': 'xxx', 'kind': 'metric',
 'source': '源表名', 'level': '网点', 'freq': '日', 'as_line': 'xxx',
 'group': '线上服务', 'desc': '一句话说明'}
```

- `kind`：`metric`（有数据）/ `tool`（工具，无数据）/ `placeholder`、`planned`（占位）
- `page`：前端渲染器名，必须存在 `src/web/assets/js/pages/<page>.js`
- `as_line`：条线 id，必须同时出现在 `viz.IMPORTERS` 和 `api.LINE_OF`
- `group` 必须与本条所在分组的名字一致（check_modules 会校验）

### ② 导入解析 `src/viz.py`（+ `src/ingest/` 或 `src/parsers/`）

写 `def import_xxx(files, line, root, data_date=None) -> (as_of, snap)`，然后登记：

```python
IMPORTERS = {..., 'xxx': import_xxx}
```

- 需要"按列名取值、缺列跳过"的表格解析，放 `src/ingest/xxx.py`
- 需要复用 `icbc-*` 技能时走 `viz.skill('icbc-xxx')`（返回的模块带 classify/compute）
- **返回的 snap 必须包含**：`as_of`、`as_of_cn`、`_files`、`_notes`；比率统一 `round(x, 6)` 存**小数**
- 不要在 importer 里直接写库：`do_import` 会调 `save_snapshot`

### ③ 存储

99% 的模块**不用改** `src/store.py`——快照是文档，结构自由。
只有需要按指标做 SQL 聚合时才加表：改 `SCHEMA_VERSION` + 在 `init()` 补升级分支（HANDOFF 4.1）。

### ④ 视图模型 `src/server/api.py`

```python
def build_xxx(on=None):
    s = _latest('xxx', on)
    if not s:
        return _no_data('xxx', on)
    return {'ok': True, 'as_of': s['as_of'], 'kpi': {...}, 'branches': [...], 'nets': [...], 'trend': [...]}
```

登记三处：`BUILDERS`、`LINE_OF`，并在 `build_overview()` 里加一行（首页卡片要用）。
**这一层只做取数与派生，不排版**；趋势用 `_upto(line, on)`。

### ⑤ 页面 `src/web/assets/js/pages/<page>.js`

照 `pages/wallet.js` 这类现成页面的默认导出结构写：`{ id, render(view, data, ctx) }`，
用 `charts.js` 的 `barRank / splitRank / bigTable` 出图，用 `ui.js` 的 `fmt / table / drawer`。
若页面名是新的，还要在 `app.js` 的 `RENDERERS` 注册。

### ⑥ 通报（可选）`src/server/report.py` + `src/web/assets/js/pages/report.js`

1. 写 `build_xxx(on)`（返回 `title/as_of/tables/text`）和 `xxx_xlsx(on)`
2. 母版：**必须用"正式成表清空数据"** 的 xlsx，放 `src/report/assets/xxx_base.xlsx`（HANDOFF 8.1-1）
3. 登记 `BUILDERS`、`XLSX`、`CAT_OF`（大类，决定哪个口令能看）
4. `report.js` 的 `LINES` 加一条 `{ id: 'xxx', name: '…', cat: 'wj' }`
5. 行序与补 0 按母版行名来；合计行取源表合计，不要自己平均

### ⑦ 模块文档 `docs/modules/<模块id>.md`

**这是交回主会话的凭据**，模板见 `templates.md`。必填：数据源、字段映射、口径、as_of 规则、
页面入口、通报对应、已知坑、改这个模块时先看什么。

---

## 3 硬规则（违反会导致返工或线上出错）

1. **数字只能来自快照**：页面与 Excel 都读同一份 snapshot；不要在 JS 里重算比率
2. 比率存**小数**（0.5578），6 位精度；显示层再乘 100
3. **网点/支行行序按母版或固定列表**，缺的补 0，不许过滤（HANDOFF 8.1-2/4）
4. 网点名归一：精确 → 去"阜阳" → 后缀唯一匹配（`report._match`）
5. 导入失败要写台账（`do_import` 已处理），不要静默吞异常
6. 前端：**不要用 `inset` 简写**，浮层用 `top/right/bottom/left`；浮层可见性别依赖 `requestAnimationFrame`
7. 保持 **Python 3.8 兼容**（目标机回退路径）：别用 `match`、`str.removeprefix`、`zoneinfo`（已有垫片）
8. 不要在业务代码里直接写文件/写库；一律 `viz.save_snapshot` / `store.*`
9. 新增通报/模块必须挂大类，否则某些口令下永远看不到
10. 改完必须提交，并让版本号 +1（`VERSION`，语义化）

---

## 4 验收（四条命令，缺一不可）

```bash
cd /home/isee/projects/icbc-dashboard
python scripts/check_modules.py --write      # 接线自检 + 重写 docs/MODULES.md
python scripts/selftest.py --root data       # 解释器/依赖/库
python scripts/check_report_parity.py        # 有通报时必跑，除 online 标题外应全 OK
python -m py_compile src/viz.py src/server/api.py src/server/report.py
node --input-type=module --check < src/web/assets/js/pages/<page>.js
```

再手动看一眼：`#/m/<模块id>`、`#/report/<kind>`（如果做了通报）、导入页能选到该模块。

---

## 5 交回主会话

完成后按这个结构输出（**必须包含**，主会话可能只看到这一段）：

```
模块：<名称>（<id>）  板块：<板块>  版本：<VERSION>
已接入：导入 ✅ 页面 ✅ 通报 ✅/—  Excel ✅/—
数据源：<源表>   粒度：<支行/网点>   最新：<as_of>
改了：<文件列表>
文档：docs/modules/<id>.md
自检：check_modules OK / parity OK
已知限制：<一句话>
```

并确保已经 `git commit`（消息形如 `feat(<板块>): 新增 <模块>`），这样主会话和后来者都能从
`docs/MODULES.md` + `docs/modules/<id>.md` + `git log` 还原全部必要信息。

---

## 6 出问题时

```bash
python scripts/check_modules.py     # 先看"谁跟谁没对上"
python scripts/migrate_to_sqlite.py --db-info   # 数据在不在
sqlite3 data/icbc.db "select line,as_of,rows from snapshot where line='<line>' order by as_of desc limit 3"
```

- 页面空白 → 看 `#/m/<id>` 的 kind 与 page，`RENDERERS` 是否注册
- 导入报错 → 看 `/api/import` 返回的 `error`/`trace`，多半是源表列名或 sheet 名变了
- 通报对不上 → `check_report_parity.py` 会指到具体单元格，按 HANDOFF 8.1 的顺序查

更完整的坑清单在 `docs/HANDOFF.md` 第 8 节，**改之前先扫一眼**。
