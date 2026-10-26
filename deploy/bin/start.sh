#!/bin/bash
# start.sh —— 后台启动（已启动则什么都不做）
set -u
. "$(dirname "$0")/env.sh"
require_python

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE" 2>/dev/null)" 2>/dev/null; then
    echo "已在运行：pid=$(cat "$PID_FILE")"
    exit 0
fi

if ! port_free; then
    echo "!! 端口 $PORT 已被占用，先停掉占用的进程（或改 ICBC_PORT）" >&2
    exit 1
fi

mkdir -p "$LOG_DIR"
echo "[start] $(date '+%F %T') 启动" >> "$APP_LOG"
nohup bash "$ICBC_HOME/bin/supervise.sh" >> "$APP_LOG" 2>&1 &
echo $! > "$PID_FILE"

if health_wait 20; then
    echo "已启动：pid=$(cat "$PID_FILE")  日志 $APP_LOG"
    for ip in $(local_ips); do
        echo "  访问 http://$ip:$PORT/"
    done
else
    echo "!! 启动后 20 秒内健康检查没通过，看日志：$APP_LOG" >&2
    tail -n 20 "$APP_LOG" >&2 || true
    exit 1
fi
