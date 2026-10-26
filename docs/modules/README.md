# 模块文档（每个模块一份）

一个模块一份 `<模块id>.md`，写清楚**数据源、字段映射、口径、as_of 规则、页面/通报入口、已知坑**。
它是「主会话 / 后来的接手者」了解某个模块的唯一入口，也是新增模块时的验收项。

- 目录总表由 `python scripts/check_modules.py --write` 生成到 `docs/MODULES.md`
- 模板见 `docs/skills/dashboard-new-module/templates.md` 的 A 节
- 范例：`jg-customer-xgj.md`（薪管家：双 sheet 通报 + 0 网点补位）

没写文档的模块在 `MODULES.md` 里显示 `—`，`check_modules.py` 会给出提示但不算错误。
