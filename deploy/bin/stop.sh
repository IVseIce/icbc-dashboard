#!/bin/bash
# stop.sh —— 停止（先 TERM 让看门狗带走子进程，10 秒不退再 KILL）
set -u
. "$(dirname "$0")/env.sh"

if [ ! -f "$PID_FILE" ]; then
    echo "没有 pid 文件，可能本来就没启动"
    rm -f "$PID_FILE"
    exit 0
fi
pid=$(cat "$PID_FILE" 2>/dev/null)
if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
    echo "进程已不在（清掉 pid 文件）"
    rm -f "$PID_FILE"
    exit 0
fi

kill -TERM "$pid" 2>/dev/null
for _ in $(seq 1 20); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.5
done
if kill -0 "$pid" 2>/dev/null; then
    echo "TERM 后仍在，强制 KILL"
    kill -KILL "$pid" 2>/dev/null
fi
rm -f "$PID_FILE"
# 兜底：看门狗被 KILL 时子进程可能残留
"$PY" - "$PORT" <<'PY' 2>/dev/null || true
import sys, urllib.request
port = sys.argv[1]
try:
    urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health', timeout=1)
except Exception:
    raise SystemExit(0)
raise SystemExit(0)
PY
echo "已停止"
