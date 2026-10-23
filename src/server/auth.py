#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""auth.py —— 口令准入：六个身份组、服务端会话、口令哈希落盘。

这不是账号体系，只有"一组一个口令"：

* 五个大类（个金/网金/个贷/银行卡/私银）各一个口令；登录后额外获得「重点项目」
* 管理员一个口令：全部板块 + 重置上面六个口令
* 会话只活在两处内存里（服务端内存 + 前端 JS 变量）：
  刷新页面、关掉网页、重启服务都要重新验证 —— 这是需求，不是缺陷

口令只存 pbkdf2 哈希（`data/auth.json`，git 忽略）。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from pathlib import Path

# 身份组：id 与 PROFESSIONALS 的 id 对齐（admin 除外）
ROLES = [
    {'id': 'jg', 'name': '个金', 'full': '个人金融'},
    {'id': 'wj', 'name': '网金', 'full': '网络金融'},
    {'id': 'loan', 'name': '个贷', 'full': '个人贷款'},
    {'id': 'card', 'name': '银行卡', 'full': '银行卡'},
    {'id': 'pbs', 'name': '私银', 'full': '私人银行'},
    {'id': 'admin', 'name': '管理员', 'full': '系统管理员'},
]
ROLE_IDS = [r['id'] for r in ROLES]

# 首次启动的初始口令（管理员登录后应立刻在「管理密码」里改掉）
DEFAULTS = {
    'jg': 'gejin2026',
    'wj': 'wangjin2026',
    'loan': 'gedai2026',
    'card': 'yinhangka2026',
    'pbs': 'siyin2026',
    'admin': 'admin2026',
}

PROJECT = 'project'
ALL_PROF = ['jg', 'wj', 'loan', 'card', 'pbs', PROJECT]

_SESSION_TTL = 12 * 3600      # 服务端会话闲置 12 小时失效（前端刷新即失效）
_ITER = 120_000
_lock = threading.Lock()
_sessions: dict[str, dict] = {}


# ---------------------------------------------------------------- 存储
def _path() -> Path:
    import viz                                  # 延迟导入：ROOT 可能被 --root 改写
    return Path(viz.ROOT) / 'auth.json'


def _digest(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'),
                               bytes.fromhex(salt), _ITER).hex()


def _fresh() -> dict:
    salt = secrets.token_hex(16)
    return {'version': 1, 'salt': salt,
            'roles': {rid: _digest(DEFAULTS[rid], salt) for rid in ROLE_IDS}}


def _load() -> dict:
    p = _path()
    if not p.exists():
        data = _fresh()
        _write(data)
        return data
    try:
        data = json.loads(p.read_text('utf-8'))
        if not data.get('salt') or not isinstance(data.get('roles'), dict):
            raise ValueError('bad auth.json')
    except Exception:
        # 文件损坏：留一份 .bad 便于排查，然后回到初始口令
        try:
            p.replace(p.with_suffix('.json.bad'))
        except OSError:
            pass
        data = _fresh()
        _write(data)
    return data


def _write(data: dict) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), 'utf-8')
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass


# ---------------------------------------------------------------- 口令
def verify(password: str) -> str | None:
    """口令 → 身份组 id；不匹配返回 None（只比哈希，不落明文）。"""
    pw = (password or '').strip()
    if not pw:
        return None
    data = _load()
    digest = _digest(pw, data['salt'])
    hit = None
    for rid in ROLE_IDS:
        stored = data['roles'].get(rid) or ''
        if stored and hmac.compare_digest(stored, digest) and hit is None:
            hit = rid
    return hit


def set_password(role: str, password: str) -> dict:
    """管理员重置某个身份组的口令。"""
    if role not in ROLE_IDS:
        return {'ok': False, 'error': f'未知身份组：{role}'}
    pw = (password or '').strip()
    if len(pw) < 6:
        return {'ok': False, 'error': '口令至少 6 位'}
    data = _load()
    data['roles'][role] = _digest(pw, data['salt'])
    _write(data)
    return {'ok': True, 'role': role, 'label': label_of(role)}


# ---------------------------------------------------------------- 会话
def scope_of(role: str) -> list[str]:
    if role == 'admin':
        return list(ALL_PROF)
    return [role, PROJECT]


def label_of(role: str) -> str:
    for r in ROLES:
        if r['id'] == role:
            return r['name']
    return role


def _public(role: str) -> dict:
    return {'role': role, 'label': label_of(role),
            'admin': role == 'admin', 'scope': scope_of(role)}


def login(password: str) -> dict | None:
    """校验口令 → 发一个只存在内存里的 token。"""
    role = verify(password)
    if not role:
        time.sleep(0.25)          # 慢一点，挡住脚本暴力试口令
        return None
    token = secrets.token_hex(24)
    now = time.time()
    with _lock:
        # 顺手清掉过期会话，避免长期运行后无限增长
        for k in [k for k, v in _sessions.items() if now - v['ts'] > _SESSION_TTL]:
            _sessions.pop(k, None)
        _sessions[token] = {'role': role, 'ts': now}
    return {'token': token, **_public(role)}


def session(token: str | None) -> dict | None:
    if not token:
        return None
    now = time.time()
    with _lock:
        s = _sessions.get(token)
        if not s:
            return None
        if now - s['ts'] > _SESSION_TTL:
            _sessions.pop(token, None)
            return None
        s['ts'] = now
    return {'token': token, **_public(s['role'])}


def logout(token: str | None) -> None:
    if not token:
        return
    with _lock:
        _sessions.pop(token, None)


def can(sess: dict | None, prof: str) -> bool:
    if not sess:
        return False
    return prof in sess.get('scope') or sess.get('admin', False)
