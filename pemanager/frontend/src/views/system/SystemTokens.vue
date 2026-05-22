<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, RefreshRight, Key, CopyDocument } from '@element-plus/icons-vue'
import { accountApi } from '../../api/accountApi'
import PageHeader from '../../components/PageHeader.vue'
import { formatDateTimeTz } from '../../utils/format'

const me = ref(null)
const list = ref([])
const loading = ref(false)
const showRevoked = ref(false)

const isAdmin = computed(() => me.value?.is_admin)

async function loadAll() {
  loading.value = true
  try {
    if (!me.value) me.value = await accountApi.me()
    const params = {}
    if (showRevoked.value) {/* show all */} else params.revoked = '0'
    list.value = await accountApi.listTokens(params)
  } catch (e) { ElMessage.error('加载失败') } finally { loading.value = false }
}

const createDialog = reactive({ visible: false, name: '', ttl_days: null, user: null })
const newlyCreated = ref(null) // { plaintext, ... }

function openCreate() {
  createDialog.name = ''
  createDialog.ttl_days = null
  createDialog.user = me.value?.id || null
  createDialog.visible = true
}

async function submitCreate() {
  if (!createDialog.name) {
    ElMessage.warning('请填写令牌名称')
    return
  }
  try {
    const body = { name: createDialog.name }
    if (createDialog.ttl_days) body.ttl_days = createDialog.ttl_days
    if (isAdmin.value && createDialog.user) body.user = createDialog.user
    const r = await accountApi.createToken(body)
    newlyCreated.value = r
    createDialog.visible = false
    loadAll()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '创建失败')
  }
}

async function copyPlain() {
  if (!newlyCreated.value?.plaintext) return
  try {
    await navigator.clipboard.writeText(newlyCreated.value.plaintext)
    ElMessage.success('已复制')
  } catch {
    ElMessage.warning('复制失败，请手动选择')
  }
}

async function revoke(row) {
  try {
    await ElMessageBox.confirm(`确认吊销令牌 ${row.name} (${row.prefix})？`, '提示', { type: 'warning' })
    await accountApi.revokeToken(row.id)
    ElMessage.success('已吊销')
    loadAll()
  } catch {/* cancel */}
}

onMounted(loadAll)
</script>

<template>
  <div class="page">
    <PageHeader title="API Token" :icon="Key"
      description="为程序化访问 PE Manager 后端 API 创建长期令牌。明文密钥仅创建时一次性显示。">
      <template #actions>
        <el-switch v-model="showRevoked" active-text="含已吊销" @change="loadAll" />
        <el-button :icon="RefreshRight" @click="loadAll">刷新</el-button>
        <el-button type="primary" :icon="Plus" @click="openCreate">创建令牌</el-button>
      </template>
    </PageHeader>

    <el-alert v-if="newlyCreated" type="success" :closable="false" style="margin-bottom: 12px">
      <template #title>
        <div>
          令牌 <strong>{{ newlyCreated.name }}</strong> 已创建，请立即复制保存：
          <el-tag size="small" type="warning" style="margin-left: 6px">
            此明文仅显示一次
          </el-tag>
        </div>
      </template>
      <div class="plain">
        <code class="tk">{{ newlyCreated.plaintext }}</code>
        <el-button :icon="CopyDocument" size="small" type="primary" @click="copyPlain">复制</el-button>
        <el-button size="small" @click="newlyCreated = null">我已保存</el-button>
      </div>
      <div class="hint">
        调用方式：<code>Authorization: Bearer pem_xxx.yyy</code> 或 <code>X-API-Key: pem_xxx.yyy</code>
      </div>
    </el-alert>

    <el-card shadow="never">
      <el-table :data="list" border size="small" v-loading="loading">
        <el-table-column prop="name" label="名称" width="180" />
        <el-table-column prop="prefix" label="前缀（识别符）" width="180">
          <template #default="{ row }">
            <code>{{ row.prefix }}</code>
          </template>
        </el-table-column>
        <el-table-column prop="user_username" label="所属账号" width="160" v-if="isAdmin" />
        <el-table-column prop="scope" label="作用域" width="100" />
        <el-table-column label="过期" width="200">
          <template #default="{ row }">
            <span v-if="row.expires_at">{{ formatDateTimeTz(row.expires_at) }}</span>
            <span v-else class="muted">永不</span>
            <el-tag v-if="row.is_expired" size="small" type="danger" style="margin-left: 4px">已过期</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最近使用" width="200">
          <template #default="{ row }">
            <div>{{ formatDateTimeTz(row.last_used_at) }}</div>
            <div class="muted small">{{ row.last_used_ip || '—' }}</div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.revoked" type="danger" size="small">已吊销</el-tag>
            <el-tag v-else type="success" size="small">有效</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button v-if="!row.revoked" link type="warning" size="small" @click="revoke(row)">吊销</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="createDialog.visible" title="创建 API 令牌" width="460px">
      <el-form label-width="100px">
        <el-form-item label="令牌名称">
          <el-input v-model="createDialog.name" placeholder="如：cron-pull-metrics" />
        </el-form-item>
        <el-form-item label="有效期 (天)">
          <el-input-number v-model="createDialog.ttl_days" :min="1" :max="3650" placeholder="留空则永不过期" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialog.visible = false">取消</el-button>
        <el-button type="primary" @click="submitCreate">生成</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page { display: flex; flex-direction: column; gap: 12px; }
.muted { color: var(--el-text-color-secondary); }
.small { font-size: 11px; }
.plain { display: flex; align-items: center; gap: 8px; margin: 8px 0; flex-wrap: wrap; }
.tk { background: #0f172a; color: #d1fae5; padding: 6px 10px; border-radius: 4px; font-family: var(--pe-mono); font-size: 12px; word-break: break-all; }
.hint { font-size: 12px; color: #475569; }
</style>
