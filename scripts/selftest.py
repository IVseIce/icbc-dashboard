#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""selftest.py —— 部署自检：解释器 / 依赖 / 数据库能不能用。

install.sh、update.sh、status.sh 都调它；出问题时也是第一条要跑的命令。

  python3 scripts/selftest.py                  # 只检查解释器与依赖
  python3 scripts/selftest.py --root /data     # 再检查数据库（会建表/升级 schema，指向临时副本时最安全）

退出码：0 = 通过；1 = 有问题（stderr 说明原因）。
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / 'src'
sys.path.insert(0, str(SRC))

MIN_PY = (3, 8)


def collect(root: str | None) -> dict:
    out = {
        'ok': True, 'problems': [],
        'python': platform.python_version(),
        'python_path': sys.executable,
        'machine': platform.machine(),
        'sqlite': None, 'version': None, 'deps': {}, 'zoneinfo': None, 'db': None,
    }
    if sys.version_info < MIN_PY:
        out['problems'].append(f'Python 版本过低：{platform.python_version()}，需要 >= 3.8')

    try:
        import sqlite3
        out['sqlite'] = sqlite3.sqlite_version
    except Exception as exc:                        # pragma: no cover
        out['problems'].append(f'sqlite3 不可用：{exc}')

    try:
        from version import app_version
        out['version'] = app_version()
    except Exception as exc:
        out['problems'].append(f'读不到版本号：{exc}')

    try:
        import compat
        out['zoneinfo'] = 'shim(3.8)' if compat.ensure_zoneinfo() else 'builtin'
    except Exception as exc:
        out['problems'].append(f'compat 加载失败：{exc}')

    for mod, label in (('openpyxl', 'openpyxl'), ('xlrd', 'xlrd'), ('yaml', 'PyYAML')):
        try:
            m = __import__(mod)
            out['deps'][label] = getattr(m, '__version__', 'ok')
            if mod == 'yaml' and getattr(m, '__with_libyaml__', False):
                out['deps'][label] += '+libyaml'
        except Exception as exc:
            out['deps'][label] = f'缺失({exc})'
            out['problems'].append(f'依赖缺失：{mod}（{exc}）')

    if root:
        try:
            import store
            from pathlib import Path as P
            if not P(root).exists():
                P(root).mkdir(parents=True, exist_ok=True)
            if not os.access(root, os.W_OK):
                raise PermissionError(f'目录不可写：{root}')
            store.use(root)
            store.init()
            st = store.stats()
            out['db'] = {k: st[k] for k in ('db', 'schema', 'sqlite', 'snapshots', 'imports', 'latest', 'size_mb')}
            out['db']['writable'] = True
        except Exception as exc:
            out['problems'].append(f'数据库不可用（{root}）：{exc}')
            out['db'] = {'root': root, 'error': str(exc)}
    out['ok'] = not out['problems']
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=None, help='数据目录（检查数据库）')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()

    info = collect(a.root)
    if a.json:
        print(json.dumps(info, ensure_ascii=False, indent=1))
    else:
        d = info
        print('ICBC 自检')
        print(f"  解释器   python {d['python']}  ({d['python_path']})  [{d['machine']}]")
        print(f"  sqlite   {d['sqlite']}    zoneinfo {d['zoneinfo']}")
        print(f"  版本     {d['version']}")
        print('  依赖     ' + ', '.join(f'{k} {v}' for k, v in d['deps'].items()))
        if d['db']:
            b = d['db']
            if 'error' in b:
                print(f"  数据库   {b['root']}  ✗ {b['error']}")
            else:
                print(f"  数据库   {b['db']}  schema v{b['schema']}/{b['sqlite']}  "
                      f"{b['snapshots']} 期 · {b['imports']} 次导入 · 最新 {b['latest']} · {b['size_mb']} MB")
        print('结果: ' + ('OK' if d['ok'] else 'FAIL'))
        for p in d['problems']:
            print('  ✗ ' + p, file=sys.stderr)

    sys.exit(0 if info['ok'] else 1)


if __name__ == '__main__':
    main()
