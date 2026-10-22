# parsers/ —— 五个条线的解析器（随项目打包）

来源：`~/.dsh/skills/icbc-{sbqb,xgj,dqzz,xsfw,qwsq}` 的**原样拷贝**（含 assets：
网点号对照表 netno.xls、空白通报模板 template.xlsx 等）。

- 项目只调用其中的**纯解析函数**（`classify / compute / read_tables / resolve_tables / aggregate`），
  不触发取信/回信逻辑；`viz.py` 的 `SKILLS` 指向本目录，找不到时才回退到 `~/.dsh/skills`。
- 同步方式：上游技能改动后，重新覆盖对应目录即可，不需要改本项目代码；
  升级后跑一遍 `python -m server.smoke`（或页面导一次样例表）确认四个条线都能出数。
- 依赖：`openpyxl`、`xlrd`（读 .xls）、`PyYAML`（技能内部读配置用）。
