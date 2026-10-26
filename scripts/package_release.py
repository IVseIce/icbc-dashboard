#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""package_release.py —— 打一个可以拷进 U 盘的发布包。

产出（默认在 dist/）：
  icbc-<version>/                      目录（exFAT 上直接拷目录也能用，脚本用 sh 启动）
  icbc-<version>.tar.gz                推荐：tar 能保住权限位与符号链接
  icbc-<version>.tar.gz.sha256         校验用（拷到内网机后先核对）

版本号默认 `YYYY.MM.DD-<git短sha>`；工作区有未提交改动时会加 `-dirty` 并告警。

  python scripts/package_release.py                       # 普通打包
  python scripts/package_release.py --runtime ~/py312-arm --arch aarch64
                                                          # 带上便携 Python 运行时

包内**不含** data/（数据库留在内网机）、docs/、.git/、__pycache__。
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
DIST = PROJECT / 'dist'
NAME = 'icbc-dashboard'

INCLUDE = ['run.py', 'requirements.txt', 'README.md', 'src', 'scripts', 'deploy', 'vendor/pylib']
EXCLUDE_DIRS = {'__pycache__', '.git', '.idea', '.pytest_cache', 'node_modules', 'dist', 'data'}
EXCLUDE_SUFFIX = {'.pyc', '.pyo', '.swp', '.DS_Store'}

ARCH_BY_ELF = {0x3E: 'x86_64', 0xB7: 'aarch64', 0x28: 'armv7l'}


def sh(*cmd: str) -> str:
    try:
        return subprocess.run(cmd, cwd=PROJECT, capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception:
        return ''


def git_version() -> tuple[str, bool]:
    sha = sh('git', 'rev-parse', '--short', 'HEAD') or 'nogit'
    dirty = bool(sh('git', 'status', '--porcelain'))
    return f'{datetime.now().strftime("%Y.%m.%d")}-{sha}' + ('-dirty' if dirty else ''), dirty


def elf_arch(path: Path) -> str | None:
    """读 ELF 头判断架构（不依赖 file/readelf）。"""
    try:
        with path.open('rb') as f:
            head = f.read(20)
        if head[:4] != b'\x7fELF':
            return None
        machine = int.from_bytes(head[18:20], 'little')
        return ARCH_BY_ELF.get(machine, hex(machine))
    except Exception:
        return None


def ignore(directory: str, names: list[str]) -> set[str]:
    out = set()
    for n in names:
        p = Path(directory) / n
        if n in EXCLUDE_DIRS or p.suffix in EXCLUDE_SUFFIX:
            out.add(n)
    return out


def copy_tree(src: Path, dst: Path) -> None:
    if not src.exists():
        print(f'  ! 跳过不存在的 {src.relative_to(PROJECT)}', file=sys.stderr)
        return
    if src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return
    shutil.copytree(src, dst, ignore=ignore, dirs_exist_ok=True)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def write_checksums(root: Path) -> Path:
    lines = []
    for p in sorted(root.rglob('*')):
        if p.is_file() and p.name != 'SHA256SUMS':
            lines.append(f'{sha256_file(p)}  {p.relative_to(root).as_posix()}')
    out = root / 'SHA256SUMS'
    out.write_text('\n'.join(lines) + '\n', 'utf-8')
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--version', default=None, help='手动指定版本号')
    ap.add_argument('--runtime', default=None, help='便携 Python 目录（含 bin/python3）')
    ap.add_argument('--arch', default='aarch64', help='运行时架构，默认 aarch64（麒麟机）')
    ap.add_argument('--no-tar', action='store_true', help='只产出目录，不压缩')
    ap.add_argument('--allow-dirty', action='store_true', help='工作区有未提交改动也照样打包')
    a = ap.parse_args()

    version, dirty = (a.version, False) if a.version else git_version()
    if dirty and not a.allow_dirty:
        print('!! 工作区有未提交改动。发布包建议从干净提交打；确认无误加 --allow-dirty。', file=sys.stderr)
        sys.exit(2)
    if dirty:
        print('!! 警告：工作区是 dirty 状态，包内含未提交改动', file=sys.stderr)

    DIST.mkdir(exist_ok=True)
    stage = DIST / f'{NAME}-{version}'
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    for item in INCLUDE:
        copy_tree(PROJECT / item, stage / item)

    if a.runtime:
        rt = Path(a.runtime).expanduser().resolve()
        py = rt / 'bin' / 'python3'
        if not py.exists():
            print(f'!! 运行时里找不到 {py}', file=sys.stderr)
            sys.exit(2)
        real = elf_arch(py)
        if real != a.arch:
            print(f'!! 运行时架构是 {real}，与 --arch {a.arch} 不一致（拷到目标机会跑不起来）',
                  file=sys.stderr)
            sys.exit(2)
        copy_tree(rt, stage / 'runtime')
        (stage / 'runtime' / 'ARCH').write_text(a.arch + '\n', 'utf-8')
        (stage / 'runtime' / 'PYTHON').write_text('bin/python3\n', 'utf-8')
        print(f'  运行时：{rt} → runtime/（{a.arch}）')

    (stage / 'VERSION').write_text(version + '\n', 'utf-8')
    # 给目录里加一句怎么装，免得 U 盘里翻文档
    (stage / 'HOW-TO-INSTALL.txt').write_text(
        '把整个目录拷到内网机，然后执行：\n'
        f'  cd {stage.name} && bash deploy/install.sh .\n'
        '以后升级就在新包里执行：\n'
        f'  bash {stage.name}/deploy/update.sh .\n'
        '（也可以用 deploy/ 里的 start/stop/status/backup/export-db 脚本）\n', 'utf-8')

    write_checksums(stage)
    size = sum(p.stat().st_size for p in stage.rglob('*') if p.is_file())
    print(f'目录：{stage}  （{size / 1048576:.1f} MB）')

    if not a.no_tar:
        tar_path = DIST / f'{NAME}-{version}.tar.gz'
        tar_path.unlink(missing_ok=True)
        with tarfile.open(tar_path, 'w:gz') as tf:
            tf.add(stage, arcname=stage.name)
        digest = sha256_file(tar_path)
        (DIST / f'{tar_path.name}.sha256').write_text(f'{digest}  {tar_path.name}\n', 'utf-8')
        print(f'压缩：{tar_path}  （{tar_path.stat().st_size / 1048576:.1f} MB）')
        print(f'校验：{digest}')

    print(f'版本：{version}')
    print('拷到 U 盘后，在内网机执行：bash deploy/install.sh .（首次）或 deploy/update.sh .（升级）')


if __name__ == '__main__':
    main()
