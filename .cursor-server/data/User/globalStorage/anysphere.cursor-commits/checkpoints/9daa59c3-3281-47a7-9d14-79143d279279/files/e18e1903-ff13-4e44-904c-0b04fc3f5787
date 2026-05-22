<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  Fold,
  Expand,
  Refresh,
  Cpu,
  Connection,
  Share,
  Coin,
  ChromeFilled,
  Lock,
  DataAnalysis,
  Document,
  Odometer,
  Tools,
  Aim,
  TrendCharts,
  Setting,
} from '@element-plus/icons-vue'

const route = useRoute()
const collapsed = ref(false)
const now = ref(new Date())

const active = computed(() => {
  return route.path
})

const GROUPS = {
  resourcemanage: '资源管理',
  interfacemanage: '接口管理',
  routemanage: '网络配置',
  qosmanage: 'QoS',
  firewallmanage: '安全防护',
  operationmanage: '运维管理',
  logmanage: '日志中心',
}

const crumbs = computed(() => {
  const matched = route.matched.filter((r) => r.meta?.title)
  const items = matched.map((r) => ({ title: r.meta.title, path: r.path }))
  const seg = route.path.split('/').filter(Boolean)[0]
  if (seg && GROUPS[seg]) {
    items.unshift({ title: GROUPS[seg] })
  }
  return items
})

onMounted(() => {
  setInterval(() => {
    now.value = new Date()
  }, 1000)
})

