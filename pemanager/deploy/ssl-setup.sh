#!/usr/bin/env bash
# =============================================================================
# PE Manager — SSL 一键启用脚本
#
# 两种模式：
#
#   1) 域名模式（推荐）：自动申请 Let's Encrypt 免费证书 + 自动续期
#        sudo bash deploy/ssl-setup.sh --domain pe.example.com [--email admin@example.com]
#        sudo bash deploy/ssl-setup.sh --domain pe.example.com --staging   # 测试不消耗速率限制
#
#   2) IP 模式：用 OpenSSL 生成 10 年自签名证书并启用 HTTPS（浏览器会提示不安全，可手工信任）
#        sudo bash deploy/ssl-setup.sh --ip                  # 自动取本机首个非回环 IPv4
#        sudo bash deploy/ssl-setup.sh --ip 1.2.3.4
#        sudo bash deploy/ssl-setup.sh --ip 1.2.3.4,fd00::1  # 多 IP/SAN，逗号分隔
#
# 公共参数：
#   --force         证书已存在时强制重签
#   --renew         仅触发一次续期检查（适用于 cron 或人工排查）
#   --status        打印当前 HTTPS / 证书 / 续期 timer 状态
#
# 部署完成后将：
#   - /etc/nginx/sites-available/pemanager.conf 内追加 443 server 块 + 80→443 跳转
#   - HSTS、SSL 现代参数（TLS1.2+ / 强加密套件）
#   - /etc/pemanager/pemanager.env 自动追加域名/IP 到 DJANGO_ALLOWED_HOSTS、CSRF_TRUSTED_ORIGINS
#   - certbot 模式：依赖系统 certbot.timer（每日两次）自动续期，并 reload nginx
# =============================================================================

set -Eeuo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log()  { printf "${BLUE}[ssl]${NC} %s\n" "$*"; }
ok()   { printf "${GREEN}[ ok ]${NC} %s\n" "$*"; }
warn() { printf "${YELLOW}[warn]${NC} %s\n" "$*"; }
err()  { printf "${RED}[ err]${NC} %s\n" "$*" >&2; }
trap 'err "脚本在第 ${LINENO} 行失败，退出码 $?"' ERR

[[ $EUID -eq 0 ]] || { err "请以 root 运行（sudo bash deploy/ssl-setup.sh ...）"; exit 1; }

MODE=""                # domain | ip
DOMAIN=""
EMAIL=""
IP_LIST=""
STAGING=0
FORCE=0
RENEW_ONLY=0
STATUS_ONLY=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --domain)  MODE="domain"; DOMAIN="$2"; shift 2 ;;
        --email)   EMAIL="$2"; shift 2 ;;
        --ip)      MODE="ip"
                   if [[ $# -ge 2 && "$2" != --* ]]; then IP_LIST="$2"; shift 2; else shift; fi
                   ;;
        --staging) STAGING=1; shift ;;
        --force)   FORCE=1; shift ;;
        --renew)   RENEW_ONLY=1; shift ;;
        --status)  STATUS_ONLY=1; shift ;;
        -h|--help) grep -E '^# (两种模式|域名|IP|公共参数|部署完成后)' "$0" | sed 's/^# //'; exit 0 ;;
        *) err "未知参数: $1"; exit 2 ;;
    esac
done

# --------- 常量 ---------
NGINX_SITE_AVAIL="/etc/nginx/sites-available/pemanager.conf"
NGINX_SITE_ENAB="/etc/nginx/sites-enabled/pemanager.conf"
SSL_DIR="/etc/pemanager/ssl"
ENV_FILE="/etc/pemanager/pemanager.env"
HSTS_LINE='add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;'

# --------- 状态查询 ---------
if [[ $STATUS_ONLY -eq 1 ]]; then
    echo "---- nginx ssl listener ----"
    grep -E 'listen .* ssl|ssl_certificate' "$NGINX_SITE_AVAIL" 2>/dev/null || echo "(未发现 ssl 配置)"
    echo
    echo "---- certbot 证书列表 ----"
    if command -v certbot >/dev/null 2>&1; then certbot certificates 2>&1 || true; else echo "(未装 certbot)"; fi
    echo
    echo "---- certbot.timer（自动续期）----"
    systemctl status certbot.timer --no-pager 2>&1 | head -n 20 || true
    echo
    echo "---- 自签名证书 ----"
    if [[ -f "${SSL_DIR}/cert.pem" ]]; then
        openssl x509 -in "${SSL_DIR}/cert.pem" -noout -subject -issuer -dates -ext subjectAltName 2>&1 || true
    else
        echo "(无 ${SSL_DIR}/cert.pem)"
    fi
    exit 0
