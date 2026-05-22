<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  DataAnalysis,
  Refresh,
  Plus,
  Connection,
  CollectionTag,
  CopyDocument,
  Promotion,
  Delete,
  EditPen,
} from '@element-plus/icons-vue'
import { qosApi } from '../../api/qosApi'
import { interfaceApi } from '../../api/interfaceApi'
import { resourceApi } from '../../api/resourceApi'
import PageHeader from '../../components/PageHeader.vue'

const KIND_META = {
  htb: {
    label: 'HTB 单类限速 (推荐)',
    short: 'HTB',
    tag: 'primary',
    desc: 'HTB rate=ceil 硬限速 + 子 fq_codel 抗拥塞；生产首选',
  },
  tbf: {
    label: 'TBF 极简硬限速',
    short: 'TBF',
    tag: 'warning',
    desc: 'Token Bucket 一条命令搞定；轻量但无 fq_codel 公平排队',
  },
}
const DIR_META = {
  egress: { label: '出向 (egress)', tag: 'primary' },
  ingress: { label: '入向 (ingress / IFB)', tag: 'warning' },
}

const loading = ref(false)
const policies = ref([])
const summary = ref({})
const ifaces = ref([])
const customers = ref([])
const pools = ref([])

const filters = reactive({ q: '', interface_name: '', customer: '', root_kind: '', enabled: '' })
const filtered = computed(() => {
  let arr = policies.value.slice()
  const f = filters
  if (f.interface_name) arr = arr.filter((p) => p.interface_name === f.interface_name)
  if (f.customer) arr = arr.filter((p) => p.customer === f.customer)
  if (f.root_kind) arr = arr.filter((p) => p.root_kind === f.root_kind)
  if (f.enabled === '1') arr = arr.filter((p) => p.enabled)
  if (f.enabled === '0') arr = arr.filter((p) => !p.enabled)
  if (f.q) {
    const q = f.q.toLowerCase()
    arr = arr.filter(
      (p) =>
        (p.name || '').toLowerCase().includes(q) ||
        (p.interface_name || '').toLowerCase().includes(q) ||
        (p.customer_name || '').toLowerCase().includes(q) ||
        (p.remark || '').toLowerCase().includes(q),
    )
  }
  return arr
})

const customerLabel = (code) => {
  if (!code) return '—'
  const c = customers.value.find((x) => x.code === code)
  return c ? `${c.name} (${c.code})` : code
}
const ifaceKind = (name) => {
  const i = ifaces.value.find((x) => x.ifname === name)
  return i?.kind || ''
}
const poolLabel = (name) => {
  if (!name) return '—'
  const p = pools.value.find((x) => x.name === name)
  return p ? `${p.name} · 总 ${p.total_mbps} Mbps` : name
}

async function loadAll() {
  loading.value = true
  try {
    const [pol, sum, ifs, cus, pls] = await Promise.all([
      qosApi.listPolicies(),
      qosApi.summary().catch(() => ({})),
      interfaceApi.liveInventory({}).then((r) => r.data?.interfaces || []).catch(() => []),
      resourceApi.listCustomers().catch(() => []),
      resourceApi.listPools().catch(() => []),
    ])
    policies.value = pol
    summary.value = sum
    ifaces.value = ifs
    customers.value = cus
    pools.value = pls
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

// 详情 / 命令预览 / 下发
const detail = ref(null)
const preview = ref(null)
const showTcResult = ref(null)
const lastApply = ref(null)
const applying = ref(false)

async function openDetail(row) {
  detail.value = await qosApi.getPolicy(row.id)
  preview.value = null
  showTcResult.value = null
  lastApply.value = null
}
async function doPreview() {
  if (!detail.value) return
  preview.value = await qosApi.previewPolicy(detail.value.id)
}
async function doApply(phase) {
  if (!detail.value) return
  const text =
    phase === 'clear'
      ? `将清除接口 ${detail.value.interface_name} 上的 tc 根 qdisc。是否继续？`
      : `将以 ${detail.value.interface_name} 为目标按「${KIND_META[detail.value.root_kind]?.short}」模板下发限速 ${detail.value.effective_rate_mbps} Mbps（含冗余 ${detail.value.headroom_pct}%）。是否继续？`
  try {
    await ElMessageBox.confirm(text, '下发确认', { type: 'warning' })
  } catch {
    return
  }
  applying.value = true
  try {
    const { data } = await qosApi.applyPolicy(detail.value.id, { phase })
    lastApply.value = data
    if (data.ok) ElMessage.success(`阶段 ${phase} 完成`)
    else ElMessage.error(data.error || '下发失败')
  } catch (e) {
    lastApply.value = e?.response?.data || { ok: false, error: e?.message || '请求失败' }
    ElMessage.error(lastApply.value.error || '请求失败')
  } finally {
    applying.value = false
  }
}
async function doShow() {
  if (!detail.value) return
  showTcResult.value = await qosApi.showPolicy(detail.value.id)
}
async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text || '')
    ElMessage.success('已复制')
  } catch {
    ElMessage.warning('复制失败')
  }
}

