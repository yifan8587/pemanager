<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Document,
  RefreshRight,
  Download,
  Filter,
  Warning,
} from '@element-plus/icons-vue'
import { logApi } from '../../api/logApi'
import JsonBlock from '../../components/JsonBlock.vue'
import PageHeader from '../../components/PageHeader.vue'
import { formatDateTimeTz, formatRelative } from '../../utils/format'

// ---------------- 过滤条件 ----------------
const filters = reactive({
  app: '',
  category: '',
  level: '',
  actor: '',
  method: '',
  target: '',
  search: '',
  since: '',
  until: '',
  pageSize: 100,
})

const meta = ref({ apps: [], categories: [], actors: [], levels: ['debug', 'info', 'warning', 'error'] })
const stats = ref({
  total_all: 0,
  total_window: 0,
  by_level_window: { debug: 0, info: 0, warning: 0, error: 0 },
  top_apps_window: {},
  window_hours: 24,
})
const logs = ref([])
const loading = ref(false)
const total = ref(0)

const detailDrawer = ref(false)
const detailRow = ref(null)

async function loadMeta() {
  try {
    meta.value = await logApi.logMeta()
  } catch {
    /* ignore */
  }
}

async function loadStats() {
  try {
    stats.value = await logApi.logStats({ hours: 24 })
  } catch {
    /* ignore */
  }
}

function _params() {
  const p = {}
  for (const k of ['app', 'category', 'level', 'actor', 'method', 'target', 'search', 'since', 'until']) {
    const v = filters[k]
    if (v) p[k] = v
  }
  p.page_size = filters.pageSize
  return p
}

async function loadLogs() {
  loading.value = true
  try {
    const r = await logApi.listAppLogs(_params())
    logs.value = r.list
    total.value = r.count
  } catch (e) {
    ElMessage.error('加载日志失败')
  } finally {
    loading.value = false
  }
}

async function refreshAll() {
  await Promise.all([loadStats(), loadLogs()])
}

function resetFilters() {
  Object.assign(filters, {
    app: '',
    category: '',
    level: '',
    actor: '',
    method: '',
    target: '',
    search: '',
    since: '',
    until: '',
    pageSize: 100,
  })
  refreshAll()
}

function openDetail(row) {
  detailRow.value = row
  detailDrawer.value = true
}

function exportCsv() {
  const url = logApi.exportCsvUrl({ ..._params(), limit: 50000 })
  const a = document.createElement('a')
  a.href = url
  a.target = '_blank'
  a.click()
}

const levelTag = (lv) => {
  switch (lv) {
    case 'error':
      return 'danger'
    case 'warning':
      return 'warning'
    case 'info':
      return 'success'
    case 'debug':
      return 'info'
    default:
      return ''
  }
}

const methodTag = (summary) => {
  const m = (summary || '').split(' ')[0]
  if (m === 'POST') return 'success'
  if (m === 'PUT' || m === 'PATCH') return 'warning'
  if (m === 'DELETE') return 'danger'
  return 'info'
}

const extractMethod = (summary) => (summary || '').split(' ')[0]
const extractStatus = (summary) => {
  const m = /->\s*(\d{3})/.exec(summary || '')
  return m ? Number(m[1]) : null
}

const topApps = computed(() =>
  Object.entries(stats.value?.top_apps_window || {}).map(([k, v]) => ({ app: k, count: v })),
)

onMounted(async () => {
  await Promise.all([loadMeta(), refreshAll()])
})
</script>

