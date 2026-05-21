<script setup>
import { onMounted, ref } from 'vue'
import {
  Connection,
  Share,
  Coin,
  DataAnalysis,
  Lock,
  Aim,
  Odometer,
} from '@element-plus/icons-vue'
import PageHeader from '../components/PageHeader.vue'
import StatCard from '../components/StatCard.vue'
import { resourceApi } from '../api/resourceApi'
import { interfaceApi } from '../api/interfaceApi'
import { routeApi } from '../api/routeApi'
import { qosApi } from '../api/qosApi'
import { firewallApi } from '../api/firewallApi'
import { operationApi } from '../api/operationApi'
import { logApi } from '../api/logApi'

const loading = ref(false)
const stats = ref({
  interfaces: 0,
  routes: 0,
  ips_alloc: 0,
  ips_avail: 0,
  bw_pools: 0,
  qos: 0,
  fw: 0,
  monitors: 0,
})
const ifaceSummary = ref({})
const bwPools = ref([])
const modules = ref([])
const recentLogs = ref([])

async function safe(fn, fallback) {
  try {
    return await fn()
  } catch {
    return fallback
  }
}

async function load() {
  loading.value = true
  const [rs, ifa, routes, qosPolicies, fwRules, targets, logs] = await Promise.all([
    safe(() => resourceApi.summary(), { data: {} }).then((r) => r?.data || r || {}),
    safe(() => interfaceApi.liveInventory().then((r) => r.data), { interfaces: [], summary: {} }),
    safe(() => routeApi.listDesiredRoutes(), []),
    safe(() => qosApi.listPolicies(), []),
    safe(() => firewallApi.listRules(), []),
    safe(() => operationApi.listTargets(), []),
    safe(() => logApi.listAppLogs({}), []),
  ])

  const ipState = rs?.ip_by_state || {}
  bwPools.value = rs?.bandwidth_pools || []
  ifaceSummary.value = ifa?.summary || {}

  stats.value = {
    interfaces: ifa?.count ?? (ifa?.interfaces?.length || 0),
    routes: routes.length || 0,
    ips_alloc: Number(ipState.allocated || 0),
    ips_avail: Number(ipState.available || 0),
    bw_pools: bwPools.value.length || 0,
    qos: qosPolicies.length || 0,
    fw: fwRules.length || 0,
    monitors: targets.length || 0,
  }

  modules.value = [
    { name: '接口管理', path: '/interfacemanage/live', status: ifa ? 'ok' : 'err', detail: `${stats.value.interfaces} 个接口` },
    { name: '静态路由', path: '/routemanage/desired-routes', status: 'ok', detail: `${stats.value.routes} 条意图` },
    { name: '资源管理', path: '/resourcemanage/summary', status: 'ok', detail: `IP ${stats.value.ips_alloc} 已分配 / ${stats.value.ips_avail} 可用` },
    { name: 'QoS 策略', path: '/qosmanage/policies', status: 'ok', detail: `${stats.value.qos} 条策略` },
    { name: '防火墙', path: '/firewallmanage/rules', status: 'ok', detail: `${stats.value.fw} 条规则` },
    { name: '运维监控', path: '/operationmanage/monitor-targets', status: 'ok', detail: `${stats.value.monitors} 个监控目标` },
    { name: '日志中心', path: '/logmanage/center', status: 'ok', detail: `${logs.length} 条最近日志` },
  ]

  recentLogs.value = (logs || []).slice(0, 8)

  loading.value = false
}

onMounted(load)

function bwTone(p) {
  if (!p.total_mbps) return ''
  const used = (p.allocated_mbps || 0) / p.total_mbps
  if (used >= 0.85) return 'exception'
  if (used >= 0.6) return 'warning'
  return 'success'
}
</script>

