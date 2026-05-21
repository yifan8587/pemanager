<script setup>
defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' },
  icon: { type: Object, default: null },
})
</script>

<template>
  <div class="ph">
    <div class="ph-left">
      <el-icon v-if="icon" class="ph-icon"><component :is="icon" /></el-icon>
      <div>
        <div class="ph-title">{{ title }}</div>
        <div v-if="description" class="ph-desc">{{ description }}</div>
      </div>
    </div>
    <div class="ph-right">
      <slot name="actions" />
    </div>
  </div>
</template>

<style scoped>
.ph {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--pe-card);
  border: 1px solid var(--pe-border-soft);
  border-radius: var(--pe-radius);
  padding: 12px 16px;
  margin-bottom: 12px;
  box-shadow: var(--pe-shadow-sm);
}
.ph-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.ph-icon {
  font-size: 22px;
  color: var(--pe-primary);
  background: var(--pe-primary-soft);
  border-radius: 8px;
  padding: 8px;
}
.ph-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--pe-text);
}
.ph-desc {
  font-size: 12px;
  color: var(--pe-text-mute);
  margin-top: 2px;
}
.ph-right {
  display: flex;
  gap: 8px;
  align-items: center;
}
</style>
