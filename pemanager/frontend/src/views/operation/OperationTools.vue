<script setup>
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Aim } from '@element-plus/icons-vue'
import { operationApi } from '../../api/operationApi'
import { interfaceApi } from '../../api/interfaceApi'
import EChart from '../../components/EChart.vue'
import PageHeader from '../../components/PageHeader.vue'

const tab = ref('ping')
const ifaces = ref([])

async function loadIfaces() {
  try {
    const { data } = await interfaceApi.liveInventory()
    ifaces.value = data.interfaces || []
  } catch {
    ifaces.value = []
  }
}

// ----- ping
const pingForm = reactive({ address: '', count: 5, source: '' })
const pingResult = ref(null)
const pingLoading = ref(false)
async function doPing() {
  if (!pingForm.address) {
    ElMessage.warning('请输入地址')
    return
  }
  pingLoading.value = true
  try {
    pingResult.value = await operationApi.ping({ ...pingForm })
  } catch (e) {
    ElMessage.error(e?.message || '请求失败')
  } finally {
    pingLoading.value = false
  }
}

// ----- mtr
const mtrForm = reactive({ address: '', count: 5, source: '' })
const mtrResult = ref(null)
const mtrLoading = ref(false)
async function doMtr() {
  if (!mtrForm.address) {
    ElMessage.warning('请输入地址')
    return
  }
  mtrLoading.value = true
  try {
    mtrResult.value = await operationApi.mtr({ ...mtrForm })
  } catch (e) {
    ElMessage.error(e?.message || '请求失败')
  } finally {
    mtrLoading.value = false
  }
}

// ----- traffic live (nload 替代)
const trafficForm = reactive({ interface: '', window_sec: 1 })
const trafficLive = ref(null)
const trafficSeries = ref([]) // [{ ts, rx_bps, tx_bps }]
const trafficRunning = ref(false)
let trafficTimer = null

async function trafficOnce() {
  try {
    trafficLive.value = await operationApi.trafficLive({ ...trafficForm })
    if (trafficLive.value?.ok) {
      const point = {
        ts: new Date().toISOString(),
        rx_mbps: (trafficLive.value.rx_bps || 0) / 1e6,
        tx_mbps: (trafficLive.value.tx_bps || 0) / 1e6,
      }
      trafficSeries.value.push(point)
      if (trafficSeries.value.length > 60) trafficSeries.value.shift()
    }
  } catch (e) {
    // ignore single error, will retry
  }
}

function startTraffic() {
  if (!trafficForm.interface) {
    ElMessage.warning('请选择接口')
    return
  }
  trafficRunning.value = true
  trafficSeries.value = []
  trafficOnce()
  trafficTimer = setInterval(trafficOnce, 2000)
}
function stopTraffic() {
  trafficRunning.value = false
  if (trafficTimer) {
    clearInterval(trafficTimer)
    trafficTimer = null
  }
}

const trafficOption = ref({})
function rebuildTrafficOption() {
  trafficOption.value = {
    grid: { left: 50, right: 16, top: 30, bottom: 30 },
    legend: { data: ['RX Mbps', 'TX Mbps'] },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'time' },
    yAxis: { type: 'value', name: 'Mbps' },
    series: [
      {
        name: 'RX Mbps',
        type: 'line',
        smooth: true,
        showSymbol: false,
        areaStyle: { opacity: 0.1 },
        data: trafficSeries.value.map((p) => [p.ts, p.rx_mbps]),
      },
      {
        name: 'TX Mbps',
        type: 'line',
        smooth: true,
        showSymbol: false,
        areaStyle: { opacity: 0.1 },
        data: trafficSeries.value.map((p) => [p.ts, p.tx_mbps]),
      },
    ],
  }
}
import { watch } from 'vue'
watch(trafficSeries, rebuildTrafficOption, { deep: true })
rebuildTrafficOption()

onUnmounted(() => stopTraffic())
onMounted(loadIfaces)
</script>

