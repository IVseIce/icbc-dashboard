#!/bin/bash
# supervise.sh —— 看门狗：应用退出后自动拉起（内网机没有 systemd，靠这个保活）。
# 由 start.sh 以 nohup 方式启动；不要手动跑两份。
set -u
. "$(dirname "$0")/env.sh"
require_python

APP_PID=""
log() { echo "[supervise] $(date '+%F %T') $*"; }

stop_app() {
    if [ -n "$APP_PID" ] && kill -0 "$APP_PID" 2>/dev/null; then
        kill -TERM "$APP_PID" 2>/dev/null
        for _ in 1 2 3 4 5 6 7 8 9 10; do
            kill -0 "$APP_PID" 2>/dev/null || break
            sleep 0.5
        done
        kill -0 "$APP_PID" 2>/dev/null && kill -KILL "$APP_PID" 2>/dev/null
    fi
    exit 0
}
trap stop_app TERM INT HUP

log "supervisor 启动 pid=$$ home=$ICBC_HOME port=$PORT"
while : ; do
    log "启动应用：$CURRENT/run.py"
    "$PY" "$CURRENT/run.py" --host "$HOST" --port "$PORT" --root "$DATA_DIR" &
    APP_PID=$!
    wait "$APP_PID"
    rc=$?
    APP_PID=""
    log "应用退出 rc=$rc，3 秒后重启"
    sleep 3
done
