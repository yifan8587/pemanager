import { http } from './client'

function unwrapList(data) {
  if (Array.isArray(data)) return data
  if (data && Array.isArray(data.results)) return data.results
  return []
}

export const logApi = {
  health: () => http.get('/api/logmanage/health/'),

  listAppLogs: (params) =>
    http.get('/api/logmanage/app-logs/', { params }).then((r) => ({
      list: unwrapList(r.data),
      count: r.data?.count ?? unwrapList(r.data).length,
    })),
  appLogDetail: (id) => http.get(`/api/logmanage/app-logs/${id}/`).then((r) => r.data),

  logMeta: () => http.get('/api/logmanage/app-logs/meta/').then((r) => r.data),
  logStats: (params) =>
    http.get('/api/logmanage/app-logs/stats/', { params }).then((r) => r.data),

  /** 返回完整 URL（前端用 anchor download） */
  exportCsvUrl: (params = {}) => {
    const qs = new URLSearchParams(params).toString()
    return `/api/logmanage/app-logs/export-csv/${qs ? `?${qs}` : ''}`
  },
}
