import { http } from './client'

function unwrapList(data) {
  if (Array.isArray(data)) return data
  if (data && Array.isArray(data.results)) return data.results
  return []
}

export const firewallApi = {
  health: () => http.get('/api/firewallmanage/health/'),
  status: () => http.get('/api/firewallmanage/status/').then((r) => r.data),
  control: (payload) => http.post('/api/firewallmanage/control/', payload),

  getSettings: () => http.get('/api/firewallmanage/settings/').then((r) => r.data),
  patchSettings: (payload) => http.patch('/api/firewallmanage/settings/', payload),

  listRules: (params) =>
    http.get('/api/firewallmanage/rules/', { params }).then((r) => unwrapList(r.data)),
  createRule: (payload) => http.post('/api/firewallmanage/rules/', payload),
  patchRule: (id, payload) => http.patch(`/api/firewallmanage/rules/${id}/`, payload),
  deleteRule: (id) => http.delete(`/api/firewallmanage/rules/${id}/`),

  listNat: (params) =>
    http.get('/api/firewallmanage/nat-rules/', { params }).then((r) => unwrapList(r.data)),
  createNat: (payload) => http.post('/api/firewallmanage/nat-rules/', payload),
  patchNat: (id, payload) => http.patch(`/api/firewallmanage/nat-rules/${id}/`, payload),
  deleteNat: (id) => http.delete(`/api/firewallmanage/nat-rules/${id}/`),

  previewRuleset: () => http.get('/api/firewallmanage/ruleset/preview/').then((r) => r.data),
  applyRuleset: (payload = {}) => http.post('/api/firewallmanage/ruleset/apply/', payload),
  showRuleset: () => http.get('/api/firewallmanage/ruleset/show/').then((r) => r.data),
}
