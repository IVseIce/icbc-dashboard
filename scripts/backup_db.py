#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""backup_db.py —— 热备份数据库（不用停服务）。

用 SQLite 的在线备份 API，把 data/icbc.db 完整复制成 data/backups/icbc-<时间戳>.db，
顺带把 auth.json 复制到同目录（口令哈希）。

用法：
  python scripts/backup_db.py                 # 备份到 data/backups/
  python scripts/backup_db.py --keep 30       # 只保留最近 30 份（默认 20）
  python scripts/backup_db.py --out /path/dir
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / 'src'))
sys.path.insert(0, str(PROJECT / 'src' / 'server'))

import store  # noqa: E402
import viz    # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=str(PROJECT / 'data'))
    ap.add_argument('--out', default=None, help='备份目录（默认 <root>/backups）')
    ap.add_argument('--keep', type=int, default=20, help='保留最近多少份')
    a = ap.parse_args()

    root = Path(a.root)
    viz.use_root(root)
    out_dir = Path(a.out) if a.out else root / 'backups'
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    target = store.backup_to(out_dir / f'icbc-{stamp}.db')

    auth = root / 'auth.json'
    if auth.exists():
        shutil.copy2(auth, out_dir / f'auth-{stamp}.json')

    olds = sorted(out_dir.glob('icbc-*.db'))[:-a.keep] if a.keep > 0 else []
    for f in olds:
        f.unlink(missing_ok=True)
        auth_old = out_dir / f.name.replace('icbc-', 'auth-').replace('.db', '.json')
        auth_old.unlink(missing_ok=True)

    db = store.stats()
    print(f'已备份 → {target}（{target.stat().st_size / 1024:.0f} KB；'
          f'库内 {db["snapshots"]} 期 / {db["imports"]} 次导入）')
    if olds:
        print(f'清理旧备份 {len(olds)} 份，保留最近 {a.keep} 份')


if __name__ == '__main__':
    main()