fi

# --------- 续期 ---------
if [[ $RENEW_ONLY -eq 1 ]]; then
    if ! command -v certbot >/dev/null 2>&1; then
        err "未安装 certbot，无法续期"
        exit 1
    fi
    certbot renew --quiet --post-hook "systemctl reload nginx"
    ok "renew 命令完成；具体续期结果见 journalctl -u certbot"
    exit 0
fi

# --------- 模式校验 ---------
if [[ -z "$MODE" ]]; then
    err "请通过 --domain <fqdn> 或 --ip [<addr>[,addr...]] 指定模式"
    exit 2
fi

# 校验 nginx 站点存在
if [[ ! -f "$NGINX_SITE_AVAIL" ]]; then
    err "未找到 ${NGINX_SITE_AVAIL}，请先 sudo bash deploy/deploy.sh"
    exit 1
fi

# 准备 SSL 目录
mkdir -p "$SSL_DIR"
chmod 0700 "$SSL_DIR"

# --------- 工具：编辑 env 追加 host ---------
add_env_host_csrf() {
    local host="$1" scheme_url="$2"
    [[ -f "$ENV_FILE" ]] || { warn "${ENV_FILE} 不存在；跳过 ALLOWED_HOSTS/CSRF 配置"; return; }

    # 1) DJANGO_ALLOWED_HOSTS 追加
    if ! grep -q "^DJANGO_ALLOWED_HOSTS=" "$ENV_FILE"; then
        echo "DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost,${host}" >> "$ENV_FILE"
    elif ! grep "^DJANGO_ALLOWED_HOSTS=" "$ENV_FILE" | grep -q "$host"; then
        sed -i "s|^DJANGO_ALLOWED_HOSTS=\(.*\)|DJANGO_ALLOWED_HOSTS=\1,${host}|" "$ENV_FILE"
    fi
    # 2) CSRF_TRUSTED_ORIGINS 追加
    if ! grep -q "^DJANGO_CSRF_TRUSTED_ORIGINS=" "$ENV_FILE"; then
        echo "DJANGO_CSRF_TRUSTED_ORIGINS=${scheme_url}" >> "$ENV_FILE"
    elif ! grep "^DJANGO_CSRF_TRUSTED_ORIGINS=" "$ENV_FILE" | grep -q "$scheme_url"; then
        sed -i "s|^DJANGO_CSRF_TRUSTED_ORIGINS=\(.*\)|DJANGO_CSRF_TRUSTED_ORIGINS=\1,${scheme_url}|" "$ENV_FILE"
    fi
    # 3) PEMANAGER_EXTRA_ORIGINS（前后端跨域时也用得到）
    if ! grep -q "^PEMANAGER_EXTRA_ORIGINS=" "$ENV_FILE"; then
        echo "PEMANAGER_EXTRA_ORIGINS=${scheme_url}" >> "$ENV_FILE"
    elif ! grep "^PEMANAGER_EXTRA_ORIGINS=" "$ENV_FILE" | grep -q "$scheme_url"; then
        sed -i "s|^PEMANAGER_EXTRA_ORIGINS=\(.*\)|PEMANAGER_EXTRA_ORIGINS=\1,${scheme_url}|" "$ENV_FILE"
    fi
    ok "已联动 ${ENV_FILE}（HOSTS / CSRF）；下一次 systemctl restart pemanager-backend 生效"
}

