#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""store.py —— SQLite 存储层（schema v1）。

为什么是"快照文档 + 规范化元数据"：

* 所有指标都是 as-of 语义（"截至某日的一期数据"），解析器已经把一份源表算成一个完整快照；
* 各条线的结构差异很大（数币=网点×4 等级、定期=支行×余额、代发=网点×十几列、五卡=支行×卡×指标），
  强行拆宽表会让"加一条线"变成改三次 schema，反而不利于长期维护；
* 所以事实层存**快照文档**（payload JSON，与原快照文件一致），元数据层（导入台账、原始文件、
  设置）用真表 + 索引。要按指标做 SQL 分析时，再加 v2 的 fact 表从 payload 派生，本层接口不变。

约定：
* 一个 (line, as_of) 只有一行，重复导入是 upsert（覆盖 payload，保留 created_at）；
* 读多写少：WAL + 线程本地连接 + 3 秒 TTL 的小缓存；
* 换库/换 root 用 `use(root)`，进程内全局（与 viz.ROOT 一致）。
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent.parent / 'data'
SCHEMA_VERSION = 1
CACHE_TTL = 3.0

_root: Path = DEFAULT_ROOT
_gen = 0                     # 本进程内的写代数（写一次 +1，缓存随之失效）
_cache: dict[str, tuple[int, float, list[dict]]] = {}
_lock = threading.Lock()
_local = threading.local()


# ---------------------------------------------------------------- 连接 / 建表
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS snapshot (
  id           INTEGER PRIMARY KEY,
  line         TEXT    NOT NULL,
  as_of        TEXT    NOT NULL,              -- 数据日期 YYYY-MM-DD
  month        TEXT,                          -- 月度条线的期间，如 2026-09
  partial      INTEGER NOT NULL DEFAULT 0,    -- 1 = 历史回填的近似快照，详情页跳过
  rows         INTEGER,                       -- 快照里的实体现数（网点/支行），便于概览
  payload      TEXT    NOT NULL,              -- 规范化快照（JSON）
  payload_hash TEXT    NOT NULL,
  source       TEXT,                          -- 来源说明（legacy-json / 上传）
  created_at   TEXT    NOT NULL,
  updated_at   TEXT    NOT NULL,
  UNIQUE(line, as_of)
);
CREATE INDEX IF NOT EXISTS idx_snapshot_line_date ON snapshot(line, as_of DESC);

