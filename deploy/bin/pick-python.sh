#!/bin/sh
# pick-python.sh —— 被 install.sh / update.sh source。
# 选解释器：优先包内便携运行时（架构匹配且自检通过），否则系统 python3（>=3.8 且自检通过）。

_selftest_ok() {  # $1=解释器 $2=release 目录 $3=数据目录
    # 加超时：万一某个解释器在这台机器上一跑就卡住，不能把安装/升级也卡死
    if command -v timeout >/dev/null 2>&1; then
        timeout 25 env PYTHONPATH="$2/vendor/pylib" "$1" "$2/scripts/selftest.py" --root "$3" >/dev/null 2>&1
    else
        PYTHONPATH="$2/vendor/pylib" "$1" "$2/scripts/selftest.py" --root "$3" >/dev/null 2>&1
    fi
}

pick_python() {   # 成功时把路径打到 stdout
    _rel=$1
    _data=$2
    _entry="bin/python3"
    [ -f "$_rel/runtime/PYTHON" ] && _entry=$(tr -d ' \r\n' < "$_rel/runtime/PYTHON")
    _bundled="$_rel/runtime/$_entry"

    if [ -f "$_rel/runtime/ARCH" ] && [ -x "$_bundled" ]; then
        _arch=$(cat "$_rel/runtime/ARCH" 2>/dev/null)
        if [ "$_arch" = "$(uname -m)" ]; then
            if _selftest_ok "$_bundled" "$_rel" "$_data"; then
                echo "$_bundled"
                return 0
            fi
            echo "!! 内置运行时（$_arch）自检没通过，回退系统 python3" >&2
        else
            echo "!! 内置运行时是 $_arch，本机是 $(uname -m)，忽略它" >&2
        fi
    fi

    for _c in python3.13 python3.12 python3.11 python3.10 python3.9 python3.8 python3; do
        _p=$(command -v "$_c" 2>/dev/null) || continue
        [ -n "$_p" ] || continue
        if _selftest_ok "$_p" "$_rel" "$_data"; then
            echo "$_p"
            return 0
        fi
    done
    return 1
}
