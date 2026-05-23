#!/usr/bin/env bash
# =============================================================================
# PE Manager 一键生产部署脚本
#
# 该脚本会：
#   1) 创建目录骨架 /opt/pemanager、/var/lib/pemanager、/var/log/pemanager
#   2) 同步源码到 /opt/pemanager，建立 venv 并安装 Python 依赖
#   3) 构建前端 dist 到 /opt/pemanager/frontend/dist/
#   4) 写入 /etc/pemanager/pemanager.env（首次部署生成强随机 SECRET_KEY）
#   5) 安装并启用 systemd unit：pemanager-backend.service + pemanager-monitor.service
#   6) 安装 nginx 站点配置，移除 default 并 reload
#   7) 配置 /etc/sysctl.d/99-pemanager-forward.conf（IP 转发）
#   8) 配置 logrotate
#   9) Django migrate + collectstatic + 自动 ensure_default_admin
#   10) 健康检查
#
# 使用：
#   sudo bash deploy/deploy.sh                  # 全量首次部署
#   sudo bash deploy/deploy.sh --update         # 只更新代码/依赖/前端（不动 env / nginx）
#   sudo bash deploy/deploy.sh --src /path/src  # 指定源码根（默认为脚本所在仓库）
#   sudo bash deploy/deploy.sh --host 1.2.3.4   # 追加 ALLOWED_HOSTS
# =============================================================================

set -Eeuo pipefail

# ----- 颜色 / 日志 -----
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log()  { printf "${BLUE}[deploy]${NC} %s\n" "$*"; }
ok()   { printf "${GREEN}[ ok ]${NC} %s\n" "$*"; }
warn() { printf "${YELLOW}[warn]${NC} %s\n" "$*"; }
err()  { printf "${RED}[ err]${NC} %s\n" "$*" >&2; }
trap 'err "脚本在第 ${LINENO} 行失败，退出码 $?"' ERR

# ----- 路径常量 -----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DEFAULT="$(cd "${SCRIPT_DIR}/.." && pwd)"
INSTALL_DIR="/opt/pemanager"
ENV_DIR="/etc/pemanager"
ENV_FILE="${ENV_DIR}/pemanager.env"
DATA_DIR="/var/lib/pemanager"
LOG_DIR="/var/log/pemanager"
RUN_DIR="/run/pemanager"
STATIC_ROOT="${DATA_DIR}/static"
DB_PATH="${DATA_DIR}/db.sqlite3"

SYSTEMD_DIR="/etc/systemd/system"
NGINX_SITE_AVAIL="/etc/nginx/sites-available/pemanager.conf"
NGINX_SITE_ENAB="/etc/nginx/sites-enabled/pemanager.conf"

# ----- 参数 -----
SRC_DIR="$SRC_DEFAULT"
UPDATE_ONLY=0
EXTRA_HOST=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --update) UPDATE_ONLY=1 ;;
        --src)    SRC_DIR="$2"; shift ;;
        --host)   EXTRA_HOST="$2"; shift ;;
        -h|--help)
            grep -E '^# (使用|参数|该脚本)' "$0" | sed 's/^# //'
            exit 0
            ;;
        *) err "未知参数: $1"; exit 2 ;;
    esac
    shift
done

# ----- root -----
if [[ $EUID -ne 0 ]]; then
    err "请以 root 运行（sudo bash deploy/deploy.sh）"
    exit 1
fi

# ----- 校验源码 -----
if [[ ! -f "${SRC_DIR}/backend/manage.py" || ! -f "${SRC_DIR}/frontend/package.json" ]]; then
    err "源码路径无效：${SRC_DIR}（需包含 backend/manage.py 与 frontend/package.json）"
    exit 1
fi
log "源码根：${SRC_DIR}"
log "安装根：${INSTALL_DIR}"

# ----- 基础依赖检查（仅 ping 几个关键命令）-----
for c in python3 npm nginx netplan ip; do
    if ! command -v "$c" >/dev/null 2>&1; then
        err "缺少命令 $c；请先运行 sudo bash deploy/setup.sh"
        exit 1
    fi
done

# ============================================================================
# 1. 目录骨架
# ============================================================================
log "[1/10] 创建目录骨架"
mkdir -p "$INSTALL_DIR" "$ENV_DIR" "$DATA_DIR" "$LOG_DIR" "$RUN_DIR" "$STATIC_ROOT"
chmod 0755 "$INSTALL_DIR" "$DATA_DIR" "$STATIC_ROOT"
chmod 0700 "$ENV_DIR"
chmod 0755 "$LOG_DIR" "$RUN_DIR"

