#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""version.py —— 版本号与构建信息。

* `VERSION`：语义化版本，仓库里维护（0.1.0 → 0.1.1 …），打包时原样带入
* `BUILD`：只有发布包里才有，记录 `日期-git短sha[-dirty]`，用于追溯

部署后 `bin/status.sh`、`/api/health`、侧栏左下角都能核对跑的是哪一版。
"""
from __future__ import annotations

from pathlib import Path

_CACHE: str | None = None
_BUILD: str | None = None


def _read(name: str) -> str | None:
    p = Path(__file__).resolve().parent.parent / name
    if not p.exists():
        return None
    txt = p.read_text('utf-8').strip()
    return txt.splitlines()[0].strip() if txt else None


def app_version() -> str:
    global _CACHE
    if not _CACHE:
        _CACHE = _read('VERSION') or 'dev'
    return _CACHE


def build_info() -> str:
    """发布日期 + 提交号；非发布包返回 dev。"""
    global _BUILD
    if not _BUILD:
        _BUILD = _read('BUILD') or 'dev'
    return _BUILD


def version_label() -> str:
    b = build_info()
    return f'{app_version()} ({b})' if b and b != 'dev' else app_version()
