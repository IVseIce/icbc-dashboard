# legacy/ —— v1 存档（不再维护）

这里是 2026-10-21 的第一版：单文件 HTML 驾驶舱 + 对应的生成脚本。

- `驾驶舱_v1_20261021.html`：v1 成品（五个条线一张长页，纯 SVG 图表）
- `build_v1.py`：v1 的生成脚本（读 `data/data/dashboard_data.json`，输出单文件 HTML）
- `serve.py`：v1 的静态 + 导入服务（端口 8765）
- `assets/`：v1 的兜底数据

**不要用它跑生产、不要据此判断现状**。v1 的数据契约与 v3 不同（v3 走 `/api/all` 视图模型），
现役代码在 `src/`，说明见根目录 `README.md` 与 `../docs/HANDOFF.md`。

保留原因：作为"最初长什么样"的参照；如需对比历史版式可以打开 HTML 直接看。
