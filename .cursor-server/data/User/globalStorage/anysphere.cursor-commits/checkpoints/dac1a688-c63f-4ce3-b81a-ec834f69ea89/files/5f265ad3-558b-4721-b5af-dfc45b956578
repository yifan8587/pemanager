import axios from 'axios'

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
  const m = (config.method || 'get').toLowerCase()
  if (['post', 'put', 'patch', 'delete'].includes(m)) {
    const token = readCookie('csrftoken')
    if (token) {
      config.headers = config.headers || {}
      config.headers['X-CSRFToken'] = token
    }
  }
  return config
})
