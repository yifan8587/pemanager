<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Share } from '@element-plus/icons-vue'
import { interfaceApi } from '../../api/interfaceApi'
import { routeApi } from '../../api/routeApi'
import JsonBlock from '../../components/JsonBlock.vue'
import PageHeader from '../../components/PageHeader.vue'

const activeTab = ref('system')
const loading = ref(false)
const rows = ref([])
const dlg = ref(false)
const saving = ref(false)
const editingId = ref(null)
const applying = ref(false)

const ipChoices = ref([])
const liveIfaces = ref([])
const dbIfnameSet = ref(new Set())
const systemSnap = ref({ ok: false, routes: [], stderr: '' })
const loadingSystem = ref(false)

const previewYaml = ref('')
const loadingPreview = ref(false)
const lastApplyResult = ref(null)
const deployActiveStep = ref(0)
const liveIfacePick = ref('')

const form = reactive({
  interface_name: '',
  netplan_device_class: 'ethernets',
  linked_interface: null,
  dest_cidr: '',
  gateway: '',
  on_link: false,
  metric: null,
  route_table: null,
  ip_allocation: null,
  remark: '',
})

const deviceClassOptions = [
  { value: 'ethernets', label: '物理网卡 (ethernets)' },
  { value: 'tunnels', label: '隧道 (tunnels)' },
  { value: 'bridges', label: '桥 (bridges)' },
  { value: 'vlans', label: 'VLAN (vlans)' },
  { value: 'bonds', label: '绑定 (bonds)' },
  { value: 'wifis', label: '无线 (wifis)' },
]

const title = computed(() => (editingId.value ? '编辑路由意图' : '新增路由意图'))

const filteredIpChoices = computed(() => {
  const ifn = (form.interface_name || '').trim()
  if (!ifn) return ipChoices.value
  return ipChoices.value.filter((x) => !x.interface_code || x.interface_code === ifn)
})

function kindToNetplanClass(kind) {
  const k = String(kind || '').toLowerCase()
  const tunnels = new Set([
    'wireguard',
    'vxlan',
    'gre',
    'gretap',
    'erspan',
    'ip6gre',
    'ip6gretap',
    'ip_gre',
    'ipip',
    'sit',
    'ip6tnl',
    'vti',
    'vti6',
    'tunnel',
    'geneve',
  ])
  if (tunnels.has(k)) return 'tunnels'
  if (k === 'bridge') return 'bridges'
  if (k === 'bond') return 'bonds'
  if (k === 'vlan' || k === 'macvlan' || k === 'ipvlan') return 'vlans'
  if (k === 'wlan' || k === 'wifi') return 'wifis'
  return 'ethernets'
}

function fillFromLiveIface(ifname) {
  if (!ifname) {
    form.linked_interface = null
    return
  }
  liveIfacePick.value = ifname
  const row = liveIfaces.value.find((x) => x.ifname === ifname)
  if (!row) {
    form.linked_interface = dbIfnameSet.value.has(ifname) ? ifname : null
    return
  }
  form.interface_name = ifname
  const sec = row.netplan && row.netplan.section
  if (sec && deviceClassOptions.some((o) => o.value === sec)) {
    form.netplan_device_class = sec
  } else {
    form.netplan_device_class = kindToNetplanClass(row.kind)
  }
  form.linked_interface = dbIfnameSet.value.has(ifname) ? ifname : null
}

function onLiveIfacePicked(ifname) {
  if (!ifname) {
    form.linked_interface =
      (form.interface_name || '').trim() && dbIfnameSet.value.has((form.interface_name || '').trim())
        ? (form.interface_name || '').trim()
        : null
    return
  }
  fillFromLiveIface(ifname)
}

function onManualIfaceInput() {
  const ifn = (form.interface_name || '').trim()
  form.linked_interface = ifn && dbIfnameSet.value.has(ifn) ? ifn : null
}

function resetForm() {
  liveIfacePick.value = ''
  form.interface_name = ''
  form.netplan_device_class = 'ethernets'
  form.linked_interface = null
  form.dest_cidr = ''
  form.gateway = ''
  form.on_link = false
  form.metric = null
  form.route_table = null
  form.ip_allocation = null
  form.remark = ''
}

