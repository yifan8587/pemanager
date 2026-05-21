import { http } from './client'

function unwrapList(data) {
  if (Array.isArray(data)) return data
  if (data && Array.isArray(data.results)) return data.results
  return []
}

export const resourceApi = {
  health: () => http.get('/api/resourcemanage/health/'),
  summary: () => http.get('/api/resourcemanage/summary/'),

  listCustomers: () => http.get('/api/resourcemanage/customers/').then((r) => unwrapList(r.data)),
  createCustomer: (payload) => http.post('/api/resourcemanage/customers/', payload),
  patchCustomer: (id, payload) => http.patch(`/api/resourcemanage/customers/${id}/`, payload),
  deleteCustomer: (id) => http.delete(`/api/resourcemanage/customers/${id}/`),

  listIps: () => http.get('/api/resourcemanage/ip-addresses/').then((r) => unwrapList(r.data)),
  createIp: (payload) => http.post('/api/resourcemanage/ip-addresses/', payload),
  patchIp: (id, payload) => http.patch(`/api/resourcemanage/ip-addresses/${id}/`, payload),
  deleteIp: (id) => http.delete(`/api/resourcemanage/ip-addresses/${id}/`),
  reserveIp: (payload) => http.post('/api/resourcemanage/ip-addresses/actions/reserve/', payload),
  allocateIp: (payload) => http.post('/api/resourcemanage/ip-addresses/actions/allocate/', payload),
  releaseIp: (payload) => http.post('/api/resourcemanage/ip-addresses/actions/release/', payload),

  listPools: () => http.get('/api/resourcemanage/bandwidth-pools/').then((r) => unwrapList(r.data)),
  createPool: (payload) => http.post('/api/resourcemanage/bandwidth-pools/', payload),
  patchPool: (id, payload) => http.patch(`/api/resourcemanage/bandwidth-pools/${id}/`, payload),
  deletePool: (id) => http.delete(`/api/resourcemanage/bandwidth-pools/${id}/`),

  listAllocations: () =>
    http.get('/api/resourcemanage/bandwidth-allocations/').then((r) => unwrapList(r.data)),
  createAllocation: (payload) => http.post('/api/resourcemanage/bandwidth-allocations/', payload),
  patchAllocation: (id, payload) =>
    http.patch(`/api/resourcemanage/bandwidth-allocations/${id}/`, payload),
  deleteAllocation: (id) => http.delete(`/api/resourcemanage/bandwidth-allocations/${id}/`),
  upsertAllocation: (payload) =>
    http.post('/api/resourcemanage/bandwidth-allocations/actions/upsert/', payload),
  deleteAllocationByKey: (payload) =>
    http.post('/api/resourcemanage/bandwidth-allocations/actions/delete-by-key/', payload),

  listLogs: () => http.get('/api/resourcemanage/allocation-logs/').then((r) => unwrapList(r.data)),
  inboundSync: (payload) => http.post('/api/resourcemanage/sync/inbound/', payload),
}
