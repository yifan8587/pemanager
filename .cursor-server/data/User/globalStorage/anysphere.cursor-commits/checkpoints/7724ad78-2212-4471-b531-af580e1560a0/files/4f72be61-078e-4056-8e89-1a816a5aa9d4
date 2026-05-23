# deploy.md — 生产部署文档

本文档描述 `deploy/deploy.sh` 的工作流、生成的目录结构、systemd / nginx 配置、权限模型、HTTPS 启用、升级与回滚。

---

## 1. 部署架构

```
                           ┌───────────────┐
   浏览器 / 用户  ──── 80 ──┤   nginx       │── unix sock ──┐
                           │   (静态前端    │               │
                           │    + /api 反代)│               ▼
                           └───────────────┘     ┌──────────────────┐
                                                 │ gunicorn (root)  │
                                                 │ Django + DRF     │
                                                 │                  │
                                                 │  ↓ subprocess    │
                                                 │  netplan / ip /  │
                                                 │  wg-quick / tc / │
                                                 │  nft / iptables  │
                                                 └──────────────────┘
                                                          │
                                                 ┌──────────────────┐
                                                 │ pemanager-monitor│
                                                 │ python manage.py │
                                                 │ monitor_loop     │
                                                 └──────────────────┘
```

---

## 2. 目录布局（部署后）

| 路径 | 用途 | 权限 |
|---|---|---|
| `/opt/pemanager/` | 项目源码 + venv + frontend/dist + deploy 模板 | `0755 root:root` |
| `/opt/pemanager/venv/` | Python 虚拟环境 | `0755 root:root` |
| `/opt/pemanager/frontend/dist/` | Vite 构建产物 | `0755 root:root` |
| `/etc/pemanager/pemanager.env` | 运行期环境变量（含 SECRET_KEY） | `0640 root:root` |
| `/var/lib/pemanager/` | 数据持久化根 | `0750 root:root` |
| `/var/lib/pemanager/db.sqlite3` | 主数据库 | `0640 root:root` |
| `/var/lib/pemanager/static/` | `collectstatic` 输出 | `0755 root:root` |
| `/var/log/pemanager/` | Gunicorn / nginx / monitor 日志 | `0755 root:root` |
| `/run/pemanager/backend.sock` | Gunicorn unix socket | `0660`，运行时创建 |
| `/etc/systemd/system/pemanager-backend.service` | 后端 systemd 单元 | `0644` |
| `/etc/systemd/system/pemanager-monitor.service` | 监控 systemd 单元 | `0644` |
| `/etc/nginx/sites-available/pemanager.conf` | nginx 站点 | `0644` |
| `/etc/nginx/sites-enabled/pemanager.conf` | nginx 启用软链 | `lrwxrwxrwx` |
| `/etc/sysctl.d/99-pemanager-forward.conf` | 启用 IP 转发 | `0644` |
| `/etc/logrotate.d/pemanager` | 日志轮转 | `0644` |

---

## 3. 一键部署

### 3.1 首次部署

```bash
cd /root/pemanager                     # 进入源码根
sudo bash deploy/setup.sh --yes        # 安装系统依赖
sudo bash deploy/deploy.sh             # 一键部署
```

完成后访问：
- 前端：`http://<本机IP>/`
- API：`http://<本机IP>/api/accountmanage/health/`
- 默认账号：`admin` / `admin123`（详见 `/etc/pemanager/pemanager.env`）

### 3.2 升级（仅更新代码、不动配置）

```bash
cd /root/pemanager
git pull                               # 拉取最新代码（如使用 git）
sudo bash deploy/deploy.sh --update    # 同步代码、装依赖、build、migrate、重启
```

`--update` 模式行为：
- 同步源码到 `/opt/pemanager/`（保留 venv / dist / db）
- 重装 Python / npm 依赖
- 重新 `vite build`
- `migrate` + `collectstatic`
- 重启 `pemanager-backend.service` 与 `pemanager-monitor.service`
- **保留** 已有 `/etc/pemanager/pemanager.env` 与 `/etc/nginx/sites-available/pemanager.conf`

### 3.3 在另一台机器部署 / 指定源码

```bash
sudo bash deploy/deploy.sh \
    --src /tmp/pemanager-src \
    --host pe.example.com          # 把 pe.example.com 追加进 ALLOWED_HOSTS
```

---

## 4. 配置详解

### 4.1 `/etc/pemanager/pemanager.env`

部署完成后，编辑此文件即可调整运行参数；改动后执行：

```bash
sudo systemctl restart pemanager-backend pemanager-monitor
```

关键字段（完整字段见模板 [`templates/pemanager.env.example`](./templates/pemanager.env.example)）：

