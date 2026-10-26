# 部署与运维（DEPLOY）

> 这份文档记录**现实约束**和据此做的结构决定。改部署方式前先读这里。

---

## 1. 现实约束（2026-10 确认）

| # | 事实 | 对结构的影响 |
|---|---|---|
| 1 | 部署在**内网 Linux 机器**，`0.0.0.0` 对外提供局域网访问 | 必须能后台常驻、开机自启、崩溃自愈；不能依赖交互终端 |
| 2 | **开发维护在本机**（WSL），部署是单向的 | 发布物必须自包含、可校验、可回滚；不在目标机上改代码 |
| 3 | 用 **U 盘**把项目文件夹搬进去 | 目标机**无外网、无 pip、无 root**：依赖必须随包带；拷贝会丢权限位 |
| 4 | **大量、持续的更新需求** | 升级必须一条命令、失败自动回滚；版本与数据必须分离 |
| 5 | 数据库在**内网机器**，但有**对外导出**需求 | 数据目录独立于代码；导出走"热备份 + 清单"，优先 `.db` |

### 目标机实测环境（来自 `kylin-v10-env` 技能）

| 项 | 值 |
|---|---|
| 系统 | 银河麒麟桌面 V10 (SP1)，UKUI，**arm64** |
| 账号 | `001775523`，home `/home/001775523`，**没有 root / sudo** |
| 网络 | 无外网，**pip 不可用** |
| Python | 机器上有 Python 3.8（PyCharm 带的那套，用户评价"不太靠谱"） |
| 可用机制 | `~/.config/autostart/*.desktop` ✅、`systemctl --user` ✅、`gsettings` ✅ |
| 不可用 | 系统级 systemd（要 root）、装包、改系统配置 |
| 已知怪癖 | 开机约 58 秒后有个进程把 dconf 设置打回原值（只影响桌面设置，不影响本项目） |

---

## 2. 结构决定

### 2.1 目录（全部在用户 home 下，不需要 root）

```
~/icbc-dashboard/
├── current -> releases/<版本>        代码（只读；升级只换这个软链）
├── releases/
│   ├── 2026.10.26-b485425/           每次 U 盘搬进来的版本，各自独立
│   └── 2026.10.30-a1b2c3d/
├── shared/                           ★ 唯一会随运行变化的地方
│   ├── data/
│   │   ├── icbc.db                  主库（+ -wal / -shm）
│   │   ├── auth.json                口令哈希
│   │   ├── imports/<line>/<stamp>/  上传原件留档
│   │   └── backups/                 热备份 + 更新前回滚点
│   ├── logs/                        app.log / autostart.log / update.log / install.log
│   └── python.path                  实际使用的解释器（探测结果，一行）
└── bin/                             start / stop / restart / status / backup / export-db / update
```

**核心原则：代码和数据分家。** 换版本只动 `releases/` 和 `current` 软链，`shared/` 永远不碰 ⇒
升级、回滚、重装都不可能覆盖数据库。

### 2.2 为什么不用 systemd

目标机没有 root，装不了系统级 unit。所以：

- 启动：`~/.config/autostart/icbc-dashboard.desktop`（技能里实测 UKUI 会执行）
- 保活：`bin/supervise.sh` 一个 `while` 循环，应用退出 3 秒后自动拉起
- 停止：`bin/stop.sh` 先 TERM 看门狗（它会带走子进程），10 秒不退再 KILL
- 只装**一条**启动路径（技能里的规则），避免开机跑两份

> 若以后拿到 root，可换成 `systemd` 服务，但 `releases/current/shared` 结构不用变。

### 2.3 Python 环境：两层打包

| 层 | 内容 | 是否随包 | 架构相关 |
|---|---|---|---|
| 依赖 | `vendor/pylib/`：openpyxl 3.1.5、xlrd 2.0.1、PyYAML 6.0.2（**全是纯 Python**） | ✅ 必带 | ❌ 与架构无关 |
| 解释器 | `runtime/`：便携 CPython（可选） | 可选 | ✅ 按目标机架构 |

安装/升级时按这个顺序选解释器，**并逐个自检**（`scripts/selftest.py`：版本、sqlite、三个依赖、开库）：

1. `runtime/bin/python3` —— 架构匹配（`runtime/ARCH` == `uname -m`）且自检通过
2. `python3.13 / 3.12 / 3.11 / 3.10 / 3.9 / 3.8 / python3` —— 第一个自检通过的
3. 都不行 → 明确报错，不动生产环境

选中的路径写进 `shared/python.path`，所有脚本读它。

**为什么解释器是可选的**：开发机是 x86_64，arm64 的解释器在这里**没法真正执行验证**。
内置运行时先自检再启用、启动失败自动回退到系统 python3，等于加了一层保险。
代码同时保持 **Python 3.8 兼容**（`src/compat.py` 补 `zoneinfo`、`store.py` 不用 `ON CONFLICT`
这类 3.9+/SQLite 3.24+ 的写法），所以"没带运行时"也能跑。

