<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Connection } from '@element-plus/icons-vue'
import { interfaceApi } from '../../api/interfaceApi'
import PageHeader from '../../components/PageHeader.vue'

const router = useRouter()
const loading = ref(false)
const data = ref(null)

const filters = reactive({
  kind: '',
  q: '',
  admin_up: '',
})

async function load() {
  loading.value = true
  try {
    const params = {}
    if (filters.kind) params.kind = filters.kind
    if (filters.q) params.q = filters.q
    if (filters.admin_up !== '' && filters.admin_up != null) {
      params.admin_up = filters.admin_up
    }
    const { data: d } = await interfaceApi.liveInventory(params)
    data.value = d
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function openDetail(row) {
  router.push({
    name: 'iface-live-detail',
    params: { ifname: row.ifname },
  })
}

onMounted(load)
</script>

<template>
  <div class="page">
    <PageHeader
      title="实时接口"
      description="kernel + netplan + WireGuard 合并视图；双击行查看详情"
      :icon="Connection"
    >
      <template #actions>
        <el-input v-model="filters.q" placeholder="接口名关键字" clearable style="width: 180px" size="small" />
        <el-select v-model="filters.kind" placeholder="类型" clearable style="width: 130px" size="small">
          <el-option label="ether" value="ether" />
          <el-option label="loopback" value="loopback" />
          <el-option label="gre" value="gre" />
          <el-option label="vxlan" value="vxlan" />
          <el-option label="wireguard" value="wireguard" />
          <el-option label="bridge" value="bridge" />
          <el-option label="bond" value="bond" />
          <el-option label="vlan" value="vlan" />
        </el-select>
        <el-select v-model="filters.admin_up" placeholder="admin_up" clearable style="width: 110px" size="small">
          <el-option label="UP" value="true" />
          <el-option label="DOWN" value="false" />
        </el-select>
        <el-button type="primary" size="small" :loading="loading" @click="load">查询</el-button>
      </template>
    </PageHeader>

    <el-row :gutter="16" class="summary" v-if="data">
      <el-col :span="24">
        <el-card shadow="never">
          <template #header>类型分布</template>
          <el-space wrap>
            <el-tag v-for="(n, k) in data.summary || {}" :key="k" type="info">
              {{ k }}: {{ n }}
            </el-tag>
          </el-space>
        </el-card>
      </el-col>
    </el-row>

    <el-table
      :data="data?.interfaces || []"
      v-loading="loading"
      border
      size="small"
      @row-dblclick="openDetail"
    >
      <el-table-column prop="ifname" label="接口" width="160" fixed>
        <template #default="{ row }">
          <el-button link type="primary" @click="openDetail(row)">{{ row.ifname }}</el-button>
        </template>
      </el-table-column>
      <el-table-column prop="kind" label="类型" width="120" />
      <el-table-column prop="admin_up" label="UP" width="80">
        <template #default="{ row }">
          <el-tag size="small" :type="row.admin_up ? 'success' : 'info'">
            {{ row.admin_up ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="operstate" label="运行" width="100" />
      <el-table-column prop="mtu" label="MTU" width="80" />
      <el-table-column prop="netplan_kind" label="Netplan段" width="110" />
      <el-table-column prop="netplan_tunnel_mode" label="隧道模式" width="120" show-overflow-tooltip />
      <el-table-column label="地址数" width="80">
        <template #default="{ row }">
          {{ (row.addresses || []).length }}
        </template>
      </el-table-column>
    </el-table>
    <el-text v-if="data?.sources" size="small" type="info">
      源状态：kernel_link_ok={{ data.sources.kernel_link_ok }}，wireguard_ok={{ data.sources.wireguard_ok }}
    </el-text>
  </div>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.summary {
  margin-bottom: 0;
}
</style>
