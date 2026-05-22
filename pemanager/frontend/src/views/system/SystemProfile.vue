<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Setting, Lock } from '@element-plus/icons-vue'
import { accountApi } from '../../api/accountApi'
import PageHeader from '../../components/PageHeader.vue'
import { formatDateTimeTz } from '../../utils/format'

const me = ref(null)
const pwd = reactive({ old_password: '', new_password: '', confirm: '' })

async function load() {
  try { me.value = await accountApi.me() } catch { ElMessage.error('加载失败') }
}

async function submit() {
  if (!pwd.old_password || !pwd.new_password) return ElMessage.warning('请填写旧密码与新密码')
  if (pwd.new_password.length < 8) return ElMessage.warning('新密码至少 8 位')
  if (pwd.new_password !== pwd.confirm) return ElMessage.warning('两次输入不一致')
  try {
    await accountApi.changePassword({ old_password: pwd.old_password, new_password: pwd.new_password })
    ElMessage.success('密码已更新，请重新登录')
    setTimeout(async () => { await accountApi.logout(); window.location.assign('/login') }, 800)
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '修改失败')
  }
}

onMounted(load)
</script>

<template>
  <div class="page" v-if="me">
    <PageHeader title="个人信息" :icon="Setting"
      description="查看当前账号信息，修改自己的密码。" />

    <el-row :gutter="12">
      <el-col :span="12">
        <el-card shadow="never" header="账号信息">
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="用户名">{{ me.username }}</el-descriptions-item>
            <el-descriptions-item label="角色">
              <el-tag size="small" :type="me.role === 'admin' ? 'danger' : me.role === 'operator' ? 'warning' : 'success'">{{ me.role }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="绑定客户">
              <span v-if="me.customer_code">{{ me.customer_code }} ({{ me.customer_name }})</span>
              <span v-else class="muted">—</span>
            </el-descriptions-item>
            <el-descriptions-item label="邮箱">{{ me.email || '—' }}</el-descriptions-item>
            <el-descriptions-item label="手机">{{ me.phone || '—' }}</el-descriptions-item>
            <el-descriptions-item label="最近登录">{{ formatDateTimeTz(me.last_login) }}</el-descriptions-item>
            <el-descriptions-item label="加入时间">{{ formatDateTimeTz(me.date_joined) }}</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card shadow="never">
          <template #header>
            <div class="row"><el-icon><Lock /></el-icon><span>修改密码</span></div>
          </template>
          <el-form label-width="100px">
            <el-form-item label="当前密码">
              <el-input v-model="pwd.old_password" type="password" show-password />
            </el-form-item>
            <el-form-item label="新密码">
              <el-input v-model="pwd.new_password" type="password" show-password placeholder="至少 8 位" />
            </el-form-item>
            <el-form-item label="确认新密码">
              <el-input v-model="pwd.confirm" type="password" show-password />
            </el-form-item>
            <el-button type="primary" @click="submit">保存</el-button>
          </el-form>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.page { display: flex; flex-direction: column; gap: 12px; }
.row { display: flex; gap: 6px; align-items: center; }
.muted { color: var(--el-text-color-secondary); }
</style>
