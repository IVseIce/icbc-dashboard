#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""export_db.py —— 把内网机器上的数据库热导出（给外部开发/复盘用）。

产出两个文件（同名不同后缀）：
  icbc-<时间戳>.db     SQLite 副本（用在线备份 API，服务不用停）
  icbc-<时间戳>.json   清单：版本、schema、各条线期数与最新日期、导入次数

  python scripts/export_db.py --root ~/icbc-dashboard/shared/data --out /media/usb
  python scripts/export_db.py --out ~/Desktop --no-manifest
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / 'src'))
sys.path.insert(0, str(PROJECT / 'src' / 'server'))

import store  # noqa: E402
import viz    # noqa: E402


def manifest(root: Path, db_file: Path) -> dict:
    st = store.stats()
    per_line = []
    for r in sorted(st['lines_detail'], key=lambda x: x['line']):
        meta = viz.LINES.get(r['line'], {})
        per_line.append({'line': r['line'], 'label': meta.get('label', r['line']),
                         'snapshots': int(r['count']), 'latest': r['as_of']})
    try:
        from version import app_version
        version = app_version()
    except Exception:
        version = 'unknown'
    return {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'version': version,
        'schema': st['schema'],
        'sqlite': st['sqlite'],
        'python': platform.python_version(),
        'source_db': str(db_file),
        'snapshots': st['snapshots'],
        'imports': st['imports'],
        'latest': st['latest'],
        'lines': per_line,
        'note': '只读副本：本机可用 sqlite3 或 python 直接打开；不要写回内网库。',
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=str(PROJECT / 'data'), help='内网数据目录')
    ap.add_argument('--out', default=str(Path.home()), help='导出到哪个目录（U 盘挂载点）')
    ap.add_argument('--tag', default=None, help='文件名时间戳，默认 YYYYmmdd-HHMM')
    ap.add_argument('--no-manifest', action='store_true')
    a = ap.parse_args()

    root = Path(a.root)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    viz.use_root(root)

    stamp = a.tag or datetime.now().strftime('%Y%m%d-%H%M')
    target = out / f'icbc-{stamp}.db'
    store.backup_to(target)
    print(f'已导出数据库 → {target}  ({target.stat().st_size / 1024:.0f} KB)')

    if not a.no_manifest:
        meta = manifest(root, target)
        mf = out / f'icbc-{stamp}.json'
        mf.write_text(json.dumps(meta, ensure_ascii=False, indent=1), 'utf-8')
        lines = '、'.join(f"{x['label']} {x['latest']}" for x in meta['lines'])
        print(f'清单 → {mf}')
        print(f"  {meta['snapshots']} 期快照 · {meta['imports']} 次导入 · 最新 {meta['latest']}")
        print(f'  {lines}')


if __name__ == '__main__':
    main()
