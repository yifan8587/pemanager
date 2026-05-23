#!/usr/bin/env bash
# =============================================================================
# PE Manager 环境检查 / 安装 脚本
#
# 用途：在目标服务器上检查 Python / Node / Nginx / netplan / wireguard / iproute2 /
#       iptables / nftables / tc / mtr / wg / journalctl 等依赖；未安装时自动安装。
#
# 支持 OS：Ubuntu 22.04+, Debian 12+（基于 apt）。其他发行版请参考 setup.md。
#
# 使用：
#   sudo bash deploy/setup.sh                   # 检查 + 自动安装缺失项
#   sudo bash deploy/setup.sh --check-only      # 只检查不安装
#   sudo bash deploy/setup.sh --yes             # 跳过交互式确认
# =============================================================================

set -Eeuo pipefail

# ---------------- 公共工具 ----------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log()  { printf "${BLUE}[setup]${NC} %s\n" "$*"; }
ok()   { printf "${GREEN}[ ok ]${NC} %s\n" "$*"; }
warn() { printf "${YELLOW}[warn]${NC} %s\n" "$*"; }
err()  { printf "${RED}[ err]${NC} %s\n" "$*" >&2; }

trap 'err "脚本在第 ${LINENO} 行失败，退出码 $?"' ERR

# ---------------- 参数解析 ----------------
CHECK_ONLY=0
ASSUME_YES=0
for arg in "$@"; do
    case "$arg" in
        --check-only) CHECK_ONLY=1 ;;
        --yes|-y)     ASSUME_YES=1 ;;
        -h|--help)
            grep -E '^# (用途|使用|支持)' "$0" | sed 's/^# //'
            exit 0
            ;;
        *) err "未知参数: $arg"; exit 2 ;;
    esac
done

# ---------------- root 校验 ----------------
if [[ $EUID -ne 0 ]]; then
    err "需要 root 权限执行（请使用 sudo bash deploy/setup.sh）"
    exit 1
fi

# ---------------- OS 探测 ----------------
if [[ ! -r /etc/os-release ]]; then
    err "缺少 /etc/os-release，无法识别系统"
    exit 1
fi
. /etc/os-release
OS_ID="${ID:-unknown}"
OS_VER="${VERSION_ID:-unknown}"
log "操作系统：${PRETTY_NAME:-$OS_ID $OS_VER}"

case "$OS_ID" in
    ubuntu|debian)
        PKG_MGR="apt-get"
        log "包管理器：${PKG_MGR}"
        ;;
    *)
        warn "当前系统 (${OS_ID}) 非 Ubuntu/Debian，已知 apt 包名可能不适用。"
        warn "脚本将继续以"检查"模式运行；安装请参考 setup.md 手动操作。"
        CHECK_ONLY=1
        PKG_MGR=""
        ;;
esac

# ---------------- 软件包矩阵 ----------------
# 三元组：apt-pkg-name | 检测命令 | 说明（用 $'\x1f' 作为不可见分隔符，避免命令中出现的字符冲突）
SEP=$'\x1f'
PKG_LIST=(
    "python3.12${SEP}python3.12 --version || python3 -c 'import sys;sys.exit(0 if sys.version_info>=(3,10) else 1)'${SEP}Python 3.10+（venv 与 Django 5）"
    "python3.12-venv${SEP}python3 -m venv /tmp/_venv_check && rm -rf /tmp/_venv_check${SEP}venv 支持"
    "python3-pip${SEP}pip3 --version${SEP}Python pip"
    "build-essential${SEP}cc --version${SEP}C 构建工具链（部分依赖编译）"
    "nodejs${SEP}node -v${SEP}Node.js 18+（vite build）"
    "npm${SEP}npm -v${SEP}npm（前端依赖）"
    "nginx${SEP}nginx -v${SEP}反向代理 + 静态站点"
    "netplan.io${SEP}netplan --version${SEP}Netplan（隧道与路由片段）"
    "wireguard-tools${SEP}wg --version${SEP}WireGuard 用户态工具（wg / wg-quick）"
    "iproute2${SEP}ip -V${SEP}ip / tc 命令"
    "iptables${SEP}iptables --version${SEP}iptables（防火墙后端）"
    "nftables${SEP}nft --version${SEP}nftables（防火墙后端）"
    "mtr-tiny${SEP}mtr --version${SEP}MTR 测量工具"
    "iputils-ping${SEP}ping -V 2>&1 | head -n1${SEP}ping/ping6"
    "traceroute${SEP}traceroute --version${SEP}traceroute"
    "openssl${SEP}openssl version${SEP}随机密钥生成"
    "curl${SEP}curl --version${SEP}HTTP 工具"
    "sqlite3${SEP}sqlite3 --version${SEP}SQLite CLI"
    "rsync${SEP}rsync --version${SEP}文件同步"
    "ca-certificates${SEP}test -d /etc/ssl/certs${SEP}HTTPS 证书库"
    "systemd${SEP}systemctl --version${SEP}systemd"
    "logrotate${SEP}logrotate --version${SEP}日志轮转"
)

