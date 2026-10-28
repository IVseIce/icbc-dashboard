# 模块清单

> 由 `python scripts/check_modules.py --write` 自动生成，**不要手改**。
> 每个模块的细节（口径/字段/坑）写在 `docs/modules/<模块id>.md`。

## 板块

| 板块 | id | 模块 | 已接入 | 说明 |
|---|---|---|---|---|
| 个人金融 | `jg` | 12 | 6 | 增存 · 增客 · 增收 |
| 网络金融 | `wj` | 3 | 3 | 线上服务 · 数币 · 企微 |
| 个人贷款 | `loan` | 1 | 0 | 框架预留，待接入 |
| 银行卡 | `card` | 1 | 0 | 框架预留，待接入 |
| 私人银行 | `pbs` | 1 | 1 | 达标客户 · 资产规模 · 产品销售 |
| 实用工具 | `tool` | 2 | 0 | 常用小工具 |
| 重点项目 | `project` | 5 | 2 | 方案推进与专项攻坚 |

## 模块

| 板块 | 分组 | 模块 | id | 类型 | 页面 | 导入条线 | 文档 |
|---|---|---|---|---|---|---|---|
| 个金 | 增存 | 定期存款 | `jg-deposit-time` | metric | deposit | dqzz | — |
| 个金 | 增存 | 定期承接 | `jg-deposit-jiepan` | placeholder | — | — | — |
| 个金 | 增存 | 行外吸金 | `jg-deposit-waihang` | placeholder | — | — | — |
| 个金 | 增存 | 降级挽回 | `jg-deposit-jiangji` | metric | downgrade | jjwh | [docs/modules/jg-deposit-jiangji.md](../modules/jg-deposit-jiangji.md) |
| 个金 | 增存 | 经理队伍 | `jg-deposit-team` | placeholder | — | — | — |
| 个金 | 增客 | 全量客户 | `jg-customer-all` | placeholder | — | — | — |
| 个金 | 增客 | 代发工资 | `jg-customer-pay` | metric | payroll | dfmx | — |
| 个金 | 增客 | 薪管家 | `jg-customer-xgj` | metric | salary | xgj | [docs/modules/jg-customer-xgj.md](../modules/jg-customer-xgj.md) |
| 个金 | 增客 | 一卡一户 | `jg-customer-yika` | metric | yika | ykh | [docs/modules/jg-customer-yika.md](../modules/jg-customer-yika.md) |
| 个金 | 增客 | 五卡唤醒 | `jg-customer-card` | metric | fivecards | wk | — |
| 个金 | 增收 | 基保理 | `jg-income-jbl` | placeholder | — | — | — |
| 个金 | 增收 | 三方支付 | `jg-income-pay` | placeholder | — | — | — |
| 网金 | 线上服务 | 线上服务 | `wj-online-svc` | metric | online | xsfw | — |
| 网金 | 数币钱包 | 数币钱包 | `wj-wallet` | metric | wallet | sbqb | — |
| 网金 | 企微社群 | 企微社群 | `wj-wecom-social` | metric | community | qwsq | — |
| 个贷 | 个人贷款 | 个贷规模与投放 | `loan-todo` | placeholder | — | — | — |
| 银行卡 | 银行卡 | 发卡与动户 | `card-todo` | placeholder | — | — | — |
| 私银 | 私人银行 | 私人银行 | `pbs-cust` | metric | pbs | pbs | [docs/modules/pbs-cust.md](../modules/pbs-cust.md) |
| 工具 | 实用工具 | 时日差计算 | `tool-date-diff` | tool | tool | — | — |
| 工具 | 实用工具 | 偏离度计算 | `tool-deviation` | tool | tool | — | — |
| 重点项目 | 重点项目 | 网点争先 | `pj-contend` | placeholder | — | — | — |
| 重点项目 | 重点项目 | 全量客户拓展 | `pj-allcustomer` | planned | — | — | — |
| 重点项目 | 重点项目 | 企微社群运营 | `pj-wecom` | metric | community | qwsq | — |
| 重点项目 | 重点项目 | 五卡唤醒 | `pj-fivecards` | metric | fivecards | wk | — |
| 重点项目 | 重点项目 | 挑战回访100位客户 | `pj-100` | placeholder | — | — | — |

## 数据条线现状

| 条线 | 期数 | 最新 |
|---|---|---|
| `sbqb` | 12 | 2026-10-22 |
| `xgj` | 15 | 2026-10-22 |
| `dqzz` | 1 | 2026-10-15 |
| `xsfw` | 15 | 2026-10-22 |
| `qwsq` | 1 | 2026-10-19 |
| `dfmx` | 9 | 2026-09-30 |
| `wk` | 1 | 2026-09-09 |
| `jjwh` | 1 | 2026-09-13 |
| `ykh` | 1 | 2026-10-25 |
| `pbs` | 3 | 2026-10-24 |
