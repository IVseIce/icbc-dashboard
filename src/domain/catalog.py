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
        'id': 'jg', 'name': '个人金融', 'short': '个金', 'color': 'violet', 'status': 'active',
        'desc': '增存 · 增客 · 增收 · 增贷',
        'groups': [
            {
                'id': 'jg-deposit', 'name': '增存', 'status': 'active',
                'desc': '各项存款规模与增量',
                'modules': [
                    {'id': 'jg-deposit-time', 'name': '定期存款', 'page': 'deposit', 'kind': 'metric',
                     'source': '分品种、期限时点报表', 'level': '支行', 'freq': '日', 'as_line': 'dqzz',
                     'desc': '定期余额、当月增量、增幅，8 家支行对比'},
                    {'id': 'jg-deposit-point', 'name': '时点存款', 'kind': 'placeholder', 'level': '客户',
                     'desc': '个人客户时点存款（暂无网点维度数据）'},
                ],
            },
            {
                'id': 'jg-customer', 'name': '增客', 'status': 'active',
                'desc': '全量客户拓展与代发客群',
                'modules': [
                    {'id': 'jg-customer-xgj', 'name': '薪管家（代发）', 'page': 'salary', 'kind': 'metric',
                     'source': '薪管家增量表 ×4', 'level': '支行 + 网点', 'freq': '日', 'as_line': 'xgj',
                     'desc': '薪酬代发金额、有效使用企业数'},
                    {'id': 'jg-customer-pay', 'name': '代发明细', 'page': 'payroll', 'kind': 'metric',
                     'level': '网点', 'source': '代发明细.xlsx（月度多 sheet）', 'freq': '月', 'as_line': 'dfmx',
                     'desc': '代发企业/客户、代发金额、新增、流失预警（月度）'},
                    {'id': 'jg-customer-card', 'name': '五卡唤醒', 'kind': 'planned', 'level': '支行',
                     'source': '五卡汇总表', 'freq': '不定期',
                     'desc': '社保卡/退役军人/养老金/信用卡/薪金卡的存量、长尾、未交易'},
                ],
            },
            {
                'id': 'jg-income', 'name': '增收', 'status': 'framework',
                'desc': '基保理销售 + 三方支付',
                'modules': [
                    {'id': 'jg-income-fund', 'name': '基金 / 保险 / 理财', 'kind': 'placeholder', 'level': '支行 + 网点',
                     'desc': '销量、保有、客户数（待接入）'},
                    {'id': 'jg-income-pay', 'name': '三方支付', 'kind': 'placeholder', 'level': '支行 + 网点',
                     'desc': '绑卡数、交易额、活跃户（待接入）'},
                ],
            },
            {
                'id': 'jg-loan', 'name': '增贷', 'status': 'framework',
                'desc': '个金暂不涉及，先留位',
                'modules': [
                    {'id': 'jg-loan-todo', 'name': '个金增贷（暂不涉及）', 'kind': 'placeholder'},
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
                    {'id': 'wj-online-svc', 'name': '网点线上服务能力', 'page': 'online', 'kind': 'metric',
                     'source': '动户率×2 + 企微明细×3 + 营销授权', 'level': '网点', 'freq': '日', 'as_line': 'xsfw',
                     'desc': '到店动户率、企微添客、签约率'},
                ],
            },
            {
                'id': 'wj-digital', 'name': '数字人民币', 'status': 'active', 'modules': [
                    {'id': 'wj-wallet', 'name': '个人钱包', 'page': 'wallet', 'kind': 'metric',
                     'source': '钱包开立明细', 'level': '网点', 'freq': '日', 'as_line': 'sbqb',
                     'desc': '累计开立、当日/当月新增、等级结构'},
                ],
            },
            {
                'id': 'wj-wecom', 'name': '企微社群', 'status': 'active', 'modules': [
                    {'id': 'wj-wecom-social', 'name': '社群运营', 'page': 'community', 'kind': 'metric',
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
        'id': 'project', 'name': '重点项目', 'short': '重点项目', 'color': 'green', 'status': 'active',
        'desc': '方案推进与专项攻坚',
        'groups': [
            {
                'id': 'pj-customer', 'name': '拓客类', 'status': 'active', 'modules': [
                    {'id': 'pj-allcustomer', 'name': '全量客户拓展方案', 'kind': 'planned', 'level': '支行',
                     'source': '全量客户场景攻坚成效图', 'freq': '周',
                     'desc': '六大场景落地/推进情况（当前为文字进度，待结构化）'},
                    {'id': 'pj-100', 'name': '挑战 100 名客户回访', 'kind': 'placeholder', 'level': '支行 + 网点',
                     'desc': '回访进度、转化（待接入）'},
                ],
            },
            {
                'id': 'pj-digital', 'name': '数字化运营', 'status': 'active', 'modules': [
                    {'id': 'pj-wecom', 'name': '企微方案', 'page': 'community', 'kind': 'metric', 'as_line': 'qwsq',
                     'level': '支行 + 网点', 'freq': '周', 'source': '同「网金·企微社群」',
                     'desc': '与网金共用一份数据，此处看项目视角'},
                    {'id': 'pj-fivecards', 'name': '五卡唤醒方案', 'kind': 'planned', 'level': '支行',
                     'source': '五卡汇总表', 'freq': '不定期',
                     'desc': '5 类卡的存量/长尾/未交易，唤醒进度'},
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
