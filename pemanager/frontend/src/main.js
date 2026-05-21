import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import './style.css'
import App from './App.vue'
import router from './router'
import { http } from './api/client'

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
})
