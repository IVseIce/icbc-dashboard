#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""merge_seed.py —— 把发布包 seed/ 里的数据**合并**进生产库（不是覆盖）。

`install.sh` 只在"还没有库"时整包铺 seed；但升级时经常是"新模块的首次数据要一起带上去"，
又不能把内网机这几个月自己导的数据冲掉。所以这里做的是**并集**：

  快照   —— 按 (line, as_of) 逐条比：生产库没有的补进去；已有的保留生产库那份
            （除非加 --overwrite-line，指定某条线以包内为准）
  台账   —— import_log / source_file 按"时间 + 条线 + 文件名"去重后补进去
  设置   —— setting 只补**缺失的键**；已存在的保留生产库的值
            （口令、产品销售这类人工维护的东西，绝不能被包里的旧值盖掉）
  原件   —— seed/imports/ 里有、生产库没有的文件按相对路径拷过去

用法：
  python scripts/merge_seed.py --seed /path/to/seed --root /path/to/data
  python scripts/merge_seed.py --seed seed --root shared/data --dry-run
  python scripts/merge_seed.py --seed seed --root shared/data --overwrite-line pbs

退出码：0 = 合并完成（或没有需要合并的），1 = 出错。
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent


def connect(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    return con


def table_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def merge_snapshots(src: sqlite3.Connection, dst: sqlite3.Connection, overwrite: set[str], dry: bool) -> dict:
    """按 (line, as_of) 补齐/覆盖快照。"""
    added = updated = kept = 0
    rows = src.execute('SELECT line, as_of, month, partial, rows, payload, payload_hash, source,'
                       ' created_at, updated_at FROM snapshot ORDER BY line, as_of').fetchall()
    have = {(r['line'], r['as_of']) for r in dst.execute('SELECT line, as_of FROM snapshot')}
    for r in rows:
        key = (r['line'], r['as_of'])
        if key not in have:
            added += 1
            if not dry:
                dst.execute(
                    'INSERT INTO snapshot(line, as_of, month, partial, rows, payload, payload_hash,'
                    ' source, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                    (r['line'], r['as_of'], r['month'], r['partial'], r['rows'], r['payload'],
                     r['payload_hash'], r['source'], r['created_at'], r['updated_at']))
        elif r['line'] in overwrite:
            updated += 1
            if not dry:
                dst.execute(
                    'UPDATE snapshot SET month=?, partial=?, rows=?, payload=?, payload_hash=?,'
                    ' source=?, updated_at=? WHERE line=? AND as_of=?',
                    (r['month'], r['partial'], r['rows'], r['payload'], r['payload_hash'],
                     r['source'], r['updated_at'], r['line'], r['as_of']))
        else:
            kept += 1
    return {'snapshot_added': added, 'snapshot_overwritten': updated, 'snapshot_kept': kept}


def merge_import_log(src: sqlite3.Connection, dst: sqlite3.Connection, dry: bool) -> dict:
    if not table_exists(src, 'import_log') or not table_exists(dst, 'import_log'):
        return {'import_log_added': 0}
    # 去重键：时间 + 条线 + 文件列表（同一批导入在两边各记了一条时不重复）
    have = set()
    for r in dst.execute('SELECT ts, line, files FROM import_log'):
        have.add((r['ts'], r['line'], r['files']))
    added = 0
    for r in src.execute('SELECT ts, line, data_date, ok, error, note, archive, files, snapshot_id'
                         ' FROM import_log ORDER BY id'):
        key = (r['ts'], r['line'], r['files'])
        if key in have:
            continue
        added += 1
        if not dry:
            # snapshot_id 指向源库，跨库无意义；置空（台账里文件与日期仍然可查）
            dst.execute('INSERT INTO import_log(ts, line, data_date, ok, error, note, archive, files,'
                        ' snapshot_id) VALUES(?,?,?,?,?,?,?,?,NULL)',
                        (r['ts'], r['line'], r['data_date'], r['ok'], r['error'], r['note'],
                         r['archive'], r['files']))
    return {'import_log_added': added}


