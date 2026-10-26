#!/bin/bash
# update.sh —— 用 U 盘里的新包升级（失败自动回滚）。
#
#   bash update.sh <包目录 | 包.tar.gz> [--force]
#
# 流程：校验包 → 装到 releases/<新版本> → 在数据库副本上预演迁移 → 备份生产库
#       → 停服 → 切 current → 起服 → 健康检查
#       → 任何一步失败：切回旧版本 + 恢复备份的库 + 再起服。
set -uo pipefail

usage() { echo "用法: bash update.sh <包目录 | 包.tar.gz> [--force]"; exit 2; }
SRC=${1:-}
[ -n "$SRC" ] || usage
[ -e "$SRC" ] || { echo "找不到：$SRC" >&2; exit 2; }
FORCE=0
[ "${2:-}" = "--force" ] && FORCE=1

ICBC_HOME=${ICBC_HOME:-$HOME/icbc-dashboard}
SHARED="$ICBC_HOME/shared"
DATA_DIR=${ICBC_DATA:-$SHARED/data}
LOG_DIR="$SHARED/logs"
CURRENT="$ICBC_HOME/current"
BIN="$ICBC_HOME/bin"
UPDLOG="$LOG_DIR/update.log"

mkdir -p "$LOG_DIR"
log() { echo "[$(date '+%F %T')] $*" | tee -a "$UPDLOG"; }

OLD_RELEASE=""
[ -L "$CURRENT" ] && OLD_RELEASE=$(readlink -f "$CURRENT")
OLD_VER=$(cat "$OLD_RELEASE/VERSION" 2>/dev/null || echo 'none')

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# ---------- 1. 解包 + 校验
case "$SRC" in
  *.tar.gz|*.tgz)
      log "解包 $SRC"
      tar -xzf "$SRC" -C "$TMP"
      PKG=$(find "$TMP" -maxdepth 2 -name VERSION -printf '%h\n' 2>/dev/null | head -n 1)
      ;;
  *)  PKG=$SRC ;;
esac
[ -n "${PKG:-}" ] && [ -f "$PKG/VERSION" ] || { log "包不完整：没找到 VERSION"; exit 1; }
VER=$(tr -d ' \r\n' < "$PKG/VERSION")

if [ -f "$PKG/SHA256SUMS" ]; then
    if (cd "$PKG" && sha256sum -c --quiet SHA256SUMS 2>/dev/null); then
        log "校验和 OK"
    else
        log "!! 校验和不匹配，包可能在拷贝中损坏。中止。"
        exit 1
    fi
fi

log "当前版本 $OLD_VER → 新版本 $VER"
if [ "$VER" = "$OLD_VER" ] && [ "$FORCE" -eq 0 ]; then
    log "已经是 $VER，不需要更新（要强制重装加 --force）"
    exit 0
fi

RELEASE="$ICBC_HOME/releases/$VER"
if [ "$RELEASE" = "$OLD_RELEASE" ]; then
    log "同版本强制重装：先停服"
    bash "$BIN/stop.sh" >>"$UPDLOG" 2>&1 || true
fi

# ---------- 2. 装到 releases（先落地，才能用包里的运行时做预演）
log "落地到 $RELEASE"
rm -rf "$RELEASE"
mkdir -p "$RELEASE"
cp -a "$PKG/." "$RELEASE/"
if [ -d "$RELEASE/runtime" ]; then
    find "$RELEASE/runtime/bin" -type f -exec chmod +x {} + 2>/dev/null || true
fi

