<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Cpu } from '@element-plus/icons-vue'
import { operationApi } from '../../api/operationApi'
import { interfaceApi } from '../../api/interfaceApi'
import PageHeader from '../../components/PageHeader.vue'

const rows = ref([])
const loading = ref(false)
const ifaces = ref([])

const dlg = ref(false)
const editingId = ref(null)
const saving = ref(false)
const form = reactive({
  name: '',
  address: '',
  kind: 'ping',
  interval_sec: 60,
  count: 5,
  source_interface: '',
  enabled: true,
  remark: '',
})

async function load() {
  loading.value = true
  try {
    rows.value = await operationApi.listTargets()
  } catch (e) {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}
async function loadIfaces() {
  try {
    const { data } = await interfaceApi.liveInventory()
    ifaces.value = data.interfaces || []
  } catch {
    ifaces.value = []
  }
}

function openCreate() {
  editingId.value = null
  Object.assign(form, {
    name: '',
    address: '',
    kind: 'ping',
    interval_sec: 60,
    count: 5,
    source_interface: '',
    enabled: true,
    remark: '',
  })
  dlg.value = true
}
function openEdit(r) {
  editingId.value = r.id
  Object.assign(form, { ...r })
  dlg.value = true
}
async function save() {
  saving.value = true
  try {
    if (editingId.value) await operationApi.patchTarget(editingId.value, form)
    else await operationApi.createTarget(form)
    ElMessage.success('已保存')
    dlg.value = false
    await load()
  } catch (e) {
    ElMessage.error(JSON.stringify(e?.response?.data || e.message))
  } finally {
    saving.value = false
  }
}
async function remove(r) {
  try {
    await ElMessageBox.confirm(`删除监控目标 ${r.name}？`, '确认', { type: 'warning' })
  } catch {
    return
  }
  await operationApi.deleteTarget(r.id)
  ElMessage.success('已删除')
  await load()
}
async function sampleNow(r) {
  try {
    const data = await operationApi.sampleNow(r.id)
    ElMessage.success(`已采样：avg=${data.rtt_avg_ms ?? '—'} loss=${data.loss_pct ?? '—'}%`)
    await load()
  } catch (e) {
    ElMessage.error(JSON.stringify(e?.response?.data || e.message))
  }
}
async function sampleAll() {
  try {
    const data = await operationApi.sampleAllNow([])
    ElMessage.success(`已采样 ${data.latency.count} 个目标 用时 ${data.latency.duration_ms}ms`)
    await load()
  } catch (e) {
    ElMessage.error('采样失败')
  }
}

onMounted(() => {
  load()
  loadIfaces()
})
</script>

<template>
  <div class="page">
    <PageHeader
      title="监控目标"
      description="维护 ping/mtr 监控目标；由 monitor_loop / monitor_once 周期采样，或点击「立即采样」按需触发"
      :icon="Cpu"
    >
      <template #actions>
        <el-button type="primary" @click="openCreate">新增目标</el-button>
        <el-button @click="sampleAll">立即采样全部</el-button>
        <el-button :loading="loading" @click="load">刷新</el-button>
      </template>
    </PageHeader>
    <el-table :data="rows" border size="small" v-loading="loading">
      <el-table-column prop="enabled" label="启用" width="64">
        <template #default="{ row }">
          <el-tag :type="row.enabled ? 'success' : 'info'" size="small">{{ row.enabled ? 'Y' : 'N' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="名称" min-width="140" />
      <el-table-column prop="address" label="地址" min-width="160" />
      <el-table-column prop="kind" label="类型" width="80" />
      <el-table-column prop="interval_sec" label="间隔(s)" width="90" />
      <el-table-column prop="count" label="报文数" width="80" />
      <el-table-column prop="source_interface" label="源接口" width="120" />
      <el-table-column prop="last_sampled_at" label="最近采样" width="180" />
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button link size="small" type="primary" @click="sampleNow(row)">立即采样</el-button>
          <el-button link size="small" @click="openEdit(row)">编辑</el-button>
          <el-button link size="small" type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dlg" :title="editingId ? '编辑监控目标' : '新增监控目标'" width="540px" destroy-on-close>
      <el-form label-width="110px">
        <el-form-item label="名称" required><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="目标地址" required><el-input v-model="form.address" placeholder="IP 或主机名" /></el-form-item>
        <el-form-item label="类型">
          <el-select v-model="form.kind" style="width:100%">
            <el-option label="Ping (ICMP)" value="ping" />
            <el-option label="MTR" value="mtr" />
          </el-select>
        </el-form-item>
        <el-form-item label="间隔(s)"><el-input-number v-model="form.interval_sec" :min="5" :max="86400" /></el-form-item>
        <el-form-item label="单次报文数"><el-input-number v-model="form.count" :min="1" :max="30" /></el-form-item>
        <el-form-item label="源接口">
          <el-select v-model="form.source_interface" filterable clearable allow-create style="width:100%">
            <el-option v-for="i in ifaces" :key="i.ifname" :label="i.ifname" :value="i.ifname" />
          </el-select>
        </el-form-item>
        <el-form-item label="启用"><el-switch v-model="form.enabled" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="form.remark" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dlg = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page { display: flex; flex-direction: column; gap: 12px; }
.row { display: flex; gap: 8px; align-items: center; }
</style>
