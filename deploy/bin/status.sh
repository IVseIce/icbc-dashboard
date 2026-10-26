#!/bin/bash
# status.sh —— 一眼看清：进程在不在、跑的是哪个版本、健康检查、库里有几期
set -u
. "$(dirname "$0")/env.sh"

echo "ICBC 驾驶舱状态"
echo "  目录    $ICBC_HOME"
_ver=$(cat "$CURRENT/VERSION" 2>/dev/null || echo '?')
_build=$(cat "$CURRENT/BUILD" 2>/dev/null || echo '')
echo "  版本    $_ver${_build:+  ($_build)}  ($(readlink -f "$CURRENT" 2>/dev/null || echo '无 current'))"
echo "  解释器  ${PY:-未配置}"
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE" 2>/dev/null)" 2>/dev/null; then
    echo "  进程    运行中 pid=$(cat "$PID_FILE")"
else
    echo "  进程    未运行"
fi
echo -n "  健康    "
if h=$(health_json 2>/dev/null); then
    echo "$h"
else
    echo "不通（端口 $PORT）"
fi
echo "  库      $(ls -lh "$DATA_DIR/icbc.db" 2>/dev/null | awk '{print $5, $9}' || echo '无')"
echo "  日志    $APP_LOG"
[ -f "$CURRENT/scripts/selftest.py" ] && PYTHONPATH="$CURRENT/vendor/pylib" "$PY" "$CURRENT/scripts/selftest.py" --root "$DATA_DIR" | sed 's/^/  /'