// 新增 / 编辑
const dlg = ref(false)
const editingId = ref(null)
const saving = ref(false)
const form = reactive({
  name: '',
  interface_name: '',
  linked_interface: '',
  customer: '',
  linked_pool: '',
  direction: 'egress',
  root_kind: 'htb',
  rate_mbps: 10,
  headroom_pct: 10,
  burst_kb: 32,
  latency_ms: 50,
  enabled: true,
  remark: '',
})
const dlgTitle = computed(() => (editingId.value ? '编辑限速策略' : '新增限速策略'))

const effectiveRate = computed(() => {
  const r = Number(form.rate_mbps) || 0
  const h = Math.max(0, Math.min(99, Number(form.headroom_pct) || 0))
  return Math.max(1, Math.floor((r * (100 - h)) / 100))
})

function resetForm() {
  Object.assign(form, {
    name: '',
    interface_name: '',
    linked_interface: '',
    customer: '',
    linked_pool: '',
    direction: 'egress',
    root_kind: 'htb',
    rate_mbps: 10,
    headroom_pct: 10,
    burst_kb: 32,
    latency_ms: 50,
    enabled: true,
    remark: '',
  })
}
function openCreate() {
  editingId.value = null
  resetForm()
  dlg.value = true
}
function openEdit(row) {
  editingId.value = row.id
  Object.assign(form, {
    name: row.name,
    interface_name: row.interface_name,
    linked_interface: row.linked_interface || row.interface_name,
    customer: row.customer || '',
    linked_pool: row.linked_pool || '',
    direction: row.direction,
    root_kind: row.root_kind,
    rate_mbps: row.rate_mbps ?? row.default_ceil_mbps ?? 10,
    headroom_pct: row.headroom_pct ?? 0,
    burst_kb: row.burst_kb ?? 32,
    latency_ms: row.latency_ms ?? 50,
    enabled: row.enabled,
    remark: row.remark || '',
  })
  dlg.value = true
}

// 选接口时若该接口已有带宽分配，自动建议
watch(
  () => form.interface_name,
  async (ifname) => {
    if (!ifname || editingId.value) return
    form.linked_interface = ifname
    try {
      const allocs = await resourceApi.listAllocations()
      const hit = (allocs || []).find((a) => a.interface_code === ifname)
      if (hit?.allocated_mbps) form.rate_mbps = hit.allocated_mbps
      if (hit?.pool_name && !form.linked_pool) form.linked_pool = hit.pool_name
    } catch {
      /* 静默 */
    }
  },
)

function payloadFromForm() {
  return {
    name: form.name.trim(),
    interface_name: form.interface_name.trim(),
    linked_interface: form.linked_interface || null,
    customer: form.customer || null,
    linked_pool: form.linked_pool || null,
    direction: form.direction,
    root_kind: form.root_kind,
    rate_mbps: Number(form.rate_mbps) || 0,
    headroom_pct: Number(form.headroom_pct) || 0,
    burst_kb: Number(form.burst_kb) || 32,
    latency_ms: Number(form.latency_ms) || 50,
    enabled: !!form.enabled,
    remark: form.remark || '',
  }
}

