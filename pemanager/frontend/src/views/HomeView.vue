<script setup>
const items = [
  { to: '/interfacemanage', label: '接口管理' },
  { to: '/resourcemanage', label: '资源管理' },
  { to: '/routemanage', label: '路由管理' },
  { to: '/qosmanage', label: 'QoS 管理' },
  { to: '/firewallmanage', label: '防火墙管理' },
  { to: '/operationmanage', label: '运维管理' },
  { to: '/logmanage', label: '日志管理' },
]
</script>

<template>
  <el-space direction="vertical" :size="16" style="width: 100%">
    <el-text size="large">PE Manager — 选择业务模块</el-text>
    <el-space wrap>
      <router-link
        v-for="item in items"
        :key="item.to"
        :to="item.to"
        custom
        v-slot="{ href, navigate }"
      >
        <el-button type="primary" plain tag="a" :href="href" @click="navigate">
          {{ item.label }}
        </el-button>
      </router-link>
    </el-space>
  </el-space>
</template>
