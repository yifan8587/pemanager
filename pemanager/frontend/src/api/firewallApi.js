import { http } from './client'

function unwrapList(data) {
  if (Array.isArray(data)) return data
  if (data && Array.isArray(data.results)) return data.results
  return []
}

export const firewallApi = {
  health: () => http.get('/api/firewallmanage/health/'),

  listRules: () => http.get('/api/firewallmanage/rules/').then((r) => unwrapList(r.data)),
  createRule: (payload) => http.post('/api/firewallmanage/rules/', payload),
  patchRule: (id, payload) => http.patch(`/api/firewallmanage/rules/${id}/`, payload),
  deleteRule: (id) => http.delete(`/api/firewallmanage/rules/${id}/`),

  previewRuleset: () => http.get('/api/firewallmanage/ruleset/preview/').then((r) => r.data),
  applyRuleset: (payload = {}) => http.post('/api/firewallmanage/ruleset/apply/', payload),
  showRuleset: () => http.get('/api/firewallmanage/ruleset/show/').then((r) => r.data),
}
