#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""prepare_runtime.py —— 把一份便携 CPython 裁成"够跑本项目"的样子，并标注架构。

目标机（麒麟 V10，arm64）没有网络也没有 pip，所以发布包里可以带一份解释器。
官方 python-build-standalone 的 `install_only` 包解开后 ~87 MB，里面大部分是
tkinter/tcl、pip/setuptools、测试与头文件——本项目都不用。

  python scripts/prepare_runtime.py --src /tmp/arm-python --out runtime-arm64 --arch aarch64

产物里会写两个小文件：
  ARCH     aarch64 / x86_64 …（安装脚本用它和 uname -m 比对）
  PYTHON   bin/python3.12 之类的相对入口（软链在 U 盘上会坏，所以写明真实入口）

注意：开发机若是 x86，就无法执行 arm64 的解释器；这里只做静态检查（ELF 架构 + glibc 符号版本）。
真正能不能跑，由安装时的 selftest 判定，跑不起来会自动回退系统 python。
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ELF_ARCH = {0x3E: 'x86_64', 0xB7: 'aarch64', 0x28: 'armv7l'}

# 本项目用不到的东西（删了不影响 import sqlite3 / ssl / zlib / email / hashlib）
DROP_DIRS = [
    'include', 'share', 'lib/pkgconfig',
    'lib/python3*/test', 'lib/python3*/idlelib', 'lib/python3*/lib2to3',
    'lib/python3*/tkinter', 'lib/python3*/ensurepip', 'lib/python3*/turtle.py',
    'lib/python3*/site-packages/pip', 'lib/python3*/site-packages/setuptools',
    'lib/python3*/site-packages/pkg_resources', 'lib/python3*/site-packages/_distutils_hack',
    'lib/python3*/site-packages/wheel', 'lib/python3*/site-packages/setuptools-*',
    'lib/python3*/site-packages/pip-*',
]
DROP_GLOBS = [
    'lib/tcl*', 'lib/tk*', 'lib/itcl*', 'lib/Tix*', 'lib/thread*', 'lib/libtcl*', 'lib/libtk*',
    'lib/libpython3*.so', 'lib/libpython3.so',
    'lib/python3*/lib-dynload/_tkinter*',
    'lib/python3*/site-packages/*.pth',
    'bin/*-config', 'bin/idle*', 'bin/2to3*', 'bin/pip*', 'bin/pydoc*', 'bin/easy_install*',
    'bin/python', 'bin/python3-config',
]


def elf_arch(path: Path) -> str | None:
    try:
        head = path.open('rb').read(20)
        if head[:4] != b'\x7fELF':
            return None
        return ELF_ARCH.get(int.from_bytes(head[18:20], 'little'))
    except Exception:
        return None


def max_glibc(path: Path) -> str | None:
    """静态看这个 .so 需要的最低 glibc（只查 libpython）。"""
    try:
        out = subprocess.run(['readelf', '--version-info', str(path)],
                             capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return None
    vers = sorted({w for w in out.replace(':', ' ').replace('(', ' ').split() if w.startswith('GLIBC_')},
                  key=lambda s: tuple(int(x) for x in s[6:].split('.') if x.isdigit()))
    return vers[-1] if vers else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True, help='解压后的便携 Python 目录（含 bin/python3）')
    ap.add_argument('--out', required=True, help='输出目录（已存在会被清空）')
    ap.add_argument('--arch', default='aarch64')
    ap.add_argument('--keep-pip', action='store_true', help='保留 pip/setuptools（默认删）')
    a = ap.parse_args()

    src = Path(a.src).expanduser().resolve()
    out = Path(a.out).expanduser().resolve()
    entry = src / 'bin' / 'python3'
    if not entry.exists():
        sys.exit(f'找不到 {entry}')

    real = elf_arch(entry)
    if real != a.arch:
        sys.exit(f'架构不符：{entry} 是 {real or "未知"}，--arch 要求 {a.arch}')

    if out.exists():
        shutil.rmtree(out)
    print(f'复制 {src} → {out}')

    def _ignore(d, names):
        # bin/python 与 bin/python3 通常是指向 python3.x 的软链；解引用会复制出两份 20+MB 二进制
        if Path(d).name == 'bin':
            return {n for n in names if n in ('python', 'python3')
                    and (Path(d) / n).is_symlink()}
        return set()

    shutil.copytree(src, out, symlinks=False, ignore=_ignore)   # 其余软链一律解引用

    removed = 0
    for pat in DROP_DIRS:
        for p in out.glob(pat):
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
                removed += 1
            elif p.exists():
                p.unlink(missing_ok=True)
                removed += 1
    for pat in DROP_GLOBS:
        if pat.endswith('.pth') and a.keep_pip:
            continue
        for p in out.glob(pat):
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
                removed += 1
            elif p.exists():
                p.unlink(missing_ok=True)
                removed += 1

    # 软链形式的 bin/python3 不复制进包（会退化成 20+MB 的重复二进制），写真实入口
    py3 = out / 'bin' / 'python3'
    if not py3.exists():
        cands = sorted((out / 'bin').glob('python3.*'))
        if not cands:
            sys.exit('裁剪后找不到 bin/python3.x')
        py3 = cands[0]
    pyrel = py3.relative_to(out).as_posix()

    libpy = next(iter(sorted((out / 'lib').glob('libpython3*.so.1.0'))), None)
    glibc = max_glibc(libpy) if libpy else None

    (out / 'ARCH').write_text(a.arch + '\n', 'utf-8')
    (out / 'PYTHON').write_text(pyrel + '\n', 'utf-8')

    size = sum(p.stat().st_size for p in out.rglob('*') if p.is_file())
    print(f'裁剪完成：{size / 1048576:.0f} MB（删掉 {removed} 项）')
    print(f'  架构 {a.arch}   入口 {pyrel}   需要 glibc ≥ {glibc or "?"}')
    print('下一步：')
    print(f'  python scripts/package_release.py --runtime {out} --arch {a.arch}')


if __name__ == '__main__':
    main()
