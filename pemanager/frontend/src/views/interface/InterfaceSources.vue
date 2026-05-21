<script setup>
import { onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Reading } from '@element-plus/icons-vue'
import { interfaceApi } from '../../api/interfaceApi'
import JsonBlock from '../../components/JsonBlock.vue'
import PageHeader from '../../components/PageHeader.vue'

const tab = ref('netplan')
const loading = ref(false)
const netplan = ref(null)
const kernel = ref(null)
const wireguard = ref(null)

async function loadNetplan() {
  loading.value = true
  try {
    const { data } = await interfaceApi.netplanSource({ format: 'json' })
    netplan.value = data
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function loadKernel() {
  loading.value = true
  try {
    const { data } = await interfaceApi.kernelSource({ depth: 'full' })
    kernel.value = data
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function loadWg() {
  loading.value = true
  try {
    const { data } = await interfaceApi.wireguardSource({ reveal_secrets: '0' })
    wireguard.value = data
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function onTab(name) {
  if (name === 'netplan' && !netplan.value) await loadNetplan()
  if (name === 'kernel' && !kernel.value) await loadKernel()
  if (name === 'wireguard' && !wireguard.value) await loadWg()
}

watch(tab, onTab)
onMounted(() => onTab(tab.value))
</script>

<template>
  <div class="page" v-loading="loading">
    <PageHeader
      title="原始采集"
      description="Netplan / Kernel (ip -json) / WireGuard 原始数据源（只读）"
      :icon="Reading"
    />
    <el-tabs v-model="tab" type="border-card">
      <el-tab-pane label="Netplan" name="netplan">
        <div class="bar">
          <el-button type="primary" @click="loadNetplan">刷新</el-button>
        </div>
        <JsonBlock v-if="netplan" :data="netplan" :rows="26" />
        <el-empty v-else description="点击刷新加载" />
      </el-tab-pane>
      <el-tab-pane label="Kernel (ip -json)" name="kernel">
        <div class="bar">
          <el-button type="primary" @click="loadKernel">刷新</el-button>
        </div>
        <JsonBlock v-if="kernel" :data="kernel" :rows="26" />
        <el-empty v-else description="切换到本页或点击刷新" />
      </el-tab-pane>
      <el-tab-pane label="WireGuard" name="wireguard">
        <div class="bar">
          <el-button type="primary" @click="loadWg">刷新</el-button>
        </div>
        <JsonBlock v-if="wireguard" :data="wireguard" :rows="22" />
        <el-empty v-else description="切换到本页或点击刷新" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.page {
  min-height: 400px;
}
.bar {
  margin-bottom: 8px;
}
</style>