<template>
  <div class="page">
    <PageHeader title="系统概览" description="路由器配置 / 资源 / 监控 / 日志一站式总览" :icon="Odometer">
      <template #actions>
        <el-button :loading="loading" @click="load">刷新</el-button>
      </template>
    </PageHeader>

    <el-row :gutter="12">
      <el-col :xs="12" :sm="8" :md="6" :lg="3">
        <StatCard label="接口" :value="stats.interfaces" :icon="Connection" tone="primary" to="/interfacemanage/live" />
      </el-col>
      <el-col :xs="12" :sm="8" :md="6" :lg="3">
        <StatCard label="路由意图" :value="stats.routes" :icon="Share" tone="info" to="/routemanage/desired-routes" />
      </el-col>
      <el-col :xs="12" :sm="8" :md="6" :lg="3">
        <StatCard label="IP 已分配" :value="stats.ips_alloc" :icon="Coin" tone="success" to="/resourcemanage/ip-addresses" hint="from resourcemanage" />
      </el-col>
      <el-col :xs="12" :sm="8" :md="6" :lg="3">
        <StatCard label="IP 可用" :value="stats.ips_avail" :icon="Coin" tone="info" to="/resourcemanage/ip-addresses" />
      </el-col>
      <el-col :xs="12" :sm="8" :md="6" :lg="3">
        <StatCard label="带宽池" :value="stats.bw_pools" :icon="DataAnalysis" tone="primary" to="/resourcemanage/bandwidth" />
      </el-col>
      <el-col :xs="12" :sm="8" :md="6" :lg="3">
        <StatCard label="QoS 策略" :value="stats.qos" :icon="DataAnalysis" tone="warning" to="/qosmanage/policies" />
      </el-col>
      <el-col :xs="12" :sm="8" :md="6" :lg="3">
        <StatCard label="防火墙规则" :value="stats.fw" :icon="Lock" tone="danger" to="/firewallmanage/rules" />
      </el-col>
      <el-col :xs="12" :sm="8" :md="6" :lg="3">
        <StatCard label="监控目标" :value="stats.monitors" :icon="Aim" tone="success" to="/operationmanage/monitor-targets" />
      </el-col>
    </el-row>

    <el-row :gutter="12" style="margin-top: 12px">
      <el-col :xs="24" :md="12">
        <el-card shadow="never">
          <template #header>
            <div class="card-head">
              <span>接口类型分布</span>
              <router-link to="/interfacemanage/live" class="more">查看接口 →</router-link>
            </div>
          </template>
          <div v-if="Object.keys(ifaceSummary).length === 0" class="empty">暂无数据</div>
          <div v-else class="kind-grid">
            <div v-for="(c, k) in ifaceSummary" :key="k" class="kind">
              <div class="kind-name">{{ k }}</div>
              <div class="kind-count">{{ c }}</div>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :xs="24" :md="12">
        <el-card shadow="never">
          <template #header>
            <div class="card-head">
              <span>带宽池占用</span>
              <router-link to="/resourcemanage/bandwidth" class="more">前往配置 →</router-link>
            </div>
          </template>
          <div v-if="!bwPools.length" class="empty">尚未创建带宽池</div>
          <div v-else class="bw-list">
            <div v-for="p in bwPools" :key="p.id" class="bw-row">
              <div class="bw-head">
                <strong>{{ p.name }}</strong>
                <span class="muted">{{ p.allocated_mbps }} / {{ p.total_mbps }} Mbps</span>
              </div>
              <el-progress
                :percentage="Math.min(100, Math.round((p.allocated_mbps / Math.max(1, p.total_mbps)) * 100))"
                :status="bwTone(p)"
                :stroke-width="10"
              />
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="12" style="margin-top: 12px">
      <el-col :xs="24" :md="12">
        <el-card shadow="never">
          <template #header>模块状态</template>
          <el-table :data="modules" border size="small">
            <el-table-column label="模块" min-width="120">
              <template #default="{ row }">
                <span class="pe-dot" :class="row.status === 'ok' ? 'ok' : 'err'"></span>
                <router-link :to="row.path">{{ row.name }}</router-link>
              </template>
            </el-table-column>
            <el-table-column prop="detail" label="状态" />
          </el-table>
        </el-card>
      </el-col>

      <el-col :xs="24" :md="12">
        <el-card shadow="never">
          <template #header>
            <div class="card-head">
              <span>最近应用日志</span>
              <router-link to="/logmanage/center" class="more">日志中心 →</router-link>
            </div>
          </template>
          <el-table :data="recentLogs" border size="small" empty-text="无最近日志">
            <el-table-column prop="created_at" label="时间" width="160">
              <template #default="{ row }">
                <span class="pe-mono">{{ (row.created_at || '').replace('T', ' ').substring(0, 19) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="app" label="app" width="100" />
            <el-table-column prop="level" label="级别" width="80">
              <template #default="{ row }">
                <el-tag size="small" :type="row.level === 'error' ? 'danger' : row.level === 'warning' ? 'warning' : 'info'">
                  {{ row.level }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="summary" label="摘要" show-overflow-tooltip />
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}
.more {
  font-size: 12px;
  color: var(--pe-primary);
  font-weight: 500;
}
.empty {
  padding: 20px;
  color: var(--pe-text-mute);
  text-align: center;
  font-size: 12px;
}
.kind-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 8px;
}
.kind {
  background: var(--pe-bg);
  border-radius: var(--pe-radius);
  padding: 10px 12px;
  border: 1px solid var(--pe-border-soft);
}
.kind-name {
  font-size: 11px;
  color: var(--pe-text-mute);
  text-transform: uppercase;
  letter-spacing: 0.4px;
}
.kind-count {
  font-size: 20px;
  font-weight: 600;
  margin-top: 4px;
  font-variant-numeric: tabular-nums;
}
.bw-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.bw-head {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  margin-bottom: 4px;
}
.muted { color: var(--pe-text-mute); }
:deep(.el-row + .el-row) { margin-top: 0; }
</style>
