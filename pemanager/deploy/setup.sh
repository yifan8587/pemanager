#!/usr/bin/env bash
# =============================================================================
# PE Manager 环境检查 / 安装 / 升级 脚本
#
# 用途：在目标服务器上检查 Python / Node / Nginx / netplan / wireguard /
#       iproute2 / iptables / nftables / tc / mtr / wg / journalctl / certbot
#       等依赖；未安装时自动安装；版本不达标时自动升级到项目所需最低版本。
#
# 支持 OS：Ubuntu 22.04+, Debian 12+（基于 apt）。其他发行版请参考 setup.md。
#
# 使用：
#   sudo bash deploy/setup.sh                   # 检查 + 自动安装/升级缺失或低版本项
#   sudo bash deploy/setup.sh --check-only      # 只检查不动系统
#   sudo bash deploy/setup.sh --yes             # 跳过交互式确认
#   sudo bash deploy/setup.sh --no-upgrade      # 仅安装缺失项，不升级已有低版本
#   sudo bash deploy/setup.sh --offline DIR     # 使用本地 apt 仓库（离线包场景）
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
DO_UPGRADE=1
OFFLINE_DIR=""
for arg in "$@"; do
    case "$arg" in
        --check-only) CHECK_ONLY=1 ;;
        --yes|-y)     ASSUME_YES=1 ;;
        --no-upgrade) DO_UPGRADE=0 ;;
        --offline)    shift; OFFLINE_DIR="$1"; shift ;;
        --offline=*)  OFFLINE_DIR="${arg#--offline=}" ;;
        -h|--help)
            grep -E '^# (用途|使用|支持)' "$0" | sed 's/^# //'
            exit 0
            ;;
        *) ;; # 兼容旧位置参数解析顺序，未识别忽略
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

PKG_MGR=""
case "$OS_ID" in
    ubuntu|debian)
        PKG_MGR="apt-get"
        log "包管理器：${PKG_MGR}"
        ;;
    *)
        warn "当前系统 (${OS_ID}) 非 Ubuntu/Debian，已知 apt 包名可能不适用。"
        warn "脚本将继续以「检查」模式运行；安装请参考 setup.md 手动操作。"
        CHECK_ONLY=1
        ;;
esac

# 离线模式：使用本地 deb 目录
if [[ -n "$OFFLINE_DIR" ]]; then
    if [[ ! -d "$OFFLINE_DIR" ]]; then
        err "--offline 目录不存在: $OFFLINE_DIR"
        exit 1
    fi
    log "离线模式：通过 ${OFFLINE_DIR} 中的 .deb 包安装"
    OFFLINE_DIR="$(cd "$OFFLINE_DIR" && pwd)"
fi

# ---------------- 项目最低版本要求 ----------------
# 与 backend/requirements.txt、frontend/package.json 保持一致
MIN_PY_MAJOR=3
MIN_PY_MINOR=10        # Django 5 要求 Python 3.10+
MIN_NODE_MAJOR=18      # Vite 5 / Vue 3 要求 Node 18+
MIN_NPM_MAJOR=9
MIN_NGINX_MAJOR=1
MIN_NGINX_MINOR=18

