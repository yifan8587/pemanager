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
  allocateIpWithRoute: (payload) =>
    http.post('/api/resourcemanage/ip-addresses/actions/allocate-with-route/', payload),
  releaseIp: (payload) => http.post('/api/resourcemanage/ip-addresses/actions/release/', payload),
  recycleIp: (payload) => http.post('/api/resourcemanage/ip-addresses/actions/recycle/', payload),
  restoreIp: (payload) => http.post('/api/resourcemanage/ip-addresses/actions/restore/', payload),
  // 批量：payload 形如 { start, end, addresses?, state?, subnet_label? }
  bulkCreateIps: (payload) =>
    http.post('/api/resourcemanage/ip-addresses/actions/bulk-create/', payload),
  // payload: { addresses: [...], customer_code, interface_code?, subnet_label?, allow_from_reserved? }
  bulkAllocateIps: (payload) =>
    http.post('/api/resourcemanage/ip-addresses/actions/bulk-allocate/', payload),
  bulkReleaseIps: (payload) =>
    http.post('/api/resourcemanage/ip-addresses/actions/bulk-release/', payload),
  bulkRecycleIps: (payload) =>
    http.post('/api/resourcemanage/ip-addresses/actions/bulk-recycle/', payload),

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
}
