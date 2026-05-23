# setup.md — 环境检查 / 依赖安装 / 版本升级

本文档说明 `deploy/setup.sh` 做了什么、检查项的含义，以及在 **非 Ubuntu/Debian** 系统上如何手工对照。
从 v2 起，`setup.sh` 不仅会装"缺失"的包，**还会对比项目所需最低版本，自动升级不达标的运行时**。

---

## 1. 适用范围

| 项 | 说明 |
|---|---|
| 操作系统 | Ubuntu 22.04+ / Debian 12+（**自动安装/升级**） |
| 其他 Linux | RHEL / CentOS / Rocky / Alma / openSUSE 仅支持 **检查**；安装请按本文末尾"软件包对照表"手工 `dnf/yum/zypper install` |
| 架构 | x86_64 / aarch64 |
| 权限 | 需要 root |

---

## 2. 用法

```bash
cd <PE Manager 源码根>            # 例如 /root/pemanager

sudo bash deploy/setup.sh                    # 检查 + 自动安装/升级
sudo bash deploy/setup.sh --check-only       # 只检查，不安装、不升级
sudo bash deploy/setup.sh --yes              # 跳过交互确认
sudo bash deploy/setup.sh --no-upgrade       # 仅安装缺失项，不升级已有低版本
sudo bash deploy/setup.sh --offline ./debs   # 离线包模式：从本地 .deb 目录装
sudo bash deploy/setup.sh -h                 # 帮助
```

退出码：
- `0` — 所有依赖、版本均就绪
- `1` — 安装/升级失败 / 仍缺包
- `2` — 参数错误

---

## 3. 项目最低版本要求（v2 新增校验）

| 组件 | 最低版本 | 不达标时的处理 |
|---|---|---|
| Python | ≥ 3.10（Django 5 要求） | 自动 `apt install python3.12`（含 `python3.12-venv`、`-distutils`）；若仓库无该版本，自动添加 `deadsnakes` PPA |
| Node.js | ≥ 18（Vite 5 / Vue 3） | 通过 NodeSource 安装 LTS 20（`node_20.x` apt 源） |
| npm | ≥ 9 | 随 Node 升级自动带 |
| nginx | ≥ 1.18 | 提示告警；通常 Ubuntu 22.04+ 自带满足 |

`setup.sh` 不会"为了升级而升级"项目无依赖的组件。已达版本下限的包，二次复检时直接通过。

---

## 4. 检查项明细

### 4.1 软件包

| apt 包 | 用途 |
|---|---|
| `python3`、`python3-venv`、`python3-pip` | 后端 Django 5 运行时与虚拟环境 |
| `build-essential`、`libffi-dev`、`libssl-dev` | 部分 Python 依赖（`cryptography` / `cffi`）编译 |
| `nginx` | 反向代理 + 前端静态站点 |
| `netplan.io` | 隧道意图、静态路由意图通过 netplan 片段持久化 |
| `wireguard-tools` | 提供 `wg`、`wg-quick` |
| `iproute2` | 提供 `ip`、`tc` |
| `iptables`、`nftables` | 防火墙后端（任选其一/共存） |
| `mtr-tiny` | 运维管理 → MTR 工具 |
| `iputils-ping` | 运维管理 → ping/ping6 |
| `traceroute` | 运维管理 → 路径诊断 |
| `openssl` | 部署时生成 `DJANGO_SECRET_KEY`，IP 模式自签名 SSL |
| `curl`、`sqlite3`、`rsync`、`ca-certificates`、`systemd`、`logrotate` | 基础工具 |
| `certbot`、`python3-certbot-nginx` | **新增**：HTTPS 自动签发与续期（Let's Encrypt） |
| `tar`、`gzip` | `package.sh` 制作离线压缩包 |

> 默认部署 **不使用** `ufw`；如已启用，`setup.sh` 会询问是否停用以避免与 PE Manager 直接管理的 nftables/iptables 规则冲突。

Node.js 不通过 apt 主源安装：当版本不达标时，`setup.sh` 会自动接入 NodeSource 官方源（`deb.nodesource.com/node_20.x`），并写入 GPG 公钥到 `/etc/apt/keyrings/nodesource.gpg`。

### 4.2 内核模块

| 模块 | 用途 | 缺失影响 |
|---|---|---|
| `wireguard` | WireGuard 隧道 | 不能 `wg-quick up`（实际首次启用时内核会自动加载） |
| `tun` | tun/tap 设备 | 部分隧道类型不可用 |
| `sch_htb` | QoS HTB 限速 | QoS 模块不可用 |
| `sch_fq_codel` | QoS 队列管理 | QoS 实际限速效果下降 |
| `nf_tables` | nftables 后端 | 防火墙 nft 模式不可用 |
| `ip_tables` | iptables 后端 | 防火墙 iptables 模式不可用 |

**注意**：模块"未加载"通常不需要 `modprobe`，内核会在首次使用时按需加载；"内核中不存在" 才是真正问题。

### 4.3 sysctl

| 键 | 期望 | 用途 |
|---|---|---|
| `net.ipv4.ip_forward` | `1` | 转发场景（PE 路由）必须 |
| `net.ipv6.conf.all.forwarding` | `1` | IPv6 转发 |

`setup.sh` 不修改 sysctl；`deploy.sh` 会写入 `/etc/sysctl.d/99-pemanager-forward.conf` 并 `sysctl --system`。