<template>
  <div class="page">
    <PageHeader
      title="操作日志中心"
      description="PE Manager 系统内所有模块操作（增/改/删/下发等）统一审计；时间一律按 UTC+8 显示"
      :icon="Document"
    >
      <template #actions>
        <el-button :icon="RefreshRight" @click="refreshAll">刷新</el-button>
        <el-button type="primary" :icon="Download" @click="exportCsv">导出 CSV</el-button>
      </template>
    </PageHeader>

    <!-- ============ KPI ============ -->
    <el-row :gutter="12">
      <el-col :span="6">
        <el-card shadow="never">
          <div class="kpi">
            <div class="kpi-label">日志总数（全部）</div>
            <div class="kpi-value">{{ stats.total_all }}</div>
            <div class="kpi-sub">最近 {{ stats.window_hours }}h: {{ stats.total_window }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never">
          <div class="kpi">
            <div class="kpi-label">近 24h 错误</div>
            <div class="kpi-value danger">{{ stats.by_level_window?.error ?? 0 }}</div>
            <div class="kpi-sub">warning: {{ stats.by_level_window?.warning ?? 0 }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never">
          <div class="kpi">
            <div class="kpi-label">近 24h info / debug</div>
            <div class="kpi-value">
              {{ stats.by_level_window?.info ?? 0 }} / {{ stats.by_level_window?.debug ?? 0 }}
            </div>
            <div class="kpi-sub">写操作多为 info</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never">
          <div class="kpi">
            <div class="kpi-label">近 24h 写操作 Top app</div>
            <div class="kpi-tags">
              <el-tag v-for="a in topApps" :key="a.app" size="small" type="info" style="margin-right:4px">
                {{ a.app }}({{ a.count }})
              </el-tag>
              <span v-if="!topApps.length" class="muted">暂无</span>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- ============ 过滤 ============ -->
    <el-card shadow="never">
      <template #header>
        <div class="row">
          <el-icon><Filter /></el-icon>
          <span>过滤</span>
          <div class="spacer" />
          <el-button text @click="resetFilters">重置</el-button>
        </div>
      </template>
      <div class="row">
        <el-select v-model="filters.app" placeholder="模块 (app)" clearable filterable style="width: 180px">
          <el-option v-for="a in meta.apps" :key="a" :label="a" :value="a" />
        </el-select>
        <el-select v-model="filters.category" placeholder="资源 (category)" clearable filterable allow-create style="width: 180px">
          <el-option v-for="c in meta.categories" :key="c" :label="c" :value="c" />
        </el-select>
        <el-select v-model="filters.level" placeholder="级别" clearable style="width: 120px">
          <el-option label="debug" value="debug" />
          <el-option label="info" value="info" />
          <el-option label="warning" value="warning" />
          <el-option label="error" value="error" />
        </el-select>
        <el-select v-model="filters.method" placeholder="HTTP 方法" clearable style="width: 130px">
          <el-option label="POST" value="POST" />
          <el-option label="PUT" value="PUT" />
          <el-option label="PATCH" value="PATCH" />
          <el-option label="DELETE" value="DELETE" />
        </el-select>
        <el-input v-model="filters.actor" placeholder="操作者 IP" clearable style="width: 160px" />
        <el-input v-model="filters.target" placeholder="目标 (target 包含)" clearable style="width: 200px" />
        <el-input v-model="filters.search" placeholder="全文搜索 summary/actor/target/category" clearable style="width: 280px" />
        <el-date-picker
          v-model="filters.since"
          type="datetime"
          placeholder="开始时间 (UTC+8)"
          value-format="YYYY-MM-DDTHH:mm:ss"
          style="width: 220px"
        />
        <el-date-picker
          v-model="filters.until"
          type="datetime"
          placeholder="结束时间 (UTC+8)"
          value-format="YYYY-MM-DDTHH:mm:ss"
          style="width: 220px"
        />
        <el-input-number v-model="filters.pageSize" :min="20" :max="500" :step="20" controls-position="right" />
        <el-button type="primary" :loading="loading" @click="loadLogs">查询</el-button>
      </div>
    </el-card>

    <!-- ============ 列表 ============ -->
    <el-card shadow="never">
      <template #header>
        <div class="row">
          <span>日志列表</span>
          <el-tag size="small" type="info">显示 {{ logs.length }} 条</el-tag>
          <el-alert
            v-if="!stats.total_all"
            :icon="Warning"
            type="info"
            :closable="false"
            title="还没有任何记录。当你点击下发、保存、删除等写操作后，审计中间件会自动落库。"
            style="flex:1"
          />
        </div>
      </template>
      <el-table :data="logs" border size="small" v-loading="loading" :max-height="640" stripe>
        <el-table-column label="时间 (UTC+8)" width="200">
          <template #default="{ row }">
            <div>{{ formatDateTimeTz(row.created_at) }}</div>
            <div class="muted small">{{ formatRelative(row.created_at) }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="app" label="模块" width="120">
          <template #default="{ row }">
            <el-tag size="small" type="info">{{ row.app }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="category" label="资源" width="130" show-overflow-tooltip />
        <el-table-column label="方法 / 状态" width="120">
          <template #default="{ row }">
            <el-tag :type="methodTag(row.summary)" size="small">{{ extractMethod(row.summary) }}</el-tag>
            <el-tag
              :type="(extractStatus(row.summary) || 0) >= 400 ? 'danger' : 'success'"
              size="small"
              style="margin-left:4px"
            >
              {{ extractStatus(row.summary) ?? '—' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="level" label="级别" width="80">
          <template #default="{ row }">
            <el-tag :type="levelTag(row.level)" size="small">{{ row.level }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="actor" label="操作者" width="140" show-overflow-tooltip />
        <el-table-column label="操作路径" min-width="320" show-overflow-tooltip>
          <template #default="{ row }">
            <code class="path">{{ (row.detail || {}).path || row.summary }}</code>
          </template>
        </el-table-column>
        <el-table-column prop="target" label="目标" width="180" show-overflow-tooltip />
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="{ row }">
            <el-button link size="small" @click="openDetail(row)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ============ 详情抽屉 ============ -->
    <el-drawer v-model="detailDrawer" title="日志详情" size="50%">
      <div v-if="detailRow" class="dt">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="时间 (UTC+8)">{{ formatDateTimeTz(detailRow.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="模块">{{ detailRow.app }}</el-descriptions-item>
          <el-descriptions-item label="资源">{{ detailRow.category }}</el-descriptions-item>
          <el-descriptions-item label="级别">
            <el-tag :type="levelTag(detailRow.level)" size="small">{{ detailRow.level }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="操作者">{{ detailRow.actor || '—' }}</el-descriptions-item>
          <el-descriptions-item label="摘要">{{ detailRow.summary }}</el-descriptions-item>
          <el-descriptions-item label="目标">{{ detailRow.target || '—' }}</el-descriptions-item>
          <el-descriptions-item label="关联 ID">{{ detailRow.correlation_id || '—' }}</el-descriptions-item>
        </el-descriptions>
        <h4 style="margin-top:12px">明细 JSON</h4>
        <JsonBlock :data="detailRow.detail || {}" :rows="20" />
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.page { display: flex; flex-direction: column; gap: 12px; }
.row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.spacer { flex: 1; }
.muted { color: var(--el-text-color-secondary); }
.small { font-size: 11px; }
.kpi { display: flex; flex-direction: column; gap: 4px; }
.kpi-label { color: var(--el-text-color-secondary); font-size: 12px; }
.kpi-value { font-size: 24px; font-weight: 600; }
.kpi-value.danger { color: var(--el-color-danger); }
.kpi-sub { color: var(--el-text-color-secondary); font-size: 12px; }
.kpi-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
.path { font-size: 12px; background: var(--el-fill-color-light); padding: 0 4px; border-radius: 3px; }
.dt h4 { margin-bottom: 6px; }
</style>
