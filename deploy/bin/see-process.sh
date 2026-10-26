#!/bin/bash
# see-process.sh —— 看清楚"到底有哪些进程在跑"（排查/交接时用）
set -u
. "$(dirname "$0")/env.sh"

echo "ICBC 进程"
if [ -f "$PID_FILE" ]; then
    sup=$(cat "$PID_FILE" 2>/dev/null)
    echo "  看门狗   pid=$sup  $([ -d /proc/$sup ] && echo 运行中 || echo 已退出)"
else
    echo "  看门狗   未运行（没有 $PID_FILE）"
fi
ps -eo pid,ppid,etime,rss,args 2>/dev/null | grep -E "icbc-dashboard/(current|releases)|current/run.py" | grep -v grep | while read -r line; do
    echo "  业务     $line"
done
echo "  端口     $(ss -ltnp 2>/dev/null | grep ":$PORT " || echo "未监听 $PORT")"
echo "  日志     $APP_LOG"
