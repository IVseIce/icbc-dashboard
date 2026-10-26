#!/bin/bash
# install.sh —— 首次部署（可重复执行，等于"修复安装"）。
#
#   bash deploy/install.sh <包目录 | 包.tar.gz>
#
# 做的事：建目录树 → 把包放进 releases/<版本> → 选解释器 → 切 current → 启动 → 装开机自启。
# 数据目录 shared/data 永远不动，所以重装/升级都不会丢库。
set -euo pipefail

usage() { echo "用法: bash deploy/install.sh <包目录 | 包.tar.gz>"; exit 2; }
[ $# -ge 1 ] || usage
SRC=$1
[ -e "$SRC" ] || { echo "找不到：$SRC" >&2; exit 2; }

ICBC_HOME=${ICBC_HOME:-$HOME/icbc-dashboard}
SHARED="$ICBC_HOME/shared"
DATA_DIR=${ICBC_DATA:-$SHARED/data}
LOG_DIR="$SHARED/logs"
CURRENT="$ICBC_HOME/current"
BIN="$ICBC_HOME/bin"

echo "== ICBC 驾驶舱 安装 =="
echo "   目标目录 $ICBC_HOME"

mkdir -p "$ICBC_HOME/releases" "$DATA_DIR" "$LOG_DIR" "$BIN"

# ---------- 1. 取包
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
case "$SRC" in
  *.tar.gz|*.tgz)
      echo "   解包 $SRC"
      tar -xzf "$SRC" -C "$TMP"
      PKG=$(find "$TMP" -maxdepth 2 -name VERSION -printf '%h\n' 2>/dev/null | head -n 1)
      ;;
  *)  PKG=$SRC ;;
esac
[ -n "${PKG:-}" ] && [ -f "$PKG/VERSION" ] || { echo "包不完整：没找到 VERSION" >&2; exit 1; }
VER=$(tr -d ' \r\n' < "$PKG/VERSION")
echo "   版本 $VER"

RELEASE="$ICBC_HOME/releases/$VER"
OLD=""
[ -L "$CURRENT" ] && OLD=$(readlink -f "$CURRENT")

# ---------- 2. 已有库就先备份一份（重装/修复时不至于丢数据）
if [ -f "$DATA_DIR/icbc.db" ] && [ -x "$BIN/backup.sh" ]; then
    echo "   已有数据库，先备份..."
    bash "$BIN/backup.sh" >>"$LOG_DIR/install.log" 2>&1 || echo "   ! 备份失败，继续（可用 update.sh 的标准流程）"
fi

# ---------- 3. 停服务（如果已经在跑）
if [ -x "$BIN/stop.sh" ] && [ -f "$LOG_DIR/app.pid" ]; then
    bash "$BIN/stop.sh" || true
fi

# ---------- 4. 放代码
rm -rf "$RELEASE"
mkdir -p "$RELEASE"
cp -a "$PKG/." "$RELEASE/"
if [ -d "$RELEASE/runtime" ]; then
    find "$RELEASE/runtime/bin" -type f -exec chmod +x {} + 2>/dev/null || true
fi

# ---------- 5. 装运维脚本
cp -f "$RELEASE/deploy/bin/"*.sh "$BIN/"
chmod 755 "$BIN"/*.sh
cat > "$BIN/autostart.sh" <<EOF
#!/bin/sh
# 登录后自启（由 ~/.config/autostart/icbc-dashboard.desktop 调用）
sleep 5
exec $BIN/start.sh >> $LOG_DIR/autostart.log 2>&1
EOF
chmod 755 "$BIN/autostart.sh"

# ---------- 6. 选解释器
echo "   探测 Python..."
. "$RELEASE/deploy/bin/pick-python.sh"
if ! PYPATH=$(pick_python "$RELEASE" "$DATA_DIR"); then
    echo "!! 找不到可用的 Python（需要 >=3.8，且能用 vendor/pylib 里的依赖）" >&2
    echo "   排查：PYTHONPATH=$RELEASE/vendor/pylib python3 $RELEASE/scripts/selftest.py" >&2
    exit 1
fi
printf '%s\n' "$PYPATH" > "$SHARED/python.path"
echo "   解释器 $PYPATH"

# ---------- 7. 切 current
ln -sfn "$RELEASE" "$CURRENT"
echo "   current -> $RELEASE"

# ---------- 8. 启动
bash "$BIN/start.sh"

# ---------- 9. 开机自启（XDG autostart，麒麟 UKUI 上实测有效；不需要 root）
if [ "${ICBC_NO_AUTOSTART:-0}" = "1" ]; then
    echo "   跳过开机自启（ICBC_NO_AUTOSTART=1）"
else
AUTO_DIR="$HOME/.config/autostart"
mkdir -p "$AUTO_DIR"
cat > "$AUTO_DIR/icbc-dashboard.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=ICBC 经营驾驶舱
Comment=阜阳分行个人金融经营驾驶舱（局域网 Web）
Exec=$BIN/autostart.sh
Terminal=false
Hidden=false
X-GNOME-Autostart-enabled=true
X-MATE-Autostart-enabled=true
EOF
echo "   已装开机自启：$AUTO_DIR/icbc-dashboard.desktop"
fi

[ -n "$OLD" ] && [ "$OLD" != "$RELEASE" ] && echo "   旧版本保留在 $OLD（回滚可用）"

echo
echo "== 完成 =="
echo "   版本 $VER"
echo "   数据 $DATA_DIR"
echo "   日志 $LOG_DIR/app.log"
echo "   检查 bash $BIN/status.sh"
