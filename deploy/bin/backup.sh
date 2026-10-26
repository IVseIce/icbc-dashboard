#!/bin/bash
# backup.sh —— 热备份数据库（不用停服务）；保留最近 KEEP 份
set -u
. "$(dirname "$0")/env.sh"
require_python
KEEP=${KEEP:-30}
exec "$PY" "$CURRENT/scripts/backup_db.py" --root "$DATA_DIR" --keep "$KEEP"
