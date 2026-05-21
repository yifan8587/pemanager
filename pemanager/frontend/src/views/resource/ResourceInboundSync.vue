<script setup>
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Switch } from '@element-plus/icons-vue'
import { resourceApi } from '../../api/resourceApi'
import JsonBlock from '../../components/JsonBlock.vue'
import PageHeader from '../../components/PageHeader.vue'

const submitting = ref(false)
const result = ref(null)

const form = reactive({
  source_app: 'external',
  actor: 'ui',
  json: JSON.stringify(
    {
      ip_updates: [],
      bandwidth_updates: [],
      bandwidth_removals: [],
    },
    null,
    2,
  ),
})

async function submit() {
  let payload
  try {
    payload = JSON.parse(form.json)
  } catch {
    ElMessage.error('JSON 格式无效')
    return
  }
  submitting.value = true
  result.value = null
  try {
    const { data } = await resourceApi.inboundSync({
      source_app: form.source_app,
      actor: form.actor,
      ip_updates: payload.ip_updates || [],
      bandwidth_updates: payload.bandwidth_updates || [],
      bandwidth_removals: payload.bandwidth_removals || [],
    })
    result.value = data
    ElMessage.success('已提交同步')
  } catch (e) {
    const d = e?.response?.data
    ElMessage.error(d ? JSON.stringify(d) : e.message || '提交失败')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="page">
    <PageHeader
      title="资源回写"
      description="将外部应用 IP / 带宽变更回写到 resourcemanage（POST /sync/inbound/）"
      :icon="Switch"
    />
    <el-form label-width="100px" class="form">
      <el-form-item label="来源应用">
        <el-input v-model="form.source_app" placeholder="例如 interfacemanage" />
      </el-form-item>
      <el-form-item label="操作者">
        <el-input v-model="form.actor" />
      </el-form-item>
      <el-form-item label="载荷 JSON">
        <el-input v-model="form.json" type="textarea" :rows="16" class="mono" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="submitting" @click="submit">提交同步</el-button>
      </el-form-item>
    </el-form>
    <el-card v-if="result" shadow="never">
      <template #header>响应</template>
      <JsonBlock :data="result" />
    </el-card>
  </div>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 960px;
}
.hint {
  margin-bottom: 8px;
}
.mono :deep(textarea) {
  font-family: ui-monospace, monospace;
  font-size: 12px;
}
</style>
