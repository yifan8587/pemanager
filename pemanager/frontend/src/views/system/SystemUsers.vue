<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, RefreshRight, User, InfoFilled, CopyDocument } from '@element-plus/icons-vue'
import { accountApi } from '../../api/accountApi'
import { resourceApi } from '../../api/resourceApi'
import PageHeader from '../../components/PageHeader.vue'
import { formatDateTimeTz } from '../../utils/format'

const route = useRoute()
const router = useRouter()

const filters = reactive({ role: '', customer_code: '', search: '' })
const list = ref([])
const customers = ref([])
const loading = ref(false)

async function loadAll() {
  loading.value = true
  try {
    const [u, c] = await Promise.all([
      accountApi.listUsers({ ...filters }),
      resourceApi.listCustomers().catch(() => []),
    ])
    list.value = u
    customers.value = c
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

const dialog = reactive({ visible: false, mode: 'create', form: null })
const lastCreated = ref(null) // 创建成功后保存一份，方便复制凭据给客户

function _randomPwd(len = 12) {
  const chars = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%'
  let out = ''
  for (let i = 0; i < len; i += 1) out += chars[Math.floor(Math.random() * chars.length)]
  return out
}

function openCreate() {
  dialog.mode = 'create'
  dialog.form = {
    username: '', email: '', role: 'customer', password: '',
    customer_code: '', is_active: true, phone: '', remark: '',
  }
  dialog.visible = true
}
function openEdit(row) {
  dialog.mode = 'edit'
  dialog.form = {
    id: row.id,
    username: row.username,
    email: row.email,
    role: row.role,
    customer_code: row.customer_code || '',
    is_active: row.is_active,
    phone: row.phone || '',
    remark: row.remark || '',
    password: '',
  }
  dialog.visible = true
}

function fillRandomPwd() {
  if (dialog.form) dialog.form.password = _randomPwd(12)
}

function _formatErr(e) {
  const data = e?.response?.data
  if (!data) return e?.message || '请求失败'
  if (typeof data === 'string') return data
  // DRF 字段错误对象
  const lines = []
  for (const [k, v] of Object.entries(data)) {
    const text = Array.isArray(v) ? v.join('; ') : (typeof v === 'object' ? JSON.stringify(v) : String(v))
    lines.push(`${k}: ${text}`)
  }
  return lines.join('\n') || '请求失败'
}

async function submit() {
  const f = dialog.form
  if (!f.username) return ElMessage.warning('请填写用户名')
  if (f.role === 'customer' && !f.customer_code) return ElMessage.warning('客户角色必须绑定客户')
  if (dialog.mode === 'create' && (!f.password || f.password.length < 8)) {
    return ElMessage.warning('密码至少 8 位')
  }
  const body = {
    username: f.username,
    email: f.email,
    role: f.role,
    customer_code: f.customer_code || null,
    is_active: f.is_active,
    phone: f.phone,
    remark: f.remark,
  }
  if (f.password) body.password = f.password
  try {
    if (dialog.mode === 'create') {
      const created = await accountApi.createUser(body)
      lastCreated.value = { user: created, password: f.password }
      ElMessage.success(`账号 ${created.username} 已创建`)
    } else {
      await accountApi.patchUser(f.id, body)
      ElMessage.success('已保存')
    }
    dialog.visible = false
    loadAll()
  } catch (e) {
    ElMessage.error(_formatErr(e))
  }
}

async function del(row) {
  try {
    await ElMessageBox.confirm(`确认删除用户 ${row.username}？此操作不可恢复。`, '提示', { type: 'warning' })
    await accountApi.deleteUser(row.id)
    ElMessage.success('已删除')
    loadAll()
  } catch {/* cancel */}
}

async function toggleActive(row) {
  try {
    if (row.is_active) await accountApi.disableUser(row.id)
    else await accountApi.enableUser(row.id)
    loadAll()
  } catch (e) { ElMessage.error('操作失败') }
}

async function resetPwd(row) {
  try {
    const r = await ElMessageBox.prompt(`为 ${row.username} 设置新密码（≥8 位）`, '重置密码', {
      inputPattern: /.{8,}/,
      inputErrorMessage: '至少 8 位',
      inputType: 'password',
    })
    await accountApi.resetPassword(row.id, r.value)
    ElMessage.success('已重置')
  } catch {/* cancel */}
}

async function copyCred() {
  if (!lastCreated.value) return
  const u = lastCreated.value.user
  const p = lastCreated.value.password
  const text = `账号: ${u.username}\n密码: ${p}\n角色: ${u.role}` + (u.customer_code ? `\n客户: ${u.customer_code} (${u.customer_name || ''})` : '')
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.warning('复制失败，请手动选择')
  }
}

const roleTag = (r) => (r === 'admin' ? 'danger' : r === 'operator' ? 'warning' : 'success')
const ROLE_DESC = {
  admin: '系统管理员：可管理所有功能、所有客户与所有账号；可创建/删除 API Token',
  operator: '运维：与管理员同等读写，但不能管理账号',
  customer: '客户账号：仅能查看绑定客户的接口、路由、IP、带宽以及对应接口的流量图，不能修改任何配置',
}

onMounted(async () => {
  await loadAll()
  // 支持 /systemmanage/users?create=1 直接打开新建弹窗
  if (route.query.create === '1') {
    openCreate()
    // 清掉 query 防止刷新又弹
    router.replace({ path: route.path })
  }
})
</script>

<template>
  <div class="page">
    <PageHeader title="账号管理" :icon="User"
      description="管理 PE Manager 全部用户：管理员 / 运维 / 客户。客户账号必须绑定客户后才能登录，登录后只能查看自己客户的接口、路由、带宽以及对应接口的流量图。">
      <template #actions>
        <el-button :icon="RefreshRight" @click="loadAll">刷新</el-button>
        <el-button type="primary" :icon="Plus" @click="openCreate">新增账号</el-button>
      </template>
    </PageHeader>

    <!-- 创建成功后的凭据卡 -->
    <el-alert
      v-if="lastCreated"
      type="success"
      :closable="false"
      style="margin-bottom: 12px"
    >
      <template #title>
        <strong>账号 {{ lastCreated.user.username }} 已创建</strong>
        <el-tag size="small" :type="roleTag(lastCreated.user.role)" style="margin-left: 6px">{{ lastCreated.user.role }}</el-tag>
        <el-tag v-if="lastCreated.user.customer_code" size="small" type="info" style="margin-left: 4px">
          客户 {{ lastCreated.user.customer_code }}
        </el-tag>
      </template>
      <div class="cred">
        <div><span class="muted">登录账号：</span><code class="tk">{{ lastCreated.user.username }}</code></div>
        <div><span class="muted">初始密码：</span><code class="tk">{{ lastCreated.password }}</code></div>
        <div class="actions">
          <el-button :icon="CopyDocument" size="small" type="primary" @click="copyCred">复制凭据</el-button>
          <el-button size="small" @click="lastCreated = null">关闭</el-button>
        </div>
      </div>
      <div class="hint">请通过线下安全渠道告知用户，用户登录后建议立即在「个人信息」中修改密码。</div>
    </el-alert>

    <!-- 角色说明 -->
    <el-card shadow="never" class="legend">
      <div class="legend-row">
        <el-tag type="danger" size="small">admin</el-tag>
        <span>{{ ROLE_DESC.admin }}</span>
      </div>
      <div class="legend-row">
        <el-tag type="warning" size="small">operator</el-tag>
        <span>{{ ROLE_DESC.operator }}</span>
      </div>
      <div class="legend-row">
        <el-tag type="success" size="small">customer</el-tag>
        <span>{{ ROLE_DESC.customer }}</span>
      </div>
    </el-card>

    <el-card shadow="never">
      <div class="row">
        <el-select v-model="filters.role" placeholder="角色" clearable style="width: 140px">
          <el-option label="管理员 admin" value="admin" />
          <el-option label="运维 operator" value="operator" />
          <el-option label="客户 customer" value="customer" />
        </el-select>
        <el-select v-model="filters.customer_code" placeholder="客户" clearable filterable style="width: 220px">
          <el-option v-for="c in customers" :key="c.code" :label="`${c.code} (${c.name})`" :value="c.code" />
        </el-select>
        <el-input v-model="filters.search" placeholder="用户名 / 邮箱搜索" clearable style="width: 240px" />
        <el-button type="primary" @click="loadAll">查询</el-button>
      </div>
      <el-table :data="list" border size="small" v-loading="loading" style="margin-top: 8px">
        <el-table-column prop="username" label="用户名" width="160" />
        <el-table-column label="角色" width="110">
          <template #default="{ row }">
            <el-tag :type="roleTag(row.role)" size="small">{{ row.role }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="绑定客户" width="220">
          <template #default="{ row }">
            <span v-if="row.customer_code">
              <el-tag size="small" type="info">{{ row.customer_code }}</el-tag>
              <span class="muted" style="margin-left: 4px">{{ row.customer_name }}</span>
            </span>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="email" label="邮箱" min-width="180" show-overflow-tooltip />
        <el-table-column prop="phone" label="手机" width="120" />
        <el-table-column label="启用" width="80">
          <template #default="{ row }">
            <el-switch :model-value="row.is_active" @change="toggleActive(row)" />
          </template>
        </el-table-column>
        <el-table-column label="最近登录" width="200">
          <template #default="{ row }">{{ formatDateTimeTz(row.last_login) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button link size="small" @click="openEdit(row)">编辑</el-button>
            <el-button link size="small" type="warning" @click="resetPwd(row)">重置密码</el-button>
            <el-button link size="small" type="danger" @click="del(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog
      v-model="dialog.visible"
      :title="dialog.mode === 'create' ? '新增账号' : '编辑账号'"
      width="560px"
    >
      <el-form v-if="dialog.form" label-width="110px">
        <el-form-item label="用户名" required>
          <el-input v-model="dialog.form.username" :disabled="dialog.mode === 'edit'" placeholder="用于登录，建议英文/数字" />
        </el-form-item>
        <el-form-item label="角色" required>
          <el-radio-group v-model="dialog.form.role">
            <el-radio-button value="admin">管理员</el-radio-button>
            <el-radio-button value="operator">运维</el-radio-button>
            <el-radio-button value="customer">客户</el-radio-button>
          </el-radio-group>
          <div class="role-desc">
            <el-icon><InfoFilled /></el-icon>
            <span>{{ ROLE_DESC[dialog.form.role] }}</span>
          </div>
        </el-form-item>
        <el-form-item label="绑定客户" :required="dialog.form.role === 'customer'">
          <el-select
            v-model="dialog.form.customer_code"
            clearable filterable
            :disabled="dialog.form.role !== 'customer'"
            :placeholder="dialog.form.role === 'customer' ? '客户角色必填' : '仅客户角色可选'"
            style="width: 100%"
          >
            <el-option v-for="c in customers" :key="c.code" :label="`${c.code} (${c.name})`" :value="c.code" />
          </el-select>
          <div v-if="dialog.form.role === 'customer'" class="form-help">
            该账号登录后能看到的接口/路由/带宽/IP/流量图，由所选客户在「资源管理 → IP 地址 / 带宽分配」中关联的 <code>interface_code</code> 决定。
          </div>
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="dialog.form.email" placeholder="可选" />
        </el-form-item>
        <el-form-item label="手机">
          <el-input v-model="dialog.form.phone" placeholder="可选" />
        </el-form-item>
        <el-form-item label="密码" v-if="dialog.mode === 'create'" required>
          <el-input v-model="dialog.form.password" show-password placeholder="至少 8 位，含字母/数字/符号">
            <template #append>
              <el-button @click="fillRandomPwd">随机生成</el-button>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="dialog.form.is_active" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="dialog.form.remark" type="textarea" :rows="2" placeholder="可选，便于运维识别该账号用途" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog.visible = false">取消</el-button>
        <el-button type="primary" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page { display: flex; flex-direction: column; gap: 12px; }
.row { display: flex; gap: 8px; flex-wrap: wrap; }
.muted { color: var(--el-text-color-secondary); }
.legend { font-size: 12px; }
.legend-row { display: flex; gap: 8px; align-items: center; padding: 2px 0; color: var(--el-text-color-regular); }
.role-desc { display: flex; gap: 6px; align-items: center; color: var(--el-text-color-secondary); font-size: 12px; margin-top: 4px; }
.form-help { color: var(--el-text-color-secondary); font-size: 12px; margin-top: 4px; }
.form-help code { background: var(--el-fill-color-light); padding: 0 4px; border-radius: 3px; }
.cred { display: flex; flex-direction: column; gap: 4px; margin: 6px 0; }
.cred .actions { display: flex; gap: 6px; margin-top: 4px; }
.tk { background: #0f172a; color: #d1fae5; padding: 2px 8px; border-radius: 4px; font-family: var(--pe-mono); font-size: 12px; }
.hint { font-size: 12px; color: #475569; }
</style>
