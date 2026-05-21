<script setup>
import { computed } from 'vue'

const props = defineProps({
  data: { type: null, required: true },
  rows: { type: Number, default: 18 },
})

const text = computed(() => {
  try {
    return JSON.stringify(props.data, null, 2)
  } catch {
    return String(props.data)
  }
})
</script>

<template>
  <el-input type="textarea" :rows="rows" readonly :model-value="text" class="json-block" />
</template>

<style scoped>
.json-block :deep(textarea) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono',
    'Courier New', monospace;
  font-size: 12px;
}
</style>
