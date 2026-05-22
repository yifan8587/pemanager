<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Lock,
  Refresh,
  Plus,
  CopyDocument,
  VideoPlay,
  VideoPause,
  RefreshRight,
  Delete,
  EditPen,
  Setting,
  Connection,
  Promotion,
  CircleCheck,
  WarningFilled,
} from '@element-plus/icons-vue'
import { firewallApi } from '../../api/firewallApi'
import { interfaceApi } from '../../api/interfaceApi'
import PageHeader from '../../components/PageHeader.vue'

const ACTION_META = {
  accept: { tag: 'success', label: 'ACCEPT' },
  drop: { tag: 'danger', label: 'DROP' },
  reject: { tag: 'warning', label: 'REJECT' },
  log: { tag: 'info', label: 'LOG' },
}
const CHAIN_META = {
  input: { tag: 'primary', label: 'INPUT' },
  output: { tag: 'success', label: 'OUTPUT' },
  forward: { tag: 'warning', label: 'FORWARD' },
}
const NAT_KIND_META = {
  dnat: { tag: 'primary', label: 'DNAT', chain: 'prerouting' },
  snat: { tag: 'success', label: 'SNAT', chain: 'postrouting' },
  masquerade: { tag: 'warning', label: 'MASQUERADE', chain: 'postrouting' },
  redirect: { tag: 'info', label: 'REDIRECT', chain: 'prerouting' },
}

const activeTab = ref('overview')
const loading = ref(false)
const status = ref({})
const settings = ref({})
const ifaces = ref([])
const rules = ref([])
const nats = ref([])

const rulesEnabled = computed(() => rules.value.filter((r) => r.enabled).length)
const natsEnabled = computed(() => nats.value.filter((n) => n.enabled).length)