# ============================================================================
# 2. 同步源码（不复制 venv / node_modules / dist / db.sqlite3）
# ============================================================================
log "[2/10] 同步源码到 ${INSTALL_DIR}"
RSYNC_EXCL=(
    --exclude '/venv/'
    --exclude '/frontend/node_modules/'
    --exclude '/frontend/dist/'
    --exclude '/backend/db.sqlite3'
    --exclude '/backend/staticfiles/'
    --exclude '__pycache__'
    --exclude '.git/'
    --exclude '.venv/'
)
rsync -a --delete-after "${RSYNC_EXCL[@]}" "${SRC_DIR}/" "${INSTALL_DIR}/"

# ============================================================================
# 3. Python venv + 依赖
# ============================================================================
log "[3/10] 准备 Python 虚拟环境"
if [[ ! -d "${INSTALL_DIR}/venv" ]]; then
    python3 -m venv "${INSTALL_DIR}/venv"
fi
# shellcheck disable=SC1091
source "${INSTALL_DIR}/venv/bin/activate"
pip install --upgrade pip wheel setuptools >/dev/null
# 后端 requirements 中没有 gunicorn，这里追加
REQ_FILE="${INSTALL_DIR}/backend/requirements.txt"
[[ -f "$REQ_FILE" ]] || REQ_FILE="${INSTALL_DIR}/requirements.txt"
pip install -r "$REQ_FILE"
pip install "gunicorn>=21.2"
deactivate
ok "Python 依赖安装完成"

# ============================================================================
# 4. 前端 build
# ============================================================================
log "[4/10] 前端依赖与构建"
pushd "${INSTALL_DIR}/frontend" >/dev/null
if [[ -f package-lock.json ]]; then
    npm ci --no-audit --no-fund
else
    npm install --no-audit --no-fund
fi
npm run build
popd >/dev/null
ok "前端 dist 已生成：${INSTALL_DIR}/frontend/dist"

# ============================================================================
# 5. 环境配置文件
# ============================================================================
log "[5/10] 写入 ${ENV_FILE}"
if [[ ! -f "$ENV_FILE" ]]; then
    cp "${INSTALL_DIR}/deploy/templates/pemanager.env.example" "$ENV_FILE"
    # 生成随机 SECRET_KEY
    SECRET="$(openssl rand -base64 60 | tr -d '\n=+/' | cut -c1-64)"
    sed -i "s|^DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=${SECRET}|" "$ENV_FILE"
    # ALLOWED_HOSTS 至少包含本机 IP
    MY_IPS=$(hostname -I 2>/dev/null | tr ' ' ',' | sed 's/,$//')
    HOSTS="127.0.0.1,localhost,${MY_IPS}"
    [[ -n "$EXTRA_HOST" ]] && HOSTS="${HOSTS},${EXTRA_HOST}"
    sed -i "s|^DJANGO_ALLOWED_HOSTS=.*|DJANGO_ALLOWED_HOSTS=${HOSTS}|" "$ENV_FILE"
    # 路径
    sed -i "s|^DJANGO_DB_PATH=.*|DJANGO_DB_PATH=${DB_PATH}|" "$ENV_FILE"
    sed -i "s|^DJANGO_STATIC_ROOT=.*|DJANGO_STATIC_ROOT=${STATIC_ROOT}|" "$ENV_FILE"
    chmod 0640 "$ENV_FILE"
    ok "首次部署：已生成随机 SECRET_KEY；ALLOWED_HOSTS=${HOSTS}"
else
    warn "${ENV_FILE} 已存在，保持原文件不变（如需重置请先 rm -f 并重跑）"
    # 仍然追加 host
    if [[ -n "$EXTRA_HOST" ]] && ! grep -q "$EXTRA_HOST" "$ENV_FILE"; then
        sed -i "s|^DJANGO_ALLOWED_HOSTS=\(.*\)|DJANGO_ALLOWED_HOSTS=\1,${EXTRA_HOST}|" "$ENV_FILE"
        ok "已向 ALLOWED_HOSTS 追加：${EXTRA_HOST}"
    fi
fi

# ============================================================================
# 6. Django migrate + collectstatic
# ============================================================================
log "[6/10] Django migrate + collectstatic"
pushd "${INSTALL_DIR}/backend" >/dev/null
# 显式以 env 文件运行（与 systemd 行为一致）
set -a; source "$ENV_FILE"; set +a
"${INSTALL_DIR}/venv/bin/python" manage.py migrate --noinput
"${INSTALL_DIR}/venv/bin/python" manage.py collectstatic --noinput
popd >/dev/null
# 数据目录权限
chown -R root:root "$DATA_DIR"
chmod 0750 "$DATA_DIR"
[[ -f "$DB_PATH" ]] && chmod 0640 "$DB_PATH"
ok "数据库初始化完成；默认 admin/admin123 已就绪（可在 ${ENV_FILE} 覆盖）"

# ============================================================================
# 7. systemd units
# ============================================================================
log "[7/10] 安装 systemd 单元"
CPU_CORES=$(nproc 2>/dev/null || echo 2)
GUNICORN_WORKERS=$(( CPU_CORES * 2 + 1 ))
[[ $GUNICORN_WORKERS -gt 8 ]] && GUNICORN_WORKERS=8

