import axios from 'axios'
import { ref } from 'vue'

const ACCESS_KEY = 'pem.access'
const REFRESH_KEY = 'pem.refresh'
const USER_KEY = 'pem.user'

// 全局响应式 user。所有页面共享这一份；
// 登录 / 调 /auth/me/ / 主动 setUser 都会更新它，菜单和顶栏会立刻刷新。
const _userRef = ref(null)
try {
  const raw = localStorage.getItem(USER_KEY)
  _userRef.value = raw ? JSON.parse(raw) : null
} catch {
  _userRef.value = null
}

function _writeUser(user) {
  if (user) {
    localStorage.setItem(USER_KEY, JSON.stringify(user))
    _userRef.value = user
  }
}

export const auth = {
  /** Vue 响应式 ref，供 setup() 直接绑定 */
  userRef: _userRef,

  getAccess: () => localStorage.getItem(ACCESS_KEY) || '',
  getRefresh: () => localStorage.getItem(REFRESH_KEY) || '',
  getUser: () => _userRef.value || null,
  setTokens: ({ access, refresh, user }) => {
    if (access) localStorage.setItem(ACCESS_KEY, access)
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh)
    if (user) _writeUser(user)
  },
  setUser: _writeUser,
  clear: () => {
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
    localStorage.removeItem(USER_KEY)
    _userRef.value = null
  },
  isAuthed: () => !!localStorage.getItem(ACCESS_KEY),
}

function readCookie(name) {
  if (typeof document === 'undefined') return null
  const m = document.cookie.match(new RegExp(`(?:^|; )${name.replace(/[.$?*|{}()[\]\\/+^]/g, '\\$&')}=([^;]*)`))
  return m ? decodeURIComponent(m[1]) : null
}

export const http = axios.create({
  baseURL: '',
  timeout: 30000,
  withCredentials: true,
  xsrfCookieName: 'csrftoken',
  xsrfHeaderName: 'X-CSRFToken',
})

http.interceptors.request.use((config) => {
  // 注入 JWT
  const token = auth.getAccess()
  if (token) {
    config.headers = config.headers || {}
    if (!config.headers.Authorization) {
      config.headers.Authorization = `Bearer ${token}`
    }
  }
  // 注入 CSRF（保留兼容 SessionAuth 的访问场景，例如 admin 后台）
  const m = (config.method || 'get').toLowerCase()
  if (['post', 'put', 'patch', 'delete'].includes(m)) {
    const csrf = readCookie('csrftoken')
    if (csrf) {
      config.headers = config.headers || {}
      if (!config.headers['X-CSRFToken']) config.headers['X-CSRFToken'] = csrf
    }
  }
  return config
})

let _isRefreshing = false
let _pending = []
function _drainPending(err, newToken) {
  _pending.forEach(({ resolve, reject, config }) => {
    if (err) reject(err)
    else {
      config.headers = config.headers || {}
      config.headers.Authorization = `Bearer ${newToken}`
      resolve(http(config))
    }
  })
  _pending = []
}

http.interceptors.response.use(
  (r) => r,
  async (error) => {
    const { response, config } = error || {}
    if (!response) throw error

    // 401 / 403 直接抛；但 401 时若有 refresh，尝试一次刷新
    if (response.status === 401 && config && !config.__isRetry) {
      const refresh = auth.getRefresh()
      // login / refresh 自己 401 不再重试
      if (
        !refresh
        || /\/api\/accountmanage\/auth\/(login|refresh)\//.test(config.url || '')
      ) {
        auth.clear()
        try { localStorage.setItem('pem.logoutAt', `${Date.now()}:expired`) } catch { /* ignore */ }
        if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/login')) {
          window.location.assign('/login?reason=expired')
        }
        throw error
      }
      if (_isRefreshing) {
        return new Promise((resolve, reject) => _pending.push({ resolve, reject, config }))
      }
      _isRefreshing = true
      try {
        const r = await axios.post('/api/accountmanage/auth/refresh/', { refresh })
        const newAccess = r?.data?.access
        if (!newAccess) throw new Error('no access in refresh response')
        auth.setTokens({ access: newAccess })
        _drainPending(null, newAccess)
        config.__isRetry = true
        config.headers = config.headers || {}
        config.headers.Authorization = `Bearer ${newAccess}`
        return http(config)
      } catch (e) {
        _drainPending(e, null)
        auth.clear()
        try { localStorage.setItem('pem.logoutAt', `${Date.now()}:expired`) } catch { /* ignore */ }
        if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/login')) {
          window.location.assign('/login?reason=expired')
        }
        throw e
      } finally {
        _isRefreshing = false
      }
    }
    throw error
  },
)
