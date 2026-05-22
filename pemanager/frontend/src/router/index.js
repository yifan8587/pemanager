import { createRouter, createWebHistory } from 'vue-router'
import { auth } from '../api/client'

// roles: 'admin' | 'operator' | 'customer' | '*'(any-authed)
const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/login/LoginView.vue'),
    meta: { public: true, title: '登录' },
  },
  {
    path: '/',
    name: 'home',
    component: () => import('../views/HomeView.vue'),
    meta: { title: '首页', roles: ['admin', 'operator', 'customer'] },
  },

  // ---- 资源管理：客户可看自己的概览 / IP / 带宽 ----
  { path: '/resourcemanage', redirect: '/resourcemanage/summary' },
  {
    path: '/resourcemanage/summary',
    name: 'resource-summary',
    component: () => import('../views/resource/ResourceSummary.vue'),
    meta: { title: '资源概览', roles: ['admin', 'operator', 'customer'] },
  },
  {
    path: '/resourcemanage/customers',
    name: 'resource-customers',
    component: () => import('../views/resource/ResourceCustomers.vue'),
    meta: { title: '客户', roles: ['admin', 'operator'] },
  },
  {
    path: '/resourcemanage/ip-addresses',
    name: 'resource-ip-addresses',
    component: () => import('../views/resource/ResourceIpAddresses.vue'),
    meta: { title: 'IP 地址', roles: ['admin', 'operator', 'customer'] },
  },
  {
    path: '/resourcemanage/bandwidth',
    name: 'resource-bandwidth',
    component: () => import('../views/resource/ResourceBandwidth.vue'),
    meta: { title: '带宽', roles: ['admin', 'operator', 'customer'] },
  },
  {
    path: '/resourcemanage/allocation-logs',
    name: 'resource-allocation-logs',
    component: () => import('../views/resource/ResourceLogs.vue'),
    meta: { title: '分配日志', roles: ['admin', 'operator'] },
  },
  { path: '/resourcemanage/inbound-sync', redirect: '/resourcemanage/summary' },

  // ---- 接口管理 ----
  { path: '/interfacemanage', redirect: '/interfacemanage/live' },
  {
    path: '/interfacemanage/live',
    name: 'iface-live',
    component: () => import('../views/interface/InterfaceLive.vue'),
    meta: { title: '实时接口', roles: ['admin', 'operator', 'customer'] },
  },
  {
    path: '/interfacemanage/live/:ifname',
    name: 'iface-live-detail',
    component: () => import('../views/interface/InterfaceLiveDetail.vue'),
    meta: { title: '接口详情', roles: ['admin', 'operator', 'customer'] },
  },
  {
    path: '/interfacemanage/tunnel-config',
    name: 'iface-tunnel-config',
    component: () => import('../views/interface/InterfaceTunnelDesired.vue'),
    meta: { title: '隧道接口配置', roles: ['admin', 'operator'] },
  },

  // ---- 路由 ----
  { path: '/routemanage', redirect: '/routemanage/static-routes' },
  { path: '/routemanage/desired-routes', redirect: '/routemanage/static-routes' },
  {
    path: '/routemanage/static-routes',
    name: 'route-static',
    component: () => import('../views/route/RouteStatic.vue'),
    meta: { title: '静态路由', roles: ['admin', 'operator', 'customer'] },
  },
  {
    path: '/routemanage/policy-rules',
    name: 'route-policy',
    component: () => import('../views/route/RoutePolicy.vue'),
    meta: { title: '策略路由', roles: ['admin', 'operator'] },
  },

  // ---- QoS ----
  { path: '/qosmanage', redirect: '/qosmanage/policies' },
  {
    path: '/qosmanage/policies',
    name: 'qos-policies',
    component: () => import('../views/qos/QosPolicies.vue'),
    meta: { title: 'QoS 策略', roles: ['admin', 'operator', 'customer'] },
  },

  // ---- 安全 ----
  { path: '/firewallmanage', redirect: '/firewallmanage/rules' },
  {
    path: '/firewallmanage/rules',
    name: 'firewall-rules',
    component: () => import('../views/firewall/FirewallRules.vue'),
    meta: { title: '防火墙规则', roles: ['admin', 'operator'] },
  },

  // ---- 运维 ----
  { path: '/operationmanage', redirect: '/operationmanage/monitor-charts' },
  {
    path: '/operationmanage/tools',
    name: 'ops-tools',
    component: () => import('../views/operation/OperationTools.vue'),
    meta: { title: '诊断工具', roles: ['admin', 'operator'] },
  },
  {
    path: '/operationmanage/monitor-targets',
    name: 'ops-monitor-targets',
    component: () => import('../views/operation/OperationMonitorTargets.vue'),
    meta: { title: '品质监控', roles: ['admin', 'operator'] },
  },
  {
    path: '/operationmanage/monitor-charts',
    name: 'ops-monitor-charts',
    component: () => import('../views/operation/OperationMonitorCharts.vue'),
    meta: { title: '监控图表', roles: ['admin', 'operator', 'customer'] },
  },

  // ---- 日志 ----
  { path: '/logmanage', redirect: '/logmanage/center' },
  {
    path: '/logmanage/center',
    name: 'log-center',
    component: () => import('../views/log/LogCenter.vue'),
    meta: { title: '操作日志中心', roles: ['admin', 'operator'] },
  },

  // ---- 系统管理 ----
  { path: '/systemmanage', redirect: '/systemmanage/profile' },
  {
    path: '/systemmanage/profile',
    name: 'sys-profile',
    component: () => import('../views/system/SystemProfile.vue'),
    meta: { title: '个人信息', roles: ['admin', 'operator', 'customer'] },
  },
  {
    path: '/systemmanage/tokens',
    name: 'sys-tokens',
    component: () => import('../views/system/SystemTokens.vue'),
    meta: { title: 'API Token', roles: ['admin', 'operator', 'customer'] },
  },
  {
    path: '/systemmanage/users',
    name: 'sys-users',
    component: () => import('../views/system/SystemUsers.vue'),
    meta: { title: '账号管理', roles: ['admin'] },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

function userRoles(user) {
  if (!user) return []
  if (user.is_admin) return ['admin', 'operator', 'customer']
  if (user.is_operator) return ['admin', 'operator', 'customer']
  return ['customer']
}

router.beforeEach((to) => {
  if (to.meta?.public) return true
  if (!auth.isAuthed()) {
    return { path: '/login', query: { next: to.fullPath } }
  }
  const required = to.meta?.roles
  if (Array.isArray(required) && required.length) {
    const user = auth.getUser()
    const roles = userRoles(user)
    if (!roles.some((r) => required.includes(r))) {
      return { path: '/' }
    }
  }
  return true
})

export default router