# ---------------- 包安装抽象（含 offline） ----------------
APT_INSTALL() {
    if [[ -n "$OFFLINE_DIR" ]]; then
        log "离线 apt: dpkg -i 安装 ${OFFLINE_DIR}/*.deb 后再处理依赖"
        dpkg -i "${OFFLINE_DIR}"/*.deb 2>/dev/null || true
        apt-get -f install -y --no-install-recommends || true
    else
        DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "$@"
    fi
}
APT_UPDATE() {
    if [[ -z "$OFFLINE_DIR" ]]; then
        DEBIAN_FRONTEND=noninteractive apt-get update -y || warn "apt update 失败，将继续尝试已有缓存"
    fi
}

# ---------------- 版本比较 ----------------
# ver_ge "<v1>" "<v2>"  →  v1 >= v2 退出 0
ver_ge() {
    [[ "$1" == "$2" ]] && return 0
    local IFS=.
    # shellcheck disable=SC2206
    local a=($1) b=($2)
    local i; for ((i=0; i<${#a[@]} || i<${#b[@]}; i++)); do
        local x=${a[i]:-0} y=${b[i]:-0}
        x=${x%%[^0-9]*}; y=${y%%[^0-9]*}
        x=${x:-0}; y=${y:-0}
        ((x>y)) && return 0
        ((x<y)) && return 1
    done
    return 0
}

# ---------------- 软件包矩阵 ----------------
# 三元组：apt-pkg-name | 检测命令 | 说明（用 $'\x1f' 作为不可见分隔符）
#
# 检测策略（避免「装了但命令 --version 偶发非零」误判）：
#   - 有 CLI 的包    → `command -v <bin>`（只判命令存在；版本另外校验）
#   - 开发库 / 插件  → `dpkg -s <pkg>`（只看包安装状态）
#   - 极少需要执行的检测（如 venv）才用「实际跑一次」
#
SEP=$'\x1f'
PKG_LIST=(
    "python3${SEP}command -v python3${SEP}Python ${MIN_PY_MAJOR}.${MIN_PY_MINOR}+（venv 与 Django 5）"
    "python3-venv${SEP}python3 -m venv /tmp/_venv_check >/dev/null 2>&1 && rm -rf /tmp/_venv_check${SEP}venv 支持"
    "python3-pip${SEP}command -v pip3 || command -v pip${SEP}Python pip"
    "build-essential${SEP}command -v cc || dpkg -s build-essential${SEP}C 构建工具链（部分依赖编译）"
    "libffi-dev${SEP}dpkg -s libffi-dev${SEP}cryptography / cffi 编译依赖"
    "libssl-dev${SEP}dpkg -s libssl-dev${SEP}cryptography / cffi 编译依赖"
    "nginx${SEP}command -v nginx${SEP}反向代理 + 静态站点"
    "netplan.io${SEP}command -v netplan || dpkg -s netplan.io${SEP}Netplan（隧道与路由片段）"
    "wireguard-tools${SEP}command -v wg${SEP}WireGuard 用户态工具（wg / wg-quick）"
    "iproute2${SEP}command -v ip${SEP}ip / tc 命令"
    "iptables${SEP}command -v iptables${SEP}iptables（防火墙后端）"
    "nftables${SEP}command -v nft${SEP}nftables（防火墙后端）"
    "mtr-tiny${SEP}command -v mtr${SEP}MTR 测量工具"
    "iputils-ping${SEP}command -v ping${SEP}ping/ping6"
    "traceroute${SEP}command -v traceroute${SEP}traceroute"
    "openssl${SEP}command -v openssl${SEP}随机密钥生成 + 自签名 SSL"
    "curl${SEP}command -v curl${SEP}HTTP 工具"
    "sqlite3${SEP}command -v sqlite3${SEP}SQLite CLI"
    "rsync${SEP}command -v rsync${SEP}文件同步"
    "ca-certificates${SEP}test -d /etc/ssl/certs${SEP}HTTPS 证书库"
    "systemd${SEP}command -v systemctl${SEP}systemd"
    "logrotate${SEP}command -v logrotate${SEP}日志轮转"
    "certbot${SEP}command -v certbot${SEP}Let's Encrypt 客户端（域名 HTTPS）"
    "python3-certbot-nginx${SEP}dpkg -s python3-certbot-nginx${SEP}certbot nginx 插件"
    "tar${SEP}command -v tar${SEP}归档（package.sh 生成 tar.gz）"
    "gzip${SEP}command -v gzip${SEP}压缩"
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

# ---------------- 版本下限校验 ----------------
log "==== 版本下限校验 ===="

NEED_UPGRADE=()    # 形如 "pkg|reason"

# Python
if command -v python3 >/dev/null 2>&1; then
    PY_VER="$(python3 -c 'import sys; print("%d.%d.%d"%sys.version_info[:3])' 2>/dev/null || echo 0.0.0)"
    if ver_ge "$PY_VER" "${MIN_PY_MAJOR}.${MIN_PY_MINOR}"; then
        ok "python3 ${PY_VER} ≥ ${MIN_PY_MAJOR}.${MIN_PY_MINOR}"
    else
        warn "python3 ${PY_VER} < ${MIN_PY_MAJOR}.${MIN_PY_MINOR}，将尝试安装 python3.12"
        NEED_UPGRADE+=("python3.12|python3.12-venv|python3.12-distutils")
    fi
fi

# Node
NODE_OK=0
if command -v node >/dev/null 2>&1; then
    NODE_VER="$(node -v 2>/dev/null | sed 's/^v//')"
    if ver_ge "$NODE_VER" "${MIN_NODE_MAJOR}.0.0"; then
        ok "node ${NODE_VER} ≥ ${MIN_NODE_MAJOR}"
        NODE_OK=1
    else
        warn "node ${NODE_VER} < ${MIN_NODE_MAJOR}，将通过 NodeSource 升级到 LTS 20"
    fi
else
    warn "未安装 node，将通过 NodeSource 安装 LTS 20"
fi

NPM_OK=0
if command -v npm >/dev/null 2>&1; then
    NPM_VER="$(npm -v 2>/dev/null || echo 0.0.0)"
    if ver_ge "$NPM_VER" "${MIN_NPM_MAJOR}.0.0"; then
        ok "npm ${NPM_VER} ≥ ${MIN_NPM_MAJOR}"
        NPM_OK=1
    else
        warn "npm ${NPM_VER} < ${MIN_NPM_MAJOR}（升级 node 时会一起带 npm）"
    fi
fi

# Nginx
if command -v nginx >/dev/null 2>&1; then
    NGX_VER="$(nginx -v 2>&1 | sed -nE 's/.*nginx\/([0-9.]+).*/\1/p')"
    if ver_ge "$NGX_VER" "${MIN_NGINX_MAJOR}.${MIN_NGINX_MINOR}.0"; then
        ok "nginx ${NGX_VER} ≥ ${MIN_NGINX_MAJOR}.${MIN_NGINX_MINOR}"
    else
        warn "nginx ${NGX_VER} 较旧，建议升级到 ${MIN_NGINX_MAJOR}.${MIN_NGINX_MINOR}+"
    fi
fi

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
check_port 80 "nginx 默认 HTTP"
check_port 443 "nginx HTTPS（启用 SSL 时使用）"
check_port 8000 "若曾以 runserver 启动过开发环境"

# ---------------- 安装/升级 ----------------
print_summary() {
    if [[ ${#MISSING_PKGS[@]} -eq 0 && ${#NEED_UPGRADE[@]} -eq 0 ]]; then
        ok "所有依赖与版本均已满足，无需变更。"
    else
        if (( ${#MISSING_PKGS[@]} > 0 )); then
            warn "缺失 ${#MISSING_PKGS[@]} 个包：${MISSING_PKGS[*]}"
        fi
        if (( ${#NEED_UPGRADE[@]} > 0 )); then
            warn "需升级 ${#NEED_UPGRADE[@]} 项（版本不达标）"
        fi
    fi
    return 0
}

if [[ $CHECK_ONLY -eq 1 ]]; then
    print_summary
    log "仅检查模式，结束。"
    exit 0
fi

if [[ ${#MISSING_PKGS[@]} -eq 0 && ${#NEED_UPGRADE[@]} -eq 0 ]]; then
    print_summary
    exit 0
fi

print_summary
if [[ $ASSUME_YES -ne 1 ]]; then
    read -r -p "是否立即安装/升级上述项？[y/N] " yn
    case "$yn" in
        y|Y|yes|YES) ;;
        *) log "已取消"; exit 0 ;;
    esac
fi

if [[ -z "$PKG_MGR" ]]; then
    err "未识别的包管理器，请手动安装：${MISSING_PKGS[*]}"
    exit 1
fi

APT_UPDATE

# 1) 缺失包安装
if [[ ${#MISSING_PKGS[@]} -gt 0 ]]; then
    log "安装缺失包：${MISSING_PKGS[*]}"
    APT_INSTALL "${MISSING_PKGS[@]}"
fi

# 2) 版本不达标升级
if [[ $DO_UPGRADE -eq 1 && ${#NEED_UPGRADE[@]} -gt 0 ]]; then
    for entry in "${NEED_UPGRADE[@]}"; do
        IFS='|' read -r -a pkgs <<<"$entry"
        log "升级安装：${pkgs[*]}"
        # 对 python3.12 在某些 ubuntu 版本里没有，回退到 deadsnakes ppa
        if [[ "${pkgs[0]}" == "python3.12" ]] && ! apt-cache show python3.12 >/dev/null 2>&1; then
            log "添加 deadsnakes PPA 以获取 python3.12"
            APT_INSTALL software-properties-common
            add-apt-repository -y ppa:deadsnakes/ppa
            APT_UPDATE
        fi
        APT_INSTALL "${pkgs[@]}" || warn "升级 ${pkgs[*]} 失败，可手动重试"
    done
fi

# 3) Node 不达标：通过 NodeSource 装 LTS 20
if [[ $DO_UPGRADE -eq 1 && $NODE_OK -eq 0 ]]; then
    log "通过 NodeSource 安装 Node.js 20 LTS"
    if [[ -z "$OFFLINE_DIR" ]]; then
        APT_INSTALL ca-certificates curl gnupg
        mkdir -p /etc/apt/keyrings
        curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
            | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg
        chmod 0644 /etc/apt/keyrings/nodesource.gpg
        NODE_REPO=node_20.x
        echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/${NODE_REPO} nodistro main" \
            > /etc/apt/sources.list.d/nodesource.list
        APT_UPDATE
        APT_INSTALL nodejs
    else
        warn "离线模式：请将 nodejs 的 .deb 放入 ${OFFLINE_DIR} 后重跑 setup.sh"
    fi
fi

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

# ---------------- 复检 ----------------
log "==== 二次复检 ===="
MISSING_PKGS=()
NEED_UPGRADE_RECHK=()
for line in "${PKG_LIST[@]}"; do
    IFS="$SEP" read -r pkg check desc <<<"$line"
    detect_one "$pkg" "$check" "$desc" || true
done
if command -v python3 >/dev/null 2>&1; then
    PY_VER="$(python3 -c 'import sys; print("%d.%d.%d"%sys.version_info[:3])' 2>/dev/null || echo 0.0.0)"
    ver_ge "$PY_VER" "${MIN_PY_MAJOR}.${MIN_PY_MINOR}" \
        && ok "python3 ${PY_VER} ≥ ${MIN_PY_MAJOR}.${MIN_PY_MINOR}" \
        || NEED_UPGRADE_RECHK+=("python3 ${PY_VER}")
fi
if command -v node >/dev/null 2>&1; then
    NODE_VER="$(node -v 2>/dev/null | sed 's/^v//')"
    ver_ge "$NODE_VER" "${MIN_NODE_MAJOR}.0.0" \
        && ok "node ${NODE_VER} ≥ ${MIN_NODE_MAJOR}" \
        || NEED_UPGRADE_RECHK+=("node ${NODE_VER}")
fi

if [[ ${#MISSING_PKGS[@]} -eq 0 && ${#NEED_UPGRADE_RECHK[@]} -eq 0 ]]; then
    ok "==== 全部依赖与版本就绪 ===="
    log "下一步：sudo bash deploy/deploy.sh"
    log "        sudo bash deploy/deploy.sh --ssl-domain pe.example.com   # 启用 HTTPS"
    log "        sudo bash deploy/deploy.sh --ssl-ip                      # 用自签名 SSL"
else
    err "仍存在未满足项：${MISSING_PKGS[*]} ${NEED_UPGRADE_RECHK[*]}"
    err "请人工排查（apt search <pkg>）"
    exit 1
fi
