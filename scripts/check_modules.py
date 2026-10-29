#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""check_modules.py —— 模块接线自检 + 生成模块清单。

新增/修改模块最容易漏东西：catalog 加了模块但没写页面、加了 as_line 但没注册导入器、
通报加了 kind 但没登记大类……这个脚本把"三处配置 + 一处前端"的对应关系全查一遍。

  python scripts/check_modules.py            # 检查（有问题退出码 1）
  python scripts/check_modules.py --write    # 检查并重写 docs/MODULES.md
  python scripts/check_modules.py --quiet    # 只输出问题

检查项：
  1. 模块 id 唯一；页面文件存在；kind 合法；group 字段与所在分组一致
  2. kind=metric 必须有 as_line，且该条线在 viz.IMPORTERS 与 api.BUILDERS 都有
  3. 通报：report.BUILDERS / report.CAT_OF / xlsx 母版 / 前端 report.js 的 LINES 对齐
  4. upload:false 的板块不许挂数据模块（否则导入页会冒出一个空板块）
  5. docs/modules/<id>.md 是否存在（WARN，不阻塞）
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / 'src'))
sys.path.insert(0, str(PROJECT / 'src' / 'server'))

import api       # noqa: E402
import report    # noqa: E402
import store     # noqa: E402
import viz       # noqa: E402
from domain import catalog  # noqa: E402

PAGES = PROJECT / 'src' / 'web' / 'assets' / 'js' / 'pages'
REPORT_JS = PAGES / 'report.js'
GUIDE_JS = PROJECT / 'src' / 'web' / 'assets' / 'js' / 'guide-content.js'
CHANGELOG_JS = PROJECT / 'src' / 'web' / 'assets' / 'js' / 'changelog.js'
KINDS = {'metric', 'tool', 'placeholder', 'planned'}


