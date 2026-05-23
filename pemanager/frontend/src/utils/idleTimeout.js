/**
 * 闲置自动退出
 *
 * 行为：
 *   - 用户连续 `timeoutMs` 毫秒无任何操作 → 清理本地登录态，跳转 /login，带 reason=idle 提示
 *   - 操作识别：mousemove / mousedown / keydown / wheel / touchstart / scroll / click / visibilitychange
 *   - 写入活动时间到 localStorage('pem.lastActivity')；多标签页通过 storage 事件相互续命
 *   - 登录 / 退出登录会通过 `markActivity()` / `markLogout()` 主动同步
 *   - 在 /login 页面不计入活动、不会被踢出
 *
 * 用法（main.js）：
 *   import { startIdleWatcher } from './utils/idleTimeout'
 *   startIdleWatcher({ timeoutMs: 5 * 60 * 1000, router })
 */
import { ElMessage } from 'element-plus'
import { auth } from '../api/client'

const LAST_ACTIVITY_KEY = 'pem.lastActivity'
const LOGOUT_BROADCAST_KEY = 'pem.logoutAt'

const ACTIVITY_EVENTS = [
  'mousemove',
  'mousedown',
  'keydown',
  'wheel',
  'touchstart',
  'scroll',
  'click',
]

const WRITE_THROTTLE_MS = 5000      // 活动时间写入 localStorage 的最小间隔
const CHECK_INTERVAL_MS = 10000     // 多久检查一次是否已超时

let _started = false
let _timeoutMs = 5 * 60 * 1000
let _router = null
let _checkTimer = null
let _lastWriteAt = 0
let _kicked = false                 // 防止反复弹提示
let _onActivity = null
let _onStorage = null
let _onVisibilityChange = null

function now() {
  return Date.now()
}

function _readLastActivity() {
  try {
    const v = Number(localStorage.getItem(LAST_ACTIVITY_KEY))
    return Number.isFinite(v) && v > 0 ? v : 0
  } catch {
    return 0
  }
}

function _writeLastActivity(ts) {
  try {
    localStorage.setItem(LAST_ACTIVITY_KEY, String(ts))
  } catch {
    /* 私有模式下可能写不进，忽略 */
  }
}

/** 在登录页 / 公共页不参与超时判断 */
function _isPublicRoute() {
  if (!_router) return false
  const path = _router.currentRoute?.value?.path || ''
  return path.startsWith('/login')
}

/** 外部 API：主动登记一次活动（如登录成功后调用） */
export function markActivity(force = false) {
  const ts = now()
  if (force || ts - _lastWriteAt >= WRITE_THROTTLE_MS) {
    _lastWriteAt = ts
    _writeLastActivity(ts)
  }
  _kicked = false
}

/** 外部 API：主动登记一次登出，让所有标签页同步退出 */
export function markLogout(reason = 'manual') {
  try {
    localStorage.setItem(LOGOUT_BROADCAST_KEY, `${now()}:${reason}`)
  } catch {
    /* ignore */
  }
}

function _kickOut(reason) {
  if (_kicked) return
  _kicked = true
  auth.clear()
  // 清理活动记录，避免下次自检看到旧值
  try {
    localStorage.removeItem(LAST_ACTIVITY_KEY)
  } catch {
    /* ignore */
  }

  const msg = reason === 'idle'
    ? '由于长时间未操作，您已被自动退出，请重新登录'
    : '登录会话已结束，请重新登录'
  try { ElMessage.warning({ message: msg, duration: 4000 }) } catch { /* ignore */ }

  if (_router) {
    const cur = _router.currentRoute?.value
    if (cur && !cur.path.startsWith('/login')) {
      _router.replace({
        path: '/login',
        query: { next: cur.fullPath, reason },
      })
    }
  } else if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/login')) {
    const nextUrl = encodeURIComponent(window.location.pathname + window.location.search)
    window.location.assign(`/login?next=${nextUrl}&reason=${reason}`)
  }
}

function _checkIdle() {
  if (!auth.isAuthed()) return       // 未登录不计时
  if (_isPublicRoute()) return       // 登录页本身不踢
  const last = _readLastActivity() || _lastWriteAt
  if (!last) {
    // 第一次没有写过：以本次为准
    markActivity(true)
    return
  }
  if (now() - last >= _timeoutMs) {
    _kickOut('idle')
  }
}

function _bind() {
  _onActivity = () => {
    if (!auth.isAuthed() || _isPublicRoute()) return
    markActivity()
  }
  for (const ev of ACTIVITY_EVENTS) {
    window.addEventListener(ev, _onActivity, { passive: true, capture: true })
  }

  // 跨标签页：其他 tab 的活动 / 登出会通过 storage 事件同步
  _onStorage = (e) => {
    if (!e) return
    if (e.key === LAST_ACTIVITY_KEY && e.newValue) {
      // 别的 tab 续了命，本 tab 同步本地 _lastWriteAt，避免下一轮误判
      const v = Number(e.newValue)
      if (Number.isFinite(v) && v > 0) _lastWriteAt = v
      _kicked = false
    } else if (e.key === LOGOUT_BROADCAST_KEY && e.newValue) {
      // 别的 tab 登出 / 被踢出 → 本 tab 一同退出
      _kickOut(String(e.newValue).split(':')[1] || 'manual')
    }
  }
  window.addEventListener('storage', _onStorage)

  // 切回前台时立刻检查一次（避免后台 setInterval 节流引起的"漏判"）
  _onVisibilityChange = () => {
    if (document.visibilityState === 'visible') _checkIdle()
  }
  document.addEventListener('visibilitychange', _onVisibilityChange)
}

function _unbind() {
  if (_onActivity) {
    for (const ev of ACTIVITY_EVENTS) {
      window.removeEventListener(ev, _onActivity, { capture: true })
    }
    _onActivity = null
  }
  if (_onStorage) {
    window.removeEventListener('storage', _onStorage)
    _onStorage = null
  }
  if (_onVisibilityChange) {
    document.removeEventListener('visibilitychange', _onVisibilityChange)
    _onVisibilityChange = null
  }
}

export function startIdleWatcher({ timeoutMs, router } = {}) {
  if (_started) return
  if (typeof window === 'undefined') return
  if (timeoutMs && Number(timeoutMs) > 0) _timeoutMs = Number(timeoutMs)
  if (router) _router = router
  _started = true
  _bind()
  // 初始登记一次：如果用户已经登录但 localStorage 没有活动时间，就以"现在"为起点
  if (auth.isAuthed()) markActivity(true)
  _checkTimer = setInterval(_checkIdle, CHECK_INTERVAL_MS)
}

export function stopIdleWatcher() {
  if (!_started) return
  _started = false
  if (_checkTimer) {
    clearInterval(_checkTimer)
    _checkTimer = null
  }
  _unbind()
}

/** 当前剩余的"还能闲多久"毫秒数；未登录或未启动返回 null */
export function getIdleRemainingMs() {
  if (!_started || !auth.isAuthed()) return null
  const last = _readLastActivity() || _lastWriteAt || now()
  return Math.max(0, _timeoutMs - (now() - last))
}
