import { http } from './client'

function unwrapList(data) {
  if (Array.isArray(data)) return data
  if (data && Array.isArray(data.results)) return data.results
  return []
}

export const interfaceApi = {
  health: () => http.get('/api/interfacemanage/health/'),

  liveInventory: (params) => http.get('/api/interfacemanage/interfaces/', { params }),
  liveDetail: (ifname) => http.get(`/api/interfacemanage/interfaces/${encodeURIComponent(ifname)}/`),
  exportInventory: (params) => http.get('/api/interfacemanage/interfaces/export/', { params }),

  netplanSource: (params) => http.get('/api/interfacemanage/sources/netplan/', { params }),
  kernelSource: (params) => http.get('/api/interfacemanage/sources/kernel/', { params }),
  wireguardSource: (params) => http.get('/api/interfacemanage/sources/wireguard/', { params }),

  drift: () => http.get('/api/interfacemanage/db/drift/'),
  syncFromSystem: () => http.post('/api/interfacemanage/db/sync/from-system/'),

  listDbInterfaces: () =>
    http.get('/api/interfacemanage/db/interfaces/').then((r) => unwrapList(r.data)),
  getDbInterface: (ifname) =>
    http.get(`/api/interfacemanage/db/interfaces/${encodeURIComponent(ifname)}/`),

  listSyncRuns: () =>
    http.get('/api/interfacemanage/db/sync-runs/').then((r) => unwrapList(r.data)),
  listNetplanFiles: () =>
    http.get('/api/interfacemanage/db/netplan-files/').then((r) => unwrapList(r.data)),
  getNetplanFile: (id) => http.get(`/api/interfacemanage/db/netplan-files/${id}/`),

  listDesiredTunnels: () =>
    http.get('/api/interfacemanage/db/desired-tunnels/').then((r) => unwrapList(r.data)),
  createDesiredTunnel: (payload) => http.post('/api/interfacemanage/db/desired-tunnels/', payload),
  patchDesiredTunnel: (id, payload) =>
    http.patch(`/api/interfacemanage/db/desired-tunnels/${id}/`, payload),
  deleteDesiredTunnel: (id) => http.delete(`/api/interfacemanage/db/desired-tunnels/${id}/`),
  applyDesiredTunnelsToSystem: () =>
    http.post('/api/interfacemanage/db/desired-tunnels/apply-system/'),
}