# --------- 通用：写入 server_name、443 server 块、80→443 跳转 ---------
# 入参：$1=server_name 字符串（多值用空格分隔）  $2=证书 path  $3=私钥 path
inject_https_block() {
    local sn="$1" cert="$2" key="$3"

    # 1) 改写 80 server 块的 server_name 为目标 server_name（同时保留 _）
    #    避免重复修改：先把 server_name <旧> 行匹配后整体替换
    if grep -q "^[[:space:]]*server_name[[:space:]]" "$NGINX_SITE_AVAIL"; then
        sed -i "s|^\([[:space:]]*\)server_name[[:space:]].*;|\1server_name ${sn} _;|" "$NGINX_SITE_AVAIL"
    fi

    # 2) 已有 443 server 块？删旧的（位于本配置文件末尾的 # >>> PEMANAGER-SSL >>> 标记之间）
    if grep -q "# >>> PEMANAGER-SSL >>>" "$NGINX_SITE_AVAIL"; then
        sed -i '/# >>> PEMANAGER-SSL >>>/,/# <<< PEMANAGER-SSL <<</d' "$NGINX_SITE_AVAIL"
    fi

    # 3) 把原 80 server 块中的所有 location 块抽出，复制到 443 块复用（用临时文件做扩展）
    #    最稳的做法：直接在文件末尾追加一个 443 server 块，并用同样的 location 配置
    #    （proxy_pass / try_files / static 等都是同源的，可以重复声明）
    local STATIC_ROOT_LINE
    STATIC_ROOT_LINE=$(grep -E "^[[:space:]]*alias[[:space:]]+/var/lib/pemanager" "$NGINX_SITE_AVAIL" | head -n1 | awk '{print $2}' | sed 's/;$//')
    [[ -z "$STATIC_ROOT_LINE" ]] && STATIC_ROOT_LINE="/var/lib/pemanager/static/"

    local DIST_ROOT
    DIST_ROOT=$(grep -E "^[[:space:]]*root[[:space:]]+/opt/pemanager" "$NGINX_SITE_AVAIL" | head -n1 | awk '{print $2}' | sed 's/;$//')
    [[ -z "$DIST_ROOT" ]] && DIST_ROOT="/opt/pemanager/frontend/dist"

    cat >>"$NGINX_SITE_AVAIL" <<EOF

# >>> PEMANAGER-SSL >>>
# 由 deploy/ssl-setup.sh 写入。请勿手工编辑此块；下一次执行 ssl-setup.sh 会被整段替换。
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;
    server_name ${sn};

    ssl_certificate     ${cert};
    ssl_certificate_key ${key};
    ssl_session_timeout 1d;
    ssl_session_cache shared:PEM:10m;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;
    ssl_ciphers "ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384";
    ${HSTS_LINE}

    client_max_body_size 16M;
    client_body_buffer_size 1M;
    access_log /var/log/pemanager/nginx-access.log;
    error_log  /var/log/pemanager/nginx-error.log;

    root ${DIST_ROOT};
    index index.html;

    location / { try_files \$uri \$uri/ /index.html; }

    location ~* \.(?:js|css|woff2?|ttf|otf|eot|ico|png|jpg|jpeg|gif|svg|webp)\$ {
        expires 30d;
        add_header Cache-Control "public, immutable";
        try_files \$uri =404;
    }

    location /static/ {
        alias ${STATIC_ROOT_LINE};
        expires 7d;
        add_header Cache-Control "public";
    }

    location /api/ {
        proxy_pass http://pemanager_backend;
        proxy_http_version 1.1;
        proxy_set_header Host              \$host;
        proxy_set_header X-Real-IP         \$remote_addr;
        proxy_set_header X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Connection        "";
        proxy_read_timeout  300s;
        proxy_send_timeout  300s;
        proxy_connect_timeout 10s;
        proxy_buffering off;
    }

    location /admin/ {
        proxy_pass http://pemanager_backend;
        proxy_http_version 1.1;
        proxy_set_header Host              \$host;
        proxy_set_header X-Real-IP         \$remote_addr;
        proxy_set_header X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
# <<< PEMANAGER-SSL <<<
EOF

    # 4) 把 80 server 块的 location / 改为 301 到 https，其他 location 也跳转
    #    采用比较激进的策略：80 server 内只保留 /.well-known/acme-challenge/ + 跳转
    #    使用 awk 替换 80 server 块
    python3 - "$NGINX_SITE_AVAIL" "$sn" <<'PYEOF'
import sys, re
path, sn = sys.argv[1], sys.argv[2]
with open(path) as f:
    text = f.read()

# 仅匹配第一段 80 server 块（# >>> PEMANAGER-SSL >>> 之前的）
def replace_first_80(text):
    pattern = re.compile(
        r"(server\s*\{\s*[^}]*?listen\s+80[^}]*?\})",  # 不够 robust，但够用
        re.DOTALL,
    )
    repl = (
        "server {\n"
        "    listen 80 default_server;\n"
        "    listen [::]:80 default_server;\n"
        f"    server_name {sn} _;\n"
        "    access_log /var/log/pemanager/nginx-access.log;\n"
        "    error_log  /var/log/pemanager/nginx-error.log;\n"
        "\n"
        "    # ACME challenge 直发到磁盘（certbot --webroot 兼容）\n"
        "    location /.well-known/acme-challenge/ {\n"
        "        root /var/www/letsencrypt;\n"
        "        default_type text/plain;\n"
        "    }\n"
        "\n"
        "    location / { return 301 https://$host$request_uri; }\n"
        "}"
    )
    new_text, n = pattern.subn(repl, text, count=1)
    if n == 0:
        return text
    return new_text

text = replace_first_80(text)
with open(path, "w") as f:
    f.write(text)
PYEOF

    mkdir -p /var/www/letsencrypt
    chown -R root:root /var/www/letsencrypt
    chmod 0755 /var/www/letsencrypt
}

reload_nginx() {
    nginx -t
    systemctl reload nginx || systemctl restart nginx
    ok "nginx 已 reload"
}

# ===========================================================================
# 域名模式
# ===========================================================================
do_domain_mode() {
    local domain="$1" email="$2"
    [[ -n "$domain" ]] || { err "--domain 不能为空"; exit 2; }

    if ! command -v certbot >/dev/null 2>&1; then
        err "未安装 certbot；请先 sudo bash deploy/setup.sh 或 sudo apt install certbot python3-certbot-nginx"
        exit 1
    fi

    # certbot 模式选择：优先 webroot（不影响现有 nginx 流量）
    local CERT_DIR="/etc/letsencrypt/live/${domain}"
    if [[ -d "$CERT_DIR" && $FORCE -ne 1 ]]; then
        ok "${CERT_DIR} 已存在；将复用现有证书（如要重签请加 --force）"
    else
        # 先确保 80 端口监听包含本域名并暴露 /.well-known
        log "在 nginx 80 server 中预留 ACME 挑战目录 /var/www/letsencrypt"
        mkdir -p /var/www/letsencrypt
        # 临时改 server_name（这样 ACME 的 HTTP-01 才能命中本站点）
        sed -i "s|^\([[:space:]]*\)server_name[[:space:]].*;|\1server_name ${domain} _;|" "$NGINX_SITE_AVAIL"
        # 临时插入 /.well-known/acme-challenge 的 location（如不存在）
        if ! grep -q "/.well-known/acme-challenge/" "$NGINX_SITE_AVAIL"; then
            sed -i "/listen 80/,/^}/{ /^}/i\\
    location /.well-known/acme-challenge/ { root /var/www/letsencrypt; default_type text/plain; }
            }" "$NGINX_SITE_AVAIL"
        fi
        reload_nginx

        local CB_OPTS=(certonly --webroot -w /var/www/letsencrypt -d "$domain" --non-interactive --agree-tos)
        if [[ -n "$email" ]]; then
            CB_OPTS+=(--email "$email")
        else
            CB_OPTS+=(--register-unsafely-without-email)
        fi
        [[ $STAGING -eq 1 ]] && CB_OPTS+=(--staging)
        [[ $FORCE -eq 1 ]]   && CB_OPTS+=(--force-renewal)

        log "调用 certbot 申请证书：certbot ${CB_OPTS[*]}"
        certbot "${CB_OPTS[@]}"
        ok "证书已签发：${CERT_DIR}"
    fi

    inject_https_block "$domain" "${CERT_DIR}/fullchain.pem" "${CERT_DIR}/privkey.pem"
    reload_nginx
    add_env_host_csrf "$domain" "https://${domain}"

    # 配置自动续期 hook（reload nginx）
    mkdir -p /etc/letsencrypt/renewal-hooks/deploy
    cat >/etc/letsencrypt/renewal-hooks/deploy/pemanager-reload-nginx.sh <<'EOF'
#!/usr/bin/env bash
systemctl reload nginx >/dev/null 2>&1 || systemctl restart nginx
EOF
    chmod 0755 /etc/letsencrypt/renewal-hooks/deploy/pemanager-reload-nginx.sh

    # 确保 certbot.timer 启用
    if systemctl list-unit-files | grep -q '^certbot\.timer'; then
        systemctl enable --now certbot.timer >/dev/null 2>&1 || true
        ok "已启用 certbot.timer（每日自动续期；剩余 <30 天才会真签）"
    else
        warn "未发现 certbot.timer；将退化为 cron"
        cat >/etc/cron.d/pemanager-certbot <<EOF
0 3 * * * root certbot renew --quiet --post-hook "systemctl reload nginx"
EOF
        chmod 0644 /etc/cron.d/pemanager-certbot
        ok "cron 已写入 /etc/cron.d/pemanager-certbot（每日 03:00 续期）"
    fi

    ok "==== HTTPS 启用完成 ===="
    echo "    访问：https://${domain}/"
    echo "    续期：sudo bash deploy/ssl-setup.sh --renew"
    echo "    状态：sudo bash deploy/ssl-setup.sh --status"
    [[ -f "$ENV_FILE" ]] && systemctl restart pemanager-backend 2>/dev/null || true
}