| 字段 | 默认 | 说明 |
|---|---|---|
| `DJANGO_DEBUG` | `0` | 生产关闭；开启会回退到详细错误页 |
| `DJANGO_SECRET_KEY` | 部署时随机生成 | 多机部署 **请勿** 复用 |
| `DJANGO_ALLOWED_HOSTS` | `127.0.0.1,localhost,<本机IP>` | 用逗号分隔，新增域名后请重启 |
| `DJANGO_DB_PATH` | `/var/lib/pemanager/db.sqlite3` | 改为外置存储时也要同步授权 |
| `PEMANAGER_ADMIN_*` | `admin / admin123` | **首次** `migrate` 时生效；之后修改请走前端「账号管理」 |
| `INTERFACEMANAGE_*_ENABLED` 等 | `1` | 全部下发开关；演示环境可置 `0` 只读 |
| `OPERATION_SCHEDULER_AUTOSTART` | `0` | 默认由独立的 `pemanager-monitor.service` 负责调度 |
| `*_CMD_PREFIX` | 空 | "非 root 模式"需设为 `sudo -n` |

### 4.2 systemd 单元

```bash
systemctl status pemanager-backend
systemctl status pemanager-monitor
journalctl -fu pemanager-backend         # 实时日志
journalctl -u pemanager-monitor --since "1h ago"
```

后端单元（关键行）：

```ini
EnvironmentFile=/etc/pemanager/pemanager.env
ExecStart=/opt/pemanager/venv/bin/gunicorn \
  --workers <CPU*2+1, ≤8> \
  --bind unix:/run/pemanager/backend.sock \
  config.wsgi:application
```

调整 worker 数量：编辑 `/etc/systemd/system/pemanager-backend.service` 后：

```bash
sudo systemctl daemon-reload
sudo systemctl restart pemanager-backend
```

### 4.3 nginx 站点

完整模板：[`templates/nginx-pemanager.conf`](./templates/nginx-pemanager.conf)

要点：
- `listen 80 default_server`：占用 80 端口；`deploy.sh` 会删除 `/etc/nginx/sites-enabled/default`
- 前端 SPA 路由：`try_files $uri $uri/ /index.html`
- `/api/` 反代到 unix socket，`proxy_read_timeout 300s`（长 mtr/ping 不会被截断）
- `/static/` 反代 Django `collectstatic` 目录（admin / DRF browsable API）
- 静态资源 30 天强缓存（Vite 产物自带哈希）

调整 server_name / 限速 / 大小限制后：

```bash
sudo nginx -t && sudo systemctl reload nginx
```

---

## 5. 权限模型

### 5.1 默认：以 root 运行

最简洁可用的模型，**也是项目默认设计**：
- `pemanager-backend.service` 与 `pemanager-monitor.service` 以 `root` 运行
- 后端能直接调用 `netplan` / `wg-quick` / `ip` / `tc` / `nft` / `iptables` / `journalctl`
- 配置文件 `/etc/netplan/99-pemanager-*.yaml`、`/etc/wireguard/*.conf` 都能直接写入
- 适用：内网管理面板、单机 PE 设备

### 5.2 可选：非 root 运行（更严格）

如需限权部署：

1) 创建系统用户

```bash
sudo useradd --system --shell /usr/sbin/nologin --home /opt/pemanager pemanager
sudo chown -R pemanager:pemanager /opt/pemanager /var/lib/pemanager /var/log/pemanager
```

2) 修改 systemd unit

```bash
sudo sed -i 's/^User=root$/User=pemanager/;s/^Group=root$/Group=pemanager/' \
    /etc/systemd/system/pemanager-backend.service \
    /etc/systemd/system/pemanager-monitor.service
sudo systemctl daemon-reload
```

3) 安装 sudoers fragment

```bash
sudo install -m 0440 /opt/pemanager/deploy/templates/sudoers.pemanager \
    /etc/sudoers.d/pemanager
sudo visudo -cf /etc/sudoers.d/pemanager
```

4) 修改 env 文件

```bash
sudo sed -i 's|^\(INTERFACEMANAGE_NETPLAN_CMD_PREFIX\)=.*|\1=sudo -n|' /etc/pemanager/pemanager.env
sudo sed -i 's|^\(QOSMANAGE_CMD_PREFIX\)=.*|\1=sudo -n|'              /etc/pemanager/pemanager.env
sudo sed -i 's|^\(FIREWALLMANAGE_CMD_PREFIX\)=.*|\1=sudo -n|'         /etc/pemanager/pemanager.env
sudo sed -i 's|^\(LOGMANAGE_JOURNAL_CMD_PREFIX\)=.*|\1=sudo -n|'      /etc/pemanager/pemanager.env
```

5) 重启

```bash
sudo systemctl restart pemanager-backend pemanager-monitor
```

> **注意**：非 root 模式下，pemanager 用户对 `/etc/netplan/`、`/etc/wireguard/` 的写入仍需通过 `sudo -n tee` 或调整文件 ACL。当前 `*_writing.py` 直接 `open(path, 'w')` 写入，需配合 ACL 或 `setfacl -m u:pemanager:rw /etc/netplan/99-pemanager-*.yaml`。生产环境建议使用 root 模式。

---

