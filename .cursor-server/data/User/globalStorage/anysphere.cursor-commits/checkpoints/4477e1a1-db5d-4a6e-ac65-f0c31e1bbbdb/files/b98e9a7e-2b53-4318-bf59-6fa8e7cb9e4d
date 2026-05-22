<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Lock } from '@element-plus/icons-vue'
import { firewallApi } from '../../api/firewallApi'
import { interfaceApi } from '../../api/interfaceApi'
import JsonBlock from '../../components/JsonBlock.vue'
import PageHeader from '../../components/PageHeader.vue'

const activeTab = ref('rules')
const loading = ref(false)
const rows = ref([])
const ifaces = ref([])

const dlg = ref(false)
const editingId = ref(null)
const saving = ref(false)
const form = reactive({
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
const title = computed(() => (editingId.value ? '编辑规则' : '新增规则'))

const preview = ref('')
const loadingPreview = ref(false)
const lastApply = ref(null)
const applying = ref(false)
const showResult = ref(null)
const deployActive = ref(0)

async function load() {
  loading.value = true
  try {
    rows.value = await firewallApi.listRules()
  } catch (e) {
    ElMessage.error(e?.message || '加载失败')
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
    if (editingId.value) await firewallApi.patchRule(editingId.value, form)
    else await firewallApi.createRule(form)
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
    await ElMessageBox.confirm(`删除规则 ${r.name}？`, '确认', { type: 'warning' })
  } catch {
    return
  }
  await firewallApi.deleteRule(r.id)
  ElMessage.success('已删除')
  await load()
}

async function genPreview() {
  loadingPreview.value = true
  try {
    const d = await firewallApi.previewRuleset()
    preview.value = d.ruleset || ''
    deployActive.value = 0
  } catch (e) {
    ElMessage.error('预览失败')
  } finally {
    loadingPreview.value = false
  }
}
async function applyPhase(phase, text) {
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
      await ElMessageBox.alert(
        `<pre style="white-space:pre-wrap;font-size:12px;max-height:420px;overflow:auto">${JSON.stringify(data, null, 2)}</pre>`,
        '失败',
        { dangerouslyUseHTMLString: true },
      )
    }
  } catch (e) {
    lastApply.value = e?.response?.data
  } finally {
    applying.value = false
  }
}

async function showSystem() {
  showResult.value = await firewallApi.showRuleset()
}

onMounted(() => {
  load()
  loadIfaces()
})
</script>

