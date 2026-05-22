<script setup>
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  option: { type: Object, required: true },
  height: { type: [String, Number], default: 320 },
  loading: { type: Boolean, default: false },
})

const el = ref(null)
const chart = shallowRef(null)

function resize() {
  chart.value?.resize()
}

onMounted(() => {
  chart.value = echarts.init(el.value)
  chart.value.setOption(props.option || {}, true)
  window.addEventListener('resize', resize)
  if (props.loading) chart.value.showLoading()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  chart.value?.dispose()
  chart.value = null
})

watch(
  () => props.option,
  (val) => {
    if (chart.value) chart.value.setOption(val || {}, true)
  },
  { deep: true },
)

watch(
  () => props.loading,
  (v) => {
    if (!chart.value) return
    if (v) chart.value.showLoading()
    else chart.value.hideLoading()
  },
)
</script>

<template>
  <div ref="el" class="echart" :style="{ height: typeof height === 'number' ? `${height}px` : height }" />
</template>

<style scoped>
.echart {
  width: 100%;
}
</style>
