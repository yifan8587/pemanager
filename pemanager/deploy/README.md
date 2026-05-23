# PE Manager — 部署目录

```
deploy/
├── setup.sh           # 环境检查 + 自动安装/升级（apt 系）
├── deploy.sh          # 一键生产部署（含可选 --ssl-domain / --ssl-ip）
├── ssl-setup.sh       # HTTPS 启用：Let's Encrypt（域名）或自签名（IP）
├── package.sh         # 制作可分发的离线压缩包（含 wheels/debs/dist 选项）
│
├── setup.md           # → 环境检查 + 版本升级文档
├── deploy.md          # → 生产部署文档（目录结构 / systemd / nginx / 权限）
├── ssl.md             # → HTTPS 启用 / 续期 / 自签名详细指南
├── package.md         # → 离线压缩包制作与离线安装指南
├── API.md             # → REST API 文档
│
└── templates/
    ├── nginx-pemanager.conf
    ├── pemanager-backend.service
    ├── pemanager-monitor.service
    ├── pemanager.env.example
    ├── sudoers.pemanager
    └── logrotate.pemanager
```

## 快速开始

### 在线部署（HTTP）

```bash
cd /root/pemanager
sudo bash deploy/setup.sh --yes
sudo bash deploy/deploy.sh
```

### 在线部署（HTTPS，域名）

```bash
sudo bash deploy/deploy.sh --ssl-domain pe.example.com --ssl-email admin@example.com
```

### 在线部署（HTTPS，自签名 IP）

```bash
sudo bash deploy/deploy.sh --ssl-ip                 # 自动取本机 IPv4
sudo bash deploy/deploy.sh --ssl-ip 1.2.3.4         # 指定
```

### 离线部署（推荐用于内网批量交付）

```bash
# 打包机（能上网）
sudo bash deploy/package.sh --with-debs --with-wheels --with-frontend

# 目标机
tar xzf pemanager-<ver>.tar.gz && cd pemanager-<ver>
sudo bash INSTALL.sh --offline                       # HTTP
sudo bash INSTALL.sh --offline --ssl-ip              # 自签名 HTTPS
```

### 升级（保留 env / nginx / 证书）

```bash
cd /root/pemanager && git pull
sudo bash deploy/deploy.sh --update
```

### HTTPS 续期 / 状态

```bash
sudo bash deploy/ssl-setup.sh --status         # 查看证书 / timer
sudo bash deploy/ssl-setup.sh --renew          # 主动触发一次续期
```

## 详细文档

| 主题 | 文档 |
|---|---|
| 环境检查与版本升级 | [setup.md](./setup.md) |
| 生产部署 / 系统集成 | [deploy.md](./deploy.md) |
| HTTPS 启用与证书管理 | [ssl.md](./ssl.md) |
| 离线压缩包制作 | [package.md](./package.md) |
| API 接口 | [API.md](./API.md) |
