import { http } from './client'

function unwrapList(data) {
  if (Array.isArray(data)) return data
  if (data && Array.isArray(data.results)) return data.results
  return []
}

export const logApi = {
  health: () => http.get('/api/logmanage/health/'),

  listAppLogs: (params) => http.get('/api/logmanage/app-logs/', { params }).then((r) => unwrapList(r.data)),
  appLogDetail: (id) => http.get(`/api/logmanage/app-logs/${id}/`).then((r) => r.data),

  queryJournal: (params) => http.get('/api/logmanage/journal/query/', { params }).then((r) => r.data),
  listUnits: (pattern) =>
    http
      .get('/api/logmanage/journal/units/', { params: pattern ? { pattern } : {} })
      .then((r) => r.data),
}
