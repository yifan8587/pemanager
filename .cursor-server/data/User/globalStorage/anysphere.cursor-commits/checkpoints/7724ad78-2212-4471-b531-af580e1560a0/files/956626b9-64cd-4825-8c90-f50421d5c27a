# setup.md — 环境检查与依赖安装

本文档说明 `deploy/setup.sh` 做了什么、检查项的含义，以及在 **非 Ubuntu/Debian** 系统上如何手工对照。

---

## 1. 适用范围

| 项 | 说明 |
|---|---|
| 操作系统 | Ubuntu 22.04+ / Debian 12+（自动安装） |
| 其他 Linux | RHEL / CentOS / Rocky / Alma / openSUSE 仅支持 **检查**；安装请按本文末尾"软件包对照表"手工 `dnf/yum/zypper install` |
| 架构 | x86_64 / aarch64 |
| 权限 | 需要 root |

---

## 2. 用法

```bash
cd <PE Manager 源码根>            # 例如 /root/pemanager
sudo bash deploy/setup.sh                  # 检查 + 自动安装缺失项
sudo bash deploy/setup.sh --check-only     # 只检查，不安装
sudo bash deploy/setup.sh --yes            # 跳过交互确认
sudo bash deploy/setup.sh -h               # 帮助
```

退出码：
- `0` — 所有依赖就绪
- `1` — 安装失败 / 仍缺包
- `2` — 参数错误

---

## 3. 检查项明细

### 3.1 软件包

| apt 包 | 用途 |
|---|---|
| `python3.12`、`python3.12-venv`、`python3-pip` | 后端 Django 5 运行时与虚拟环境 |
| `build-essential` | 部分 Python 依赖编译（如 `cryptography` 旧版本） |
| `nodejs`、`npm` | 前端 Vite 构建 |
| `nginx` | 反向代理 + 前端静态站点 |
| `netplan.io` | 隧道意图、静态路由意图通过 netplan 片段持久化 |
| `wireguard-tools` | 提供 `wg`、`wg-quick` |
| `iproute2` | 提供 `ip`、`tc` |
| `iptables`、`nftables` | 防火墙后端（任选其一/共存） |
| `mtr-tiny` | 运维管理 → MTR 工具 |
| `iputils-ping` | 运维管理 → ping/ping6 |
| `traceroute` | 运维管理 → 路径诊断 |
| `openssl` | 部署时生成 `DJANGO_SECRET_KEY` |
| `curl`、`sqlite3`、`rsync`、`ca-certificates`、`systemd`、`logrotate` | 基础工具 |

> 默认部署 **不使用** `ufw`；如已启用，`setup.sh` 会询问是否停用以避免与 PE Manager 直接管理的 nftables/iptables 规则冲突。

### 3.2 内核模块

| 模块 | 用途 | 缺失影响 |
|---|---|---|
| `wireguard` | WireGuard 隧道 | 不能 `wg-quick up`（实际首次启用时内核会自动加载） |
| `tun` | tun/tap 设备 | 部分隧道类型不可用 |
| `sch_htb` | QoS HTB 限速 | QoS 模块不可用 |
| `sch_fq_codel` | QoS 队列管理 | QoS 实际限速效果下降 |
| `nf_tables` | nftables 后端 | 防火墙 nft 模式不可用 |
| `ip_tables` | iptables 后端 | 防火墙 iptables 模式不可用 |

**注意**：模块"未加载"通常不需要 `modprobe`，内核会在首次使用时按需加载；"内核中不存在" 才是真正问题。

### 3.3 sysctl

| 键 | 期望 | 用途 |
|---|---|---|
| `net.ipv4.ip_forward` | `1` | 转发场景（PE 路由）必须 |
| `net.ipv6.conf.all.forwarding` | `1` | IPv6 转发 |

`setup.sh` 不修改 sysctl；`deploy.sh` 会写入 `/etc/sysctl.d/99-pemanager-forward.conf` 并 `sysctl --system`。

### 3.4 端口

`setup.sh` 检查 80（nginx）与 8000（开发期 runserver）是否被占用。`deploy.sh` 使用 **unix socket**（`/run/pemanager/backend.sock`）作为 Gunicorn 监听，不占 8000 端口；80 端口将归 nginx 使用。

---

## 4. 软件包对照表（非 apt 系）

| 功能 | apt | dnf (RHEL 9) | zypper (SUSE) |
|---|---|---|---|
| Python venv | `python3.12-venv` | `python3.12 python3.12-pip`（自带 venv） | `python312 python312-pip` |
| 编译工具 | `build-essential` | `@'Development Tools'` | 模式 `devel_C_C++` |
| Node.js | `nodejs npm` | `nodejs npm`（启用 nodejs:20 模块流） | `nodejs20 npm20` |
| Netplan | `netplan.io` | **无官方包**；CentOS/RHEL 不使用 netplan，需改用 `nmcli` 或 `ifcfg`，PE Manager 的 netplan 写入功能将不可用 |
| WireGuard | `wireguard-tools` | `wireguard-tools` | `wireguard-tools` |
| nftables | `nftables` | `nftables` | `nftables` |
| iptables | `iptables` | `iptables` | `iptables` |

> **RHEL/CentOS 用户重要提示**：项目核心的"隧道意图 → netplan 片段下发"功能依赖 `netplan.io`。若目标系统使用 `NetworkManager + nmcli`，请考虑：① 在该系统上仅启用 WireGuard / iptables / QoS 功能；② 或迁移到 Ubuntu/Debian。

---

## 5. 常见问题

### 5.1 提示 "kmod wireguard 内核中不存在"
旧内核（< 5.6）需要：
```bash
sudo apt install linux-headers-$(uname -r) linux-modules-extra-$(uname -r)
sudo modprobe wireguard
```

### 5.2 提示 "端口 80 已被占用"
检查现有服务：
```bash
sudo ss -ltnp 'sport = :80'
```
若是 Apache：
```bash
sudo systemctl stop apache2 && sudo systemctl disable apache2
```

### 5.3 检测到 ufw 启用
PE Manager 直接管理 `nftables`/`iptables`，与 ufw 共存会出现规则被相互覆盖。建议：
```bash
sudo systemctl stop ufw && sudo systemctl disable ufw
```

### 5.4 想自定义 Python / Node 版本
脚本只校验 "Python ≥ 3.10、Node ≥ 18"；若你已通过 `pyenv` / `nvm` 安装更高版本，可以让 `python3 --version` / `node -v` 指向所需版本即可（创建 venv 时会复用 `python3` 当前指向）。

---

## 6. 下一步

`setup.sh` 成功结束后，进入 [deploy.md](./deploy.md) 进行一键部署。