function fmtClock(d) {
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function reload() {
  window.location.reload()
}
</script>

<template>
  <el-container class="layout">
    <el-header class="topbar">
      <div class="brand">
        <el-icon class="brand-icon"><ChromeFilled /></el-icon>
        <div class="brand-text">
          <div class="brand-name">PE Manager</div>
          <div class="brand-sub">边界路由 · 配置 / 监控 / 审计</div>
        </div>
      </div>
      <div class="topbar-mid">
        <span class="pill"><span class="pe-dot ok"></span>system online</span>
        <span class="clock">{{ fmtClock(now) }}</span>
      </div>
      <div class="topbar-right">
        <el-button type="primary" link @click="reload">
          <el-icon><Refresh /></el-icon>
          <span class="lbl">刷新</span>
        </el-button>
        <el-divider direction="vertical" />
        <span class="user">
          <el-icon><Setting /></el-icon>
          <span class="lbl">管理员</span>
        </span>
      </div>
    </el-header>

    <el-container class="below">
      <el-aside :width="collapsed ? '64px' : '220px'" class="aside">
        <div class="collapse-btn" @click="collapsed = !collapsed">
          <el-icon><component :is="collapsed ? Expand : Fold" /></el-icon>
          <span v-if="!collapsed" class="lbl">收起</span>
        </div>
        <el-menu
          :default-active="active"
          :collapse="collapsed"
          router
          class="nav"
          unique-opened
        >
          <el-menu-item index="/">
            <el-icon><Odometer /></el-icon>
            <template #title>系统概览</template>
          </el-menu-item>

          <el-sub-menu index="grp-iface">
            <template #title>
              <el-icon><Connection /></el-icon>
              <span>接口管理</span>
            </template>
            <el-menu-item index="/interfacemanage/live">实时接口</el-menu-item>
            <el-menu-item index="/interfacemanage/db-mirror">配置镜像库</el-menu-item>
            <el-menu-item index="/interfacemanage/tunnel-config">隧道接口配置</el-menu-item>
            <el-menu-item index="/interfacemanage/sources">原始采集</el-menu-item>
          </el-sub-menu>

          <el-sub-menu index="grp-net">
            <template #title>
              <el-icon><Share /></el-icon>
              <span>网络配置</span>
            </template>
            <el-menu-item index="/routemanage/desired-routes">静态路由</el-menu-item>
          </el-sub-menu>

          <el-sub-menu index="grp-resource">
            <template #title>
              <el-icon><Coin /></el-icon>
              <span>资源管理</span>
            </template>
            <el-menu-item index="/resourcemanage/summary">资源概览</el-menu-item>
            <el-menu-item index="/resourcemanage/customers">客户</el-menu-item>
            <el-menu-item index="/resourcemanage/ip-addresses">IP 地址</el-menu-item>
            <el-menu-item index="/resourcemanage/bandwidth">带宽</el-menu-item>
            <el-menu-item index="/resourcemanage/allocation-logs">分配日志</el-menu-item>
            <el-menu-item index="/resourcemanage/inbound-sync">资源回写</el-menu-item>
          </el-sub-menu>

          <el-sub-menu index="grp-qos">
            <template #title>
              <el-icon><DataAnalysis /></el-icon>
              <span>QoS</span>
            </template>
            <el-menu-item index="/qosmanage/policies">QoS 策略</el-menu-item>
          </el-sub-menu>

          <el-sub-menu index="grp-sec">
            <template #title>
              <el-icon><Lock /></el-icon>
              <span>安全防护</span>
            </template>
            <el-menu-item index="/firewallmanage/rules">防火墙规则</el-menu-item>
          </el-sub-menu>

          <el-sub-menu index="grp-ops">
            <template #title>
              <el-icon><Tools /></el-icon>
              <span>运维管理</span>
            </template>
            <el-menu-item index="/operationmanage/tools">
              <el-icon><Aim /></el-icon>
              <template #title>诊断工具</template>
            </el-menu-item>
            <el-menu-item index="/operationmanage/monitor-targets">
              <el-icon><Cpu /></el-icon>
              <template #title>监控目标</template>
            </el-menu-item>
            <el-menu-item index="/operationmanage/monitor-charts">
              <el-icon><TrendCharts /></el-icon>
              <template #title>监控图表</template>
            </el-menu-item>
          </el-sub-menu>

          <el-menu-item index="/logmanage/center">
            <el-icon><Document /></el-icon>
            <template #title>日志中心</template>
          </el-menu-item>
        </el-menu>
      </el-aside>

      <el-container class="content-area">
        <div class="crumb">
          <el-breadcrumb separator="/">
            <el-breadcrumb-item :to="{ path: '/' }">首页</el-breadcrumb-item>
            <el-breadcrumb-item
              v-for="(c, i) in crumbs"
              :key="`${c.path}-${i}`"
              :to="i < crumbs.length - 1 ? c.path : undefined"
            >
              {{ c.title }}
            </el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <el-main class="main">
          <router-view />
        </el-main>
      </el-container>
    </el-container>
  </el-container>
</template>

<style scoped>
.layout {
  min-height: 100vh;
  background: var(--pe-bg);
}
.topbar {
  background: var(--pe-header-bg);
  color: var(--pe-header-text);
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 56px;
  padding: 0 16px;
  border-bottom: 1px solid #0b1220;
  position: sticky;
  top: 0;
  z-index: 50;
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
}
.brand-icon {
  font-size: 26px;
  color: #60a5fa;
}
.brand-text { line-height: 1.1; }
.brand-name { font-size: 15px; font-weight: 700; letter-spacing: 0.4px; }
.brand-sub { font-size: 11px; opacity: 0.6; margin-top: 2px; }
.topbar-mid {
  display: flex;
  align-items: center;
  gap: 14px;
  font-size: 12px;
}
.pill {
  background: rgba(255, 255, 255, 0.06);
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.08);
}
.clock {
  font-family: var(--pe-mono);
  opacity: 0.8;
}
.topbar-right {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--pe-header-text);
}
.topbar-right :deep(.el-button) {
  color: var(--pe-header-text);
}
.user {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
}
.lbl { margin-left: 4px; }
.below { min-height: calc(100vh - 56px); }
.aside {
  background: var(--pe-aside-bg);
  border-right: 1px solid var(--pe-border-soft);
  transition: width 0.2s ease;
  display: flex;
  flex-direction: column;
}
.collapse-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 16px;
  color: var(--pe-text-mute);
  font-size: 12px;
  cursor: pointer;
  border-bottom: 1px solid var(--pe-border-soft);
}
.collapse-btn:hover {
  background: #f8fafc;
  color: var(--pe-primary);
}
.nav {
  flex: 1;
  overflow-y: auto;
}
.nav :deep(.el-menu-item.is-active) {
  background: var(--pe-aside-active-bg);
  color: var(--pe-aside-active-text);
  border-right: 2px solid var(--pe-primary);
}
.content-area {
  display: flex;
  flex-direction: column;
}
.crumb {
  background: var(--pe-card);
  padding: 8px 18px;
  border-bottom: 1px solid var(--pe-border-soft);
}
.main {
  padding: 14px 18px 24px;
  background: var(--pe-bg);
  min-height: calc(100vh - 56px - 36px);
}
</style>
