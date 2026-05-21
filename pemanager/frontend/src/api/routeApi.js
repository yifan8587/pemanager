import { http } from './client'

function unwrapList(data) {
  if (Array.isArray(data)) return data
  if (data && Array.isArray(data.results)) return data.results
  return []
}

export const routeApi = {
  health: () => http.get('/api/routemanage/health/'),

  listSystemRoutes: () => http.get('/api/routemanage/system-routes/').then((r) => r.data),

  listDesiredRoutes: () =>
    http.get('/api/routemanage/desired-routes/').then((r) => unwrapList(r.data)),
  createDesiredRoute: (payload) => http.post('/api/routemanage/desired-routes/', payload),
  patchDesiredRoute: (id, payload) =>
    http.patch(`/api/routemanage/desired-routes/${id}/`, payload),
  deleteDesiredRoute: (id) => http.delete(`/api/routemanage/desired-routes/${id}/`),
  previewRouteYaml: () =>
    http.get('/api/routemanage/desired-routes/preview-yaml/').then((r) => r.data),
  applyRoutesToSystem: (payload = {}) =>
    http.post('/api/routemanage/desired-routes/apply-system/', payload),
  importRoutesFromSystem: (routes) =>
    http.post('/api/routemanage/desired-routes/import-from-system/', { routes }).then((r) => r.data),

  listIpAllocationChoices: () =>
    http.get('/api/routemanage/ip-allocation-choices/').then((r) => r.data),
}
