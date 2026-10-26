#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""compat.py —— Python 3.8 兼容垫片（目标机回退路径需要）。

为什么留着 3.8 兼容：内网机自带 python3 是 3.8，且装不了东西。部署时优先用包里自带的
便携运行时（3.12）；万一它在这台机器上跑不起来（架构/glibc 不匹配），就回退到系统 python3。
要让回退真的可用，代码就必须在 3.8 上能跑——成本很低，收益是"永远有一条退路"。

3.8 唯一的硬伤是 `zoneinfo`（3.9+）。vendor 进来的 icbc-* 技能在模块顶层 import 它，
这里注入一个最小实现：中国无夏令时，Asia/Shanghai 直接给固定 +08:00。

在 3.9+ 上什么都不做（真 zoneinfo 优先）。
"""
from __future__ import annotations

import sys
from datetime import timedelta, timezone

CST = timezone(timedelta(hours=8), 'CST')


def ensure_zoneinfo() -> bool:
    """缺 zoneinfo 时注入垫片；返回是否真的注入了。"""
    if 'zoneinfo' in sys.modules:
        return False
    try:
        import zoneinfo  # noqa: F401
        return False
    except ImportError:
        pass

    import types

    mod = types.ModuleType('zoneinfo')

    class ZoneInfo:
        """极简替代：忽略时区名，一律 +08:00（本项目只用 Asia/Shanghai）。"""

        def __new__(cls, key=None):
            return CST

    class ZoneInfoNotFoundError(KeyError):
        pass

    mod.ZoneInfo = ZoneInfo
    mod.ZoneInfoNotFoundError = ZoneInfoNotFoundError
    mod.available_timezones = lambda: {'Asia/Shanghai'}
    sys.modules['zoneinfo'] = mod
    return True
