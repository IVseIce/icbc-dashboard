#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""catalog.py —— 系统目录：六大板块 → 分组 → 模块。

这是整个系统的“单一事实来源”：导航、首页卡片、上传的两级选择、路由都从这里生成。
新增一个模块，只在这里加一条 + 在 src/web/assets/js/pages/ 放一个页面文件（或先占位）。
"""

from __future__ import annotations

# kind: metric=已有数据可出图；placeholder=先占位等数据
# status: active / planned
PROFESSIONALS = [
    {
        'id': 'jg', 'name': '个人金融', 'short': '个金', 'color': 'violet', 'status': 'active', 'nested': True,
        'desc': '增存 · 增客 · 增收',
        'groups': [
            {
                'id': 'jg-deposit', 'name': '增存', 'status': 'active', 'desc': '存款规模、承接与稳存',
                'modules': [
                    {'id': 'jg-deposit-time', 'name': '定期存款', 'page': 'deposit', 'kind': 'metric',
                     'level': '支行', 'freq': '日', 'as_line': 'dqzz', 'group': '增存',
                     'source': '分品种、期限时点报表',
                     'desc': '定期余额、当月增量、增幅，8 家支行对比'},
                    {'id': 'jg-deposit-jiepan', 'name': '定期承接', 'kind': 'placeholder', 'group': '增存',
                     'desc': '到期定期承接率、承接金额（待接入）'},
                    {'id': 'jg-deposit-waihang', 'name': '行外吸金', 'kind': 'placeholder', 'group': '增存',
                     'desc': '行外资金流入、他行转介（待接入）'},
                    {'id': 'jg-deposit-jiangji', 'name': '降级挽回', 'kind': 'placeholder', 'group': '增存',
                     'desc': '定期降级客户清单与挽回（待接入）'},
                    {'id': 'jg-deposit-team', 'name': '经理队伍', 'kind': 'placeholder', 'group': '增存',
                     'desc': '客户经理管户、产能与考核（待接入）'},
                ],
            },
            {
                'id': 'jg-customer', 'name': '增客', 'status': 'active', 'desc': '拓客、代发与卡片唤醒',
                'modules': [
                    {'id': 'jg-customer-all', 'name': '全量客户', 'kind': 'placeholder', 'level': '支行',
                     'group': '增客', 'desc': '全量客户拓展进度（待接入）'},
                    {'id': 'jg-customer-pay', 'name': '代发工资', 'page': 'payroll', 'kind': 'metric',
                     'level': '网点', 'source': '代发明细（月度）', 'freq': '月', 'as_line': 'dfmx',
                     'group': '增客', 'desc': '代发企业/客户、金额、新增与流失预警'},
                    {'id': 'jg-customer-xgj', 'name': '薪管家', 'page': 'salary', 'kind': 'metric',
                     'source': '薪管家增量表 ×4', 'level': '支行 + 网点', 'freq': '日', 'as_line': 'xgj',
                     'group': '增客', 'desc': '薪酬代发金额、有效使用企业数'},
                    {'id': 'jg-customer-yika', 'name': '一卡一户', 'kind': 'placeholder', 'group': '增客',
                     'desc': '一人一卡一户渗透（待接入）'},
                    {'id': 'jg-customer-card', 'name': '五卡唤醒', 'page': 'fivecards', 'kind': 'metric',
                     'level': '支行', 'source': '五卡汇总表', 'freq': '不定期', 'as_line': 'wk',
                     'group': '增客', 'desc': '社保卡/退役军人/养老金/信用卡/薪金卡唤醒'},
                ],
            },
            {
                'id': 'jg-income', 'name': '增收', 'status': 'framework', 'desc': '中收来源',
                'modules': [
                    {'id': 'jg-income-jbl', 'name': '基保理', 'kind': 'placeholder', 'group': '增收',
                     'desc': '基金/保险/理财销量与保有（待接入）'},
                    {'id': 'jg-income-pay', 'name': '三方支付', 'kind': 'placeholder', 'group': '增收',
                     'desc': '绑卡数、交易额、活跃户（待接入）'},
                ],
            },
        ],
    },
    {
        'id': 'wj', 'name': '网络金融', 'short': '网金', 'color': 'blue', 'status': 'active',
        'desc': '线上服务 · 数币 · 企微',
        'groups': [
            {
                'id': 'wj-online', 'name': '线上服务', 'status': 'active', 'modules': [
                    {'id': 'wj-online-svc', 'name': '线上服务', 'page': 'online', 'kind': 'metric',
                     'source': '动户率×2 + 企微明细×3 + 营销授权', 'level': '网点', 'freq': '日', 'as_line': 'xsfw',
                     'desc': '到店动户率、企微添客、签约率'},
                ],
            },
            {
                'id': 'wj-digital', 'name': '数币钱包', 'status': 'active', 'modules': [
                    {'id': 'wj-wallet', 'name': '数币钱包', 'page': 'wallet', 'kind': 'metric',
                     'source': '钱包开立明细', 'level': '网点', 'freq': '日', 'as_line': 'sbqb',
                     'desc': '累计开立、当日/当月新增、等级结构'},
                ],
            },
            {
                'id': 'wj-wecom', 'name': '企微社群', 'status': 'active', 'modules': [
                    {'id': 'wj-wecom-social', 'name': '企微社群', 'page': 'community', 'kind': 'metric',
                     'source': '成员群聊数据统计（本周+上周）', 'level': '支行 + 网点', 'freq': '周', 'as_line': 'qwsq',
                     'desc': '群数、客户数、交互、熟识率'},
                ],
            },
        ],
    },
    {
        'id': 'loan', 'name': '个人贷款', 'short': '个贷', 'color': 'teal', 'status': 'planned',
        'desc': '框架预留，待接入',
        'groups': [{'id': 'loan-main', 'name': '个人贷款', 'modules': [
            {'id': 'loan-todo', 'name': '个贷规模与投放', 'kind': 'placeholder', 'desc': '待接入数据'},
        ]}],
    },
    {
        'id': 'card', 'name': '银行卡', 'short': '银行卡', 'color': 'amber', 'status': 'planned',
        'desc': '框架预留，待接入',
        'groups': [{'id': 'card-main', 'name': '银行卡', 'modules': [
            {'id': 'card-todo', 'name': '发卡与动户', 'kind': 'placeholder', 'desc': '待接入数据'},
        ]}],
    },
    {
        'id': 'pbs', 'name': '私人银行', 'short': '私银', 'color': 'red', 'status': 'planned',
        'desc': '框架预留，待接入',
        'groups': [{'id': 'pbs-main', 'name': '私人银行', 'modules': [
            {'id': 'pbs-todo', 'name': '私银客户与 AUM', 'kind': 'placeholder', 'desc': '待接入数据'},
        ]}],
    },
    {
        'id': 'tool', 'name': '实用工具', 'short': '工具', 'color': 'slate', 'status': 'active',
        'upload': False,                      # 工具类不与数据条线挂钩，导入页不显示
        'desc': '常用小工具',
        'groups': [{'id': 'tool-main', 'name': '实用工具', 'status': 'active', 'modules': [
            {'id': 'tool-date-diff', 'name': '时日差计算', 'page': 'tool', 'kind': 'tool',
             'group': '实用工具', 'desc': '待实现'},
            {'id': 'tool-deviation', 'name': '偏离度计算', 'page': 'tool', 'kind': 'tool',
             'group': '实用工具', 'desc': '待实现'},
        ]}],
    },
    {
        'id': 'project', 'name': '重点项目', 'short': '重点项目', 'color': 'green', 'status': 'active',
        'desc': '方案推进与专项攻坚',
        'groups': [
            {
                'id': 'pj-main', 'name': '重点项目', 'status': 'active', 'modules': [
                    {'id': 'pj-contend', 'name': '网点争先', 'kind': 'placeholder',
                     'desc': '网点竞赛排名与积分（待接入）'},
                    {'id': 'pj-allcustomer', 'name': '全量客户拓展', 'kind': 'planned', 'level': '支行',
                     'source': '全量客户场景攻坚成效图', 'freq': '周',
                     'desc': '六大场景落地/推进（当前为文字进度）'},
                    {'id': 'pj-wecom', 'name': '企微社群运营', 'page': 'community', 'kind': 'metric',
                     'as_line': 'qwsq', 'level': '支行 + 网点', 'freq': '周',
                     'source': '成员群聊数据统计（本周+上周）', 'desc': '群数、客户数、交互、熟识率'},
                    {'id': 'pj-fivecards', 'name': '五卡唤醒', 'page': 'fivecards', 'kind': 'metric',
                     'as_line': 'wk', 'level': '支行', 'freq': '不定期',
                     'source': '五卡汇总表', 'desc': '5 类卡存量/长尾/未交易（与增客共用）'},
                    {'id': 'pj-100', 'name': '挑战回访100位客户', 'kind': 'placeholder',
                     'desc': '回访进度与转化（待接入）'},
                ],
            },
        ],
    },
]


def iter_modules():
    for prof in PROFESSIONALS:
        for grp in prof['groups']:
            for mod in grp['modules']:
                yield prof, grp, mod


def catalog() -> dict:
    return {'ok': True, 'professionals': PROFESSIONALS, 'version': 'v3-m1'}


def module_map() -> dict:
    return {m['id']: (p, g, m) for p, g, m in iter_modules()}


def lines_of(prof_ids) -> set[str]:
    """这些大类下所有可上传条线（id 集合）。用于按权限裁剪导入页的"数据时点"。"""
    ids = set(prof_ids or ())
    return {m['as_line'] for p, _g, m in iter_modules()
            if p['id'] in ids and m.get('as_line')}
