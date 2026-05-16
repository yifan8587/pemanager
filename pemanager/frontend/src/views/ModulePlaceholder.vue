<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { http } from '../api/client'

const route = useRoute()
const title = computed(() => route.meta.title || route.name)
const apiPrefix = computed(() => route.meta.apiPrefix || '')
const loading = ref(false)
const error = ref('')
const payload = ref(null)

onMounted(async () => {
  loading.value = true
  error.value = ''
  try {
    const { data } = await http.get(`${apiPrefix.value}health/`)
    payload.value = data
  } catch (e) {
    error.value = e?.message || '请求失败'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <span>{{ title }}</span>
    </template>
    <el-skeleton v-if="loading" :rows="4" animated />
    <el-alert v-else-if="error" :title="error" type="error" show-icon />
    <el-descriptions v-else-if="payload" title="后端健康检查" :column="1" border>
      <el-descriptions-item label="应用">{{ payload.app }}</el-descriptions-item>
      <el-descriptions-item label="状态">{{ payload.status }}</el-descriptions-item>
      <el-descriptions-item label="接口">{{ apiPrefix }}health/</el-descriptions-item>
    </el-descriptions>
  </el-card>
</template>