<template>
  <div class="page">
    <PageHeader
      title="防火墙规则"
      description="nftables inet 表 pemanager；下发分「预览 → 校验 nft -c → 应用 nft -f」三步"
      :icon="Lock"
    />
    <el-tabs v-model="activeTab" type="border-card">
      <el-tab-pane label="① 规则管理" name="rules">
        <div class="row">
          <el-button type="primary" @click="openCreate">新增规则</el-button>
          <el-button :loading="loading" @click="load">刷新</el-button>
        </div>
        <el-table :data="rows" border size="small" v-loading="loading" style="margin-top: 8px">
          <el-table-column prop="enabled" label="启用" width="64">
            <template #default="{ row }">
              <el-tag :type="row.enabled ? 'success' : 'info'" size="small">{{ row.enabled ? 'Y' : 'N' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="name" label="名称" min-width="140" />
          <el-table-column prop="chain" label="chain" width="100" />
          <el-table-column prop="action" label="action" width="100" />
          <el-table-column prop="protocol" label="proto" width="80" />
          <el-table-column prop="family" label="family" width="80" />
          <el-table-column prop="src_cidr" label="src" />
          <el-table-column prop="dst_cidr" label="dst" />
          <el-table-column label="port" width="140">
            <template #default="{ row }">
              <span>{{ row.src_port || '*' }} → {{ row.dst_port || '*' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="iif/oif" width="160">
            <template #default="{ row }">{{ row.in_interface || '*' }} / {{ row.out_interface || '*' }}</template>
          </el-table-column>
          <el-table-column prop="priority" label="prio" width="70" />
          <el-table-column label="操作" width="150" fixed="right">
            <template #default="{ row }">
              <el-button link size="small" @click="openEdit(row)">编辑</el-button>
              <el-button link type="danger" size="small" @click="remove(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="② 下发与校验" name="deploy">
        <el-steps :active="deployActive" align-center finish-status="success" style="margin-bottom: 12px">
          <el-step title="预览" />
          <el-step title="校验 nft -c" />
          <el-step title="应用 nft -f" />
        </el-steps>
        <div class="row">
          <el-button :loading="loadingPreview" @click="genPreview">生成预览</el-button>
          <el-button type="warning" :loading="applying" @click="applyPhase('validate', '执行 nft -c 校验渲染后的规则集，是否继续？')">校验</el-button>
          <el-button type="success" :loading="applying" @click="applyPhase('apply', '执行 nft -f 应用渲染后的规则集（会先 flush 三条链），是否继续？')">应用</el-button>
          <el-button type="danger" plain :loading="applying" @click="applyPhase('flush', '清空 pemanager 表的 input/output/forward，是否继续？')">flush</el-button>
        </div>
        <el-input
          v-model="preview"
          type="textarea"
          :rows="20"
          readonly
          placeholder="点击「生成预览」加载 nftables 规则集"
          class="mono"
          style="margin-top: 8px"
        />
        <el-collapse v-if="lastApply" style="margin-top: 8px">
          <el-collapse-item title="最近下发结果" name="1"><JsonBlock :data="lastApply" :rows="22" /></el-collapse-item>
        </el-collapse>
      </el-tab-pane>

      <el-tab-pane label="③ 现网规则" name="show">
        <div class="row">
          <el-button @click="showSystem">读取 nft list table inet pemanager</el-button>
        </div>
        <pre v-if="showResult" class="mono blk">{{ showResult.stdout || showResult.stderr }}</pre>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="dlg" :title="title" width="640px" destroy-on-close>
      <el-form label-width="110px">
        <el-form-item label="名称" required><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="启用"><el-switch v-model="form.enabled" /></el-form-item>
        <el-form-item label="chain">
          <el-select v-model="form.chain" style="width:100%">
            <el-option label="INPUT" value="input" />
            <el-option label="OUTPUT" value="output" />
            <el-option label="FORWARD" value="forward" />
          </el-select>
        </el-form-item>
        <el-form-item label="action">
          <el-select v-model="form.action" style="width:100%">
            <el-option label="ACCEPT" value="accept" />
            <el-option label="DROP" value="drop" />
            <el-option label="REJECT" value="reject" />
            <el-option label="LOG + accept" value="log" />
          </el-select>
        </el-form-item>
        <el-form-item label="family">
          <el-select v-model="form.family" style="width:100%">
            <el-option label="IPv4" value="ipv4" />
            <el-option label="IPv6" value="ipv6" />
            <el-option label="IPv4 + IPv6" value="both" />
          </el-select>
        </el-form-item>
        <el-form-item label="protocol">
          <el-select v-model="form.protocol" style="width:100%">
            <el-option label="ANY" value="any" />
            <el-option label="TCP" value="tcp" />
            <el-option label="UDP" value="udp" />
            <el-option label="ICMP" value="icmp" />
          </el-select>
        </el-form-item>
        <el-form-item label="src CIDR"><el-input v-model="form.src_cidr" placeholder="如 10.0.0.0/24" /></el-form-item>
        <el-form-item label="dst CIDR"><el-input v-model="form.dst_cidr" /></el-form-item>
        <el-form-item label="sport"><el-input v-model="form.src_port" placeholder="22 或 1000-2000" :disabled="!['tcp','udp'].includes(form.protocol)" /></el-form-item>
        <el-form-item label="dport"><el-input v-model="form.dst_port" :disabled="!['tcp','udp'].includes(form.protocol)" /></el-form-item>
        <el-form-item label="in iif">
          <el-select v-model="form.in_interface" filterable allow-create clearable style="width:100%">
            <el-option v-for="i in ifaces" :key="i.ifname" :label="i.ifname" :value="i.ifname" />
          </el-select>
        </el-form-item>
        <el-form-item label="out oif">
          <el-select v-model="form.out_interface" filterable allow-create clearable style="width:100%">
            <el-option v-for="i in ifaces" :key="i.ifname" :label="i.ifname" :value="i.ifname" />
          </el-select>
        </el-form-item>
        <el-form-item label="priority"><el-input-number v-model="form.priority" /></el-form-item>
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
.row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.mono :deep(textarea) { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 12px; }
.blk { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 12px; background: var(--el-fill-color-light); padding: 10px; border-radius: 4px; overflow:auto; max-height: 360px; }
</style>