class Checker:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warns: list[str] = []

    def err(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warns.append(msg)


def js_report_lines() -> dict[str, str]:
    """从 report.js 的 LINES 里抓 {id: 'xxx', name: '…', cat: 'yyy'}。"""
    if not REPORT_JS.exists():
        return {}
    src = REPORT_JS.read_text('utf-8')
    block = re.search(r'const LINES = \[(.*?)\];', src, re.S)
    if not block:
        return {}
    return {m.group(1): m.group(2) for m in
            re.finditer(r"id: '(\w+)',\s*name: '[^']*',\s*cat: '(\w+)'", block.group(1))}


def js_guide_sections() -> set[str]:
    """使用指南（guide-content.js）里的章节 id 集合。"""
    if not GUIDE_JS.exists():
        return set()
    return set(re.findall(r"^\s{4}id: '([\w.-]+)',", GUIDE_JS.read_text('utf-8'), re.M))


def js_changelog_versions() -> list[str]:
    """changelog.js 里记录的版本号，按书写顺序（最新在最前）。"""
    if not CHANGELOG_JS.exists():
        return []
    return re.findall(r"^\s{4}version: '([\d.]+)',", CHANGELOG_JS.read_text('utf-8'), re.M)


def run() -> tuple[Checker, list[dict]]:
    c = Checker()
    rows: list[dict] = []
    seen: dict[str, str] = {}
    prof_ids = {p['id'] for p in catalog.PROFESSIONALS}
    lines_of_cat = catalog.lines_of(prof_ids)

    for prof in catalog.PROFESSIONALS:
        for grp in prof['groups']:
            if not (grp.get('modules') or []):
                c.warn(f"{prof['id']}/{grp['id']} 分组是空的（如果是有意的占位，可忽略）")
            for m in grp.get('modules') or []:
                mid = m['id']
                if mid in seen:
                    c.err(f'模块 id 重复：{mid}（{seen[mid]} 与 {prof["id"]}）')
                seen[mid] = prof['id']

                kind = m.get('kind')
                if kind not in KINDS:
                    c.err(f'{mid}: kind={kind!r} 不合法（应属于 {sorted(KINDS)}）')
                if m.get('group') and m['group'] != grp['name']:
                    c.err(f'{mid}: group={m["group"]!r} 与所在分组 {grp["name"]!r} 不一致')

                page = m.get('page')
                if page and not (PAGES / f'{page}.js').exists():
                    c.err(f'{mid}: page={page!r} 没有对应的 pages/{page}.js')

                line = m.get('as_line')
                if kind == 'metric' and not line:
                    c.err(f'{mid}: kind=metric 必须配 as_line（否则没有数据源）')
                if line:
                    if line not in viz.IMPORTERS:
                        c.err(f'{mid}: as_line={line!r} 没有注册导入器（viz.IMPORTERS）')
                    if line not in {v for v in api.LINE_OF.values()}:
                        c.err(f'{mid}: as_line={line!r} 没有对应的视图模型（api.LINE_OF）')
                    if prof.get('upload') is False:
                        c.err(f'{mid}: 所属板块 upload=false（工具类）不该挂数据条线 {line!r}')

                rows.append({
                    'prof': prof['short'] if prof.get('short') else prof['name'],
                    'prof_id': prof['id'],
                    'group': grp['name'],
                    'name': m['name'],
                    'id': mid,
                    'kind': kind or '',
                    'page': page or '',
                    'line': line or '',
                    'docs': (PROJECT / 'docs' / 'modules' / f'{mid}.md').exists(),
                })

    # 通报三处对齐
    # 母版检查：一份通报可以有多份成表（pbs / team），按 XLSX 注册的 key 找母版，
    # 只有"既不是 builder 又没有 downloads"的才算缺（team 用 ck_base / yw_base）
    # 一份通报可以有多份成表：pbs（核心指标 + 发展情况）、team（财客 + 远维）。
    # 这类通报的 builder 名与母版名不同，按 XLSX 注册表里"以它自己开头"的 key 找母版。
    def bases_of(k: str) -> list[str]:
        return list(report.BASES_OF.get(k) or (k,))

    xlsx_missing = [k for k in report.BUILDERS
                    if not any((PROJECT / 'src' / 'report' / 'assets' / f'{b}_base.xlsx').exists()
                               for b in bases_of(k))]
    for k in xlsx_missing:
        c.err(f'通报 {k}: 缺少样式母版 src/report/assets/{k}_base.xlsx')
    for k in report.BUILDERS:
        if k not in report.CAT_OF:
            c.err(f'通报 {k}: report.CAT_OF 里没有登记所属大类')
        elif report.CAT_OF[k] not in prof_ids:
            c.err(f'通报 {k}: 大类 {report.CAT_OF[k]!r} 不存在')
    js_lines = js_report_lines()
    if not js_lines:
        c.err('report.js: 解析不到 LINES（结构变了？）')
    for k in js_lines:
        if k not in report.BUILDERS:
            c.err(f'report.js: 通报 {k!r} 后端没有 builder')
    for k in report.BUILDERS:
        if k not in js_lines:
            c.err(f'通报 {k}: report.js 的 LINES 里没有（前端看不到这条通报）')
    for k, cat in report.CAT_OF.items():
        if k in js_lines and js_lines[k] != cat:
            c.err(f'通报 {k}: 大类不一致（后端 {cat} / 前端 {js_lines[k]}）')

    # 工具类板块
    for prof in catalog.PROFESSIONALS:
        if prof.get('upload') is False:
            mods = [m for g in prof['groups'] for m in (g.get('modules') or [])]
            if any(m.get('as_line') for m in mods):
                c.err(f"{prof['id']}: upload=false 但含数据模块")

    # 数据现状（只是提示）
    for line in viz.LINES:
        try:
            dates = store.dates(line)
        except Exception:
            dates = []
        rows.append({'line_stat': line, 'last': dates[-1] if dates else None, 'count': len(dates)})

    # 使用指南：每个数据/工具模块都该有一节；changelog 顶部版本要等于 VERSION
    # 覆盖规则放宽：也可以用「共享同一个 page+条线」的模块章节来覆盖（重点项目复用网金页面）；
    # 工具类还可以由一节 id='tool' 的通用说明覆盖。
    secs = js_guide_sections()
    if not secs:
        c.err('guide-content.js: 解析不到 GUIDE_SECTIONS（结构变了？）')
    else:
        live = [r for r in rows if r.get('kind') in ('metric', 'tool')]
        shared = {}
        for m in live:
            shared.setdefault((m['page'], m['line']), []).append(m['id'])
        for m in live:
            if m['id'] in secs:
                continue
            if m['kind'] == 'tool' and 'tool' in secs:
                continue
            if any(x in secs for x in shared[(m['page'], m['line'])]):
                continue
            c.warn(f"使用指南里没有 {m['id']}（{m['name']}）的说明")
        versions = js_changelog_versions()
        if not versions:
            c.err('changelog.js: 解析不到版本条目')
        else:
            try:
                cur = (PROJECT / 'VERSION').read_text('utf-8').strip()
            except OSError:
                cur = ''
            if cur and versions[0] != cur:
                c.warn(f'changelog.js 最新一条是 {versions[0]}，VERSION 是 {cur}（发版时补一条）')

    return c, rows


def render(c: Checker, rows: list[dict]) -> str:
    mods = [r for r in rows if 'id' in r]
    stats = [r for r in rows if 'line_stat' in r]
    out = ['# 模块清单', '',
           '> 由 `python scripts/check_modules.py --write` 自动生成，**不要手改**。',
           '> 每个模块的细节（口径/字段/坑）写在 `docs/modules/<模块id>.md`。', '']

    out += ['## 板块', '', '| 板块 | id | 模块 | 已接入 | 说明 |', '|---|---|---|---|---|']
    for p in catalog.PROFESSIONALS:
        ms = [m for g in p['groups'] for m in (g.get('modules') or [])]
        ready = sum(1 for m in ms if m.get('kind') == 'metric')
        out.append(f"| {p['name']} | `{p['id']}` | {len(ms)} | {ready} | {p.get('desc','')} |")
    out.append('')

    out += ['## 模块', '', '| 板块 | 分组 | 模块 | id | 类型 | 页面 | 导入条线 | 文档 |',
            '|---|---|---|---|---|---|---|---|']
    for r in mods:
        doc = f"[docs/modules/{r['id']}.md](../modules/{r['id']}.md)" if r['docs'] else '—'
        out.append(f"| {r['prof']} | {r['group']} | {r['name']} | `{r['id']}` | {r['kind']} | "
                   f"{r['page'] or '—'} | {r['line'] or '—'} | {doc} |")
    out.append('')

    out += ['## 数据条线现状', '', '| 条线 | 期数 | 最新 |', '|---|---|---|']
    for s in stats:
        out.append(f"| `{s['line_stat']}` | {s['count']} | {s['last'] or '—'} |")
    out.append('')
    return '\n'.join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--write', action='store_true', help='重写 docs/MODULES.md')
    ap.add_argument('--quiet', action='store_true')
    a = ap.parse_args()

    c, rows = run()
    if not a.quiet:
        for w in c.warns:
            print(f'  ! {w}')
        for e in c.errors:
            print(f'  ✗ {e}', file=sys.stderr)
        mods = [r for r in rows if 'id' in r]
        print(f'\n模块 {len(mods)} 个（数据 {sum(1 for m in mods if m["kind"] == "metric")} / '
              f'工具 {sum(1 for m in mods if m["kind"] == "tool")} / '
              f'占位 {sum(1 for m in mods if m["kind"] in ("placeholder", "planned"))}）')
    if a.write:
        dst = PROJECT / 'docs' / 'MODULES.md'
        dst.write_text(render(c, rows), 'utf-8')
        print(f'已写入 {dst.relative_to(PROJECT)}')
    print('结果: ' + ('OK' if not c.errors else f'{len(c.errors)} 个问题'))
    sys.exit(0 if not c.errors else 1)


if __name__ == '__main__':
    main()
