# API.md — PE Manager 接口文档

> 本文档基于 `/root/pemanager/backend/` 实际代码自动整理；如代码与文档不一致，以代码为准。
>
> - Base URL：`http://<host>/api/`
> - 时间字段：均为 ISO 8601 + Asia/Shanghai 偏移，例 `2026-05-22T11:02:38+0800`
> - 鉴权：三种共存——JWT（推荐）、API Token、Session
> - 写操作（POST/PUT/PATCH/DELETE）会自动落入 `logmanage` 审计日志

---

## 0. 通用约定

### 0.1 鉴权

| 方式 | Header | 适用 |
|---|---|---|
| JWT Access Token | `Authorization: Bearer <access_token>` | Web 前端、脚本 |
| API Token | `Authorization: Bearer pem_xxxxxxxxxxxx` | 自动化 / CI |
| Session | Cookie | Django admin |

获取 JWT：见 [§1.1 登录](#11-登录)。获取 API Token：见 [§1.8 API Token](#18-api-token)。

### 0.2 响应通用结构

- 列表接口默认返回数组；如开启分页则返回 `{ count, next, previous, results: [...] }`
- 错误统一为 DRF 风格：`{ "detail": "..." }` 或 `{ "<field>": ["..."] }`
- 下发类接口（`apply-*`）统一返回 `{ ok: bool, steps: [...], error?, ... }`，HTTP 200/400 对应 ok/失败

### 0.3 角色

| 角色 | 范围 |
|---|---|
| `admin` | 全部 |
| `operator` | 同 admin（细分预留） |
| `customer` | 只能 CRUD / 下发 **自己作用域内** 的接口、路由、监控目标；其它 403/404 |

可见性边界由后端 `scope_qs(customer_field=…, interface_field=…)` 强制；客户操作越权 id 会被自动过滤为空集，下发返回 400 "无可下发（选中集合为空或越权）"。

### 0.4 健康检查

每个 app 都有 `GET /api/<app>/health/`，返回 `{"app":"<app名>","status":"ok"}`。一般用于探活：

```
GET /api/accountmanage/health/
GET /api/interfacemanage/health/
GET /api/resourcemanage/health/
GET /api/routemanage/health/
GET /api/qosmanage/health/
GET /api/firewallmanage/health/
GET /api/operationmanage/health/
GET /api/logmanage/health/
```

---

## 1. 账号管理（accountmanage）

前缀：`/api/accountmanage/`

### 1.1 登录

```
POST /api/accountmanage/auth/login/
Content-Type: application/json

{ "username": "admin", "password": "admin123" }
```

响应：

```json
{
  "access":  "<JWT access token，默认 8 小时>",
  "refresh": "<JWT refresh token，默认 14 天>",
  "user": {
    "id": 1, "username": "admin", "role": "admin",
    "customer": null, "customer_code": null, "customer_name": null,
    "email": "admin@pemanager.local"
  }
}
```

### 1.2 刷新

```
POST /api/accountmanage/auth/refresh/
{ "refresh": "<refresh token>" }
→ { "access": "<new access>" }
```

### 1.3 校验

```
POST /api/accountmanage/auth/verify/
{ "token": "<access token>" }
→ 200 OK 表示有效
```

### 1.4 注销

```
POST /api/accountmanage/auth/logout/    （Bearer JWT）
{ "refresh": "<refresh>" }              # 服务端拉黑该 refresh
```

### 1.5 当前用户

```
GET /api/accountmanage/auth/me/         （Bearer JWT）
→ {
    "id":..., "username":..., "role":..., "customer_code":..., "customer_name":...,
    "is_active": true, "last_login": "...",
    "permissions": { ... }
  }
```

### 1.6 修改密码

```
POST /api/accountmanage/auth/change-password/
{ "old_password": "...", "new_password": "..." }
```

### 1.7 账号 CRUD（admin only）

| 路径 | 方法 | 说明 |
|---|---|---|
| `/api/accountmanage/users/` | GET / POST | 列表 / 新建 |
| `/api/accountmanage/users/{id}/` | GET / PATCH / DELETE | 详情 / 编辑 / 删除 |
| `/api/accountmanage/users/{id}/reset-password/` | POST | 重置密码，body `{ "new_password": "..." }` |
| `/api/accountmanage/users/{id}/disable/` | POST | 禁用 |
| `/api/accountmanage/users/{id}/enable/` | POST | 启用 |

创建账号示例：

```json
{
  "username": "acme_user",
  "password": "<≥8 字符>",
  "role": "customer",
  "customer": "acme",        // 客户角色必填，值为 ResourceCustomer.code
  "email": "ops@acme.io",
  "remark": ""
}
```

### 1.8 API Token

| 路径 | 方法 | 说明 |
|---|---|---|
| `/api/accountmanage/api-tokens/` | GET / POST | 列表 / 新建（仅响应一次性 plaintext） |
| `/api/accountmanage/api-tokens/{id}/` | GET / DELETE | 详情 / 删除 |
| `/api/accountmanage/api-tokens/{id}/revoke/` | POST | 撤销 |

新建响应：

```json
{
  "id": "uuid", "name": "ci-deploy",
  "plaintext": "pem_xxxxxxxxxxxxxxxx",   // 仅本次返回
  "expires_at": null, "scope": "full"
}
```

使用：`Authorization: Bearer pem_xxxxxxxxxxxxxxxx`

### 1.9 登录尝试日志

```
GET /api/accountmanage/login-attempts/   （admin only，可分页过滤）
```

---

## 2. 接口管理（interfacemanage）

前缀：`/api/interfacemanage/`

### 2.1 实时接口

| 路径 | 方法 | 说明 |
|---|---|---|
| `/interfaces/` | GET | 系统现场（kernel + netplan + wg 合并）；query: `?kind=wireguard&q=tun&admin_up=1` |
| `/interfaces/{ifname}/` | GET | 详情 |
| `/interfaces/{ifname}/preview-config/` | POST | 预览（不落盘） |
| `/interfaces/{ifname}/apply-config/` | POST | 应用单接口 netplan/IP 配置 |
| `/interfaces/{ifname}/remove-config/` | POST | 移除该接口 PE 受控配置 |
| `/interfaces/export/` | GET | 导出 CSV |

### 2.2 数据库镜像 / 同步

| 路径 | 方法 | 说明 |
|---|---|---|
| `/db/sync/from-system/` | POST | 把系统现场覆盖写入 DB |
| `/db/drift/` | GET | DB 与系统差异（in_sync、added、removed、changed） |
| `/db/interfaces/` | GET | DB 中的接口列表 |
| `/db/interfaces/{ifname}/` | GET | DB 单接口详情 |
| `/db/sync-runs/` | GET | 同步历史 |
| `/db/netplan-files/` | GET / 详情 | netplan 文件快照 |

### 2.3 隧道意图（核心）

| 路径 | 方法 | 说明 |
|---|---|---|
| `/db/desired-tunnels/` | GET / POST | 列表 / 新建 |
| `/db/desired-tunnels/{id}/` | GET / PATCH / DELETE | 详情 / 编辑 / 删除 |
| `/db/desired-tunnels/apply-system/` | POST | **下发到系统** |

下发 body：

```json
{
  "ids": ["uuid1", "uuid2"]        // 可选；不传 = admin 全量、客户 = 自己作用域内全部
}
```

行为：
- 仅含 WireGuard 选中：跳过 netplan，只对选中接口 `wg-quick down → up`
- 含 GRE/VXLAN：写 netplan fragment + `netplan generate + try`（netplan try 只 reload 差异接口，已正常的不重启）
- 越权 ids 自动过滤为空集 → 400

新建/编辑 body（WireGuard 示例）：

```json
{
  "ifname": "wg0", "kind": "wireguard",
  "customer": "acme",                                 // ResourceCustomer.code，可空
  "spec": {
    "type": "wireguard",
    "netplan_tunnel": { "addresses": ["10.99.0.1/24"], "listen_port": 51820 },
    "wireguard": {
      "private_key": "<base64>",
      "peers": [
        { "public_key": "<base64>", "allowed_ips": "10.99.0.2/32", "endpoint": "1.2.3.4:51820", "keepalive": 25 }
      ]
    }
  },
  "remark": "客户 ACME 主隧道"
}
```

### 2.4 WireGuard 私钥工具

| 路径 | 方法 | 说明 |
|---|---|---|
| `/tools/wg/genkey/` | POST | 服务端生成私钥（base64） |
| `/tools/wg/pubkey/` | POST | `{ private: "<b64>" }` → `{ public: "<b64>" }` |

### 2.5 现场数据源

| 路径 | 方法 | 说明 |
|---|---|---|
| `/sources/netplan/` | GET | 当前 netplan 文件树（合并） |
| `/sources/kernel/` | GET | `ip -json` 抓取 |
| `/sources/wireguard/` | GET | `wg show` 抓取 |

---

## 3. 资源管理（resourcemanage）

前缀：`/api/resourcemanage/`

### 3.1 客户

| 路径 | 方法 |
|---|---|
| `/customers/` | GET / POST |
| `/customers/{id}/` | GET / PATCH / DELETE |

### 3.2 IP 资源

| 路径 | 方法 | 说明 |
|---|---|---|
| `/ip-addresses/` | GET / POST | 列表 / 新建 |
| `/ip-addresses/{id}/` | GET / PATCH / DELETE | |
| `/ip-addresses/actions/reserve/` | POST | 预留 |
| `/ip-addresses/actions/allocate/` | POST | 分配给客户 |
| `/ip-addresses/actions/release/` | POST | 释放（可用） |
| `/ip-addresses/actions/recycle/` | POST | 回收（不可用） |
| `/ip-addresses/actions/restore/` | POST | 把回收态恢复为可用 |
| `/ip-addresses/actions/allocate-with-route/` | POST | 分配同时下发对应静态路由 |

分配 body：

```json
{
  "address": "10.99.0.20",
  "customer_code": "acme",
  "interface_code": "acme-test",
  "subnet_label": "客户管理网"
}
```

### 3.3 带宽池 / 分配

| 路径 | 方法 | 说明 |
|---|---|---|
| `/bandwidth-pools/` | GET / POST / PATCH / DELETE | admin only |
| `/bandwidth-allocations/` | GET / POST / PATCH / DELETE | |
| `/bandwidth-allocations/actions/upsert/` | POST | 按 `(customer_code, interface_code)` upsert |
| `/bandwidth-allocations/actions/delete-by-key/` | POST | 按 key 删除 |

### 3.4 操作流水

```
GET /api/resourcemanage/allocation-logs/    （admin only）
```

---

## 4. 路由管理（routemanage）

前缀：`/api/routemanage/`

### 4.1 系统视图

| 路径 | 方法 | 说明 |
|---|---|---|
| `/system-routes/` | GET | `ip route` 实时 |
| `/system-rules/` | GET | `ip rule` 实时 |
| `/ip-allocation-choices/` | GET | 资源 IP 联动下拉 |

### 4.2 静态路由意图

| 路径 | 方法 | 说明 |
|---|---|---|
| `/desired-routes/` | GET / POST | |
| `/desired-routes/{id}/` | GET / PATCH / DELETE | |
| `/desired-routes/preview-yaml/` | GET | 预览 netplan 片段 |
| `/desired-routes/apply-system/` | POST | **下发**，body `{ phase, ids }` |
| `/desired-routes/preview-wireguard/` | GET | 预览 WG 路由块 |
| `/desired-routes/apply-wireguard/` | POST | **下发 WG**，body `{ ids }` |
| `/desired-routes/import-from-system/` | POST | 从系统导入（admin only） |

**`apply-system` 行为**：
- 不传 ids：全量重写 netplan fragment + generate + try（持久化）
- 传 ids：`ip route replace` 即时下发选中条目，不写 netplan、不影响其它路由
- phase：`validate` / `try` / `full`（默认 full），仅影响全量模式

**`apply-wireguard` 行为**：
- 不传 ids：对全部 WG 接口 reconcile + `wg-quick down/up`
- 传 ids：仅对选中路由所属的 WG 接口操作，避免一次性重启所有 WG

新建静态路由 body：

```json
{
  "dest_cidr": "10.99.0.20/32",
  "gateway":   "10.10.2.6",        // 可空
  "interface_name": "acme-test",
  "metric": null,
  "route_table": null,
  "customer": "acme",              // 可空
  "remark": "客户 ACME 服务路由"
}
```

### 4.3 策略路由（ip rule）

| 路径 | 方法 | 说明 |
|---|---|---|
| `/policy-rules/` | GET / POST | |
| `/policy-rules/{id}/` | GET / PATCH / DELETE | |
| `/policy-rules/preview/` | GET | 预览渲染命令 |
| `/policy-rules/apply-system/` | POST | **下发**，body `{ phase, ids }` |

`apply-system` 选择性下发时，只删除选中 rule 的当前 priority，不动 owned-range 中其它规则。

---

## 5. QoS 管理（qosmanage）

前缀：`/api/qosmanage/`

| 路径 | 方法 | 说明 |
|---|---|---|
| `/policies/` | GET / POST | 限速策略列表 / 新建 |
| `/policies/{id}/` | GET / PATCH / DELETE | |
| `/policies/{id}/preview/` | GET | 渲染 tc 命令预览 |
| `/policies/{id}/apply-system/` | POST | 下发（HTB 单类 + FQ-CoDel） |
| `/policies/{id}/show-system/` | GET | `tc -s class show dev <if>` |
| `/rules/` | GET / POST / 详情 / 编辑 / 删除 | 规则（admin only） |
| `/summary/` | GET | 全局统计 |

策略 body 示例：

```json
{
  "name": "acme-20mbit",
  "interface_code": "acme-test",
  "customer_code": "acme",
  "rate_mbps": 20,                  // HTB rate
  "ceil_mbps": 20,                  // 与 rate 相同 = 硬限速
  "remark": ""
}
```

---

## 6. 防火墙管理（firewallmanage）

前缀：`/api/firewallmanage/`

| 路径 | 方法 | 说明 |
|---|---|---|
| `/rules/` | GET / POST / 详情 / 编辑 / 删除 | filter 链规则 |
| `/nat-rules/` | GET / POST / 详情 / 编辑 / 删除 | NAT 规则 |
| `/settings/` | GET | 后端引擎（nftables/iptables）、启用状态 |
| `/status/` | GET | 服务状态、规则计数 |
| `/control/` | POST | 启停、切换引擎 |
| `/ruleset/preview/` | GET | 渲染待写入文本 |
| `/ruleset/apply/` | POST | 下发 |
| `/ruleset/show/` | GET | 现网 `nft list ruleset` 等 |

---

## 7. 运维管理（operationmanage）

前缀：`/api/operationmanage/`

### 7.1 在线工具（实时）

| 路径 | 方法 | 说明 |
|---|---|---|
| `/tools/ping/` | POST | 同步 / `count>10` 异步 |
| `/tools/mtr/` | POST | 同 |
| `/tools/traffic-live/` | POST | 单次接口流量样本 |
| `/tools/jobs/{id}/` | GET | 异步任务状态 |
| `/tools/sources/` | GET | 源 IP / 接口可选下拉 |
| `/tools/diagnose/` | POST | 综合诊断（路由+ping+traceroute+ARP+iface） |

ping body 示例：

```json
{ "address": "8.8.8.8", "count": 5, "source": "tun_sino" }
```

### 7.2 监控目标（品质监控）

持续化采样目标；前端"品质监控"配置后由 `pemanager-monitor.service` 调度。

| 路径 | 方法 | 说明 |
|---|---|---|
| `/monitor-targets/` | GET / POST | |
| `/monitor-targets/{id}/` | GET / PATCH / DELETE | |
| `/monitor-targets/{id}/sample-now/` | POST | 立即采样一次 |
| `/monitor-targets/{id}/diagnose/` | POST | 立即综合诊断（admin only） |
| `/monitor-targets/{id}/series/` | GET | 时序数据 `?bucket=minute|hour|day|month` |
| `/latency-samples/` | GET | 原始 ping 样本（admin only） |

### 7.3 接口流量监控

| 路径 | 方法 | 说明 |
|---|---|---|
| `/monitor-interfaces/` | GET / POST | |
| `/monitor-interfaces/{id}/` | GET / PATCH / DELETE | |
| `/monitor-interfaces/{id}/sample-now/` | POST | 立即采样 |
| `/monitor-interfaces/{id}/series/` | GET | `?bucket=minute|hour|day|month` |
| `/traffic-samples/` | GET | 原始流量样本 |

监控目标 body 示例：

```json
{
  "name": "客户 ACME 网关",
  "address": "10.99.0.1",
  "source_interface": "acme-test",
  "count": 5,
  "interval_sec": 60,
  "enabled": true,
  "customer": "acme"
}
```

---

## 8. 日志管理（logmanage）

前缀：`/api/logmanage/`

| 路径 | 方法 | 说明 |
|---|---|---|
| `/app-logs/` | GET | 应用审计日志；query: `?actor=admin&action_type=write&since=...&until=...&q=keyword` |
| `/app-logs/meta/` | GET | 字段枚举（用于前端筛选下拉） |
| `/app-logs/stats/` | GET | 按时段聚合 |
| `/app-logs/export-csv/` | GET | 导出 CSV |

> 系统日志（journalctl）不通过 REST 暴露；后端 `logmanage/services/journal.py` 仅供内部调用。

---

## 9. 错误码

| HTTP | 含义 |
|---|---|
| 200 | 成功（含下发完成） |
| 201 | 新建成功 |
| 204 | 删除成功 |
| 400 | 业务校验失败 / 下发失败（含越权 ids 被过滤为空） |
| 401 | 未登录 / Token 失效 |
| 403 | 角色权限不足（如客户访问 admin-only 路径） |
| 404 | 资源不存在或不在你的可见范围内 |
| 405 | 方法不允许 |
| 409 | 业务冲突（如 ifname 唯一约束） |
| 500 | 服务器内部错误（请看 `journalctl -u pemanager-backend`） |

---

## 10. 调用示例

### 10.1 curl + JWT

```bash
# 1) 登录
TOKEN=$(curl -s -X POST http://127.0.0.1/api/accountmanage/auth/login/ \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}' | jq -r .access)

# 2) 列出隧道
curl -H "Authorization: Bearer $TOKEN" \
     http://127.0.0.1/api/interfacemanage/db/desired-tunnels/

# 3) 下发选中
curl -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
     -d '{"ids":["<uuid1>","<uuid2>"]}' \
     http://127.0.0.1/api/interfacemanage/db/desired-tunnels/apply-system/
```

### 10.2 Python + requests

```python
import requests
S = requests.Session()
r = S.post("http://127.0.0.1/api/accountmanage/auth/login/",
           json={"username": "admin", "password": "admin123"})
S.headers["Authorization"] = f"Bearer {r.json()['access']}"
print(S.get("http://127.0.0.1/api/interfacemanage/db/desired-tunnels/").json())
S.post("http://127.0.0.1/api/routemanage/desired-routes/apply-system/",
       json={"ids": ["<uuid>"]})
```

### 10.3 Node.js + axios

```js
const axios = require('axios')
const api = axios.create({ baseURL: 'http://127.0.0.1/api' })
;(async () => {
  const { data: { access } } = await api.post('/accountmanage/auth/login/',
    { username: 'admin', password: 'admin123' })
  api.defaults.headers.common.Authorization = `Bearer ${access}`
  const { data } = await api.get('/interfacemanage/db/desired-tunnels/')
  console.log(data)
})()
```

---

## 11. 字段精度说明（前端展示）

监控/流量数值前端统一按 **2 位小数** 显示：
- `rx_bps` / `tx_bps`：前端 `(v/1e6).toFixed(2)` → Mbps
- `loss_pct` / `rtt_*_ms` / `jitter_ms`：`.toFixed(2)`
- ECharts tooltip / axisLabel 也已统一为 `(v) => Number(v).toFixed(2)`

后端原始字段不四舍五入，保留浮点精度供二次分析。