<template>
  <div class="page">
    <PageHeader
      title="诊断工具"
      description="即席 ping / mtr / 接口实时流量；基于 /proc/net/dev 增量（nload 的浏览器化替代）"
      :icon="Aim"
    />
    <el-tabs v-model="tab" type="border-card">
      <el-tab-pane label="Ping" name="ping">
        <div class="row">
          <el-input v-model="pingForm.address" placeholder="目标 IP/主机名" style="width: 260px" />
          <el-input-number v-model="pingForm.count" :min="1" :max="64" />
          <el-select v-model="pingForm.source" placeholder="源接口（可选）" clearable filterable style="width: 200px">
            <el-option v-for="i in ifaces" :key="i.ifname" :label="i.ifname" :value="i.ifname" />
          </el-select>
          <el-button type="primary" :loading="pingLoading" @click="doPing">Ping</el-button>
        </div>
        <el-descriptions v-if="pingResult" :column="3" border size="small" style="margin-top: 10px">
          <el-descriptions-item label="发送 / 接收">{{ pingResult.packets_sent }}/{{ pingResult.packets_recv }}</el-descriptions-item>
          <el-descriptions-item label="丢包率(%)">{{ pingResult.loss_pct }}</el-descriptions-item>
          <el-descriptions-item label="RTT min/avg/max(ms)">
            {{ pingResult.rtt_min_ms ?? '—' }} / {{ pingResult.rtt_avg_ms ?? '—' }} / {{ pingResult.rtt_max_ms ?? '—' }}
          </el-descriptions-item>
        </el-descriptions>
        <pre v-if="pingResult?.stdout" class="raw">{{ pingResult.stdout }}</pre>
      </el-tab-pane>

      <el-tab-pane label="MTR" name="mtr">
        <div class="row">
          <el-input v-model="mtrForm.address" placeholder="目标 IP/主机名" style="width: 260px" />
          <el-input-number v-model="mtrForm.count" :min="1" :max="30" />
          <el-select v-model="mtrForm.source" placeholder="源接口（可选）" clearable filterable style="width: 200px">
            <el-option v-for="i in ifaces" :key="i.ifname" :label="i.ifname" :value="i.ifname" />
          </el-select>
          <el-button type="primary" :loading="mtrLoading" @click="doMtr">MTR</el-button>
        </div>
        <el-table v-if="mtrResult?.hops?.length" :data="mtrResult.hops" border size="small" style="margin-top: 10px">
          <el-table-column prop="count" label="#" width="50" />
          <el-table-column prop="host" label="hop" min-width="180" />
          <el-table-column prop="loss_pct" label="loss%" width="80" />
          <el-table-column prop="snt" label="snt" width="60" />
          <el-table-column prop="last_ms" label="last" width="80" />
          <el-table-column prop="avg_ms" label="avg" width="80" />
          <el-table-column prop="best_ms" label="best" width="80" />
          <el-table-column prop="worst_ms" label="worst" width="80" />
          <el-table-column prop="stdev_ms" label="stdev" width="80" />
        </el-table>
        <pre v-else-if="mtrResult?.raw" class="raw">{{ mtrResult.raw }}</pre>
      </el-tab-pane>

      <el-tab-pane label="接口流量 (实时)" name="traffic">
        <div class="row">
          <el-select v-model="trafficForm.interface" filterable placeholder="选择接口" style="width: 220px">
            <el-option v-for="i in ifaces" :key="i.ifname" :label="`${i.ifname} (${i.kind})`" :value="i.ifname" />
          </el-select>
          <el-input-number v-model="trafficForm.window_sec" :min="0.5" :max="5" :step="0.5" />
          <el-button v-if="!trafficRunning" type="primary" @click="startTraffic">开始</el-button>
          <el-button v-else type="danger" @click="stopTraffic">停止</el-button>
        </div>
        <el-descriptions v-if="trafficLive?.ok" :column="3" border size="small" style="margin-top: 10px">
          <el-descriptions-item label="窗口(s)">{{ trafficLive.window_sec?.toFixed?.(2) }}</el-descriptions-item>
          <el-descriptions-item label="RX Mbps">{{ (trafficLive.rx_bps / 1e6).toFixed(3) }}</el-descriptions-item>
          <el-descriptions-item label="TX Mbps">{{ (trafficLive.tx_bps / 1e6).toFixed(3) }}</el-descriptions-item>
          <el-descriptions-item label="RX 累计字节">{{ trafficLive.rx_bytes_total }}</el-descriptions-item>
          <el-descriptions-item label="TX 累计字节">{{ trafficLive.tx_bytes_total }}</el-descriptions-item>
          <el-descriptions-item label="RX/TX 累计包">{{ trafficLive.rx_packets_total }} / {{ trafficLive.tx_packets_total }}</el-descriptions-item>
        </el-descriptions>
        <EChart :option="trafficOption" :height="320" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.page { display: flex; flex-direction: column; gap: 12px; }
.row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.raw { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 12px; background: var(--el-fill-color-light); padding: 10px; border-radius: 4px; overflow:auto; max-height: 360px; }
</style>