MISSING_PKGS=()
detect_one() {
    local pkg="$1" check="$2" desc="$3"
    if bash -c "$check" >/dev/null 2>&1; then
        ok "${pkg}  — ${desc}"
        return 0
    fi
    warn "缺少：${pkg}  — ${desc}"
    MISSING_PKGS+=("$pkg")
    return 1
}

log "==== 软件包依赖检查 ===="
for line in "${PKG_LIST[@]}"; do
    IFS="$SEP" read -r pkg check desc <<<"$line"
    detect_one "$pkg" "$check" "$desc" || true
done

# ---------------- 内核模块/能力 ----------------
log "==== 内核能力检查 ===="

check_kmod() {
    local mod="$1" desc="$2"
    if lsmod 2>/dev/null | awk '{print $1}' | grep -q "^${mod}$"; then
        ok "kmod ${mod} 已加载 — ${desc}"
    elif modinfo "$mod" >/dev/null 2>&1; then
        warn "kmod ${mod} 未加载但可用；首次使用时会自动加载 — ${desc}"
    else
        warn "kmod ${mod} 内核中不存在 — ${desc}（如不使用该功能可忽略）"
    fi
}
check_kmod wireguard "WireGuard 隧道（首次 wg-quick up 时自动 modprobe）"
check_kmod tun        "tun/tap 设备"
check_kmod sch_htb    "HTB 限速（QoS）"
check_kmod sch_fq_codel "FQ-CoDel 队列（QoS）"
check_kmod nf_tables  "nftables"
check_kmod ip_tables  "iptables"

# IP 转发
if [[ "$(sysctl -n net.ipv4.ip_forward 2>/dev/null || echo 0)" == "1" ]]; then
    ok "sysctl net.ipv4.ip_forward = 1"
else
    warn "sysctl net.ipv4.ip_forward = 0（PE 路由场景建议开启；deploy.sh 会写入 /etc/sysctl.d/）"
fi

# ---------------- 端口占用 ----------------
log "==== 端口占用检查 ===="
check_port() {
    local port="$1" desc="$2"
    if ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE ":(${port})$"; then
        warn "端口 ${port} 已被占用 — ${desc}"
    else
        ok "端口 ${port} 空闲 — ${desc}"
    fi
}
check_port 80 "nginx 默认"
check_port 8000 "若曾以 runserver 启动过开发环境"

# ---------------- 安装 ----------------
print_summary() {
    if [[ ${#MISSING_PKGS[@]} -eq 0 ]]; then
        ok "所有依赖均已满足，无需安装。"
    else
        warn "缺失 ${#MISSING_PKGS[@]} 个包：${MISSING_PKGS[*]}"
    fi
}

if [[ $CHECK_ONLY -eq 1 ]]; then
    print_summary
    log "仅检查模式，结束。"
    exit 0
fi

if [[ ${#MISSING_PKGS[@]} -eq 0 ]]; then
    print_summary
    exit 0
fi

print_summary
if [[ $ASSUME_YES -ne 1 ]]; then
    read -r -p "是否立即安装上述缺失包？[y/N] " yn
    case "$yn" in
        y|Y|yes|YES) ;;
        *) log "已取消"; exit 0 ;;
    esac
fi

if [[ -z "$PKG_MGR" ]]; then
    err "未识别的包管理器，请手动安装：${MISSING_PKGS[*]}"
    exit 1
fi

log "更新 apt 索引..."
$PKG_MGR update -y

log "安装：${MISSING_PKGS[*]}"
DEBIAN_FRONTEND=noninteractive $PKG_MGR install -y "${MISSING_PKGS[@]}"

# 关闭并禁用 ufw（如存在）以避免与 PE Manager 的 nftables/iptables 规则冲突
if systemctl list-unit-files | grep -q '^ufw\.service'; then
    if systemctl is-active --quiet ufw 2>/dev/null; then
        warn "检测到 ufw 启用中；PE Manager 直接管理 nftables/iptables，建议停用 ufw。"
        if [[ $ASSUME_YES -eq 1 ]]; then
            systemctl stop ufw && systemctl disable ufw && ok "已停用 ufw"
        else
            read -r -p "停用 ufw？[y/N] " yn
            [[ "$yn" =~ ^[yY] ]] && systemctl stop ufw && systemctl disable ufw && ok "已停用 ufw"
        fi
    fi
fi

# 复检
log "==== 二次复检 ===="
MISSING_PKGS=()
for line in "${PKG_LIST[@]}"; do
    IFS="$SEP" read -r pkg check desc <<<"$line"
    detect_one "$pkg" "$check" "$desc" || true
done

if [[ ${#MISSING_PKGS[@]} -eq 0 ]]; then
    ok "==== 全部依赖就绪 ===="
    log "下一步：sudo bash deploy/deploy.sh"
else
    err "仍有 ${#MISSING_PKGS[@]} 个包未就绪：${MISSING_PKGS[*]}"
    err "请人工排查（apt search <pkg>）"
    exit 1
fi
