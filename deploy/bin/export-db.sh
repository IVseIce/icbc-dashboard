#!/bin/bash
# export-db.sh [目标目录] —— 导出 .db 副本 + 清单（默认导出到当前目录）
set -u
. "$(dirname "$0")/env.sh"
require_python
OUT=${1:-$(pwd)}
exec "$PY" "$CURRENT/scripts/export_db.py" --root "$DATA_DIR" --out "$OUT"