## 6. 启用 HTTPS（Let's Encrypt）

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d pe.example.com
```

certbot 会自动在 `/etc/nginx/sites-available/pemanager.conf` 追加 443 server 块、80→443 跳转，并装好自动续期 cron。

---

## 7. 备份与恢复

### 7.1 关键备份对象

| 路径 | 频率 | 备份方法 |
|---|---|---|
| `/var/lib/pemanager/db.sqlite3` | 每日 | `sqlite3 db.sqlite3 ".backup '/backup/db-$(date +%F).sqlite3'"` |
| `/etc/pemanager/pemanager.env` | 修改后立即 | `cp` |
| `/etc/netplan/99-pemanager-*.yaml` | 修改后立即 | `cp`（理论上由 PE 管理） |
| `/etc/wireguard/*.conf` | 修改后立即 | `cp`（理论上由 PE 管理） |

### 7.2 恢复到新机

```bash
# 1. 在新机上运行 setup.sh + deploy.sh（首次部署）
sudo bash deploy/setup.sh --yes
sudo bash deploy/deploy.sh

# 2. 停服务
sudo systemctl stop pemanager-backend pemanager-monitor

# 3. 还原数据库与 env
sudo cp /backup/db-2026-05-22.sqlite3 /var/lib/pemanager/db.sqlite3
sudo cp /backup/pemanager.env /etc/pemanager/pemanager.env

# 4. 启动
sudo systemctl start pemanager-backend pemanager-monitor
```

### 7.3 迁移到 PostgreSQL（可选）

默认 SQLite 适合单机 / 中小规模。当并发写入或行数明显增多时可迁移到 PostgreSQL：

```bash
sudo apt install postgresql python3-psycopg2
sudo -u postgres createuser -P pemanager      # 输入密码
sudo -u postgres createdb -O pemanager pemanager
```

`/opt/pemanager/venv/bin/pip install psycopg[binary]` 后，编辑 `/etc/pemanager/pemanager.env` 增加：

```env
DJANGO_DB_URL=postgres://pemanager:<pwd>@127.0.0.1:5432/pemanager
```

> 当前 `settings.py` 暂不解析 `DJANGO_DB_URL`；若需切换 PG，请编辑 `/opt/pemanager/backend/config/settings.py` 中 `DATABASES`，并执行 `python manage.py migrate`。如需我们补 `dj-database-url` 集成，请提 issue。

---

## 8. 故障排查

| 现象 | 排查 |
|---|---|
| `502 Bad Gateway` | `systemctl status pemanager-backend`、确认 `/run/pemanager/backend.sock` 存在；`journalctl -u pemanager-backend -n 200` |
| `400 Bad Request DisallowedHost` | `ALLOWED_HOSTS` 未包含访问域名；`sudo bash deploy/deploy.sh --host pe.example.com` 或手工编辑 env |
| 「下发到系统」按钮失败 | `journalctl -u pemanager-backend`；典型原因：`netplan generate` 失败、`/etc/netplan/` 权限不对、非 root 模式但 `*_CMD_PREFIX` 没配 |
| WireGuard 路由不通 | `wg show <ifname>`、`ip route`；检查 `/etc/wireguard/<ifname>.conf` 中 `[Interface]` 的 `Address` 与意图一致 |
| 监控图表为空 | `journalctl -u pemanager-monitor -f`；可能没创建监控目标；点击「品质监控 → 新增」 |
| 修改 env 不生效 | `sudo systemctl restart pemanager-backend pemanager-monitor` |
| nginx 配置改了不生效 | `sudo nginx -t && sudo systemctl reload nginx` |
| db 文件读不动 | 检查 `chown root:root /var/lib/pemanager/db.sqlite3` 与运行用户匹配 |

### 8.1 日志一览

```bash
journalctl -u pemanager-backend -f     # 后端实时
journalctl -u pemanager-monitor -f     # 监控实时
tail -f /var/log/pemanager/gunicorn-error.log
tail -f /var/log/pemanager/nginx-error.log
```

### 8.2 卸载

```bash
sudo systemctl stop pemanager-backend pemanager-monitor
sudo systemctl disable pemanager-backend pemanager-monitor
sudo rm -f /etc/systemd/system/pemanager-{backend,monitor}.service
sudo rm -f /etc/nginx/sites-enabled/pemanager.conf /etc/nginx/sites-available/pemanager.conf
sudo rm -f /etc/sysctl.d/99-pemanager-forward.conf /etc/logrotate.d/pemanager
sudo rm -rf /opt/pemanager
# 视情况删除数据：
# sudo rm -rf /var/lib/pemanager /var/log/pemanager /etc/pemanager
sudo systemctl daemon-reload
sudo systemctl reload nginx
```

---

## 9. 升级清单（开发者）

- 修改了 `settings.py` 或 env 字段 → 同步更新 [`templates/pemanager.env.example`](./templates/pemanager.env.example)
- 新增 ViewSet / action → 同步更新 [API.md](./API.md)
- 新增 systemd 调度任务 → 在 `deploy.sh` 第 7 步追加 unit 渲染、enable、restart
- 新增 root 系统命令 → 同步更新 [`templates/sudoers.pemanager`](./templates/sudoers.pemanager) 的 `Cmnd_Alias`
