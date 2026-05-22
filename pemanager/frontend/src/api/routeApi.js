import { http } from './client'

function unwrapList(data) {
  if (Array.isArray(data)) return data
  if (data && Array.isArray(data.results)) return data.results
  return []
}

export const routeApi = {
  health: () => http.get('/api/routemanage/health/'),

  // 系统视图
  listSystemRoutes: (params = {}) =>
    http.get('/api/routemanage/system-routes/', { params }).then((r) => r.data),
  listSystemRules: (params = {}) =>
    http.get('/api/routemanage/system-rules/', { params }).then((r) => r.data),

  // 静态路由意图（DesiredRouteConfig）
  listDesiredRoutes: () =>
    http.get('/api/routemanage/desired-routes/').then((r) => unwrapList(r.data)),
  createDesiredRoute: (payload) => http.post('/api/routemanage/desired-routes/', payload),
  patchDesiredRoute: (id, payload) =>
    http.patch(`/api/routemanage/desired-routes/${id}/`, payload),
  deleteDesiredRoute: (id) => http.delete(`/api/routemanage/desired-routes/${id}/`),
  previewRouteYaml: () =>
    http.get('/api/routemanage/desired-routes/preview-yaml/').then((r) => r.data),
  // payload 可包含 { phase: 'full'|'validate'|'try', ids: string[] }
  applyRoutesToSystem: (payload = {}) =>
    http.post('/api/routemanage/desired-routes/apply-system/', payload),
  previewWireguardRoutes: () =>
    http.get('/api/routemanage/desired-routes/preview-wireguard/').then((r) => r.data),
  // payload 可包含 { ids: string[] }；不传则全量
  applyWireguardRoutes: (payload = {}) =>
    http.post('/api/routemanage/desired-routes/apply-wireguard/', payload),
  importRoutesFromSystem: (routes) =>
    http.post('/api/routemanage/desired-routes/import-from-system/', { routes }).then((r) => r.data),

  // 策略路由（PolicyRouteRule）
  listPolicyRules: () =>
    http.get('/api/routemanage/policy-rules/').then((r) => unwrapList(r.data)),
  createPolicyRule: (payload) => http.post('/api/routemanage/policy-rules/', payload),
  patchPolicyRule: (id, payload) =>
    http.patch(`/api/routemanage/policy-rules/${id}/`, payload),
  deletePolicyRule: (id) => http.delete(`/api/routemanage/policy-rules/${id}/`),
  previewPolicyRules: () =>
    http.get('/api/routemanage/policy-rules/preview/').then((r) => r.data),
  applyPolicyRules: (payload = {}) =>
    http.post('/api/routemanage/policy-rules/apply-system/', payload),

  // 资源关联
  listIpAllocationChoices: () =>
    http.get('/api/routemanage/ip-allocation-choices/').then((r) => r.data),
}
