#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""一键启动：python run.py [--port 8766] [--host 0.0.0.0] [--root DIR]

代码在 src/，数据默认在 data/（可用 --root 指向别处）。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'src'))

from server.app import main  # noqa: E402

if __name__ == '__main__':
    main()
