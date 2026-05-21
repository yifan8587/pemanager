import { createRouter, createWebHistory } from 'vue-router'

const modules = [
  { path: '/', name: 'home', title: '首页', component: () => import('../views/HomeView.vue') },
  { path: '/interfacemanage', name: 'interfacemanage', title: '接口管理', component: () => import('../views/ModulePlaceholder.vue'), meta: { apiPrefix: '/api/interfacemanage/' } },
  { path: '/resourcemanage', name: 'resourcemanage', title: '资源管理', component: () => import('../views/ModulePlaceholder.vue'), meta: { apiPrefix: '/api/resourcemanage/' } },
  { path: '/routemanage', name: 'routemanage', title: '路由管理', component: () => import('../views/ModulePlaceholder.vue'), meta: { apiPrefix: '/api/routemanage/' } },
  { path: '/qosmanage', name: 'qosmanage', title: 'QoS 管理', component: () => import('../views/ModulePlaceholder.vue'), meta: { apiPrefix: '/api/qosmanage/' } },
  { path: '/firewallmanage', name: 'firewallmanage', title: '防火墙管理', component: () => import('../views/ModulePlaceholder.vue'), meta: { apiPrefix: '/api/firewallmanage/' } },
  { path: '/operationmanage', name: 'operationmanage', title: '运维管理', component: () => import('../views/ModulePlaceholder.vue'), meta: { apiPrefix: '/api/operationmanage/' } },
  { path: '/logmanage', name: 'logmanage', title: '日志管理', component: () => import('../views/ModulePlaceholder.vue'), meta: { apiPrefix: '/api/logmanage/' } },
]

const routes = modules.map((m) => ({
  path: m.path,
  name: m.name,
  component: m.component,
  meta: { title: m.title, ...(m.meta || {}) },
}))

export default createRouter({
  history: createWebHistory(),
  routes,
})