async function loadAll() {
  loading.value = true
  try {
    const [st, cfg, rs, ns, ifs] = await Promise.all([
      firewallApi.status(),
      firewallApi.getSettings(),
      firewallApi.listRules(),
      firewallApi.listNat(),
      interfaceApi.liveInventory({}).then((r) => r.data?.interfaces || []).catch(() => []),
    ])
    status.value = st
    settings.value = cfg
    rules.value = rs
    nats.value = ns
    ifaces.value = ifs
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

// ---------------------- 服务控制 ----------------------
async function ctrl(action) {
  const text = {
    start: '启动 nftables 服务？',
    stop: '停止 nftables 服务（将清空内核规则集）？',
    restart: '重启 nftables 服务？',
    reload: '重载 nftables 服务？',
    enable: '设置 nftables 开机自启？',
    disable: '取消 nftables 开机自启？',
  }[action]
  try {
    await ElMessageBox.confirm(text, '确认', { type: action === 'stop' ? 'warning' : 'info' })
  } catch {
    return
  }
  try {
    const { data } = await firewallApi.control({ unit: 'nftables', action })
    if (data.ok) ElMessage.success(`${action} 成功`)
    else ElMessage.error(data?.result?.stderr || data?.error || '失败')
    await loadAll()
  } catch (e) {
    ElMessage.error(e?.response?.data?.error || e.message || '失败')
  }
}

async function patchSettings(patch) {
  try {
    const { data } = await firewallApi.patchSettings(patch)
    settings.value = data
    ElMessage.success('已保存设置')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  }
}

// ---------------------- Rule 表单（步骤式） ----------------------
const ruleDlg = ref(false)
const ruleStep = ref(0)
const ruleEditingId = ref(null)
const ruleSaving = ref(false)
const ruleForm = reactive({
  name: '',
  enabled: true,
  chain: 'input',
  action: 'accept',
  family: 'both',
  protocol: 'any',
  src_cidr: '',
  dst_cidr: '',
  src_port: '',
  dst_port: '',
  in_interface: '',
  out_interface: '',
  priority: 100,
  remark: '',
})
function ruleReset() {
  Object.assign(ruleForm, {
    name: '',
    enabled: true,
    chain: 'input',
    action: 'accept',
    family: 'both',
    protocol: 'any',
    src_cidr: '',
    dst_cidr: '',
    src_port: '',
    dst_port: '',
    in_interface: '',
    out_interface: '',
    priority: 100,
    remark: '',
  })
}
function openRuleCreate() {
  ruleEditingId.value = null
  ruleStep.value = 0
  ruleReset()
  ruleDlg.value = true
}
function openRuleEdit(r) {
  ruleEditingId.value = r.id
  ruleStep.value = 0
  Object.assign(ruleForm, { ...r })
  ruleDlg.value = true
}
async function saveRule() {
  if (!ruleForm.name.trim()) {
    ElMessage.error('名称必填')
    ruleStep.value = 0
    return
  }
  ruleSaving.value = true
  try {
    if (ruleEditingId.value) await firewallApi.patchRule(ruleEditingId.value, ruleForm)
    else await firewallApi.createRule(ruleForm)
    ElMessage.success('已保存')
    ruleDlg.value = false
    await loadAll()
  } catch (e) {
    ElMessage.error(JSON.stringify(e?.response?.data || e.message))
  } finally {
    ruleSaving.value = false
  }
}
async function removeRule(r) {
  try {
    await ElMessageBox.confirm(`删除规则「${r.name}」？`, '确认', { type: 'warning' })
  } catch {
    return
  }
  await firewallApi.deleteRule(r.id)
  ElMessage.success('已删除')
  await loadAll()
}
async function toggleRule(r) {
  await firewallApi.patchRule(r.id, { enabled: !r.enabled })
  await loadAll()
}

// ---------------------- NAT 表单（步骤式） ----------------------
const natDlg = ref(false)
const natStep = ref(0)
const natEditingId = ref(null)
const natSaving = ref(false)
const natForm = reactive({
  name: '',
  enabled: true,
  kind: 'masquerade',
  family: 'ipv4',
  protocol: 'any',
  in_interface: '',
  out_interface: '',
  src_cidr: '',
  dst_cidr: '',
  dst_port: '',
  to_ip: '',
  to_port: '',
  priority: 100,
  remark: '',
})
function natReset() {
  Object.assign(natForm, {
    name: '',
    enabled: true,
    kind: 'masquerade',
    family: 'ipv4',
    protocol: 'any',
    in_interface: '',
    out_interface: '',
    src_cidr: '',
    dst_cidr: '',
    dst_port: '',
    to_ip: '',
    to_port: '',
    priority: 100,
    remark: '',
  })
}
function openNatCreate() {
  natEditingId.value = null
  natStep.value = 0
  natReset()
  natDlg.value = true
}
function openNatEdit(r) {
  natEditingId.value = r.id
  natStep.value = 0
  Object.assign(natForm, { ...r })
  natDlg.value = true
}
async function saveNat() {
  if (!natForm.name.trim()) {
    ElMessage.error('名称必填')
    natStep.value = 0
    return
  }
  if (natForm.kind === 'dnat' && !natForm.to_ip && !natForm.to_port) {
    ElMessage.error('DNAT 至少要填 to_ip 或 to_port')
    natStep.value = 1
    return
  }
  if (natForm.kind === 'snat' && !natForm.to_ip) {
    ElMessage.error('SNAT 必须填 to_ip')
    natStep.value = 1
    return
  }
  if (natForm.kind === 'masquerade' && !natForm.out_interface) {
    ElMessage.error('MASQUERADE 必须指定出接口 (oifname)')
    natStep.value = 1
    return
  }
  if (natForm.kind === 'redirect' && !natForm.to_port) {
    ElMessage.error('REDIRECT 必须指定 to_port（本机端口）')
    natStep.value = 1
    return
  }
  natSaving.value = true
  try {
    if (natEditingId.value) await firewallApi.patchNat(natEditingId.value, natForm)
    else await firewallApi.createNat(natForm)
    ElMessage.success('已保存')
    natDlg.value = false
    await loadAll()
  } catch (e) {
    ElMessage.error(JSON.stringify(e?.response?.data || e.message))
  } finally {
    natSaving.value = false
  }
}
async function removeNat(r) {
  try {
    await ElMessageBox.confirm(`删除 NAT 规则「${r.name}」？`, '确认', { type: 'warning' })
  } catch {
    return
  }
  await firewallApi.deleteNat(r.id)
  ElMessage.success('已删除')
  await loadAll()
}
async function toggleNat(r) {
  await firewallApi.patchNat(r.id, { enabled: !r.enabled })
  await loadAll()
}

// ---------------------- 下发与现状 ----------------------
const preview = ref(null)
const lastApply = ref(null)
const showResult = ref(null)
const applying = ref(false)
const deployActive = ref(0)

async function genPreview() {
  preview.value = await firewallApi.previewRuleset()
  deployActive.value = 0
}
async function applyPhase(phase) {
  const engine = settings.value?.engine || status.value?.engine || 'nft'
  const text = {
    validate: `引擎=${engine}：执行 ${engine === 'nft' ? 'nft -c' : 'iptables-restore --test'} 校验生成的规则集，继续？`,
    apply: `引擎=${engine}：将渲染并应用规则集到内核，继续？`,
    flush: `引擎=${engine}：清空 pemanager 自定义链下的所有规则，继续？`,
  }[phase]
  try {
    await ElMessageBox.confirm(text, '确认', { type: 'warning' })
  } catch {
    return
  }
  applying.value = true
  try {
    const { data } = await firewallApi.applyRuleset({ phase })
    lastApply.value = data
    if (data.ok) {
      if (phase === 'validate') deployActive.value = 1
      else if (phase === 'apply') deployActive.value = 2
      ElMessage.success(`${phase} 完成`)
    } else {
      ElMessage.error(data.error || '失败')
    }
    await loadAll()
  } catch (e) {
    lastApply.value = e?.response?.data || { ok: false, error: e.message }
    ElMessage.error(lastApply.value?.error || '请求失败')
  } finally {
    applying.value = false
  }
}
async function showSystem() {
  showResult.value = await firewallApi.showRuleset()
}
async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text || '')
    ElMessage.success('已复制')
  } catch {
    ElMessage.warning('复制失败')
  }
}

