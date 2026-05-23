<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Coin,
  Refresh,
  Plus,
  Promotion,
  ArrowRight,
  Delete,
  CircleClose,
  RefreshRight,
  EditPen,
} from '@element-plus/icons-vue'
import { resourceApi } from '../../api/resourceApi'
import { interfaceApi } from '../../api/interfaceApi'
import PageHeader from '../../components/PageHeader.vue'

const loading = ref(false)
const rows = ref([])
const customers = ref([])
const ifaces = ref([])

const STATE_META = {
  available: { label: '可用', type: 'success' },
  allocated: { label: '已分配', type: 'primary' },
  reserved: { label: '预留', type: 'warning' },
  recycled: { label: '回收 (不可分配)', type: 'info' },
}

const filters = reactive({ state: '', q: '' })
const filtered = computed(() => {
  let r = rows.value.slice()
  if (filters.state) r = r.filter((x) => x.state === filters.state)
  if (filters.q) {
    const q = filters.q.toLowerCase()
    r = r.filter(
      (x) =>
        String(x.address).toLowerCase().includes(q) ||
        String(x.interface_code || '').toLowerCase().includes(q) ||
        String(x.customer_code || '').toLowerCase().includes(q) ||
        String(x.subnet_label || '').toLowerCase().includes(q),
    )
  }
  return r
})

const stats = computed(() => {
  const out = { total: rows.value.length, available: 0, allocated: 0, reserved: 0, recycled: 0 }
  for (const r of rows.value) {
    if (r.state in out) out[r.state] += 1
  }
  return out
})

function customerName(code) {
  if (!code) return ''
  const c = customers.value.find((x) => x.code === code)
  return c ? c.name || c.code : code
}