function openCreate() {
  editingId.value = null
  resetForm()
  dlg.value = true
}

function openEdit(row) {
  editingId.value = row.id
  liveIfacePick.value = row.interface_name || ''
  form.interface_name = row.interface_name
  form.netplan_device_class = row.netplan_device_class || 'ethernets'
  form.linked_interface = row.linked_interface || null
  form.dest_cidr = row.dest_cidr
  form.gateway = row.gateway || ''
  form.on_link = Boolean(row.on_link)
  form.metric = row.metric ?? null
  form.route_table = row.route_table ?? null
  form.ip_allocation = row.ip_allocation
  form.remark = row.remark || ''
  dlg.value = true
}

function onPickIp(id) {
  if (!id) return
  const row = ipChoices.value.find((x) => x.id === id)
  if (row?.interface_code) {
    const code = row.interface_code.trim()
    form.interface_name = code
    fillFromLiveIface(code)
  }
}

function buildBody() {
  const body = {
    interface_name: (form.interface_name || '').trim(),
    netplan_device_class: form.netplan_device_class,
    dest_cidr: (form.dest_cidr || '').trim(),
    on_link: form.on_link,
    remark: (form.remark || '').trim(),
  }
  if ((form.gateway || '').trim()) body.gateway = form.gateway.trim()
  else body.gateway = null
  if (form.metric != null && form.metric !== '') body.metric = Number(form.metric)
  else body.metric = null
  if (form.route_table != null && form.route_table !== '') body.route_table = Number(form.route_table)
  else body.route_table = null
  body.ip_allocation = form.ip_allocation || null
  body.linked_interface = form.linked_interface || null
  return body
}

async function save() {
  if (!((form.interface_name || '').trim())) {
    ElMessage.error('请填写接口名或从实时清单选择接口')
    return
  }
  if (!((form.dest_cidr || '').trim())) {
    ElMessage.error('请填写目标网段或 default')
    return
  }
  saving.value = true
  try {
    const body = buildBody()
    if (editingId.value) {
      await routeApi.patchDesiredRoute(editingId.value, body)
      ElMessage.success('已更新')
    } else {
      await routeApi.createDesiredRoute(body)
      ElMessage.success('已保存')
    }
    dlg.value = false
    await load()
  } catch (e) {
    const d = e?.response?.data
    ElMessage.error(d ? JSON.stringify(d) : e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`删除路由意图 ${row.interface_name} → ${row.dest_cidr}？`, '确认删除', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await routeApi.deleteDesiredRoute(row.id)
    ElMessage.success('已删除')
    await load()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '删除失败')
  }
}

function routeRowToImportPayload(row) {
  if (!row.dev) return null
  return {
    dst: row.dst,
    dev: row.dev,
    gateway: row.gateway || null,
    metric: row.metric ?? null,
    table: row.table ?? null,
    on_link: Boolean(!row.gateway && String(row.dst || '').toLowerCase() !== 'default'),
  }
}

async function importSystemRoute(row) {
  const payload = routeRowToImportPayload(row)
  if (!payload) {
    ElMessage.warning('该路由缺少出口接口 dev，无法生成意图')
    return
  }
  try {
    await ElMessageBox.confirm(
      `将内核路由 ${payload.dst} via ${payload.gateway || '(on-link)'} dev ${payload.dev} 导入为「路由意图」？`,
      '导入确认',
      { type: 'info' },
    )
  } catch {
    return
  }
  try {
    const data = await routeApi.importRoutesFromSystem([payload])
    if (data.errors?.length) {
      await ElMessageBox.alert(
        `<pre style="white-space:pre-wrap;font-size:12px">${JSON.stringify(data, null, 2)}</pre>`,
        '导入含错误',
        { dangerouslyUseHTMLString: true },
      )
    } else {
      ElMessage.success(`已导入 ${data.created_count || 0} 条`)
    }
    activeTab.value = 'intent'
    await load()
  } catch (e) {
    const d = e?.response?.data
    ElMessage.error(d ? JSON.stringify(d) : e.message || '导入失败')
  }
}

