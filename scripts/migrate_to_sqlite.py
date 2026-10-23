#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""migrate_to_sqlite.py —— 把旧的 JSON 快照库迁进 SQLite（一次性，可重复执行）。

做三件事：
1. 建库/建表（`src/store.py`，schema v1）；
2. 把 `data/snapshots/<line>/*.json` 与 `data/ledger.jsonl` 灌进 `data/icbc.db`；
3. 校验条数一致后，把旧的 JSON 目录整体挪到 `data/legacy_json_<时间戳>/`（不删，只挪）。

用法：
  python scripts/migrate_to_sqlite.py            # 迁移 + 挪走旧文件
  python scripts/migrate_to_sqlite.py --keep     # 迁移但不挪（旧 JSON 保留，下次启动不会再灌一遍）
  python scripts/migrate_to_sqlite.py --db-info  # 只看库里现状
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / 'src'))
sys.path.insert(0, str(PROJECT / 'src' / 'server'))

import store  # noqa: E402
import viz    # noqa: E402


def json_counts(root: Path) -> dict[str, int]:
    base = root / 'snapshots'
    if not base.exists():
        return {}
    return {d.name: len(list(d.glob('*.json'))) for d in sorted(base.iterdir()) if d.is_dir()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=str(PROJECT / 'data'))
    ap.add_argument('--keep', action='store_true', help='迁移后保留旧 JSON 目录（默认挪到 legacy_json_<ts>）')
    ap.add_argument('--db-info', action='store_true', help='只打印库现状')
    a = ap.parse_args()

    root = Path(a.root)
    viz.use_root(root)          # 建表 + 首次自动灌数据（import_legacy 幂等）

    if a.db_info:
        print(json.dumps(store.stats(), ensure_ascii=False, indent=1))
        return

    before = json_counts(root)
    if not before and not (root / 'ledger.jsonl').exists():
        db = store.stats()
        print(f'旧 JSON 已迁移完（data/ 下没有 snapshots/）。'
              f'库内 {db["snapshots"]} 期快照 / {db["imports"]} 次导入，最新 {db["latest"]}，'
              f'{db["size_mb"]} MB')
        return
    stats = {r['line']: r['count'] for r in store.line_stats()}
    ledger_json = 0
    if (root / 'ledger.jsonl').exists():
        ledger_json = sum(1 for ln in (root / 'ledger.jsonl').read_text('utf-8').splitlines() if ln.strip())
    db = store.stats()

    print(f'数据库：{store.db_path()}  （schema v{db["schema"]}，{db["size_mb"]} MB）')
    print(f'{"条线":<8}{"JSON":>6}{"SQLite":>8}')
    ok = True
    for line in sorted(set(before) | set(stats)):
        j, s = before.get(line, 0), int(stats.get(line, 0))
        flag = '' if j <= s else '  ← 不一致'
        ok = ok and j <= s
        print(f'{line:<8}{j:>6}{s:>8}{flag}')
    print(f'导入台账：JSON {ledger_json} 行 → SQLite {db["imports"]} 行')
    print(f'快照合计：{db["snapshots"]} 期，最新 {db["latest"]}')

    if not ok:
        print('!! 有 JSON 快照没进库，先别挪旧文件；把上面的差异发出来排查', file=sys.stderr)
        sys.exit(2)

    if a.keep:
        print('按 --keep 保留旧 JSON 目录（已写 setting.legacy_json_imported，不会重复灌）')
        return

    olds = [n for n in ('snapshots', 'ledger.jsonl') if (root / n).exists()]
    if not olds:
        print('旧 JSON 已经处理过（data/ 下没有 snapshots/ 或 ledger.jsonl），无需再挪')
        return
    stamp = datetime.now().strftime('%Y%m%d_%H%M')
    dest = root / f'legacy_json_{stamp}'
    dest.mkdir(parents=True, exist_ok=True)
    for name in olds:
        shutil.move(str(root / name), str(dest / name))
    print(f'旧文件已挪到 {dest}（{", ".join(olds)}）；确认无误后可自行删除')


if __name__ == '__main__':
    main()