async function save() {
  if (!form.name.trim()) {
    ElMessage.error('名称必填')
    return
  }
  if (!form.interface_name.trim()) {
    ElMessage.error('请选择接口')
    return
  }
  if (!Number(form.rate_mbps) || Number(form.rate_mbps) <= 0) {
    ElMessage.error('限速必须 > 0 Mbps')
    return
  }
  saving.value = true
  try {
    if (editingId.value) {
      await qosApi.patchPolicy(editingId.value, payloadFromForm())
      ElMessage.success('已更新（同步至资源管理）')
    } else {
      await qosApi.createPolicy(payloadFromForm())
      ElMessage.success('已创建（同步至资源管理）')
    }
    dlg.value = false
    await loadAll()
  } catch (e) {
    const d = e?.response?.data
    ElMessage.error(d ? JSON.stringify(d) : e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(
      `删除策略「${row.name}」？同时会清理在资源管理中由它自动写入的「带宽分配」记录。`,
      '确认删除',
      { type: 'warning' },
    )
  } catch {
    return
  }
  await qosApi.deletePolicy(row.id)
  ElMessage.success('已删除（联动资源管理已清理）')
  if (detail.value?.id === row.id) detail.value = null
  await loadAll()
}

async function toggleEnabled(row) {
  try {
    await qosApi.patchPolicy(row.id, { enabled: !row.enabled })
    ElMessage.success(`已${row.enabled ? '停用' : '启用'}`)
    await loadAll()
    if (detail.value?.id === row.id) detail.value = await qosApi.getPolicy(row.id)
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '操作失败')
  }
}

onMounted(loadAll)
</script>