---

## 3. 日常操作（runbook）

### 3.1 首次部署

U 盘里放 `icbc-dashboard-<版本>/`（或 `.tar.gz`），拷到内网机后：

```bash
cd ~/下载/icbc-dashboard-2026.10.26-b485425      # 或解压出来的目录
bash deploy/install.sh .                          # 用当前目录当包
# 或者
bash deploy/install.sh /media/usb/icbc-dashboard-2026.10.26-b485425.tar.gz
```

它会建目录、落版本、探测解释器、切 `current`、启动、装开机自启，最后打印访问地址。

### 3.2 升级

```bash
bash /media/usb/icbc-dashboard-<新版本>/deploy/update.sh /media/usb/icbc-dashboard-<新版本>
# 或
bash ~/下载/icbc-dashboard-<新版本>/deploy/update.sh ~/下载/icbc-dashboard-<新版本>.tar.gz
```

流程：校验 `SHA256SUMS` → 落到 `releases/<新版本>` → **在数据库副本上预演迁移** → 备份生产库 →
停服 → 切软链 → 起服 → 健康检查；任一步失败自动切回旧版本 + 恢复备份的库。整个过程约 5 秒（失败回滚约 25 秒）。

### 3.3 回滚

`update.sh` 失败会自动回滚。人工回滚：

```bash
ln -sfn ~/icbc-dashboard/releases/<旧版本> ~/icbc-dashboard/current
bash ~/icbc-dashboard/bin/restart.sh
```

### 3.4 备份 / 导出

```bash
bash ~/icbc-dashboard/bin/backup.sh              # → shared/data/backups/，保留 30 份
bash ~/icbc-dashboard/bin/export-db.sh /media/usb # → icbc-<时间戳>.db + .json 清单
```

`.db` 可以直接在内网机或开发机上用 sqlite3 打开复盘；清单里带版本、schema、各条线期数与最新日期。

### 3.5 查看状态 / 起停

```bash
bash ~/icbc-dashboard/bin/status.sh    # 进程、版本、健康、库大小、自检
bash ~/icbc-dashboard/bin/start.sh
bash ~/icbc-dashboard/bin/stop.sh
bash ~/icbc-dashboard/bin/restart.sh
```

---

## 4. 开发 → 发布流程

1. 本机改代码，跑测试：
   ```bash
   python scripts/selftest.py --root data
   python scripts/check_report_parity.py
   ```
2. **提交（干净工作区）**，然后打包：
   ```bash
   python scripts/package_release.py
   # 需要内置解释器时：
   python scripts/package_release.py --runtime ~/py-arm64 --arch aarch64
   ```
   版本号自动取 `YYYY.MM.DD-<git短sha>`；包内写 `VERSION`、`SHA256SUMS`、`HOW-TO-INSTALL.txt`。
3. 把 `dist/icbc-dashboard-<版本>.tar.gz`（+ `.sha256`）拷到 U 盘。
   优先用 **tar.gz**：目录方式经 exFAT 会丢执行权限和符号链接（脚本里已对 `runtime/bin` 补 chmod，但 tar 更稳）。
4. 内网机执行 `deploy/install.sh`（首次）或 `deploy/update.sh`（升级）。

### 版本号规则

`YYYY.MM.DD-<git短sha>`，工作区有未提交改动会变成 `-dirty`（默认拒绝打包，`--allow-dirty` 才放行）。
部署后可以用 `bin/status.sh` 或页面左下角 `v<版本>` 核对。

### 数据库变更纪律

- 改表结构：`src/store.py` 里 `SCHEMA_VERSION += 1`，在 `init()` 的升级分支里写迁移；
- 迁移必须**前向、幂等**（老库能升到新库，重复执行无副作用）；
- `update.sh` 会先在数据库副本上跑一遍再动生产，所以迁移写错会在预演阶段被拦下；
- 回滚会把数据库恢复到更新前（更新窗口内的写入会丢，可重新导入）。

---

## 5. 已知风险 / TODO

| 项 | 说明 | 处理 |
|---|---|---|
| arm64 运行时未实测 | 开发机 x86，无法执行验证 | 首次装到机器上后用 `status.sh` 看 `解释器` 是不是 runtime；不对就删 `runtime/` 重装回退 |
| 开机自启依赖登录 | XDG autostart 要有人登录桌面 | 若需要"无人登录也跑"，得申请 root 上 systemd |
| Excel/CSV 导出 | 用户列为低优先级 | 待明确需要的表口径后加 `scripts/export_xlsx.py` |
| 磁盘增长 | `imports/` 原件只增不减 | 目前 14 MB；到 GB 级再考虑保留策略 |
| 口令文件不在库里 | `auth.json` 与 `icbc.db` 同目录 | 备份/导出脚本都已包含它 |
