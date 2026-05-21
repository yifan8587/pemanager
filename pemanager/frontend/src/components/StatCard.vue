<script setup>
defineProps({
  label: { type: String, required: true },
  value: { type: [String, Number], default: '—' },
  unit: { type: String, default: '' },
  hint: { type: String, default: '' },
  tone: { type: String, default: 'primary' }, // primary | success | warning | danger | info
  icon: { type: Object, default: null },
  to: { type: [String, Object], default: null },
})
</script>

<template>
  <component :is="to ? 'router-link' : 'div'" :to="to" class="stat" :class="`tone-${tone}`">
    <div class="stat-row">
      <div class="stat-label">{{ label }}</div>
      <el-icon v-if="icon" class="stat-icon"><component :is="icon" /></el-icon>
    </div>
    <div class="stat-value">
      <span class="num">{{ value }}</span>
      <span v-if="unit" class="unit">{{ unit }}</span>
    </div>
    <div v-if="hint" class="stat-hint">{{ hint }}</div>
  </component>
</template>

<style scoped>
.stat {
  display: block;
  background: var(--pe-card);
  border: 1px solid var(--pe-border-soft);
  border-radius: var(--pe-radius);
  padding: 14px 16px;
  box-shadow: var(--pe-shadow-sm);
  color: inherit;
  text-decoration: none !important;
  transition: transform 0.12s ease, box-shadow 0.12s ease;
  height: 100%;
}
.stat:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08);
}
.stat-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.stat-label {
  font-size: 12px;
  color: var(--pe-text-mute);
  font-weight: 500;
  letter-spacing: 0.2px;
}
.stat-icon {
  font-size: 16px;
  border-radius: 6px;
  padding: 5px;
}
.stat-value {
  margin-top: 6px;
  display: flex;
  align-items: baseline;
  gap: 4px;
}
.num {
  font-size: 24px;
  font-weight: 600;
  color: var(--pe-text);
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
}
.unit {
  font-size: 12px;
  color: var(--pe-text-mute);
}
.stat-hint {
  margin-top: 4px;
  font-size: 11px;
  color: var(--pe-text-mute);
}
.tone-primary .stat-icon { color: var(--pe-primary); background: var(--pe-primary-soft); }
.tone-success .stat-icon { color: #047857; background: rgba(16, 185, 129, 0.1); }
.tone-warning .stat-icon { color: #b45309; background: rgba(245, 158, 11, 0.1); }
.tone-danger  .stat-icon { color: #b91c1c; background: rgba(239, 68, 68, 0.1); }
.tone-info    .stat-icon { color: #475569; background: rgba(100, 116, 139, 0.1); }
</style>
