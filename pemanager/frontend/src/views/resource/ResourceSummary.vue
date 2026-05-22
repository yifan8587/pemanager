<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Coin, User, DataAnalysis, Refresh } from '@element-plus/icons-vue'
import { resourceApi } from '../../api/resourceApi'
import PageHeader from '../../components/PageHeader.vue'

const router = useRouter()
const loading = ref(false)
const data = ref(null)

async function load() {
  loading.value = true
  try {
    const { data: d } = await resourceApi.summary()
    data.value = d
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

const customers = computed(() => data.value?.customers || { total: 0, active: 0, inactive: 0, recent: [] })
const ipBlock = computed(() => data.value?.ip || { total: 0, by_state: {}, by_customer: [], by_subnet: [] })
const bandwidth = computed(
  () => data.value?.bandwidth || { pools: [], total_mbps: 0, allocated_mbps: 0, remaining_mbps: 0, usage_pct: 0, allocations_total: 0, by_customer: [] },
)
const ipStates = computed(() => ipBlock.value.by_state || {})

const STATE_META = {
  available: { label: '可用', type: 'success' },
  allocated: { label: '已分配', type: 'primary' },
  reserved: { label: '预留', type: 'warning' },
  recycled: { label: '回收 (不可分配)', type: 'info' },
}

function go(path) {
  router.push(path)
}

onMounted(load)
</script>

<template>
  <div class="page">
    <PageHeader title="资源概览" description="PE 系统的客户、IP、带宽资源全景" :icon="Coin">
      <template #actions>
        <el-button :loading="loading" :icon="Refresh" @click="load">刷新</el-button>
      </template>
    </PageHeader>

    <el-skeleton v-if="loading && !data" :rows="6" animated />
    <template v-else-if="data">
      <!-- 上：KPI 三大维度 -->
      <el-row :gutter="16" class="kpi-row">
        <el-col :xs="24" :md="8">
          <el-card shadow="hover" class="kpi" @click="go('/resourcemanage/customers')">
            <div class="kpi-head">
              <el-icon class="kpi-icon kpi-customer"><User /></el-icon>
              <span class="kpi-title">客户</span>
            </div>
            <div class="kpi-main">{{ customers.total }}</div>
            <div class="kpi-sub">
              <el-tag size="small" type="success" effect="plain">启用 {{ customers.active }}</el-tag>
              <el-tag v-if="customers.inactive" size="small" type="info" effect="plain" style="margin-left: 6px">
                停用 {{ customers.inactive }}
              </el-tag>
            </div>
          </el-card>
        </el-col>
        <el-col :xs="24" :md="8">
          <el-card shadow="hover" class="kpi" @click="go('/resourcemanage/ip-addresses')">
            <div class="kpi-head">
              <el-icon class="kpi-icon kpi-ip"><Coin /></el-icon>
              <span class="kpi-title">IP 地址</span>
            </div>
            <div class="kpi-main">{{ ipBlock.total }}</div>
            <div class="kpi-sub">
              <el-tag
                v-for="(meta, key) in STATE_META"
                :key="key"
                size="small"
                :type="meta.type"
                effect="plain"
                style="margin-right: 6px"
              >
                {{ meta.label }} {{ ipStates[key] || 0 }}
              </el-tag>
            </div>
          </el-card>
        </el-col>
        <el-col :xs="24" :md="8">
          <el-card shadow="hover" class="kpi" @click="go('/resourcemanage/bandwidth')">
            <div class="kpi-head">
              <el-icon class="kpi-icon kpi-bw"><DataAnalysis /></el-icon>
              <span class="kpi-title">带宽（Mbps）</span>
            </div>
            <div class="kpi-main">{{ bandwidth.total_mbps }}</div>
            <div class="kpi-sub">
              <span class="muted">已分配</span>
              <strong style="color: var(--pe-primary)">{{ bandwidth.allocated_mbps }}</strong>
              <span class="muted" style="margin-left: 12px">剩余</span>
              <strong style="color: var(--pe-success, #67c23a)">{{ bandwidth.remaining_mbps }}</strong>
              <el-tag size="small" effect="plain" style="margin-left: 8px">
                用量 {{ bandwidth.usage_pct }}%
              </el-tag>
            </div>
            <el-progress
              :percentage="Number(bandwidth.usage_pct) || 0"
              :stroke-width="6"
              :show-text="false"
              :color="bandwidth.usage_pct > 85 ? '#f56c6c' : (bandwidth.usage_pct > 60 ? '#e6a23c' : '#409eff')"
              style="margin-top: 8px"
            />
          </el-card>
        </el-col>
      </el-row>

      <!-- 下：三块明细，纵向排列 -->
      <!-- 客户明细 -->
      <el-card shadow="never" class="detail">
        <template #header>
          <div class="card-head">
            <span><el-icon><User /></el-icon> 客户明细 · 近期变更 / 资源占用 Top {{ customers.recent.length }}</span>
            <el-button link type="primary" @click="go('/resourcemanage/customers')">查看全部</el-button>
          </div>
        </template>
        <el-table :data="customers.recent" border size="small" empty-text="暂无客户">
          <el-table-column prop="code" label="客户编码" width="160" />
          <el-table-column prop="name" label="客户名称" min-width="160" />
          <el-table-column label="启用" width="80">
            <template #default="{ row }">
              <el-tag size="small" :type="row.is_active ? 'success' : 'info'">
                {{ row.is_active ? '是' : '否' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="IP 数" width="100" align="right">
            <template #default="{ row }"><strong>{{ row.ip_count }}</strong></template>
          </el-table-column>
          <el-table-column label="带宽 (Mbps)" width="130" align="right">
            <template #default="{ row }"><strong>{{ row.bw_mbps }}</strong></template>
          </el-table-column>
          <el-table-column label="更新时间" width="180">
            <template #default="{ row }">
              <span class="mono">{{ (row.updated_at || '').replace('T', ' ').substring(0, 19) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <!-- IP 明细 -->
      <el-card shadow="never" class="detail">
        <template #header>
          <div class="card-head">
            <span><el-icon><Coin /></el-icon> IP 明细</span>
            <el-button link type="primary" @click="go('/resourcemanage/ip-addresses')">查看全部</el-button>
          </div>
        </template>
        <el-row :gutter="12">
          <el-col :xs="24" :md="8">
            <div class="sub-title">按状态分布</div>
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item v-for="(meta, key) in STATE_META" :key="key" :label="meta.label">
                <el-tag :type="meta.type" size="small" effect="plain">{{ ipStates[key] || 0 }}</el-tag>
                <el-progress
                  v-if="ipBlock.total"
                  :percentage="Math.round(((ipStates[key] || 0) * 100) / ipBlock.total)"
                  :stroke-width="6"
                  :show-text="false"
                  style="margin-top: 4px"
                />
              </el-descriptions-item>
            </el-descriptions>
          </el-col>
          <el-col :xs="24" :md="8">
            <div class="sub-title">按客户 Top 10</div>
            <el-table :data="ipBlock.by_customer.slice(0, 10)" size="small" border empty-text="无客户绑定">
              <el-table-column prop="customer_name" label="客户" min-width="120" show-overflow-tooltip />
              <el-table-column prop="customer_code" label="编码" width="100" />
              <el-table-column prop="count" label="IP 数" width="80" align="right" />
            </el-table>
          </el-col>
          <el-col :xs="24" :md="8">
            <div class="sub-title">按网段标签 Top 10</div>
            <el-table :data="ipBlock.by_subnet.slice(0, 10)" size="small" border empty-text="未配置网段标签">
              <el-table-column prop="subnet_label" label="网段标签" />
              <el-table-column prop="count" label="IP 数" width="80" align="right" />
            </el-table>
          </el-col>
        </el-row>
      </el-card>

      <!-- 带宽明细 -->
      <el-card shadow="never" class="detail">
        <template #header>
          <div class="card-head">
            <span><el-icon><DataAnalysis /></el-icon> 带宽明细 · 共 {{ bandwidth.pools.length }} 个池 / {{ bandwidth.allocations_total }} 条分配</span>
            <el-button link type="primary" @click="go('/resourcemanage/bandwidth')">查看全部</el-button>
          </div>
        </template>
        <el-row :gutter="12">
          <el-col :xs="24" :md="14">
            <div class="sub-title">带宽池占用</div>
            <el-table :data="bandwidth.pools" size="small" border empty-text="尚未创建带宽池">
              <el-table-column prop="name" label="池名称" min-width="120" />
              <el-table-column label="总量 (Mbps)" width="120" align="right">
                <template #default="{ row }"><strong>{{ row.total_mbps }}</strong></template>
              </el-table-column>
              <el-table-column label="已分配" width="120" align="right">
                <template #default="{ row }">
                  <span style="color: var(--pe-primary)">{{ row.allocated_mbps }}</span>
                </template>
              </el-table-column>
              <el-table-column label="剩余" width="120" align="right">
                <template #default="{ row }">
                  <span :class="{ low: row.remaining_mbps === 0 }">{{ row.remaining_mbps }}</span>
                </template>
              </el-table-column>
              <el-table-column label="用量" min-width="180">
                <template #default="{ row }">
                  <el-progress
                    :percentage="Number(row.usage_pct) || 0"
                    :stroke-width="10"
                    :color="row.usage_pct > 85 ? '#f56c6c' : (row.usage_pct > 60 ? '#e6a23c' : '#409eff')"
                  />
                </template>
              </el-table-column>
            </el-table>
          </el-col>
          <el-col :xs="24" :md="10">
            <div class="sub-title">按客户 Top 10</div>
            <el-table :data="bandwidth.by_customer.slice(0, 10)" size="small" border empty-text="无客户绑定">
              <el-table-column prop="customer_name" label="客户" min-width="120" show-overflow-tooltip />
              <el-table-column prop="customer_code" label="编码" width="100" />
              <el-table-column prop="mbps" label="Mbps" width="90" align="right" />
              <el-table-column prop="allocations" label="分配数" width="80" align="right" />
            </el-table>
          </el-col>
        </el-row>
      </el-card>
    </template>
  </div>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.kpi-row { margin: 0; }
.kpi {
  cursor: pointer;
  transition: transform 0.12s;
}
.kpi:hover { transform: translateY(-2px); }
.kpi-head {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--pe-text-mute);
  font-size: 13px;
  margin-bottom: 4px;
}
.kpi-icon { font-size: 16px; }
.kpi-customer { color: #409eff; }
.kpi-ip { color: #67c23a; }
.kpi-bw { color: #e6a23c; }
.kpi-title { font-weight: 600; letter-spacing: 0.3px; }
.kpi-main {
  font-size: 32px;
  font-weight: 700;
  line-height: 1.1;
  color: var(--pe-text);
  margin: 4px 0 4px;
}
.kpi-sub { font-size: 12px; color: var(--pe-text-mute); }
.detail :deep(.el-card__body) { padding: 14px; }
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
}
.card-head .el-icon { margin-right: 4px; vertical-align: -2px; }
.sub-title {
  font-size: 12px;
  color: var(--pe-text-mute);
  margin-bottom: 6px;
  font-weight: 600;
  letter-spacing: 0.3px;
}
.muted { color: var(--pe-text-mute); margin-right: 4px; font-size: 12px; }
.mono { font-family: var(--pe-mono); font-size: 12px; }
.low { color: #f56c6c; font-weight: 600; }
</style>
