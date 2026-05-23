import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import './style.css'
import App from './App.vue'
import router from './router'
import { http } from './api/client'
import { startIdleWatcher } from './utils/idleTimeout'

// 全局闲置超时：5 分钟无操作自动退出（可由 VITE_IDLE_TIMEOUT_MIN 覆盖）
const IDLE_MIN = Number(import.meta.env.VITE_IDLE_TIMEOUT_MIN || 5)
const IDLE_TIMEOUT_MS = Math.max(1, IDLE_MIN) * 60 * 1000

async function bootstrap() {
  try {
    await http.get('/api/csrf/')
  } catch (e) {
    console.warn('CSRF cookie bootstrap failed (后续 POST 可能仍失败):', e?.message || e)
  }
}

bootstrap().then(() => {
  const app = createApp(App)
  for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
    app.component(key, component)
  }
  app.use(ElementPlus)
  app.use(router)
  app.mount('#app')

  // 启动闲置看门狗（在 router 挂载之后，确保 currentRoute 可用）
  startIdleWatcher({ timeoutMs: IDLE_TIMEOUT_MS, router })
})
