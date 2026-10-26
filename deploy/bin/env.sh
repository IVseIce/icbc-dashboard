#!/bin/sh
# env.sh —— 被 bin/ 下其它脚本 source，不要直接执行。
#
# 目录约定（全部在用户 home 下，内网机没有 root 也能装）：
#   $ICBC_HOME/current            -> releases/<version>   代码（只读，升级只换软链）
#   $ICBC_HOME/releases/<ver>/    每次拷进来的版本
#   $ICBC_HOME/shared/data/       icbc.db / imports / backups / auth.json  ← 永远不随版本覆盖
#   $ICBC_HOME/shared/logs/       app.log / autostart.log / update.log
#   $ICBC_HOME/bin/               start/stop/status/backup/update ...

ICBC_HOME=${ICBC_HOME:-$HOME/icbc-dashboard}
export ICBC_HOME

SHARED="$ICBC_HOME/shared"
DATA_DIR=${ICBC_DATA:-$SHARED/data}
LOG_DIR="$SHARED/logs"
CURRENT="$ICBC_HOME/current"
PY_FILE="$SHARED/python.path"
PID_FILE="$LOG_DIR/app.pid"
APP_LOG="$LOG_DIR/app.log"
PORT=${ICBC_PORT:-8766}
HOST=${ICBC_HOST:-0.0.0.0}

mkdir -p "$DATA_DIR" "$LOG_DIR" 2>/dev/null || true

# 内网代理环境可能把 127.0.0.1 也代理掉，健康检查必须直连
no_proxy="127.0.0.1,localhost${no_proxy:+,$no_proxy}"
NO_PROXY="$no_proxy"
export no_proxy NO_PROXY

if [ -f "$PY_FILE" ]; then
    PY=$(cat "$PY_FILE" 2>/dev/null)
fi
PY=${PY:-}
export PY
export PYTHONPATH="$CURRENT/vendor/pylib${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONIOENCODING=utf-8
export PYTHONUNBUFFERED=1

require_python() {
    if [ -z "${PY:-}" ] || [ ! -x "$PY" ]; then
        echo "!! 没有可用的 Python：$PY_FILE 缺失或指向的解释器不存在" >&2
        echo "   跑一次 $ICBC_HOME/bin/install.sh 或 deploy/install.sh 重新探测" >&2
        exit 1
    fi
}

# 打印健康检查 JSON；服务没起来时返回非 0
health_json() {
    "$PY" - "$PORT" <<'PY'
import json, sys, urllib.request
port = sys.argv[1]
try:
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health', timeout=3) as r:
        sys.stdout.write(r.read().decode('utf-8'))
except Exception as exc:
    print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False))
    raise SystemExit(1)
PY
}

# health_wait <秒>
health_wait() {
    _n=${1:-15}
    _i=0
    while [ "$_i" -lt "$_n" ]; do
        if health_json >/dev/null 2>&1; then
            return 0
        fi
        _i=$((_i + 1))
        sleep 1
    done
    return 1
}

port_free() {
    "$PY" - "$PORT" <<'PY'
import socket, sys
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    s.bind(('0.0.0.0', int(sys.argv[1])))
except OSError:
    raise SystemExit(1)
finally:
    s.close()
PY
}

local_ips() {
    "$PY" - <<'PY'
import socket
ips = set()
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(('223.5.5.5', 80))
    ips.add(s.getsockname()[0])
    s.close()
except Exception:
    pass
try:
    for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
        ips.add(info[4][0])
except Exception:
    pass
print(' '.join(sorted(i for i in ips if not i.startswith('127.'))))
PY
}