### 4.4 端口

`setup.sh` 检查 80（nginx）、443（HTTPS）与 8000（开发期 runserver）是否被占用。`deploy.sh` 使用 **unix socket**（`/run/pemanager/backend.sock`）作为 Gunicorn 监听，不占 8000 端口；80/443 端口将归 nginx 使用。

---

## 5. 离线 / 内网部署

针对受限网络场景，提供两种途径：

### 5.1 完全离线压缩包（推荐）

在能上网的机器制作：

```bash
sudo bash deploy/package.sh \
    --with-debs       \  # 把所有 .deb 装一起
    --with-wheels     \  # 把所有 Python wheels 装一起
    --with-frontend   \  # 把已 build 的 frontend/dist 装一起
    --output deploy/dist/pemanager-offline.tar.gz
```

拷到目标机：

```bash
tar xzf pemanager-offline.tar.gz && cd pemanager-*
sudo bash INSTALL.sh --offline                       # 完全离线
sudo bash INSTALL.sh --offline --ssl-ip              # 自签名 SSL（无 DNS）
```

详见 [`package.md`](./package.md)。

### 5.2 仅离线 apt

仅有 `.deb` 集合时：

```bash
sudo bash deploy/setup.sh --yes --offline /path/to/debs
```

`setup.sh` 会先 `dpkg -i *.deb`，再尝试 `apt-get -f install -y` 解决依赖。

---

## 6. 软件包对照表（非 apt 系）

| 功能 | apt | dnf (RHEL 9) | zypper (SUSE) |
|---|---|---|---|
| Python venv | `python3.12-venv` | `python3.12 python3.12-pip` | `python312 python312-pip` |
| 编译工具 | `build-essential libffi-dev libssl-dev` | `@'Development Tools' libffi-devel openssl-devel` | 模式 `devel_C_C++` + `libffi-devel libopenssl-devel` |
| Node.js | `nodejs npm`（NodeSource） | `nodejs npm`（启用 nodejs:20 模块流） | `nodejs20 npm20` |
| Netplan | `netplan.io` | **无官方包**；CentOS/RHEL 不使用 netplan，需改用 `nmcli` 或 `ifcfg`，PE Manager 的 netplan 写入功能将不可用 |
| WireGuard | `wireguard-tools` | `wireguard-tools` | `wireguard-tools` |
| nftables | `nftables` | `nftables` | `nftables` |
| iptables | `iptables` | `iptables` | `iptables` |
| Certbot | `certbot python3-certbot-nginx` | `certbot python3-certbot-nginx` | `certbot python3-certbot-nginx` |

> **RHEL/CentOS 用户重要提示**：项目核心的"隧道意图 → netplan 片段下发"功能依赖 `netplan.io`。若目标系统使用 `NetworkManager + nmcli`，请考虑：① 在该系统上仅启用 WireGuard / iptables / QoS 功能；② 或迁移到 Ubuntu/Debian。

---

## 7. 常见问题

### 7.1 提示 "kmod wireguard 内核中不存在"
旧内核（< 5.6）需要：
```bash
sudo apt install linux-headers-$(uname -r) linux-modules-extra-$(uname -r)
sudo modprobe wireguard
```

### 7.2 提示 "端口 80/443 已被占用"
检查现有服务：
```bash
sudo ss -ltnp 'sport = :80 or sport = :443'
```
若是 Apache：
```bash
sudo systemctl stop apache2 && sudo systemctl disable apache2
```

### 7.3 检测到 ufw 启用
PE Manager 直接管理 `nftables`/`iptables`，与 ufw 共存会出现规则被相互覆盖。建议：
```bash
sudo systemctl stop ufw && sudo systemctl disable ufw
```

### 7.4 Python 不达标但不想升级到 3.12
传 `--no-upgrade`：`setup.sh` 只装缺失项，不动已有运行时；之后你需要自行解决 Django 5 的 Python 3.10+ 要求（否则 deploy 会失败）。

### 7.5 NodeSource 安装失败 / 离线机
- 离线：用 `package.sh --with-debs` 把 NodeSource 的 nodejs.deb 一并打入；目标机 `INSTALL.sh --offline`
- 在线但拒绝外网仓库：可以 `apt install nodejs` 走主源（版本可能略低），随后跑 `npm install -g n && n 20` 切版

### 7.6 自定义 Python / Node 版本
脚本只校验 "Python ≥ 3.10、Node ≥ 18"；若你已通过 `pyenv` / `nvm` 安装更高版本，让 `python3 --version` / `node -v` 指向所需版本即可（创建 venv 时会复用 `python3` 当前指向）。

---

## 8. 下一步

`setup.sh` 成功结束后：

```bash
# 普通 HTTP 部署
sudo bash deploy/deploy.sh

# 域名 + 自动 Let's Encrypt 证书 + 续期
sudo bash deploy/deploy.sh --ssl-domain pe.example.com --ssl-email admin@example.com

# 仅有 IP 时用自签名 HTTPS
sudo bash deploy/deploy.sh --ssl-ip            # 自动取本机首个 IPv4
sudo bash deploy/deploy.sh --ssl-ip 1.2.3.4
```

详见 [deploy.md](./deploy.md) 与 [ssl.md](./ssl.md)。
