# 模板与骨架

复制后按实际情况改，**不要**留下示例字符串。

---

## A. 模块文档 `docs/modules/<模块id>.md`

```markdown
# <模块名>（<模块id>）

| 项 | 值 |
|---|---|
| 板块 / 分组 | 网络金融 / 数币钱包 |
| 类型 | 数据模块（metric） |
| 数据源 | 数币开立明细（《数币数据》xlsx，含 网点号/钱包等级/注册日期） |
| 粒度 | 网点（40 个），支行由网点汇总 |
| 频率 | 日 |
| as_of | 明细表里最新 `注册日期` 的次日 / 源表日期列 |
| 导入 | `viz.import_sbqb` → `IMPORTERS['sbqb']` |
| 视图 | `api.build_wallet` → `BUILDERS['wallet']` / `LINE_OF['wallet']='sbqb'` |
| 页面 | `pages/wallet.js`，路由 `#/m/wj-wallet` |
| 通报 | `report.build_wallet` / `wallet_xlsx`，`CAT_OF['wallet']='wj'`，母版 `wallet_base.xlsx` |
| 口令可见 | 网金口令、管理员 |

## 字段映射

| 源表列 | 快照字段 | 说明 |
|---|---|---|
| 网点号 | `nets[].netno` | 前 6 位定支行 |
| … | … | … |

## 口径

- 累计开立 = 明细去重后的钱包数；当月/当日 = 按注册日期落在区间内
- 比率一律小数、6 位（`round(x, 6)`）

## 已知坑

- 网点名在快照里是短名（无"阜阳"），报表里要归一
- 明细表偶尔缺网点号，落到"未知"

## 改这个模块时先看

1. `src/viz.py::import_sbqb`
2. `src/report/assets/wallet_base.xlsx` 的 A 列合并单元格
3. `scripts/check_report_parity.py` 里 wallet 的用例
```

---

## B. 导入解析（`src/viz.py`）

```python
def import_xxx(files, line, root, data_date=None):
    """<一句话说明源表与口径>。"""
    from ingest import readers          # 需要读 Excel/CSV 时
    rows = []
    for name, blob in files:
        for title, table in readers.sheets(blob, name):
            rows.extend(table)

    snap = {
        'as_of': data_date or <推导出的日期>,
        'as_of_cn': ...,
        'nets': [...],                  # 网点明细（或 branches）
        'totals': {...},
        '_files': [{'name': n, 'role': '明细'} for n, _ in files],
        '_notes': [f'{len(rows)} 行'],
    }
    return snap['as_of'], snap

IMPORTERS = {..., 'xxx': import_xxx}
```

要点：`as_of` 与 `snap['as_of']` 一致；比率 `round(x, 6)`；不要 `print`。

---

## C. 视图模型（`src/server/api.py`）

```python
def build_xxx(on: str | None = None) -> dict:
    s = _latest('xxx', on)
    if not s:
        return _no_data('xxx', on)
    nets = s.get('nets') or []
    trend = [{'d': x['as_of'], 'v': (x.get('total') or 0)}
             for x in _upto('xxx', on) if x.get('total') is not None]
    return {
        'ok': True, 'as_of': s['as_of'],
        'kpi': {'total': s.get('total'), 'nets': len(nets)},
        'branches': sorted(s.get('branches') or [], key=lambda b: -(b.get('total') or 0)),
        'nets': sorted(nets, key=lambda n: -(n['total'] or 0)),
        'trend': trend,
    }

BUILDERS = {..., 'xxx': build_xxx}
LINE_OF = {..., 'xxx': 'xxx'}
```

`build_overview()` 里补一行（首页要用）：

```python
'xxx': {'ok': d.get('ok'), 'as_of': d.get('as_of'), 'kpi': d.get('kpi'),
        'spark': (d.get('trend') or [])[-12:]},
```

---

## D. 页面（`src/web/assets/js/pages/<page>.js`）

```js
/* <模块名>：<一句话> */
import { fmt, countUp, icon } from '../ui.js';
import { barRank, splitRank, bigTable, C } from '../charts.js';

export default {
  id: 'xxx',
  render(view, data, ctx) {
    const d = data.xxx;                       // 来自 /api/all 的 key
    if (!d?.ok) {
      view.innerHTML = `<div class="card"><div class="empty"><b>暂无数据</b>
        在「导入数据」里选 <b><模块名></b> 上传源表</div></div>`;
      return;
    }
    const k = d.kpi;
    view.innerHTML = `
      <div class="page-head">
        <div><h1><模块名></h1><p>${fmt.date(d.as_of)} · ${k.nets} 个网点</p></div>
        <div class="spacer"></div>
        <span class="chip">${d.nets.length} 条明细</span>
      </div>
      <div class="grid g4">…KPI 卡…</div>
      <div class="card" style="margin-top:14px">
        <div class="card-head"><h3>明细</h3></div>
        <div id="chart"></div>
      </div>`;
    barRank(view.querySelector('#chart'), d.nets, { name: 'name', value: 'total', unit: '户' });
    view.querySelectorAll('[data-count]').forEach((el) =>
      countUp(el, Number(el.dataset.count), { decimals: Number(el.dataset.dec || 0) }));
  },
};
```

新页面还要在 `app.js` 顶部 `import` 并注册：

```js
import xxx from './pages/xxx.js';
const RENDERERS = { ..., xxx };
```

---

## E. 通报（`src/server/report.py`）

```python
def build_xxx(on: str | None = None) -> dict:
    d = api.build_xxx(on)
    if not d.get('ok'):
        return {'ok': False, 'error': '该日期没有数据'}
    rows = [...]
    return {'ok': True, 'kind': 'xxx', 'title': f'…（{d["as_of"]}）', 'as_of': d['as_of'],
            'prev_as_of': d.get('prev_as_of'),
            'tables': [{'name': '支行', 'columns': [...], 'rows': rows, 'totals': {...}}],
            'text': '……'}

def xxx_xlsx(on: str | None = None) -> tuple[bytes, str]:
    import openpyxl, io
    d = build_xxx(on)
    wb = openpyxl.load_workbook(BASE / 'xxx_base.xlsx')
    ws = wb.active
    ws['A1'] = d['title']
    for r, rec in enumerate(d['tables'][0]['rows'], start=<母版起始行>):
        ws.cell(row=r, column=1).value = rec['name']
        ws.cell(row=r, column=2).value = rec['value']
        ws.cell(row=r, column=2).number_format = '#,##0'
    buf = io.BytesIO(); wb.save(buf)
    return buf.getvalue(), f'<文件名>.xlsx'

BUILDERS = {..., 'xxx': build_xxx}
XLSX = {..., 'xxx': xxx_xlsx}
CAT_OF = {..., 'xxx': 'wj'}
```

`report.js`：

```js
const LINES = [
  ...,
  { id: 'xxx', name: '<显示名>', cat: 'wj' },
];
```

---

## F. 自检命令

```bash
python scripts/check_modules.py --write
python scripts/selftest.py --root data
python scripts/check_report_parity.py
```