async function load() {
  loading.value = true
  try {
    const [ips, cust, iff] = await Promise.all([
      resourceApi.listIps(),
      resourceApi.listCustomers(),
      interfaceApi.liveInventory({}).then((r) => r.data?.interfaces || []).catch(() => []),
    ])
    rows.value = ips
    customers.value = cust
    ifaces.value = iff
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

// ---- 录入可用 IP ----
const addDlg = ref(false)
const addForm = reactive({ address: '', state: 'available', subnet_label: '' })
function openAdd() {
  addForm.address = ''
  addForm.state = 'available'
  addForm.subnet_label = ''
  addDlg.value = true
}
async function createRaw() {
  if (!addForm.address) {
    ElMessage.warning('请填写 IP 地址')
    return
  }
  try {
    await resourceApi.createIp({
      address: addForm.address,
      state: addForm.state,
      subnet_label: addForm.subnet_label,
    })
    ElMessage.success('已录入')
    addDlg.value = false
    await load()
  } catch (e) {
    const d = e?.response?.data
    ElMessage.error(d ? JSON.stringify(d) : e.message || '创建失败')
  }
}

// ---- 预留 ----
const reserveDlg = ref(false)
const reserveForm = reactive({ address: '', customer_code: '', interface_code: '', subnet_label: '' })
function openReserve(row) {
  reserveForm.address = row?.address || ''
  reserveForm.customer_code = ''
  reserveForm.interface_code = ''
  reserveForm.subnet_label = row?.subnet_label || ''
  reserveDlg.value = true
}
async function submitReserve() {
  if (!reserveForm.address) {
    ElMessage.warning('请填写 IP 地址')
    return
  }
  try {
    await resourceApi.reserveIp({
      address: reserveForm.address,
      customer_code: reserveForm.customer_code || undefined,
      interface_code: reserveForm.interface_code,
      subnet_label: reserveForm.subnet_label,
    })
    ElMessage.success('已预留')
    reserveDlg.value = false
    await load()
  } catch (e) {
    const d = e?.response?.data
    ElMessage.error(d ? JSON.stringify(d) : e.message || '预留失败')
  }
}

// ---- 分配 (联动客户 + 接口 + 可选路由) ----
const allocateDlg = ref(false)
const allocateForm = reactive({
  address: '',
  customer_code: '',
  interface_code: '',
  subnet_label: '',
  allow_from_reserved: true,
  create_route: false,
  route: {
    dest_cidr: '',
    gateway: '',
    on_link: false,
    metric: null,
    route_table: null,
    netplan_device_class: 'ethernets',
    remark: '',
  },
})
const allocating = ref(false)

function openAllocate(row) {
  allocateForm.address = row?.address || ''
  allocateForm.customer_code = row?.customer_code || ''
  allocateForm.interface_code = row?.interface_code || ''
  allocateForm.subnet_label = row?.subnet_label || ''
  allocateForm.allow_from_reserved = true
  allocateForm.create_route = false
  allocateForm.route.dest_cidr = ''
  allocateForm.route.gateway = ''
  allocateForm.route.on_link = false
  allocateForm.route.metric = null
  allocateForm.route.route_table = null
  allocateForm.route.netplan_device_class = 'ethernets'
  allocateForm.route.remark = ''
}

function onIfaceSelected(name) {
  allocateForm.interface_code = name || ''
  const it = ifaces.value.find((x) => x.ifname === name)
  if (it) {
    const k = (it.kind || '').toLowerCase()
    if (['gre', 'gretap', 'vxlan', 'ip6gre', 'wireguard', 'geneve'].includes(k)) {
      allocateForm.route.netplan_device_class = 'tunnels'
    } else if (k === 'bridge') allocateForm.route.netplan_device_class = 'bridges'
    else if (k === 'bond') allocateForm.route.netplan_device_class = 'bonds'
    else if (k === 'vlan') allocateForm.route.netplan_device_class = 'vlans'
    else allocateForm.route.netplan_device_class = 'ethernets'
  }
}

async function submitAllocate() {
  if (!allocateForm.address) {
    ElMessage.warning('请填写 IP 地址')
    return
  }
  if (!allocateForm.customer_code) {
    ElMessage.warning('请选择客户')
    return
  }
  if (allocateForm.create_route && !allocateForm.route.dest_cidr) {
    ElMessage.warning('已开启「联动创建路由」，请填写目标 CIDR')
    return
  }
  allocating.value = true
  try {
    const payload = {
      address: allocateForm.address,
      customer_code: allocateForm.customer_code,
      interface_code: allocateForm.interface_code,
      subnet_label: allocateForm.subnet_label,
      allow_from_reserved: allocateForm.allow_from_reserved,
    }
    if (allocateForm.create_route) {
      payload.route = {
        dest_cidr: allocateForm.route.dest_cidr,
        gateway: allocateForm.route.gateway || null,
        on_link: allocateForm.route.on_link,
        metric: allocateForm.route.metric,
        route_table: allocateForm.route.route_table,
        netplan_device_class: allocateForm.route.netplan_device_class || 'ethernets',
        interface_name: allocateForm.interface_code,
        remark: allocateForm.route.remark,
      }
    }
    const { data } = await resourceApi.allocateIpWithRoute(payload)
    if (data?.route_id) {
      ElMessage.success(`已分配并联动创建路由（route_id=${data.route_id.slice(0, 8)}…）`)
    } else {
      ElMessage.success('已分配')
    }
    allocateDlg.value = false
    await load()
  } catch (e) {
    const d = e?.response?.data
    ElMessage.error(d?.detail || (typeof d === 'string' ? d : JSON.stringify(d || {})) || e.message || '分配失败')
  } finally {
    allocating.value = false
  }
}

// ---- 释放 ----
async function releaseRow(row) {
  try {
    await ElMessageBox.confirm(
      `将释放 IP ${row.address}：清空客户/接口绑定并删除所有关联的路由意图。继续？`,
      '释放 IP',
      { type: 'warning', confirmButtonText: '释放', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    const { data } = await resourceApi.releaseIp({ address: row.address })
    const cnt = (data?.removed_routes || []).length
    ElMessage.success(cnt > 0 ? `已释放并删除 ${cnt} 条关联路由` : '已释放')
    await load()
  } catch (e) {
    const d = e?.response?.data
    ElMessage.error(d ? JSON.stringify(d) : e.message || '释放失败')
  }
}

// ---- 回收 ----
const recycleDlg = ref(false)
const recycleForm = reactive({ address: '', reason: '' })
function openRecycle(row) {
  recycleForm.address = row.address
  recycleForm.reason = ''
  recycleDlg.value = true
}
async function submitRecycle() {
  try {
    const { data } = await resourceApi.recycleIp({
      address: recycleForm.address,
      reason: recycleForm.reason,
    })
    const cnt = (data?.removed_routes || []).length
    ElMessage.success(cnt > 0 ? `已回收并删除 ${cnt} 条关联路由` : '已回收')
    recycleDlg.value = false
    await load()
  } catch (e) {
    const d = e?.response?.data
    ElMessage.error(d ? JSON.stringify(d) : e.message || '回收失败')
  }
}

// ---- 恢复 (recycled → available) ----
async function restoreRow(row) {
  try {
    await ElMessageBox.confirm(
      `将把回收态 IP ${row.address} 恢复为「可用」（不会自动重新绑定客户/接口）。继续？`,
      '恢复 IP',
      { type: 'info', confirmButtonText: '恢复', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await resourceApi.restoreIp({ address: row.address })
    ElMessage.success('已恢复为可用')
    await load()
  } catch (e) {
    const d = e?.response?.data
    ElMessage.error(d ? JSON.stringify(d) : e.message || '恢复失败')
  }
}

// ---- 删除条目 ----
async function deleteRow(row) {
  try {
    await ElMessageBox.confirm(`从资源库中删除 IP 条目 ${row.address}？（不可恢复）`, '删除 IP', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await resourceApi.deleteIp(row.id)
    ElMessage.success('已删除')
    await load()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '删除失败')
  }
}

onMounted(load)

// 打开分配对话框时复用统一入口
function openAllocateWithReset(row) {
  if (row?.state === 'recycled') {
    ElMessage.warning('该 IP 已被回收（不可分配），请先「恢复」为可用状态')
    return
  }
  openAllocate(row)
  allocateDlg.value = true
}
</script>

<template>
  <div class="page">
    <PageHeader title="IP 地址" description="可用 / 已分配 / 预留 / 回收（不可分配）" :icon="Coin">
      <template #actions>
        <el-button :icon="Plus" @click="openAdd">录入 IP</el-button>
        <el-button :icon="EditPen" @click="openReserve(null)">预留</el-button>
        <el-button type="primary" :icon="Promotion" @click="openAllocateWithReset(null)">分配</el-button>
        <el-button :loading="loading" :icon="Refresh" @click="load">刷新</el-button>
      </template>
    </PageHeader>

    <!-- KPI 行 -->
    <el-row :gutter="12" class="kpi-row">
      <el-col :xs="12" :md="6">
        <div class="kpi-tile">
          <div class="kpi-lbl">合计</div>
          <div class="kpi-num">{{ stats.total }}</div>
        </div>
      </el-col>
      <el-col :xs="12" :md="6">
        <div class="kpi-tile k-success">
          <div class="kpi-lbl">可用</div>
          <div class="kpi-num">{{ stats.available }}</div>
        </div>
      </el-col>
      <el-col :xs="12" :md="6">
        <div class="kpi-tile k-primary">
          <div class="kpi-lbl">已分配</div>
          <div class="kpi-num">{{ stats.allocated }}</div>
        </div>
      </el-col>
      <el-col :xs="12" :md="6">
        <div class="kpi-tile k-info">
          <div class="kpi-lbl">回收 (不可分配)</div>
          <div class="kpi-num">{{ stats.recycled }}</div>
        </div>
      </el-col>
    </el-row>

    <!-- 工具栏 -->
    <div class="toolbar">
      <el-select v-model="filters.state" placeholder="按状态过滤" clearable style="width: 200px">
        <el-option v-for="(meta, key) in STATE_META" :key="key" :label="meta.label" :value="key" />
      </el-select>
      <el-input v-model="filters.q" placeholder="搜索 IP / 接口 / 客户 / 网段" clearable style="width: 280px" />
      <span class="muted">显示 {{ filtered.length }} / {{ rows.length }}</span>
    </div>

    <!-- 列表 -->
    <el-table :data="filtered" border v-loading="loading" size="small" stripe>
      <el-table-column prop="address" label="IP" width="160" fixed>
        <template #default="{ row }">
          <code class="mono">{{ row.address }}</code>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="150">
        <template #default="{ row }">
          <el-tag :type="STATE_META[row.state]?.type || 'info'" size="small" effect="dark">
            {{ STATE_META[row.state]?.label || row.state }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="subnet_label" label="网段标签" width="140">
        <template #default="{ row }">
          <span v-if="row.subnet_label">{{ row.subnet_label }}</span>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="客户" min-width="160">
        <template #default="{ row }">
          <template v-if="row.customer_code">
            <strong>{{ customerName(row.customer_code) }}</strong>
            <span class="muted" style="margin-left: 4px">（{{ row.customer_code }}）</span>
          </template>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column prop="interface_code" label="接口" width="160">
        <template #default="{ row }">
          <code v-if="row.interface_code" class="mono">{{ row.interface_code }}</code>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="290" fixed="right">
        <template #default="{ row }">
          <template v-if="row.state === 'available' || row.state === 'reserved'">
            <el-button link type="primary" size="small" :icon="ArrowRight" @click="openAllocateWithReset(row)">
              分配
            </el-button>
            <el-button link type="warning" size="small" :icon="CircleClose" @click="openRecycle(row)">
              回收
            </el-button>
          </template>
          <template v-else-if="row.state === 'allocated'">
            <el-button link type="primary" size="small" @click="openAllocateWithReset(row)">
              重新分配
            </el-button>
            <el-button link type="success" size="small" @click="releaseRow(row)">
              释放
            </el-button>
            <el-button link type="warning" size="small" :icon="CircleClose" @click="openRecycle(row)">
              回收
            </el-button>
          </template>
          <template v-else-if="row.state === 'recycled'">
            <el-tooltip content="回收态不可再分配；如需重新启用请先恢复为可用" placement="top">
              <el-button link type="info" size="small" :icon="RefreshRight" @click="restoreRow(row)">
                恢复
              </el-button>
            </el-tooltip>
          </template>
          <el-button link type="danger" size="small" :icon="Delete" @click="deleteRow(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 录入 IP -->
    <el-dialog v-model="addDlg" title="录入 IP" width="480px">
      <el-form label-width="100px">
        <el-form-item label="IP 地址" required>
          <el-input v-model="addForm.address" placeholder="例如 10.0.0.10" />
        </el-form-item>
        <el-form-item label="初始状态">
          <el-radio-group v-model="addForm.state">
            <el-radio-button label="available">可用</el-radio-button>
            <el-radio-button label="reserved">预留</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="网段标签">
          <el-input v-model="addForm.subnet_label" placeholder="如 client-vlan10（可选）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addDlg = false">取消</el-button>
        <el-button type="primary" @click="createRaw">创建</el-button>
      </template>
    </el-dialog>

    <!-- 预留 -->
    <el-dialog v-model="reserveDlg" title="预留 IP" width="520px">
      <el-form label-width="100px">
        <el-form-item label="IP 地址" required>
          <el-input v-model="reserveForm.address" />
        </el-form-item>
        <el-form-item label="客户">
          <el-select v-model="reserveForm.customer_code" filterable clearable placeholder="可选">
            <el-option v-for="c in customers" :key="c.id" :label="`${c.code} — ${c.name}`" :value="c.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="接口标识">
          <el-input v-model="reserveForm.interface_code" placeholder="如 wg0 / vlan10（可选）" />
        </el-form-item>
        <el-form-item label="网段标签">
          <el-input v-model="reserveForm.subnet_label" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="reserveDlg = false">取消</el-button>
        <el-button type="primary" @click="submitReserve">预留</el-button>
      </template>
    </el-dialog>

    <!-- 分配（联动路由） -->
    <el-dialog v-model="allocateDlg" title="分配 IP（联动客户 / 接口 / 路由）" width="640px" top="6vh">
      <el-form label-width="120px" size="small">
        <el-divider content-position="left">IP 与归属</el-divider>
        <el-form-item label="IP 地址" required>
          <el-input v-model="allocateForm.address" />
        </el-form-item>
        <el-form-item label="客户" required>
          <el-select v-model="allocateForm.customer_code" filterable placeholder="必选">
            <el-option v-for="c in customers" :key="c.id" :label="`${c.code} — ${c.name}`" :value="c.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="接口">
          <el-select
            :model-value="allocateForm.interface_code"
            filterable
            allow-create
            placeholder="选择接口或手填接口编码"
            @update:model-value="onIfaceSelected"
          >
            <el-option v-for="it in ifaces" :key="it.ifname" :label="`${it.ifname}  (${it.kind || '?'})`" :value="it.ifname" />
          </el-select>
        </el-form-item>
        <el-form-item label="网段标签">
          <el-input v-model="allocateForm.subnet_label" />
        </el-form-item>
        <el-form-item label="允许预留→分配">
          <el-switch v-model="allocateForm.allow_from_reserved" />
        </el-form-item>

        <el-divider content-position="left">
          联动创建路由
          <el-switch v-model="allocateForm.create_route" style="margin-left: 12px" />
        </el-divider>
        <template v-if="allocateForm.create_route">
          <el-form-item label="目标 CIDR" required>
            <el-input v-model="allocateForm.route.dest_cidr" placeholder="例如 10.20.30.0/24 或 default" />
          </el-form-item>
          <el-form-item label="下一跳 (via)">
            <el-input v-model="allocateForm.route.gateway" placeholder="可选；与 on-link 二选一" />
          </el-form-item>
          <el-form-item label="on-link">
            <el-switch v-model="allocateForm.route.on_link" :disabled="!!allocateForm.route.gateway" />
            <span class="muted hint">直连/无网关时启用</span>
          </el-form-item>
          <el-row :gutter="12">
            <el-col :span="12">
              <el-form-item label="metric">
                <el-input-number v-model="allocateForm.route.metric" :min="0" :max="9999" style="width: 100%" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="route table">
                <el-input-number v-model="allocateForm.route.route_table" :min="0" :max="255" style="width: 100%" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item label="netplan 设备类">
            <el-select v-model="allocateForm.route.netplan_device_class" style="width: 220px">
              <el-option label="ethernets" value="ethernets" />
              <el-option label="tunnels" value="tunnels" />
              <el-option label="bridges" value="bridges" />
              <el-option label="vlans" value="vlans" />
              <el-option label="bonds" value="bonds" />
            </el-select>
            <span class="muted hint">通常根据所选接口自动匹配，可手动调整</span>
          </el-form-item>
          <el-form-item label="备注">
            <el-input v-model="allocateForm.route.remark" />
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="allocateDlg = false">取消</el-button>
        <el-button type="primary" :loading="allocating" :icon="Promotion" @click="submitAllocate">
          分配后{{ allocateForm.create_route ? '并创建路由' : '' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 回收 -->
    <el-dialog v-model="recycleDlg" title="回收 IP" width="480px">
      <el-alert type="warning" :closable="false" show-icon style="margin-bottom: 12px">
        回收后 IP 进入「不可分配」状态；同时删除所有关联的路由意图。如需再次启用请使用「恢复」操作。
      </el-alert>
      <el-form label-width="100px">
        <el-form-item label="IP 地址">
          <code class="mono">{{ recycleForm.address }}</code>
        </el-form-item>
        <el-form-item label="回收原因">
          <el-input v-model="recycleForm.reason" placeholder="可选；如 设备退网 / 地址污染" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="recycleDlg = false">取消</el-button>
        <el-button type="warning" @click="submitRecycle">确认回收</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.kpi-row { margin: 0; }
.kpi-tile {
  border: 1px solid var(--pe-border);
  border-radius: var(--pe-radius);
  padding: 10px 14px;
  background: var(--pe-card-bg, #fff);
}
.kpi-tile .kpi-lbl {
  font-size: 12px;
  color: var(--pe-text-mute);
  letter-spacing: 0.3px;
  font-weight: 600;
}
.kpi-tile .kpi-num {
  font-size: 24px;
  font-weight: 700;
  margin-top: 2px;
}
.k-success { border-left: 3px solid #67c23a; }
.k-primary { border-left: 3px solid #409eff; }
.k-info { border-left: 3px solid #909399; }
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.muted { color: var(--pe-text-mute); font-size: 12px; }
.hint { margin-left: 8px; font-size: 11px; }
.mono { font-family: var(--pe-mono); font-size: 12px; }
</style>