render_unit() {
    local src="$1" dst="$2"
    sed -e "s|__PEM_INSTALL_DIR__|${INSTALL_DIR}|g" \
        -e "s|__PEM_GUNICORN_WORKERS__|${GUNICORN_WORKERS}|g" \
        -e "s|__PEM_STATIC_ROOT__|${STATIC_ROOT}|g" \
        "$src" >"$dst"
}

render_unit "${INSTALL_DIR}/deploy/templates/pemanager-backend.service" \
            "${SYSTEMD_DIR}/pemanager-backend.service"
render_unit "${INSTALL_DIR}/deploy/templates/pemanager-monitor.service" \
            "${SYSTEMD_DIR}/pemanager-monitor.service"

systemctl daemon-reload
systemctl enable pemanager-backend.service pemanager-monitor.service >/dev/null
systemctl restart pemanager-backend.service
sleep 2
systemctl restart pemanager-monitor.service || warn "monitor 服务首次启动可能因尚无任务而退出，可忽略"
ok "后端服务已 enable + restart（workers=${GUNICORN_WORKERS}）"

# ============================================================================
# 8. nginx 站点
# ============================================================================
log "[8/10] 配置 nginx 站点"
if [[ "$UPDATE_ONLY" -eq 1 && -f "$NGINX_SITE_AVAIL" ]]; then
    ok "更新模式：保留现有 nginx 站点（${NGINX_SITE_AVAIL}）"
else
    sed -e "s|__PEM_INSTALL_DIR__|${INSTALL_DIR}|g" \
        -e "s|__PEM_STATIC_ROOT__|${STATIC_ROOT}|g" \
        "${INSTALL_DIR}/deploy/templates/nginx-pemanager.conf" \
        >"$NGINX_SITE_AVAIL"
    [[ -L "$NGINX_SITE_ENAB" ]] || ln -s "$NGINX_SITE_AVAIL" "$NGINX_SITE_ENAB"
    # 关闭 default site（与本站点的 listen 80 default_server 冲突）
    if [[ -L /etc/nginx/sites-enabled/default ]]; then
        rm -f /etc/nginx/sites-enabled/default
        ok "已移除 /etc/nginx/sites-enabled/default"
    fi
fi
nginx -t
systemctl reload nginx || systemctl restart nginx
ok "nginx 已 reload"

# ============================================================================
# 9. sysctl + logrotate
# ============================================================================
log "[9/10] 配置 sysctl + logrotate"
SYSCTL_FILE=/etc/sysctl.d/99-pemanager-forward.conf
cat >"$SYSCTL_FILE" <<EOF
# PE Manager 路由场景需要 IP 转发
net.ipv4.ip_forward = 1
net.ipv6.conf.all.forwarding = 1
EOF
sysctl --system >/dev/null
ok "已配置 net.ipv4.ip_forward = 1"

cp "${INSTALL_DIR}/deploy/templates/logrotate.pemanager" /etc/logrotate.d/pemanager
chmod 0644 /etc/logrotate.d/pemanager
ok "logrotate 已安装"

# ============================================================================
# 10. 健康检查
# ============================================================================
log "[10/10] 健康检查"
sleep 1

HEALTH_OK=0
for ep in /api/accountmanage/health/ /api/interfacemanage/health/ /api/routemanage/health/ /api/operationmanage/health/; do
    code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1${ep}" || echo 000)
    if [[ "$code" == "200" ]]; then
        ok "GET ${ep} → 200"
        HEALTH_OK=$((HEALTH_OK + 1))
    else
        warn "GET ${ep} → ${code}（可能 ALLOWED_HOSTS 未含 127.0.0.1 / 服务尚未就绪）"
    fi
done

FRONT_CODE=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1/" || echo 000)
if [[ "$FRONT_CODE" == "200" ]]; then
    ok "GET / → 200（前端 SPA 已就绪）"
else
    warn "GET / → ${FRONT_CODE}（可能 nginx 端口被占或 SELinux 拦截）"
fi

echo
ok "==== 部署完成 ===="
echo
echo "服务管理："
echo "  systemctl status  pemanager-backend pemanager-monitor"
echo "  journalctl -fu    pemanager-backend"
echo "  systemctl restart pemanager-backend"
echo
echo "默认登录："
ADM_U=$(grep '^PEMANAGER_ADMIN_USERNAME=' "$ENV_FILE" | cut -d= -f2-)
ADM_P=$(grep '^PEMANAGER_ADMIN_PASSWORD=' "$ENV_FILE" | cut -d= -f2-)
echo "  用户名：${ADM_U:-admin}"
echo "  密  码：${ADM_P:-admin123}"
echo
echo "访问地址：http://<本机IP>/    （API：http://<本机IP>/api/）"
echo
echo "下次更新（仅同步代码、不动配置）："
echo "  sudo bash deploy/deploy.sh --update"
