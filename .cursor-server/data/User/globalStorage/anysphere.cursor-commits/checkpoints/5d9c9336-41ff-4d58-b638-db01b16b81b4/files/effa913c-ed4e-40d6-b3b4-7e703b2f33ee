<script setup>
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ChromeFilled, User, Lock } from '@element-plus/icons-vue'
import { accountApi } from '../../api/accountApi'

const router = useRouter()
const route = useRoute()

const form = ref({ username: '', password: '' })
const loading = ref(false)

async function doLogin() {
  if (!form.value.username || !form.value.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    const r = await accountApi.login(form.value)
    ElMessage.success(`欢迎，${r.user?.username || ''}`)
    const next = route.query.next || '/'
    router.replace(typeof next === 'string' ? next : '/')
  } catch (e) {
    const msg = e?.response?.data?.detail || e?.message || '登录失败'
    ElMessage.error(msg)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <div class="brand">
        <el-icon class="brand-icon"><ChromeFilled /></el-icon>
        <div class="brand-text">
          <div class="brand-title">PE Manager</div>
          <div class="brand-sub">边界路由 · 配置 / 监控 / 审计</div>
        </div>
      </div>
      <el-form @submit.prevent="doLogin" label-position="top" size="large">
        <el-form-item label="用户名">
          <el-input v-model="form.username" :prefix-icon="User" placeholder="admin" autocomplete="username" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            :prefix-icon="Lock"
            placeholder="••••••••"
            autocomplete="current-password"
            @keyup.enter="doLogin"
          />
        </el-form-item>
        <el-button type="primary" :loading="loading" @click="doLogin" style="width: 100%">登录</el-button>
      </el-form>
      <div class="tips">
        <div>初次使用：默认管理员账号 <code>admin</code> / <code>admin123</code>，登录后请立即修改密码。</div>
        <div>客户账号请联系管理员创建并绑定客户。</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background:
    radial-gradient(circle at 20% 20%, rgba(59,130,246,0.18) 0%, transparent 35%),
    radial-gradient(circle at 80% 80%, rgba(16,185,129,0.16) 0%, transparent 35%),
    #0f172a;
}
.login-card {
  width: 380px;
  background: #fff;
  border-radius: 12px;
  padding: 28px;
  box-shadow: 0 20px 60px rgba(2, 6, 23, 0.3);
}
.brand { display: flex; gap: 12px; align-items: center; margin-bottom: 16px; }
.brand-icon { font-size: 32px; color: #2563eb; }
.brand-title { font-size: 18px; font-weight: 700; }
.brand-sub { font-size: 12px; color: #64748b; }
.tips { margin-top: 14px; font-size: 12px; color: #64748b; line-height: 1.6; }
.tips code { background: #f1f5f9; padding: 0 4px; border-radius: 3px; }
</style>
