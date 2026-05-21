import { http } from './client'

function unwrapList(data) {
  if (Array.isArray(data)) return data
  if (data && Array.isArray(data.results)) return data.results
  return []
}

export const qosApi = {
  health: () => http.get('/api/qosmanage/health/'),

  listPolicies: () => http.get('/api/qosmanage/policies/').then((r) => unwrapList(r.data)),
  getPolicy: (id) => http.get(`/api/qosmanage/policies/${id}/`).then((r) => r.data),
  createPolicy: (payload) => http.post('/api/qosmanage/policies/', payload),
  patchPolicy: (id, payload) => http.patch(`/api/qosmanage/policies/${id}/`, payload),
  deletePolicy: (id) => http.delete(`/api/qosmanage/policies/${id}/`),
  previewPolicy: (id) => http.get(`/api/qosmanage/policies/${id}/preview/`).then((r) => r.data),
  applyPolicy: (id, payload = {}) => http.post(`/api/qosmanage/policies/${id}/apply-system/`, payload),
  showPolicy: (id) => http.get(`/api/qosmanage/policies/${id}/show-system/`).then((r) => r.data),

  listRules: () => http.get('/api/qosmanage/rules/').then((r) => unwrapList(r.data)),
  createRule: (payload) => http.post('/api/qosmanage/rules/', payload),
  patchRule: (id, payload) => http.patch(`/api/qosmanage/rules/${id}/`, payload),
  deleteRule: (id) => http.delete(`/api/qosmanage/rules/${id}/`),
}
