<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { interfaceApi } from '../../api/interfaceApi'
import JsonBlock from '../../components/JsonBlock.vue'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const row = ref(null)

async function load() {
  const ifname = route.params.ifname
  if (!ifname) return
  loading.value = true
  try {
    const { data } = await interfaceApi.liveDetail(ifname)
    row.value = data
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '加载失败')
    row.value = null
  } finally {
    loading.value = false
  }
}

watch(
  () => route.params.ifname,
  () => load(),
)

onMounted(load)
</script>

<template>
  <div class="page" v-loading="loading">
    <div class="head">
      <el-button @click="router.push({ name: 'iface-live' })">返回列表</el-button>
      <el-text tag="b" size="large">{{ route.params.ifname }}</el-text>
      <el-button :loading="loading" @click="load">刷新</el-button>
    </div>
    <JsonBlock v-if="row" :data="row" :rows="28" />
    <el-empty v-else description="无数据" />
  </div>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.head {
  display: flex;
  align-items: center;
  gap: 12px;
}
</style>