<template>
  <div class="page">
    <PageHeader
      title="QoS 接口限速"
      description="对接口进行单值限速，可配置冗余度（自动从限速中扣减）；保存后联动写入资源管理的带宽分配"
      :icon="DataAnalysis"
    />

    <!-- KPI -->
    <el-row :gutter="12" class="kpis">
      <el-col :span="6">
        <el-card shadow="never" class="kpi">
          <div class="kpi-title">策略总数</div>
          <div class="kpi-val">{{ summary.total ?? policies.length }}</div>
          <div class="kpi-sub">启用 <b>{{ summary.enabled ?? 0 }}</b> · 停用 <b>{{ summary.disabled ?? 0 }}</b></div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="kpi">
          <div class="kpi-title">关联接口 / 客户</div>
          <div class="kpi-val">{{ summary.interfaces ?? 0 }} <small class="muted">/ {{ summary.customers ?? 0 }}</small></div>
          <div class="kpi-sub">覆盖接口数 / 关联客户数</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="kpi">
          <div class="kpi-title">配置限速合计（启用）</div>
          <div class="kpi-val">{{ summary.total_rate_mbps ?? 0 }} <span class="unit">Mbps</span></div>
          <div class="kpi-sub">实际下发 <b>{{ summary.total_effective_mbps ?? 0 }}</b> Mbps（含冗余度）</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="kpi">
          <div class="kpi-title">模板分布</div>
          <div class="kpi-kinds">
            <el-tag v-for="(c, k) in summary.by_root_kind || {}" :key="k" size="small">
              {{ KIND_META[k]?.short || k }} × {{ c }}
            </el-tag>
            <span v-if="!Object.keys(summary.by_root_kind || {}).length" class="muted">—</span>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 过滤 + 工具栏 -->
    <el-card shadow="never">
      <div class="row">
        <el-input v-model="filters.q" placeholder="搜索 名称/接口/客户/备注" clearable style="width: 220px" />
        <el-select v-model="filters.interface_name" placeholder="按接口" clearable style="width: 160px">
          <el-option v-for="i in ifaces" :key="i.ifname" :label="`${i.ifname} (${i.kind})`" :value="i.ifname" />
        </el-select>
        <el-select v-model="filters.customer" placeholder="按客户" clearable style="width: 160px">
          <el-option v-for="c in customers" :key="c.code" :label="`${c.name} (${c.code})`" :value="c.code" />
        </el-select>
        <el-select v-model="filters.root_kind" placeholder="按模板" clearable style="width: 160px">
          <el-option v-for="(m, k) in KIND_META" :key="k" :label="m.short" :value="k" />
        </el-select>
        <el-select v-model="filters.enabled" placeholder="按状态" clearable style="width: 110px">
          <el-option label="启用" value="1" />
          <el-option label="停用" value="0" />
        </el-select>
        <div class="spacer" />
        <el-button :icon="Refresh" size="small" :loading="loading" @click="loadAll">刷新</el-button>
        <el-button type="primary" size="small" :icon="Plus" @click="openCreate">新增策略</el-button>
      </div>
    </el-card>

    <!-- 策略列表 -->
    <el-card shadow="never">
      <template #header>
        <div class="row">
          <span><el-icon><CollectionTag /></el-icon> 策略列表 ({{ filtered.length }})</span>
          <div class="spacer" />
          <small v-if="detail" class="muted">当前选中：<b>{{ detail.name }}</b> @ {{ detail.interface_name }}</small>
        </div>
      </template>
      <el-table
        :data="filtered"
        border
        size="small"
        v-loading="loading"
        highlight-current-row
        @row-click="openDetail"
        style="cursor: pointer"
      >
        <el-table-column prop="name" label="策略" min-width="140" />
        <el-table-column label="客户" min-width="140">
          <template #default="{ row }">
            <el-tag v-if="row.customer" type="success" size="small">{{ customerLabel(row.customer) }}</el-tag>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="接口" width="160">
          <template #default="{ row }">
            <div class="if-cell">
              <b class="mono">{{ row.interface_name }}</b>
              <small v-if="row.interface_kind || ifaceKind(row.interface_name)" class="muted">
                {{ row.interface_kind || ifaceKind(row.interface_name) }}
              </small>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="模板" width="100">
          <template #default="{ row }">
            <el-tag :type="KIND_META[row.root_kind]?.tag || 'info'" size="small">
              {{ KIND_META[row.root_kind]?.short || row.root_kind }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="方向" width="100">
          <template #default="{ row }">
            <el-tag :type="DIR_META[row.direction]?.tag || 'info'" size="small">
              {{ DIR_META[row.direction]?.label || row.direction }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="限速 / 冗余 / 实下" min-width="220">
          <template #default="{ row }">
            <div class="bw-cell">
              <span class="mono">
                {{ row.rate_mbps }} Mbps
                <small class="muted">- {{ row.headroom_pct || 0 }}% =</small>
                <b>{{ row.effective_rate_mbps }} Mbps</b>
              </span>
              <el-progress
                :percentage="row.rate_mbps ? Math.round((row.effective_rate_mbps / row.rate_mbps) * 100) : 0"
                :stroke-width="6"
                :show-text="false"
              />
            </div>
          </template>
        </el-table-column>
        <el-table-column label="带宽池" min-width="120">
          <template #default="{ row }">
            <el-tag v-if="row.linked_pool" type="warning" size="small">{{ row.linked_pool }}</el-tag>
            <span v-else class="muted">未关联</span>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="72">
          <template #default="{ row }">
            <el-switch
              :model-value="row.enabled"
              size="small"
              @click.stop
              @change="() => toggleEnabled(row)"
            />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button link size="small" type="primary" :icon="EditPen" @click.stop="openEdit(row)">编辑</el-button>
            <el-button link size="small" type="danger" :icon="Delete" @click.stop="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 详情卡（下方） -->
    <el-card shadow="never">
      <template #header>
        <div class="row">
          <span>
            <el-icon><Connection /></el-icon>
            {{ detail ? `策略详情：${detail.name}` : '点击上方策略查看详情' }}
          </span>
          <div class="spacer" />
          <template v-if="detail">
            <el-button size="small" @click="doPreview">预览命令</el-button>
            <el-button type="warning" size="small" :loading="applying" :icon="Promotion" @click="doApply('apply')">下发</el-button>
            <el-button type="danger" size="small" plain :loading="applying" @click="doApply('clear')">清除</el-button>
            <el-button size="small" @click="doShow">读取 tc -s</el-button>
          </template>
        </div>
      </template>
      <el-empty v-if="!detail" description="未选择策略" :image-size="80" />
      <template v-else>
        <el-alert
          v-if="lastApply && lastApply.ok === false"
          type="error"
          :title="`下发失败：${lastApply.error || ''}`"
          :description="lastApply.hint || ''"
          show-icon
          :closable="false"
          style="margin-bottom: 10px"
        />
        <el-alert
          v-if="lastApply && lastApply.ok === true"
          type="success"
          :title="`下发完成：阶段 ${lastApply.phase || 'apply'}，实下 ${lastApply.effective_rate_mbps || detail.effective_rate_mbps} Mbps`"
          show-icon
          :closable="false"
          style="margin-bottom: 10px"
        />

        <el-descriptions :column="3" border size="small">
          <el-descriptions-item label="客户">
            <el-tag v-if="detail.customer" type="success" size="small">{{ customerLabel(detail.customer) }}</el-tag>
            <span v-else class="muted">—</span>
          </el-descriptions-item>
          <el-descriptions-item label="接口">
            <span class="mono">{{ detail.interface_name }}</span>
            <small v-if="detail.interface_kind" class="muted"> ({{ detail.interface_kind }})</small>
          </el-descriptions-item>
          <el-descriptions-item label="模板">
            <el-tag :type="KIND_META[detail.root_kind]?.tag" size="small">
              {{ KIND_META[detail.root_kind]?.label || detail.root_kind }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="方向">
            <el-tag :type="DIR_META[detail.direction]?.tag" size="small">
              {{ DIR_META[detail.direction]?.label || detail.direction }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="限速 (用户配置)">{{ detail.rate_mbps }} Mbps</el-descriptions-item>
          <el-descriptions-item label="冗余度">{{ detail.headroom_pct }} %</el-descriptions-item>
          <el-descriptions-item label="实际下发">
            <b class="mono">{{ detail.effective_rate_mbps }} Mbps</b>
          </el-descriptions-item>
          <el-descriptions-item label="关联带宽池">
            <span v-if="detail.linked_pool">{{ poolLabel(detail.linked_pool) }}</span>
            <span v-else class="muted">未关联</span>
          </el-descriptions-item>
          <el-descriptions-item label="启用">
            <el-tag :type="detail.enabled ? 'success' : 'info'" size="small">{{ detail.enabled ? '是' : '否' }}</el-tag>
          </el-descriptions-item>
          <template v-if="detail.root_kind === 'tbf'">
            <el-descriptions-item label="TBF burst">{{ detail.burst_kb }} KB</el-descriptions-item>
            <el-descriptions-item label="TBF 最大延迟">{{ detail.latency_ms }} ms</el-descriptions-item>
            <el-descriptions-item label="" />
          </template>
          <el-descriptions-item label="备注" :span="3">{{ detail.remark || '—' }}</el-descriptions-item>
        </el-descriptions>

        <el-collapse v-if="preview" style="margin-top: 12px">
          <el-collapse-item title="预览 tc 命令" name="p">
            <div class="row">
              <small class="muted">下发流程：先 del root 清理，然后按下方命令序列执行</small>
              <div class="spacer" />
              <el-button size="small" :icon="CopyDocument" @click="copyText((preview.commands || []).join('\n'))">复制</el-button>
            </div>
            <pre class="mono block">{{ (preview.commands || []).join('\n') || '—' }}</pre>
            <small class="muted">清除：</small>
            <pre class="mono block">{{ (preview.clear_commands || []).join('\n') || '—' }}</pre>
          </el-collapse-item>
        </el-collapse>

        <el-collapse v-if="lastApply" :model-value="['a']" style="margin-top: 8px">
          <el-collapse-item :title="lastApply.ok ? '下发结果（成功）' : '下发结果（失败）'" name="a">
            <el-table :data="lastApply.steps || []" size="small" border>
              <el-table-column prop="step" label="阶段" width="80" />
              <el-table-column prop="cmd" label="命令" min-width="320">
                <template #default="{ row }"><span class="mono">{{ row.cmd }}</span></template>
              </el-table-column>
              <el-table-column label="结果" width="80" align="center">
                <template #default="{ row }">
                  <el-tag :type="row.ok ? 'success' : 'danger'" size="small">{{ row.ok ? 'OK' : 'FAIL' }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="stderr / note" min-width="200">
                <template #default="{ row }"><span class="mono">{{ row.stderr || row.note || row.stdout || '' }}</span></template>
              </el-table-column>
            </el-table>
          </el-collapse-item>
        </el-collapse>

        <el-collapse v-if="showTcResult" style="margin-top: 8px">
          <el-collapse-item title="系统现状 tc -s" name="s">
            <div v-for="k in ['qdisc', 'class', 'filter']" :key="k">
              <strong>{{ k }}</strong>
              <pre class="mono block">{{ showTcResult[k]?.stdout || showTcResult[k]?.stderr || '—' }}</pre>
            </div>
          </el-collapse-item>
        </el-collapse>
      </template>
    </el-card>

    <!-- 新增 / 编辑 -->
    <el-dialog v-model="dlg" :title="dlgTitle" width="640px" destroy-on-close>
      <el-form label-width="120px">
        <el-form-item label="策略名" required>
          <el-input v-model="form.name" placeholder="例如 cust-A-egress" />
        </el-form-item>
        <el-form-item label="所属客户">
          <el-select v-model="form.customer" filterable clearable placeholder="（可选）" style="width:100%">
            <el-option v-for="c in customers" :key="c.code" :label="`${c.name} (${c.code})`" :value="c.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="接口" required>
          <el-select v-model="form.interface_name" filterable allow-create placeholder="选择接口" style="width:100%">
            <el-option
              v-for="i in ifaces"
              :key="i.ifname"
              :label="`${i.ifname} (${i.kind}${i.operstate ? ' · ' + i.operstate : ''})`"
              :value="i.ifname"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="方向">
          <el-radio-group v-model="form.direction">
            <el-radio-button label="egress">出向 (egress)</el-radio-button>
            <el-radio-button label="ingress" disabled>入向 (需 IFB)</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="限速模板">
          <el-radio-group v-model="form.root_kind">
            <el-radio-button label="htb">HTB 单类</el-radio-button>
            <el-radio-button label="tbf">TBF 极简</el-radio-button>
          </el-radio-group>
          <div class="muted" style="margin-top:4px;font-size:12px">
            {{ KIND_META[form.root_kind]?.desc }}
          </div>
        </el-form-item>
        <el-form-item label="限速">
          <el-input-number v-model="form.rate_mbps" :min="1" :max="100000" controls-position="right" />
          <span class="unit-label">Mbps</span>
        </el-form-item>
        <el-form-item label="冗余度">
          <el-input-number v-model="form.headroom_pct" :min="0" :max="50" controls-position="right" />
          <span class="unit-label">%</span>
          <el-tag style="margin-left:8px" type="info" size="small">
            实下 ≈ {{ effectiveRate }} Mbps
          </el-tag>
        </el-form-item>
        <template v-if="form.root_kind === 'tbf'">
          <el-form-item label="TBF burst">
            <el-input-number v-model="form.burst_kb" :min="1" :max="4096" controls-position="right" />
            <span class="unit-label">KB</span>
            <small class="muted" style="margin-left:8px">建议约速率的 1/100；太小会卡顿</small>
          </el-form-item>
          <el-form-item label="TBF 最大延迟">
            <el-input-number v-model="form.latency_ms" :min="1" :max="2000" controls-position="right" />
            <span class="unit-label">ms</span>
          </el-form-item>
        </template>
        <el-form-item label="关联带宽池">
          <el-select v-model="form.linked_pool" filterable clearable placeholder="（可选）保存后会同步写入「带宽分配」" style="width:100%">
            <el-option
              v-for="p in pools"
              :key="p.name"
              :label="`${p.name} · 总 ${p.total_mbps} Mbps · 剩 ${p.remaining_mbps ?? '?'} Mbps`"
              :value="p.name"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="启用"><el-switch v-model="form.enabled" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="form.remark" /></el-form-item>
      </el-form>
      <el-alert
        v-if="form.linked_pool"
        type="success"
        show-icon
        :closable="false"
        title="保存后将同步至资源管理"
        :description="`pool=${form.linked_pool}, interface=${form.interface_name || '—'}, mbps=${effectiveRate}（已含冗余）`"
      />
      <template #footer>
        <el-button @click="dlg = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存策略</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page { display: flex; flex-direction: column; gap: 12px; }
.row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.spacer { flex: 1; }
.muted { color: var(--el-text-color-secondary); }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 12px; }
.mono.block { background: var(--el-fill-color-light); padding: 8px; border-radius: 4px; overflow: auto; max-height: 240px; white-space: pre-wrap; word-break: break-all; }
.kpis .kpi { background: linear-gradient(180deg, var(--el-color-primary-light-9), var(--el-fill-color-blank)); }
.kpi-title { font-size: 12px; color: var(--el-text-color-secondary); }
.kpi-val { font-size: 22px; font-weight: 700; margin: 4px 0; }
.kpi-val .unit { font-size: 12px; color: var(--el-text-color-secondary); font-weight: 400; }
.kpi-sub { font-size: 12px; color: var(--el-text-color-secondary); }
.kpi-kinds { display: flex; gap: 4px; flex-wrap: wrap; }
.if-cell { display: flex; flex-direction: column; line-height: 1.2; }
.if-cell small { color: var(--el-text-color-secondary); }
.bw-cell { display: flex; flex-direction: column; gap: 2px; }
.unit-label { margin-left: 6px; color: var(--el-text-color-secondary); font-size: 12px; }
</style>
