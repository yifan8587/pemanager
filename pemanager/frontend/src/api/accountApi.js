import { http, auth } from './client'

function unwrapList(data) {
  if (Array.isArray(data)) return data
  if (data && Array.isArray(data.results)) return data.results
  return []
}

export const accountApi = {
  /** 登录：返回 { access, refresh, user }，并写入 localStorage */
  login: async ({ username, password }) => {
    const r = await http.post('/api/accountmanage/auth/login/', { username, password })
    const { access, refresh, user } = r.data || {}
    auth.setTokens({ access, refresh, user })
    return r.data
  },
  logout: async () => {
    try { await http.post('/api/accountmanage/auth/logout/') } catch {}
    auth.clear()
  },
  me: () =>
    http.get('/api/accountmanage/auth/me/').then((r) => {
      auth.setUser(r.data)
      return r.data
    }),
  changePassword: ({ old_password, new_password }) =>
    http.post('/api/accountmanage/auth/change-password/', { old_password, new_password }).then((r) => r.data),

  // ---- users (admin) ----
  listUsers: (params) =>
    http.get('/api/accountmanage/users/', { params }).then((r) => unwrapList(r.data)),
  createUser: (body) => http.post('/api/accountmanage/users/', body).then((r) => r.data),
  patchUser: (id, body) => http.patch(`/api/accountmanage/users/${id}/`, body).then((r) => r.data),
  deleteUser: (id) => http.delete(`/api/accountmanage/users/${id}/`),
  resetPassword: (id, new_password) =>
    http.post(`/api/accountmanage/users/${id}/reset-password/`, { new_password }).then((r) => r.data),
  enableUser: (id) => http.post(`/api/accountmanage/users/${id}/enable/`).then((r) => r.data),
  disableUser: (id) => http.post(`/api/accountmanage/users/${id}/disable/`).then((r) => r.data),

  // ---- api tokens ----
  listTokens: (params) =>
    http.get('/api/accountmanage/api-tokens/', { params }).then((r) => unwrapList(r.data)),
  createToken: (body) => http.post('/api/accountmanage/api-tokens/', body).then((r) => r.data),
  revokeToken: (id) => http.post(`/api/accountmanage/api-tokens/${id}/revoke/`).then((r) => r.data),
  deleteToken: (id) => http.delete(`/api/accountmanage/api-tokens/${id}/`),

  // ---- login attempts (admin) ----
  listLoginAttempts: (params) =>
    http.get('/api/accountmanage/login-attempts/', { params }).then((r) => unwrapList(r.data)),

  // ---- 复用 ----
  auth,
}