def merge_settings(src: sqlite3.Connection, dst: sqlite3.Connection, dry: bool) -> dict:
    if not table_exists(src, 'setting') or not table_exists(dst, 'setting'):
        return {'setting_added': 0, 'setting_kept': 0}
    have = {r['key'] for r in dst.execute('SELECT key FROM setting')}
    added = kept = 0
    for r in src.execute('SELECT key, value, updated_at FROM setting'):
        if r['key'] in have:
            kept += 1            # 生产库已有的设置一律不动（口令、手工维护的产品销售等）
            continue
        added += 1
        if not dry:
            dst.execute('INSERT INTO setting(key, value, updated_at) VALUES(?,?,?)',
                        (r['key'], r['value'], r['updated_at']))
    return {'setting_added': added, 'setting_kept': kept}


def merge_files(seed: Path, root: Path, dry: bool) -> dict:
    """把 seed/imports 里有、生产库没有的原件按相对路径补过去。"""
    src_dir, dst_dir = seed / 'imports', root / 'imports'
    if not src_dir.exists():
        return {'files_copied': 0}
    copied = 0
    for p in src_dir.rglob('*'):
        if not p.is_file():
            continue
        rel = p.relative_to(src_dir)
        dst = dst_dir / rel
        if dst.exists():
            continue
        copied += 1
        if not dry:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dst)
    return {'files_copied': copied}


def rebase_paths(con: sqlite3.Connection, root: Path, dry: bool) -> int:
    """把归档路径里的绝对前缀去掉，统一成相对 data/ 的写法（换机器也不失效）。"""
    if dry:
        return 0
    prefix = str(root.resolve()).rstrip('/') + '/'
    n = 0
    for table, cols in (('source_file', ('path', 'archive')), ('import_log', ('archive',))):
        if not table_exists(con, table):
            continue
        for col in cols:
            cur = con.execute(f"UPDATE {table} SET {col} = substr({col}, ?) "
                              f"WHERE {col} LIKE ?", (len(prefix) + 1, prefix + '%'))
            n += cur.rowcount
            cur = con.execute(f"UPDATE {table} SET {col} = substr({col}, instr({col}, 'imports/')) "
                              f"WHERE instr({col}, 'imports/') > 0 AND {col} NOT LIKE 'imports/%'")
            n += cur.rowcount
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--seed', required=True, help='发布包里的 seed/ 目录')
    ap.add_argument('--root', required=True, help='生产数据目录（含 icbc.db）')
    ap.add_argument('--overwrite-line', action='append', default=[],
                    help='这条线的快照以包内为准（可多次指定）')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    seed = Path(a.seed).expanduser().resolve()
    root = Path(a.root).expanduser().resolve()
    src_db = seed / 'icbc.db'
    dst_db = root / 'icbc.db'
    if not src_db.exists():
        print(f'包内没有 {src_db}，跳过合并')
        return 0
    if not dst_db.exists():
        print(f'生产库 {dst_db} 不存在：走 install.sh 整包铺 seed，这里不做')
        return 0

    stats: dict = {}
    src = connect(src_db)
    dst = connect(dst_db)
    try:
        stats |= merge_snapshots(src, dst, set(a.overwrite_line), a.dry_run)
        stats |= merge_import_log(src, dst, a.dry_run)
        stats |= merge_settings(src, dst, a.dry_run)
        stats['paths_rebased'] = rebase_paths(dst, root, a.dry_run)
        if not a.dry_run:
            dst.commit()
    except Exception as exc:
        dst.rollback()
        print(f'合并失败：{exc}', file=sys.stderr)
        return 1
    finally:
        src.close()
        dst.close()

    stats |= merge_files(seed, root, a.dry_run)

    tag = '（预演，未写库）' if a.dry_run else ''
    print('seed 合并' + tag)
    print(f'  快照    新增 {stats["snapshot_added"]} 期，'
          f'覆盖 {stats["snapshot_overwritten"]} 期，保留生产 {stats["snapshot_kept"]} 期')
    print(f'  导入台账 新增 {stats["import_log_added"]} 条')
    print(f'  设置    新增 {stats["setting_added"]} 项，保留生产 {stats["setting_kept"]} 项')
    print(f'  原件    复制 {stats["files_copied"]} 个')
    return 0


if __name__ == '__main__':
    sys.exit(main())