async function loadSystemRoutes() {
  loadingSystem.value = true
  try {
    systemSnap.value = await routeApi.listSystemRoutes()
    if (!systemSnap.value?.ok) {
      ElMessage.warning(systemSnap.value?.stderr || '读取内核路由表失败（需本机 ip 命令权限）')
    }
  } catch (e) {
    systemSnap.value = { ok: false, routes: [], stderr: e?.message || '' }
    ElMessage.error(e?.response?.data?.detail || e.message || '加载系统路由失败')
  } finally {
    loadingSystem.value = false
  }
}

async function fetchPreviewYaml() {
  loadingPreview.value = true
  try {
    const data = await routeApi.previewRouteYaml()
    if (data.ok) {
      previewYaml.value = data.yaml || ''
      deployActiveStep.value = 0
      ElMessage.success('已根据当前意图生成 YAML 预览')
    } else {
      previewYaml.value = ''
      ElMessage.error(data.error || '预览失败')
    }
  } catch (e) {
    const d = e?.response?.data
    previewYaml.value = ''
    ElMessage.error(d ? JSON.stringify(d) : e.message || '预览请求失败')
  } finally {
    loadingPreview.value = false
  }
}

async function applyPhase(phase, confirmText) {
  if (!rows.value.length && phase !== 'try') {
    ElMessage.warning('没有可下发的路由意图')
    return
  }
  try {
    await ElMessageBox.confirm(confirmText, '操作确认', { type: 'warning' })
  } catch {
    return
  }
  applying.value = true
  lastApplyResult.value = null
  try {
    const { data } = await routeApi.applyRoutesToSystem({ phase })
    lastApplyResult.value = data
    if (data.ok) {
      if (phase === 'validate') {
        deployActiveStep.value = 1
        ElMessage.success('已写入片段并完成 netplan generate')
      } else if (phase === 'try') {
        deployActiveStep.value = 2
        ElMessage.success('netplan try 已执行')
      } else {
        deployActiveStep.value = 2
        ElMessage.success('已执行完整流程：写入 / 校验 / try')
      }
    } else {
      await ElMessageBox.alert(
        `<pre style="white-space:pre-wrap;font-size:12px;max-height:420px;overflow:auto">${JSON.stringify(data, null, 2)}</pre>`,
        '下发失败',
        { dangerouslyUseHTMLString: true },
      )
    }
  } catch (e) {
    const d = e?.response?.data
    lastApplyResult.value = d
    await ElMessageBox.alert(
      `<pre style="white-space:pre-wrap;font-size:12px">${JSON.stringify(d || e.message, null, 2)}</pre>`,
      '请求失败',
      { dangerouslyUseHTMLString: true },
    )
  } finally {
    applying.value = false
  }
}

