# ssl.md — HTTPS 启用与证书管理

PE Manager 提供独立的 `deploy/ssl-setup.sh` 脚本，支持两种典型场景：

- **域名场景**：通过 [Let's Encrypt](https://letsencrypt.org/) 申请 90 天免费证书，并配置自动续期
- **IP 场景**：用 OpenSSL 生成 10 年自签名证书（无域名 / 内网环境）

> 启用 HTTPS 后，脚本会自动把目标域名 / IP 追加到 `/etc/pemanager/pemanager.env` 的
> `DJANGO_ALLOWED_HOSTS`、`DJANGO_CSRF_TRUSTED_ORIGINS`、`PEMANAGER_EXTRA_ORIGINS`，
> 并 `restart pemanager-backend`，无需手工编辑。

---

## 1. 先决条件

| 条件 | 说明 |
|---|---|
| `setup.sh` 已跑过 | 会自动装好 `certbot` 与 `python3-certbot-nginx`、`openssl` |
| `deploy.sh` 已跑过 | 已经生成 `/etc/nginx/sites-available/pemanager.conf` |
| 域名模式：80 端口可达公网 | Let's Encrypt 通过 HTTP-01 挑战验证；要求 `:80` 能从公网拨入 |
| 域名模式：DNS 已生效 | A/AAAA 记录已正确指向本机 |
| IP 模式：网络可达 | 浏览器/客户端能用该 IP 访问本机 80/443 |

---

## 2. 域名 + Let's Encrypt（推荐）

### 2.1 申请 + 启用

```bash
sudo bash deploy/ssl-setup.sh --domain pe.example.com --email admin@example.com
```

或在 `deploy.sh` 部署阶段一并启用：

```bash
sudo bash deploy/deploy.sh --ssl-domain pe.example.com --ssl-email admin@example.com
```

行为：
1. 把本站点的 `server_name` 改为 `pe.example.com _`，并在 80 server 里添加 `/.well-known/acme-challenge/` 静态目录
2. `reload nginx`
3. `certbot certonly --webroot -w /var/www/letsencrypt -d pe.example.com`
4. 在 `pemanager.conf` 文件末尾插入一段标记 `# >>> PEMANAGER-SSL >>>` ... `# <<< PEMANAGER-SSL <<<` 的 443 server 块（TLS 1.2/1.3、HSTS、与 80 同一套 location）
5. 把 80 server 块改为 `301 → https://$host$request_uri`（仍保留 `/.well-known` 留给续期挑战）
6. `reload nginx`，并联动写入 env

### 2.2 自动续期机制

| 系统 | 机制 |
|---|---|
| 现代 systemd（默认） | `certbot.timer` 每日两次检查；剩余 < 30 天才会真正向 ACME 申请；成功后调用 `/etc/letsencrypt/renewal-hooks/deploy/pemanager-reload-nginx.sh` 自动 `reload nginx` |
| 老系统 / 无 timer | 退化为 `/etc/cron.d/pemanager-certbot` 每日 03:00 `certbot renew --quiet --post-hook "systemctl reload nginx"` |

`deploy/ssl-setup.sh` 完成时已经为你启用 `certbot.timer`，无需手工干预。

### 2.3 测试（staging，不消耗速率限制）

```bash
sudo bash deploy/ssl-setup.sh --domain pe.example.com --staging
```

> Let's Encrypt 生产环境对同一域名每周最多 50 张；调试用 `--staging` 模拟。
> 调试通过后再去掉 `--staging` + `--force` 重签换成正式证书。

### 2.4 强制重签 / 切换域名

```bash
sudo bash deploy/ssl-setup.sh --domain pe.example.com --force
```

如需替换为另一个域名，先用 `certbot delete --cert-name old.example.com` 删除旧证书，再换 `--domain new.example.com`。

---

## 3. IP + 自签名

适合："只有 IP，没有域名" 或 "纯内网部署"。

### 3.1 启用

```bash
sudo bash deploy/ssl-setup.sh --ip                       # 自动取本机首个 IPv4
sudo bash deploy/ssl-setup.sh --ip 1.2.3.4
sudo bash deploy/ssl-setup.sh --ip 1.2.3.4,10.0.0.1      # 多 IP（写入 SAN）
sudo bash deploy/ssl-setup.sh --ip 1.2.3.4,fd00::1       # IPv6
```

或在部署阶段一并启用：

```bash
sudo bash deploy/deploy.sh --ssl-ip                # 自动 IP
sudo bash deploy/deploy.sh --ssl-ip 1.2.3.4        # 指定 IP
```

行为：
1. 在 `/etc/pemanager/ssl/` 生成 `cert.pem` + `key.pem`（RSA 2048，10 年），所有传入的 IP 写入 `subjectAltName: IP:1.2.3.4,...`
2. 同样插入 443 server 块 + 80→443 跳转 + HSTS
3. 浏览器首次访问会提示「证书无效 / NET::ERR_CERT_AUTHORITY_INVALID」，**这是预期行为**

### 3.2 让客户端"信任"自签名证书

- **Chrome / Edge**：地址栏「不安全」→ 证书 → 详细信息 → 导出 → 在客户端「钥匙串 / 受信任的根证书颁发机构」中导入并信任
- **Firefox**：「高级 → 接受风险」即可（Firefox 不读系统证书库）
- **curl**：`curl --cacert /etc/pemanager/ssl/cert.pem https://1.2.3.4/api/...`
- **Linux 客户端**：把 `cert.pem` 拷到 `/usr/local/share/ca-certificates/pemanager.crt` 后 `update-ca-certificates`

### 3.3 续期 / 重签

自签名 10 年到期前重跑即可：

```bash
sudo bash deploy/ssl-setup.sh --ip 1.2.3.4 --force
```

`--force` 会覆盖 `/etc/pemanager/ssl/cert.pem`，并 reload nginx。

---

## 4. 状态查询

```bash
sudo bash deploy/ssl-setup.sh --status
```

输出示例：

```
---- nginx ssl listener ----
    listen 443 ssl;
    ssl_certificate     /etc/letsencrypt/live/pe.example.com/fullchain.pem;
---- certbot 证书列表 ----
  Certificate Name: pe.example.com
    Expiry Date: 2026-08-21 14:13:08+00:00 (VALID: 89 days)
    Certificate Path: /etc/letsencrypt/live/pe.example.com/fullchain.pem
---- certbot.timer ----
● certbot.timer - Run certbot twice daily
   Active: active (waiting) since ...
---- 自签名证书 ----
(无 /etc/pemanager/ssl/cert.pem)
```

---

## 5. 手动续期 / 排错

```bash
# 主动触发一次续期检查
sudo bash deploy/ssl-setup.sh --renew

# 查看续期 journal
sudo journalctl -u certbot --since "1 day ago"

# 查看 nginx 错误
sudo nginx -t
sudo tail -n 100 /var/log/pemanager/nginx-error.log

# 临时禁用 HTTPS（仅保留 80）
sudo sed -i '/# >>> PEMANAGER-SSL >>>/,/# <<< PEMANAGER-SSL <<</d' /etc/nginx/sites-available/pemanager.conf
sudo systemctl reload nginx
```

---

## 6. 常见问题

### 6.1 `certbot` 提示 "DNS problem: NXDOMAIN"
A/AAAA 记录未生效或写错了；在能上网的机器上 `dig pe.example.com` 验证。

### 6.2 `certbot` 提示 "Connection refused" 或 "Timeout"
说明 ACME 服务器无法从公网访问本机 `:80`：
- 防火墙拦了：`sudo ss -ltn 'sport = :80'` 确认监听；机房安全组允许 80
- 端口被其它服务占了：`sudo lsof -i :80`

### 6.3 nginx 报 "cannot load certificate ... no such file"
你可能用 `--force` 在 staging 拿了证书，但 conf 里写的是生产路径。重跑：
```bash
sudo bash deploy/ssl-setup.sh --domain pe.example.com   # 不带 --staging
```

### 6.4 自签名场景，前端 axios 报 "self-signed certificate"
后端按浏览器手工信任即可；API 用 curl/脚本调用时加 `--insecure` 或导入证书。

### 6.5 想退到 HTTP
1. 编辑 `/etc/nginx/sites-available/pemanager.conf`，删除 `# >>> PEMANAGER-SSL >>>` ~ `# <<< PEMANAGER-SSL <<<` 之间的整段
2. 把 80 server 里的 `return 301 https://...` 改回原来的 `try_files` 行为（或直接重跑 `deploy.sh`，它会覆盖生成 80 配置）
3. `sudo systemctl reload nginx`

### 6.6 多站点共用 nginx
本脚本只动 `pemanager.conf`，不会污染其它 site；如有冲突的 `default_server` 关键字，请检查 `/etc/nginx/sites-enabled/` 是否有其他文件抢占了 443。

---

## 7. 端到端示例

### 7.1 域名 + 一键全量

```bash
# 1. 准备：DNS A 记录 pe.example.com → 1.2.3.4 已生效；安全组开 80/443
# 2. 安装依赖（含 certbot）
sudo bash deploy/setup.sh --yes
# 3. 部署 + HTTPS
sudo bash deploy/deploy.sh --ssl-domain pe.example.com --ssl-email admin@example.com

# 4. 验证
curl -I https://pe.example.com/
curl -fsSL https://pe.example.com/api/accountmanage/health/
sudo bash deploy/ssl-setup.sh --status
```

### 7.2 内网 IP + 自签名

```bash
sudo bash deploy/setup.sh --yes
sudo bash deploy/deploy.sh --ssl-ip 10.0.0.10

# 在客户端导入 /etc/pemanager/ssl/cert.pem 到根证书库后：
curl https://10.0.0.10/ -fsS
```
