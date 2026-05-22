<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  option: { type: Object, required: true },
  height: { type: [String, Number], default: 320 },
  loading: { type: Boolean, default: false },
})

const el = ref(null)
const chart = shallowRef(null)
let ro = null

function resize() {
  // 父容器宽度可能在 el-tabs / 折叠面板切换瞬间为 0，等下一帧再次尝试
  chart.value?.resize()
  nextTick(() => chart.value?.resize())
}

onMounted(() => {
  chart.value = echarts.init(el.value)
  chart.value.setOption(props.option || {}, true)
  window.addEventListener('resize', resize)
  // 对元素本身做 ResizeObserver，能解决 el-tabs 切换后宽度由 0 变正常导致图表不重排的问题
  if (typeof ResizeObserver !== 'undefined') {
    ro = new ResizeObserver(() => resize())
    ro.observe(el.value)
  }
  if (props.loading) chart.value.showLoading()
  // 首次挂载后再 resize 一次，覆盖初始时父容器宽度 = 0 的情况
  nextTick(resize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  ro?.disconnect()
  ro = null
  chart.value?.dispose()
  chart.value = null
})

watch(
  () => props.option,
  (val) => {
    if (!chart.value) return
    chart.value.setOption(val || {}, true)
    // setOption 之后也尝试一次 resize（用户切换时可能立刻有新数据）
    nextTick(resize)
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

watch(
  () => props.height,
  () => nextTick(resize),
)

defineExpose({ resize })
</script>

<template>
  <div
    ref="el"
    class="echart"
    :style="{ height: typeof height === 'number' ? `${height}px` : height, minWidth: '320px' }"
  />
</template>

<style scoped>
.echart {
  width: 100%;
  display: block;
}
</style>