async function load() {
  loading.value = true
  try {
    rows.value = await routeApi.listDesiredRoutes()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function loadIpChoices() {
  try {
    ipChoices.value = await routeApi.listIpAllocationChoices()
  } catch {
    ipChoices.value = []
  }
}

async function loadLiveIfaces() {
  try {
    const { data } = await interfaceApi.liveInventory()
    liveIfaces.value = data.interfaces || []
  } catch {
    liveIfaces.value = []
  }
}

async function loadDbIfaces() {
  try {
    const list = await interfaceApi.listDbInterfaces()
    dbIfnameSet.value = new Set((list || []).map((x) => x.ifname).filter(Boolean))
  } catch {
    dbIfnameSet.value = new Set()
  }
}

const drawerRow = ref(null)
const drawerOpen = ref(false)
function showJson(row) {
  drawerRow.value = row
  drawerOpen.value = true
}

onMounted(() => {
  load()
  loadIpChoices()
  loadLiveIfaces()
  loadDbIfaces()
  loadSystemRoutes()
})
</script>

<template>
  <div class="page">
    <PageHeader
      title="静态路由"
      description="左侧为只读现场，中层维护待下发意图，底层按「预览 → 校验 → 测试」分步执行 netplan"
      :icon="Share"
    />

    <el-alert
      title="关联资源 IP 时可自动对齐接口名；若需将意图与「接口库」FK 绑定，请先执行「接口管理 → 同步到数据库」。"
      type="info"
      show-icon
      :closable="false"
      class="hint"
    />

    <el-tabs v-model="activeTab" type="border-card">
      <el-tab-pane label="① 系统路由表（只读）" name="system">
        <el-card shadow="never" class="section-card">
          <div class="toolbar">
            <el-button type="primary" :loading="loadingSystem" @click="loadSystemRoutes">刷新内核表</el-button>
          </div>
          <el-table :data="systemSnap.routes" border size="small" v-loading="loadingSystem" empty-text="暂无数据或采集失败">
            <el-table-column prop="dev" label="接口" width="120" />
            <el-table-column prop="dst" label="目标" min-width="160" show-overflow-tooltip />
            <el-table-column prop="gateway" label="下一跳" width="140" />
            <el-table-column prop="metric" label="metric" width="90" />
            <el-table-column prop="table" label="table" width="90" />
            <el-table-column prop="protocol" label="协议" width="100" />
            <el-table-column label="操作" width="120" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" :disabled="!row.dev" @click="importSystemRoute(row)">
                  导入意图
                </el-button>
              </template>
            </el-table-column>
          </el-table>
          <p v-if="!systemSnap.ok && systemSnap.stderr" class="err-note">{{ systemSnap.stderr }}</p>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="② 路由意图（CRUD）" name="intent">
        <el-card shadow="never" class="section-card">
          <div class="toolbar">
            <el-button type="primary" @click="openCreate">新增意图</el-button>
            <el-button :loading="loading" @click="load">刷新</el-button>
          </div>
          <el-table :data="rows" border size="small" v-loading="loading">
            <el-table-column prop="interface_name" label="接口" width="130" />
            <el-table-column prop="netplan_device_class" label="设备类" width="110" />
            <el-table-column label="关联库" width="100" show-overflow-tooltip>
              <template #default="{ row }">
                <span v-if="row.linked_interface">{{ row.linked_interface }}</span>
                <span v-else>—</span>
              </template>
            </el-table-column>
            <el-table-column prop="dest_cidr" label="目标" min-width="140" show-overflow-tooltip />
            <el-table-column prop="gateway" label="下一跳" width="130" />
            <el-table-column prop="on_link" label="on-link" width="80">
              <template #default="{ row }">{{ row.on_link ? '是' : '否' }}</template>
            </el-table-column>
            <el-table-column prop="metric" label="metric" width="80" />
            <el-table-column prop="route_table" label="table" width="70" />
            <el-table-column label="关联 IP" min-width="120" show-overflow-tooltip>
              <template #default="{ row }">
                <span v-if="row.ip_address">{{ row.ip_address }}</span>
                <span v-else>—</span>
              </template>
            </el-table-column>
            <el-table-column prop="remark" label="备注" show-overflow-tooltip />
            <el-table-column prop="updated_at" label="更新时间" width="180" />
            <el-table-column label="操作" width="200" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="showJson(row)">JSON</el-button>
                <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
                <el-button link type="danger" @click="remove(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="③ 下发与校验" name="deploy">
        <el-card shadow="never" class="section-card">
          <el-steps :active="deployActiveStep" finish-status="success" align-center class="steps">
            <el-step title="预览 YAML" description="根据意图生成 netplan 片段" />
            <el-step title="写入并校验" description="落盘 + netplan generate" />
            <el-step title="测试应用" description="netplan try（可回滚）" />
          </el-steps>

          <div class="deploy-actions">
            <el-button :loading="loadingPreview" @click="fetchPreviewYaml">1. 生成预览</el-button>
            <el-button
              type="warning"
              :loading="applying"
              @click="
                applyPhase(
                  'validate',
                  '将写入路由片段并执行 netplan generate。不会立即 netplan try。是否继续？',
                )
              "
            >
              2. 写入并 netplan generate
            </el-button>
            <el-button
              type="success"
              :loading="applying"
              @click="
                applyPhase(
                  'try',
                  '将仅执行 netplan try（依赖上一步已写入的片段）。是否继续？',
                )
              "
            >
              3. netplan try
            </el-button>
            <el-button
              type="primary"
              :loading="applying"
              @click="
                applyPhase(
                  'full',
                  '将写入片段、netplan generate 与 netplan try 一次完成。是否继续？',
                )
              "
            >
              一键全流程
            </el-button>
          </div>

          <el-form-item label="YAML 预览" class="yaml-wrap">
            <el-input
              v-model="previewYaml"
              type="textarea"
              :rows="16"
              readonly
              placeholder="点击「生成预览」加载根据当前意图合并后的 netplan 片段"
              class="mono"
            />
          </el-form-item>

          <el-collapse v-if="lastApplyResult">
            <el-collapse-item title="最近一次下发结果（raw）" name="1">
              <JsonBlock :data="lastApplyResult" :rows="22" />
            </el-collapse-item>
          </el-collapse>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="dlg" :title="title" width="620px" destroy-on-close>
      <el-form label-width="140px">
        <el-form-item label="实时清单选接口">
          <el-select
            v-model="liveIfacePick"
            clearable
            filterable
            placeholder="可选：自动填接口名 / 设备类 / 库 FK"
            style="width: 100%"
            @change="onLiveIfacePicked"
          >
            <el-option
              v-for="iface in liveIfaces"
              :key="iface.ifname"
              :label="`${iface.ifname} (${iface.kind || 'unknown'})`"
              :value="iface.ifname"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="关联 IP（可选）">
          <el-select
            v-model="form.ip_allocation"
            clearable
            filterable
            placeholder="与资源管理联动；自动对齐接口名"
            style="width: 100%"
            @change="onPickIp"
          >
            <el-option
              v-for="ip in filteredIpChoices"
              :key="ip.id"
              :label="`${ip.address} (${ip.interface_code || '无接口标识'})`"
              :value="ip.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="接口名" required>
          <el-input v-model="form.interface_name" placeholder="如 eth0、wg01" @input="onManualIfaceInput" />
        </el-form-item>
        <el-form-item label="关联接口库 FK">
          <el-tooltip content="仅在「接口已同步到数据库」时有值；否则仅保存接口名与设备类。" placement="top">
            <el-tag v-if="form.linked_interface" type="success">{{ form.linked_interface }}</el-tag>
            <el-tag v-else type="info">未绑定（可正常保存）</el-tag>
          </el-tooltip>
        </el-form-item>
        <el-form-item label="netplan 设备类" required>
          <el-select v-model="form.netplan_device_class" style="width: 100%">
            <el-option v-for="o in deviceClassOptions" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标 (to)" required>
          <el-input v-model="form.dest_cidr" placeholder="CIDR 或 default" />
        </el-form-item>
        <el-form-item label="下一跳 (via)">
          <el-input v-model="form.gateway" placeholder="可选" :disabled="form.on_link" />
        </el-form-item>
        <el-form-item label="on-link">
          <el-switch v-model="form.on_link" />
        </el-form-item>
        <el-form-item label="metric">
          <el-input-number v-model="form.metric" :min="0" :max="4294967295" controls-position="right" />
        </el-form-item>
        <el-form-item label="table">
          <el-input-number v-model="form.route_table" :min="0" :max="4294967295" controls-position="right" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dlg = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="drawerOpen" title="row JSON" size="45%">
      <JsonBlock v-if="drawerRow" :data="drawerRow" :rows="28" />
    </el-drawer>
  </div>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-width: 1280px;
  margin: 0 auto;
}
.page-head {
  padding-bottom: 4px;
}
.page-title {
  font-size: 18px;
  font-weight: 600;
}
.sub {
  margin: 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.toolbar {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-bottom: 10px;
}
.hint {
  margin-bottom: 4px;
}
.section-card {
  border: none;
}
.steps {
  margin-bottom: 16px;
}
.deploy-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.yaml-wrap {
  margin-bottom: 8px;
}
.mono :deep(textarea) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
  font-size: 12px;
}
.err-note {
  color: var(--el-color-danger);
  font-size: 12px;
  margin-top: 8px;
}
</style>