# ---------- 3. 预演：在数据库副本上跑一遍迁移 + 选解释器
PRE="$TMP/preflight"
mkdir -p "$PRE"
if [ -f "$DATA_DIR/icbc.db" ] && [ -n "$OLD_RELEASE" ] && [ -f "$OLD_RELEASE/scripts/backup_db.py" ]; then
    OLD_PY=$(cat "$SHARED/python.path" 2>/dev/null)
    log "备份并预演（当前解释器 $OLD_PY）"
    PYTHONPATH="$OLD_RELEASE/vendor/pylib" "$OLD_PY" "$OLD_RELEASE/scripts/backup_db.py" \
        --root "$DATA_DIR" --out "$PRE" --keep 0 >/dev/null || { log "!! 预演备份失败"; rm -rf "$RELEASE"; exit 1; }
    PRE_DB=$(find "$PRE" -name 'icbc-*.db' | head -n 1)
    [ -n "$PRE_DB" ] && mv "$PRE_DB" "$PRE/icbc.db"
fi

. "$RELEASE/deploy/bin/pick-python.sh"
if ! NEW_PY=$(pick_python "$RELEASE" "$PRE"); then
    log "!! 新版本自检没通过（或找不到可用 Python），已中止，生产环境未改动"
    PYTHONPATH="$RELEASE/vendor/pylib" python3 "$RELEASE/scripts/selftest.py" --root "$PRE" 2>&1 \
        | sed 's/^/    /' | tee -a "$UPDLOG" >&2
    rm -rf "$RELEASE"
    exit 1
fi
log "新版本解释器 $NEW_PY"

# ---------- 4. 生产备份（回滚点）
ROLLBACK_DB=""
if [ -f "$DATA_DIR/icbc.db" ]; then
    mkdir -p "$DATA_DIR/backups"
    ROLLBACK_DB="$DATA_DIR/backups/pre-${OLD_VER}-to-${VER}-$(date '+%Y%m%d-%H%M%S').db"
    cp -f "$PRE/icbc.db" "$ROLLBACK_DB" 2>/dev/null || cp -f "$DATA_DIR/icbc.db" "$ROLLBACK_DB"
    log "回滚点 $ROLLBACK_DB"
fi

# ---------- 5. 切换
bash "$BIN/stop.sh" >>"$UPDLOG" 2>&1 || true
cp -f "$RELEASE/deploy/bin/"*.sh "$BIN/"
cp -f "$RELEASE/deploy/install.sh" "$RELEASE/deploy/update.sh" "$BIN/"
chmod 755 "$BIN"/*.sh
printf '%s\n' "$NEW_PY" > "$SHARED/python.path"
ln -sfn "$RELEASE" "$CURRENT"
log "current -> $RELEASE"

# ---------- 6. 起服 + 健康检查
if bash "$BIN/start.sh" >>"$UPDLOG" 2>&1; then
    log "更新成功：$VER"
else
    log "!! 新版本启动失败，开始回滚"
    bash "$BIN/stop.sh" >>"$UPDLOG" 2>&1 || true
    if [ -n "$OLD_RELEASE" ] && [ -d "$OLD_RELEASE" ]; then
        ln -sfn "$OLD_RELEASE" "$CURRENT"
        if [ -n "$ROLLBACK_DB" ] && [ -f "$ROLLBACK_DB" ]; then
            rm -f "$DATA_DIR/icbc.db-wal" "$DATA_DIR/icbc.db-shm"
            cp -f "$ROLLBACK_DB" "$DATA_DIR/icbc.db"
            log "已恢复数据库到更新前"
        fi
        bash "$BIN/start.sh" >>"$UPDLOG" 2>&1 || true
        log "已回滚到 $OLD_VER"
    else
        log "!! 没有旧版本可回滚，请人工检查"
    fi
    exit 1
fi

# ---------- 7. 清理旧版本（保留最近 5 个；当前与回滚目标不动）
cd "$ICBC_HOME/releases" || exit 0
ls -1dt */ 2>/dev/null | tail -n +6 | while read -r d; do
    d=${d%/}
    [ "$ICBC_HOME/releases/$d" = "$(readlink -f "$CURRENT")" ] && continue
    [ -n "$OLD_RELEASE" ] && [ "$ICBC_HOME/releases/$d" = "$OLD_RELEASE" ] && continue
    log "清理旧版本 $d"
    rm -rf -- "$ICBC_HOME/releases/$d"
done