CREATE TABLE IF NOT EXISTS source_file (
  id          INTEGER PRIMARY KEY,
  snapshot_id INTEGER REFERENCES snapshot(id) ON DELETE SET NULL,
  line        TEXT    NOT NULL,
  name        TEXT    NOT NULL,               -- 原始文件名
  sha256      TEXT    NOT NULL,
  bytes       INTEGER NOT NULL,
  path        TEXT    NOT NULL,               -- 归档后的实际路径
  archive     TEXT,                           -- 这一批次的目录
  created_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_source_file_line ON source_file(line, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_source_file_snap ON source_file(snapshot_id);

CREATE TABLE IF NOT EXISTS import_log (
  id          INTEGER PRIMARY KEY,
  ts          TEXT    NOT NULL,
  line        TEXT    NOT NULL,
  data_date   TEXT,
  ok          INTEGER NOT NULL,
  error       TEXT,
  note        TEXT,
  archive     TEXT,
  files       TEXT    NOT NULL DEFAULT '[]',  -- JSON 数组：原始文件名
  snapshot_id INTEGER REFERENCES snapshot(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_import_log_ts ON import_log(ts DESC);

CREATE TABLE IF NOT EXISTS setting (
  key        TEXT PRIMARY KEY,
  value      TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""


def use(root) -> Path:
    """切换数据根目录（= viz.ROOT）。已缓存的连接/结果全部作废。"""
    global _root, _gen
    _root = Path(root)
    with _lock:
        _gen += 1
        _cache.clear()
    conn = getattr(_local, 'conn', None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
    _local.conn = None
    _local.path = None
    return _root


def root() -> Path:
    return _root


def db_path() -> Path:
    return Path(_root) / 'icbc.db'


def connect() -> sqlite3.Connection:
    path = str(db_path())
    conn = getattr(_local, 'conn', None)
    if conn is not None and getattr(_local, 'path', None) == path:
        return conn
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA synchronous=NORMAL')
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA busy_timeout=5000')
    init(conn)
    _local.conn, _local.path = conn, path
    return conn


def init(conn: sqlite3.Connection | None = None) -> int:
    """建表 / 升级 schema；返回当前版本。"""
    conn = conn or connect()
    v = conn.execute('PRAGMA user_version').fetchone()[0]
    if v == SCHEMA_VERSION:
        return v
    if v > SCHEMA_VERSION:
        raise RuntimeError(f'数据库版本 v{v} 高于代码支持的 v{SCHEMA_VERSION}，请升级程序')
    if v == 0:
        conn.executescript(SCHEMA_SQL)
    else:
        # v < SCHEMA_VERSION：按版本递进升级（加 v2 时在这里补 _upgrade_2(conn)）
        pass
    conn.execute(f'PRAGMA user_version = {SCHEMA_VERSION}')
    return SCHEMA_VERSION


def _now() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def safe_name(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', '_', name or 'file')


# ---------------------------------------------------------------- 设置
def get(key: str, default=None):
    row = connect().execute('SELECT value FROM setting WHERE key=?', (key,)).fetchone()
    if not row:
        return default
    try:
        return json.loads(row['value'])
    except Exception:
        return row['value']


def set_setting(key: str, value) -> None:
    connect().execute(
        'INSERT INTO setting(key, value, updated_at) VALUES(?,?,?) '
        'ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at',
        (key, json.dumps(value, ensure_ascii=False), _now()))


# ---------------------------------------------------------------- 快照
def _bump() -> None:
    global _gen
    with _lock:
        _gen += 1
        _cache.clear()


def save_snapshot(line: str, as_of: str, snap: dict, *, source: str | None = None,
                  partial: bool | None = None) -> int:
    """写入/覆盖一期快照，返回 snapshot.id。"""
    if not line or not as_of:
        raise ValueError('save_snapshot 需要 line 与 as_of')
    snap = dict(snap or {})
    snap['as_of'] = as_of
    snap.setdefault('line', line)
    if partial is None:
        partial = bool(snap.get('partial'))
    payload = json.dumps(snap, ensure_ascii=False)
    digest = hashlib.sha256(payload.encode('utf-8')).hexdigest()[:32]
    now = _now()
    conn = connect()
    conn.execute(
        'INSERT INTO snapshot(line, as_of, month, partial, rows, payload, payload_hash, source, created_at, updated_at)'
        ' VALUES(?,?,?,?,?,?,?,?,?,?)'
        ' ON CONFLICT(line, as_of) DO UPDATE SET'
        '   month=excluded.month, partial=excluded.partial, rows=excluded.rows,'
        '   payload=excluded.payload, payload_hash=excluded.payload_hash,'
        '   source=COALESCE(excluded.source, snapshot.source), updated_at=excluded.updated_at',
        (line, as_of, snap.get('month'), int(bool(partial)),
         len(snap.get('nets') or snap.get('branches') or []), payload, digest, source, now, now))
    row = conn.execute('SELECT id FROM snapshot WHERE line=? AND as_of=?', (line, as_of)).fetchone()
    _bump()
    return int(row['id'])


def _rows_to_snaps(rows) -> list[dict]:
    out = []
    for r in rows:
        try:
            snap = json.loads(r['payload'])
        except Exception:
            continue
        if isinstance(snap, dict):
            out.append(snap)
    return out


def load_snapshots(line: str, since: str | None = None, until: str | None = None) -> list[dict]:
    """按 as_of 升序返回该条线的快照（含 partial）。

    返回值是缓存里的同一批 dict：**只读**，不要原地改。
    """
    if since is None and until is None:
        hit = _cache_get(line)
        if hit is not None:
            return hit
        rows = connect().execute(
            'SELECT payload FROM snapshot WHERE line=? ORDER BY as_of', (line,)).fetchall()
        snaps = _rows_to_snaps(rows)
        _cache_put(line, snaps)
        return snaps
    sql = 'SELECT payload FROM snapshot WHERE line=?'
    params: list = [line]
    if since:
        sql += ' AND as_of>=?'
        params.append(since)
    if until:
        sql += ' AND as_of<=?'
        params.append(until)
    sql += ' ORDER BY as_of'
    return _rows_to_snaps(connect().execute(sql, params).fetchall())


def latest(line: str, on: str | None = None, *, partial_ok: bool = False) -> dict | None:
    """「不晚于 on」的最新一期；默认跳过 partial（历史回填的近似值）。"""
    sql = 'SELECT payload FROM snapshot WHERE line=?'
    params: list = [line]
    if not partial_ok:
        sql += ' AND partial=0'
    if on:
        sql += ' AND as_of<=?'
        params.append(on)
    sql += ' ORDER BY as_of DESC LIMIT 1'
    row = connect().execute(sql, params).fetchone()
    return json.loads(row['payload']) if row else None


def dates(line: str) -> list[str]:
    return [r[0] for r in connect().execute(
        'SELECT as_of FROM snapshot WHERE line=? ORDER BY as_of', (line,))]


def all_dates() -> list[str]:
    return [r[0] for r in connect().execute('SELECT DISTINCT as_of FROM snapshot ORDER BY as_of')]


def delete_snapshot(line: str, as_of: str) -> bool:
    cur = connect().execute('DELETE FROM snapshot WHERE line=? AND as_of=?', (line, as_of))
    _bump()
    return bool(cur.rowcount)


def line_stats() -> list[dict]:
    rows = connect().execute(
        'SELECT line, MAX(as_of) AS as_of, COUNT(*) AS count, MAX(updated_at) AS updated_at'
        ' FROM snapshot GROUP BY line').fetchall()
    return [dict(r) for r in rows]


def stats() -> dict:
    conn = connect()
    one = lambda sql: conn.execute(sql).fetchone()[0]      # noqa: E731
    return {
        'ok': True, 'db': str(db_path()),
        'schema': conn.execute('PRAGMA user_version').fetchone()[0],
        'size_mb': round(db_path().stat().st_size / 1048576, 2) if db_path().exists() else 0,
        'snapshots': one('SELECT COUNT(*) FROM snapshot'),
        'lines': one('SELECT COUNT(DISTINCT line) FROM snapshot'),
        'source_files': one('SELECT COUNT(*) FROM source_file'),
        'imports': one('SELECT COUNT(*) FROM import_log'),
        'latest': one('SELECT MAX(as_of) FROM snapshot'),
        'lines_detail': line_stats(),
    }


# ---------------------------------------------------------------- 缓存（进程内，短 TTL）
def _cache_get(line: str) -> list[dict] | None:
    with _lock:
        hit = _cache.get(line)
    if not hit:
        return None
    gen, ts, snaps = hit
    if gen != _gen or time.time() - ts > CACHE_TTL:
        return None
    return snaps


def _cache_put(line: str, snaps: list[dict]) -> None:
    with _lock:
        _cache[line] = (_gen, time.time(), snaps)


# ---------------------------------------------------------------- 导入台账 / 原始文件
def log_import(rec: dict) -> int:
    rec = dict(rec or {})
    files = rec.get('files') or []
    files = [f if isinstance(f, str) else f.get('name', '') for f in files]
    cur = connect().execute(
        'INSERT INTO import_log(ts, line, data_date, ok, error, note, archive, files, snapshot_id)'
        ' VALUES(?,?,?,?,?,?,?,?,?)',
        (rec.get('ts') or _now(), rec.get('line') or '', rec.get('data_date'),
         1 if rec.get('ok') else 0, rec.get('error'), rec.get('note'), rec.get('archive'),
         json.dumps(files, ensure_ascii=False), rec.get('snapshot_id')))
    return int(cur.lastrowid or 0)


def recent_imports(limit: int = 12, allow: set[str] | None = None) -> list[dict]:
    sql = 'SELECT * FROM import_log'
    params: list = []
    if allow is not None:
        allow = set(allow)
        if not allow:
            return []
        sql += f' WHERE line IN ({",".join("?" * len(allow))})'
        params = list(allow)
    sql += ' ORDER BY ts DESC, id DESC LIMIT ?'
    params.append(limit)
    out = []
    for r in connect().execute(sql, params):
        d = dict(r)
        try:
            d['files'] = json.loads(d.get('files') or '[]')
        except Exception:
            d['files'] = []
        d['ok'] = bool(d.get('ok'))
        out.append(d)
    return out


def add_source_files(line: str, snapshot_id: int | None, files, archive: Path) -> int:
    """files: [(name, blob)]；归档目录已由 viz.archive 写好。"""
    now = _now()
    n = 0
    conn = connect()
    for name, blob in files:
        conn.execute(
            'INSERT INTO source_file(snapshot_id, line, name, sha256, bytes, path, archive, created_at)'
            ' VALUES(?,?,?,?,?,?,?,?)',
            (snapshot_id, line, name, hashlib.sha256(blob).hexdigest(), len(blob),
             str(Path(archive) / safe_name(name)), str(archive), now))
        n += 1
    return n


# ---------------------------------------------------------------- 备份
def backup_to(target: Path) -> Path:
    """热备份（sqlite 在线备份 API），不用停服务。"""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    dst = sqlite3.connect(str(target))
    try:
        connect().backup(dst)
    finally:
        dst.close()
    return target


# ---------------------------------------------------------------- 旧 JSON 迁移（一次性）
def import_legacy(root_dir=None) -> dict:
    """把 data/snapshots/*.json 与 ledger.jsonl 灌进库；幂等，但不重复做（有 setting 标记）。

    只在"第一次迁移"时生效；之后 JSON 目录会被 scripts/migrate_to_sqlite.py 挪走。
    """
    base = Path(root_dir or _root)
    snap_dir = base / 'snapshots'
    ledger_file = base / 'ledger.jsonl'
    out = {'snapshots': 0, 'ledger': 0, 'moved': False}
    if not snap_dir.exists() and not ledger_file.exists():
        return out
    if get('legacy_json_imported'):
        return out
    line_dirs = sorted(p for p in snap_dir.glob('*') if p.is_dir()) if snap_dir.exists() else []
    for line_dir in line_dirs:
        line = line_dir.name
        for f in sorted(line_dir.glob('*.json')):
            try:
                snap = json.loads(f.read_text('utf-8'))
            except Exception:
                continue
            as_of = snap.get('as_of') or f.stem
            save_snapshot(line, as_of, snap, source=f'legacy-json:{f.name}')
            out['snapshots'] += 1
    if ledger_file.exists():
        for raw in ledger_file.read_text('utf-8').splitlines():
            if not raw.strip():
                continue
            try:
                rec = json.loads(raw)
            except Exception:
                continue
            log_import(rec)
            out['ledger'] += 1
    set_setting('legacy_json_imported', {'at': _now(), **out})
    return out
