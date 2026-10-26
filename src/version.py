#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""version.py —— 读发布版本号（打包时写入 `VERSION`，仓库里没有就是 dev）。

版本号格式：`YYYY.MM.DD-<git短sha>`，例：`2026.10.23-b485425`。
部署后用它确认"这台机器上跑的到底是哪个版本"。
"""
from __future__ import annotations

from pathlib import Path

_CACHE: str | None = None


def app_version() -> str:
    global _CACHE
    if _CACHE:
        return _CACHE
    root = Path(__file__).resolve().parent.parent
    for name in ('VERSION', 'version.txt'):
        p = root / name
        if p.exists():
            txt = p.read_text('utf-8').strip()
            if txt:
                _CACHE = txt.splitlines()[0].strip()
                return _CACHE
    _CACHE = 'dev'
    return _CACHE
