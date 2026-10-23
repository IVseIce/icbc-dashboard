# parsers/ —— 五个条线的解析器（随项目打包）

来源：`~/.dsh/skills/icbc-{sbqb,xgj,dqzz,xsfw,qwsq}` 的**原样拷贝**（含 assets：
网点号对照表 netno.xls、空白通报模板 template.xlsx 等）。

- 项目只调用其中的**纯解析函数**（`classify / compute / read_tables / resolve_tables / aggregate`），
  不触发取信/回信逻辑；`viz.py` 的 `SKILLS` 指向本目录，找不到时才回退到 `~/.dsh/skills`。
- 同步方式：上游技能改动后，重新覆盖对应目录即可，不需要改本项目代码；
  升级后在页面上各导一次样例表，或跑 `python scripts/check_report_parity.py` 确认输出未变。
- 各子目录里的 `SKILL.md` 是**上游技能的说明**（含取信/回信流程），本项目只调用纯解析函数，
  其中的邮件流程、路径约定对本项目不适用，不要照做。
- 依赖：`openpyxl`、`xlrd`（读 .xls）、`PyYAML`（技能内部读配置用）。