# ===========================================================================
# IP 自签名模式
# ===========================================================================
do_ip_mode() {
    local ip_list="$1"
    if [[ -z "$ip_list" ]]; then
        # 自动取本机首个非回环 IPv4
        ip_list="$(hostname -I 2>/dev/null | awk '{print $1}')"
        [[ -z "$ip_list" ]] && { err "未检测到本机 IPv4，请显式传 --ip <addr>"; exit 1; }
        log "未指定 --ip，自动使用本机 IP：${ip_list}"
    fi

    local CERT="${SSL_DIR}/cert.pem"
    local KEY="${SSL_DIR}/key.pem"

    if [[ -f "$CERT" && $FORCE -ne 1 ]]; then
        ok "${CERT} 已存在；将复用（如要重签请加 --force）"
    else
        log "生成 10 年自签名证书：${CERT}"
        # 构造 SAN
        local SAN=""
        IFS=',' read -ra IPS <<<"$ip_list"
        local primary="${IPS[0]}"
        for ip in "${IPS[@]}"; do
            ip="${ip// /}"
            [[ -z "$ip" ]] && continue
            SAN+="IP:${ip},"
        done
        SAN="${SAN%,}"
        local CONF="${SSL_DIR}/openssl.cnf"
        cat >"$CONF" <<EOF
[req]
distinguished_name = req_dn
req_extensions     = v3_req
prompt             = no
[req_dn]
C  = CN
O  = PE Manager
CN = ${primary}
[v3_req]
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth, clientAuth
subjectAltName = ${SAN}
EOF
        openssl req -x509 -nodes -newkey rsa:2048 \
            -days 3650 \
            -keyout "$KEY" \
            -out    "$CERT" \
            -config "$CONF" \
            -extensions v3_req >/dev/null 2>&1
        chmod 0600 "$KEY"
        chmod 0644 "$CERT"
        ok "已生成：${CERT} / ${KEY}（SAN=${SAN}）"
    fi

    # 主机名用 _ 占位（IP 场景无 server_name）
    inject_https_block "_" "$CERT" "$KEY"
    reload_nginx

    IFS=',' read -ra IPS <<<"$ip_list"
    for ip in "${IPS[@]}"; do
        ip="${ip// /}"; [[ -z "$ip" ]] && continue
        add_env_host_csrf "$ip" "https://${ip}"
    done

    ok "==== HTTPS（自签名）启用完成 ===="
    echo "    访问：https://${IPS[0]}/   （浏览器会提示「不安全」，可手工信任本证书）"
    echo "    证书：${CERT}"
    echo "    续期：自签名 10 年；到期前重跑：sudo bash deploy/ssl-setup.sh --ip ${ip_list} --force"
    [[ -f "$ENV_FILE" ]] && systemctl restart pemanager-backend 2>/dev/null || true
}

case "$MODE" in
    domain) do_domain_mode "$DOMAIN" "$EMAIL" ;;
    ip)     do_ip_mode    "$IP_LIST" ;;
    *)      err "未知模式：$MODE"; exit 2 ;;
esac