onMounted(loadAll)
</script>

<template>
  <div class="page">
    <PageHeader
      title="防火墙管理"
      description="过滤规则 + NAT 规则；支持 nftables / iptables 两种引擎，下发分预览 → 校验 → 应用三步"
      :icon="Lock"
    />

    <!-- 顶部状态 KPI -->
    <el-row :gutter="12" class="kpis">
      <el-col :span="6">
        <el-card shadow="never" class="kpi">
          <div class="kpi-title">引擎</div>
          <div class="kpi-val">
            <el-tag :type="status.engine === 'iptables' ? 'warning' : 'primary'">
              {{ status.engine === 'iptables' ? 'iptables' : 'nftables' }}
            </el-tag>
            <el-select
              :model-value="settings.engine"
              size="small"
              style="margin-left:8px;width:130px"
              @change="(v) => patchSettings({ engine: v })"
            >
              <el-option label="nftables (nft)" value="nft" />
              <el-option label="iptables-restore" value="iptables" />
            </el-select>
          </div>
          <div class="kpi-sub">
            apply: <b :class="{ green: status.apply_enabled, red: !status.apply_enabled }">{{ status.apply_enabled ? 'ON' : 'OFF' }}</b>
            · subprocess: <b :class="{ green: status.subprocess_enabled, red: !status.subprocess_enabled }">{{ status.subprocess_enabled ? 'ON' : 'OFF' }}</b>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="kpi">
          <div class="kpi-title">nftables 服务</div>
          <div class="kpi-val">
            <el-tag :type="status.services?.nftables?.active ? 'success' : 'info'">
              {{ status.services?.nftables?.active_state || '—' }}
            </el-tag>
            <el-tag :type="status.services?.nftables?.enabled ? 'success' : 'info'" style="margin-left:4px">
              {{ status.services?.nftables?.enabled_state || '—' }}
            </el-tag>
          </div>
          <div class="kpi-sub btns">
            <el-button size="small" :icon="VideoPlay" type="success" plain @click="ctrl('start')">启动</el-button>
            <el-button size="small" :icon="VideoPause" type="danger" plain @click="ctrl('stop')">停止</el-button>
            <el-button size="small" :icon="RefreshRight" @click="ctrl('restart')">重启</el-button>
            <el-button size="small" plain @click="ctrl('enable')">开机自启</el-button>
            <el-button size="small" plain @click="ctrl('disable')">取消自启</el-button>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="kpi">
          <div class="kpi-title">规则统计</div>
          <div class="kpi-val">{{ rules.length }} <small class="muted">过滤</small> · {{ nats.length }} <small class="muted">NAT</small></div>
          <div class="kpi-sub">启用 <b>{{ rulesEnabled }}</b> + <b>{{ natsEnabled }}</b></div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="kpi">
          <div class="kpi-title">最近下发</div>
          <div class="kpi-val">
            <el-tag :type="status.last_apply_ok ? 'success' : 'danger'">
              <el-icon><CircleCheck v-if="status.last_apply_ok" /><WarningFilled v-else /></el-icon>
              {{ status.last_apply_ok ? '成功' : (status.last_apply_at ? '失败' : '尚未下发') }}
            </el-tag>
          </div>
          <div class="kpi-sub">
            <small class="muted">{{ status.last_apply_at || '—' }}</small>
            <br />
            <small class="muted">{{ status.last_apply_summary || '' }}</small>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 默认策略快速调整 -->
    <el-card shadow="never">
      <div class="row">
        <span><el-icon><Setting /></el-icon> 默认策略</span>
        <span class="muted">input</span>
        <el-select :model-value="settings.policy_input" size="small" style="width:110px"
          @change="(v) => patchSettings({ policy_input: v })">
          <el-option label="ACCEPT" value="accept" />
          <el-option label="DROP" value="drop" />
        </el-select>
        <span class="muted">output</span>
        <el-select :model-value="settings.policy_output" size="small" style="width:110px"
          @change="(v) => patchSettings({ policy_output: v })">
          <el-option label="ACCEPT" value="accept" />
          <el-option label="DROP" value="drop" />
        </el-select>
        <span class="muted">forward</span>
        <el-select :model-value="settings.policy_forward" size="small" style="width:110px"
          @change="(v) => patchSettings({ policy_forward: v })">
          <el-option label="ACCEPT" value="accept" />
          <el-option label="DROP" value="drop" />
        </el-select>
        <div class="spacer" />
        <el-button :icon="Refresh" size="small" :loading="loading" @click="loadAll">刷新</el-button>
      </div>
    </el-card>

    <el-tabs v-model="activeTab" type="border-card">
      <!-- 过滤规则 -->
      <el-tab-pane label="① 过滤规则 (filter)" name="filter">
        <div class="row">
          <el-button type="primary" :icon="Plus" @click="openRuleCreate">新增规则</el-button>
          <small class="muted">{{ rules.length }} 条 / 启用 {{ rulesEnabled }}</small>
        </div>
        <el-table :data="rules" border size="small" v-loading="loading" style="margin-top:8px">
          <el-table-column label="启用" width="64">
            <template #default="{ row }">
              <el-switch :model-value="row.enabled" size="small" @change="() => toggleRule(row)" />
            </template>
          </el-table-column>
          <el-table-column prop="name" label="名称" min-width="140" />
          <el-table-column label="链" width="100">
            <template #default="{ row }">
              <el-tag :type="CHAIN_META[row.chain]?.tag" size="small">{{ CHAIN_META[row.chain]?.label || row.chain }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="动作" width="90">
            <template #default="{ row }">
              <el-tag :type="ACTION_META[row.action]?.tag" size="small">{{ ACTION_META[row.action]?.label || row.action }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="protocol" label="proto" width="76" />
          <el-table-column prop="family" label="family" width="80" />
          <el-table-column label="src" min-width="140">
            <template #default="{ row }">
              <span class="mono">{{ row.src_cidr || 'any' }}<span v-if="row.src_port">:{{ row.src_port }}</span></span>
            </template>
          </el-table-column>
          <el-table-column label="dst" min-width="140">
            <template #default="{ row }">
              <span class="mono">{{ row.dst_cidr || 'any' }}<span v-if="row.dst_port">:{{ row.dst_port }}</span></span>
            </template>
          </el-table-column>
          <el-table-column label="iif / oif" width="160">
            <template #default="{ row }">
              <span class="mono">{{ row.in_interface || '*' }} / {{ row.out_interface || '*' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="priority" label="prio" width="64" align="center" />
          <el-table-column label="操作" width="140" fixed="right">
            <template #default="{ row }">
              <el-button link size="small" :icon="EditPen" type="primary" @click="openRuleEdit(row)">编辑</el-button>
              <el-button link size="small" :icon="Delete" type="danger" @click="removeRule(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- NAT 规则 -->
      <el-tab-pane label="② NAT 规则" name="nat">
        <div class="row">
          <el-button type="primary" :icon="Plus" @click="openNatCreate">新增 NAT</el-button>
          <small class="muted">{{ nats.length }} 条 / 启用 {{ natsEnabled }}</small>
        </div>
        <el-table :data="nats" border size="small" v-loading="loading" style="margin-top:8px">
          <el-table-column label="启用" width="64">
            <template #default="{ row }">
              <el-switch :model-value="row.enabled" size="small" @change="() => toggleNat(row)" />
            </template>
          </el-table-column>
          <el-table-column prop="name" label="名称" min-width="140" />
          <el-table-column label="类型 / 链" width="170">
            <template #default="{ row }">
              <el-tag :type="NAT_KIND_META[row.kind]?.tag" size="small">{{ NAT_KIND_META[row.kind]?.label }}</el-tag>
              <small class="muted">&nbsp;{{ NAT_KIND_META[row.kind]?.chain }}</small>
            </template>
          </el-table-column>
          <el-table-column prop="family" label="family" width="80" />
          <el-table-column prop="protocol" label="proto" width="76" />
          <el-table-column label="iif / oif" width="170">
            <template #default="{ row }">
              <span class="mono">{{ row.in_interface || '*' }} / {{ row.out_interface || '*' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="dst" min-width="160">
            <template #default="{ row }">
              <span class="mono">{{ row.dst_cidr || 'any' }}<span v-if="row.dst_port">:{{ row.dst_port }}</span></span>
            </template>
          </el-table-column>
          <el-table-column label="→ to" min-width="180">
            <template #default="{ row }">
              <span class="mono">
                <template v-if="row.kind === 'masquerade'">(动态出口源)</template>
                <template v-else>
                  {{ row.to_ip || '' }}<span v-if="row.to_port">:{{ row.to_port }}</span>
                </template>
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="priority" label="prio" width="64" align="center" />
          <el-table-column label="操作" width="140" fixed="right">
            <template #default="{ row }">
              <el-button link size="small" :icon="EditPen" type="primary" @click="openNatEdit(row)">编辑</el-button>
              <el-button link size="small" :icon="Delete" type="danger" @click="removeNat(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 下发与现状 -->
      <el-tab-pane label="③ 下发与现状" name="deploy">
        <el-steps :active="deployActive" align-center finish-status="success" style="margin-bottom: 12px">
          <el-step title="① 预览" />
          <el-step title="② 校验" />
          <el-step title="③ 应用" />
        </el-steps>
        <div class="row">
          <el-button :loading="loading" @click="genPreview">生成预览</el-button>
          <el-button type="warning" :loading="applying" @click="applyPhase('validate')">校验</el-button>
          <el-button type="success" :loading="applying" :icon="Promotion" @click="applyPhase('apply')">应用</el-button>
          <el-button type="danger" plain :loading="applying" @click="applyPhase('flush')">flush pemanager</el-button>
          <div class="spacer" />
          <el-button @click="showSystem">读取系统现状</el-button>
        </div>

        <el-alert
          v-if="lastApply && lastApply.ok === false"
          type="error"
          :title="`下发失败：${lastApply.error || ''}`"
          :description="lastApply.hint || ''"
          show-icon
          :closable="false"
          style="margin-top: 8px"
        />
        <el-alert
          v-if="lastApply && lastApply.ok === true"
          type="success"
          :title="`阶段 ${lastApply.phase} 完成（engine=${lastApply.engine}）`"
          show-icon
          :closable="false"
          style="margin-top: 8px"
        />

        <div v-if="preview" style="margin-top: 12px">
          <div class="row">
            <strong>规则集预览（engine={{ preview.engine }}）</strong>
            <div class="spacer" />
            <el-button size="small" :icon="CopyDocument" @click="copyText(preview.ruleset)">复制</el-button>
          </div>
          <pre class="mono blk">{{ preview.ruleset || '—' }}</pre>
          <template v-if="preview.ruleset_ipv6">
            <strong>IPv6 规则集</strong>
            <pre class="mono blk">{{ preview.ruleset_ipv6 }}</pre>
          </template>
        </div>

        <el-collapse v-if="lastApply" :model-value="['a']" style="margin-top: 8px">
          <el-collapse-item title="下发步骤" name="a">
            <el-table :data="lastApply.steps || []" size="small" border>
              <el-table-column prop="step" label="阶段" min-width="240">
                <template #default="{ row }"><span class="mono">{{ row.step }}</span></template>
              </el-table-column>
              <el-table-column label="结果" width="80" align="center">
                <template #default="{ row }">
                  <el-tag :type="row.ok ? 'success' : 'danger'" size="small">{{ row.ok ? 'OK' : 'FAIL' }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="stderr / note" min-width="220">
                <template #default="{ row }"><span class="mono">{{ row.stderr || row.note || row.stdout || '' }}</span></template>
              </el-table-column>
            </el-table>
          </el-collapse-item>
        </el-collapse>

        <el-collapse v-if="showResult" style="margin-top: 8px">
          <el-collapse-item title="系统现状" name="s">
            <div v-for="(v, k) in showResult.tables || {}" :key="k">
              <strong>{{ k }}</strong>
              <pre class="mono blk">{{ v.stdout || v.stderr || '—' }}</pre>
            </div>
          </el-collapse-item>
        </el-collapse>
      </el-tab-pane>
    </el-tabs>

    <!-- Rule 步骤式 -->
    <el-dialog v-model="ruleDlg" :title="ruleEditingId ? '编辑过滤规则' : '新增过滤规则'" width="680px" destroy-on-close>
      <el-steps :active="ruleStep" finish-status="success" simple>
        <el-step title="基本" />
        <el-step title="匹配条件" />
        <el-step title="动作 / 确认" />
      </el-steps>

      <div v-show="ruleStep === 0" class="step">
        <el-form label-width="110px">
          <el-form-item label="名称" required><el-input v-model="ruleForm.name" placeholder="如 allow-ssh" /></el-form-item>
          <el-form-item label="启用"><el-switch v-model="ruleForm.enabled" /></el-form-item>
          <el-form-item label="链 (chain)">
            <el-radio-group v-model="ruleForm.chain">
              <el-radio-button label="input">INPUT 入向</el-radio-button>
              <el-radio-button label="output">OUTPUT 出向</el-radio-button>
              <el-radio-button label="forward">FORWARD 转发</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="协议族">
            <el-radio-group v-model="ruleForm.family">
              <el-radio-button label="ipv4">IPv4</el-radio-button>
              <el-radio-button label="ipv6">IPv6</el-radio-button>
              <el-radio-button label="both">IPv4+IPv6</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="备注"><el-input v-model="ruleForm.remark" /></el-form-item>
        </el-form>
      </div>

      <div v-show="ruleStep === 1" class="step">
        <el-form label-width="110px">
          <el-form-item label="L4 协议">
            <el-radio-group v-model="ruleForm.protocol">
              <el-radio-button label="any">ANY</el-radio-button>
              <el-radio-button label="tcp">TCP</el-radio-button>
              <el-radio-button label="udp">UDP</el-radio-button>
              <el-radio-button label="icmp">ICMP</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="src CIDR"><el-input v-model="ruleForm.src_cidr" placeholder="如 10.0.0.0/24" /></el-form-item>
          <el-form-item label="dst CIDR"><el-input v-model="ruleForm.dst_cidr" /></el-form-item>
          <el-form-item label="sport">
            <el-input v-model="ruleForm.src_port" placeholder="22 或 1000-2000" :disabled="!['tcp','udp'].includes(ruleForm.protocol)" />
          </el-form-item>
          <el-form-item label="dport">
            <el-input v-model="ruleForm.dst_port" :disabled="!['tcp','udp'].includes(ruleForm.protocol)" />
          </el-form-item>
          <el-form-item label="入接口 iif">
            <el-select v-model="ruleForm.in_interface" filterable allow-create clearable style="width:100%">
              <el-option v-for="i in ifaces" :key="i.ifname" :label="`${i.ifname} (${i.kind})`" :value="i.ifname" />
            </el-select>
          </el-form-item>
          <el-form-item label="出接口 oif">
            <el-select v-model="ruleForm.out_interface" filterable allow-create clearable style="width:100%">
              <el-option v-for="i in ifaces" :key="i.ifname" :label="`${i.ifname} (${i.kind})`" :value="i.ifname" />
            </el-select>
          </el-form-item>
        </el-form>
      </div>

      <div v-show="ruleStep === 2" class="step">
        <el-form label-width="110px">
          <el-form-item label="动作 (verdict)">
            <el-radio-group v-model="ruleForm.action">
              <el-radio-button label="accept">ACCEPT</el-radio-button>
              <el-radio-button label="drop">DROP</el-radio-button>
              <el-radio-button label="reject">REJECT</el-radio-button>
              <el-radio-button label="log">LOG + accept</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="优先级"><el-input-number v-model="ruleForm.priority" /></el-form-item>
        </el-form>
        <el-alert type="info" :closable="false" show-icon>
          <template #title>
            预览：<b class="mono">{{ CHAIN_META[ruleForm.chain]?.label }}</b> / family=<b>{{ ruleForm.family }}</b> /
            <b>{{ ruleForm.protocol }}</b>
            <span v-if="ruleForm.src_cidr"> src={{ ruleForm.src_cidr }}</span>
            <span v-if="ruleForm.dst_cidr"> dst={{ ruleForm.dst_cidr }}</span>
            <span v-if="ruleForm.dst_port"> dport={{ ruleForm.dst_port }}</span>
            → <b>{{ ACTION_META[ruleForm.action]?.label }}</b>
          </template>
          保存后需要在「下发与现状」执行「校验 → 应用」才会真正生效。
        </el-alert>
      </div>

      <template #footer>
        <el-button @click="ruleDlg = false">取消</el-button>
        <el-button v-if="ruleStep > 0" @click="ruleStep -= 1">上一步</el-button>
        <el-button v-if="ruleStep < 2" type="primary" @click="ruleStep += 1">下一步</el-button>
        <el-button v-else type="primary" :loading="ruleSaving" @click="saveRule">保存规则</el-button>
      </template>
    </el-dialog>

    <!-- NAT 步骤式 -->
    <el-dialog v-model="natDlg" :title="natEditingId ? '编辑 NAT 规则' : '新增 NAT 规则'" width="680px" destroy-on-close>
      <el-steps :active="natStep" finish-status="success" simple>
        <el-step title="选择 NAT 类型" />
        <el-step title="转换目标" />
        <el-step title="匹配 / 确认" />
      </el-steps>

      <div v-show="natStep === 0" class="step">
        <el-form label-width="110px">
          <el-form-item label="名称" required><el-input v-model="natForm.name" placeholder="如 wan-masq" /></el-form-item>
          <el-form-item label="启用"><el-switch v-model="natForm.enabled" /></el-form-item>
          <el-form-item label="类型">
            <el-radio-group v-model="natForm.kind">
              <el-radio-button label="masquerade">MASQUERADE</el-radio-button>
              <el-radio-button label="snat">SNAT</el-radio-button>
              <el-radio-button label="dnat">DNAT</el-radio-button>
              <el-radio-button label="redirect">REDIRECT</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-alert :type="'info'" :closable="false" show-icon>
            <template #title>
              <span v-if="natForm.kind === 'masquerade'">MASQUERADE：出接口动态源 NAT（PPPoE/DHCP 推荐）。必填 oifname。</span>
              <span v-else-if="natForm.kind === 'snat'">SNAT：把源 IP 改写为固定 to_ip。建议同时指定 oifname。</span>
              <span v-else-if="natForm.kind === 'dnat'">DNAT：把命中流量目的改写为 to_ip[:to_port]，常用于端口映射。</span>
              <span v-else>REDIRECT：重定向到本机 to_port，常用于透明代理。</span>
            </template>
          </el-alert>
          <el-form-item label="协议族">
            <el-radio-group v-model="natForm.family">
              <el-radio-button label="ipv4">IPv4</el-radio-button>
              <el-radio-button label="ipv6">IPv6</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="备注"><el-input v-model="natForm.remark" /></el-form-item>
        </el-form>
      </div>

      <div v-show="natStep === 1" class="step">
        <el-form label-width="110px">
          <el-form-item v-if="['snat','dnat'].includes(natForm.kind)" label="to_ip" :required="natForm.kind === 'snat'">
            <el-input v-model="natForm.to_ip" placeholder="如 10.0.0.5" />
          </el-form-item>
          <el-form-item v-if="['dnat','redirect'].includes(natForm.kind)" label="to_port" :required="natForm.kind === 'redirect'">
            <el-input v-model="natForm.to_port" placeholder="80 或 1000-2000" />
          </el-form-item>
          <el-form-item v-if="natForm.kind === 'masquerade'" label="说明">
            <el-tag>MASQUERADE 无需填写转换目标</el-tag>
          </el-form-item>
        </el-form>
      </div>

      <div v-show="natStep === 2" class="step">
        <el-form label-width="110px">
          <el-form-item label="L4 协议">
            <el-radio-group v-model="natForm.protocol">
              <el-radio-button label="any">ANY</el-radio-button>
              <el-radio-button label="tcp">TCP</el-radio-button>
              <el-radio-button label="udp">UDP</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="入接口 iif" :required="['dnat','redirect'].includes(natForm.kind)">
            <el-select v-model="natForm.in_interface" filterable allow-create clearable style="width:100%">
              <el-option v-for="i in ifaces" :key="i.ifname" :label="`${i.ifname} (${i.kind})`" :value="i.ifname" />
            </el-select>
          </el-form-item>
          <el-form-item label="出接口 oif" :required="['masquerade','snat'].includes(natForm.kind)">
            <el-select v-model="natForm.out_interface" filterable allow-create clearable style="width:100%">
              <el-option v-for="i in ifaces" :key="i.ifname" :label="`${i.ifname} (${i.kind})`" :value="i.ifname" />
            </el-select>
          </el-form-item>
          <el-form-item label="src CIDR"><el-input v-model="natForm.src_cidr" /></el-form-item>
          <el-form-item label="dst CIDR"><el-input v-model="natForm.dst_cidr" /></el-form-item>
          <el-form-item label="dst_port">
            <el-input v-model="natForm.dst_port" :disabled="!['tcp','udp'].includes(natForm.protocol)" placeholder="80 或 1000-2000" />
          </el-form-item>
          <el-form-item label="优先级"><el-input-number v-model="natForm.priority" /></el-form-item>
        </el-form>
        <el-alert type="info" :closable="false" show-icon>
          <template #title>
            预览：<b>{{ NAT_KIND_META[natForm.kind]?.label }}</b>（{{ NAT_KIND_META[natForm.kind]?.chain }}）
            iif=<b>{{ natForm.in_interface || '*' }}</b> oif=<b>{{ natForm.out_interface || '*' }}</b>
            dst=<b>{{ natForm.dst_cidr || 'any' }}</b><span v-if="natForm.dst_port">:{{ natForm.dst_port }}</span>
            <template v-if="natForm.kind !== 'masquerade'">
              → <b>{{ natForm.to_ip || '' }}<span v-if="natForm.to_port">:{{ natForm.to_port }}</span></b>
            </template>
          </template>
          保存后到「下发与现状」点击「校验 → 应用」生效。
        </el-alert>
      </div>

      <template #footer>
        <el-button @click="natDlg = false">取消</el-button>
        <el-button v-if="natStep > 0" @click="natStep -= 1">上一步</el-button>
        <el-button v-if="natStep < 2" type="primary" @click="natStep += 1">下一步</el-button>
        <el-button v-else type="primary" :loading="natSaving" @click="saveNat">保存 NAT 规则</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page { display: flex; flex-direction: column; gap: 12px; }
.row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.spacer { flex: 1; }
.muted { color: var(--el-text-color-secondary); }
.green { color: var(--el-color-success); }
.red { color: var(--el-color-danger); }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 12px; }
.mono.blk { background: var(--el-fill-color-light); padding: 10px; border-radius: 4px; overflow: auto; max-height: 320px; white-space: pre-wrap; word-break: break-all; }
.kpis .kpi { background: linear-gradient(180deg, var(--el-color-primary-light-9), var(--el-fill-color-blank)); }
.kpi-title { font-size: 12px; color: var(--el-text-color-secondary); }
.kpi-val { font-size: 18px; font-weight: 600; margin: 4px 0; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.kpi-sub { font-size: 12px; color: var(--el-text-color-secondary); }
.kpi-sub.btns { display: flex; gap: 4px; flex-wrap: wrap; }
.step { padding: 12px 0; }
</style>
