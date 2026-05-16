<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { Menu, House } from '@element-plus/icons-vue'

const route = useRoute()
const active = computed(() => route.path)

const menu = [
  { index: '/', label: '首页', icon: House },
  { index: '/interfacemanage', label: '接口管理' },
  { index: '/resourcemanage', label: '资源管理' },
  { index: '/routemanage', label: '路由管理' },
  { index: '/qosmanage', label: 'QoS 管理' },
  { index: '/firewallmanage', label: '防火墙管理' },
  { index: '/operationmanage', label: '运维管理' },
  { index: '/logmanage', label: '日志管理' },
]
</script>

<template>
  <el-container class="layout">
    <el-aside width="220px" class="aside">
      <div class="brand">
        <el-icon><Menu /></el-icon>
        <span>PE Manager</span>
      </div>
      <el-menu :default-active="active" router class="menu">
        <el-menu-item v-for="m in menu" :key="m.index" :index="m.index">
          <el-icon v-if="m.icon"><component :is="m.icon" /></el-icon>
          <span>{{ m.label }}</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <el-breadcrumb separator="/">
          <el-breadcrumb-item :to="{ path: '/' }">首页</el-breadcrumb-item>
          <el-breadcrumb-item v-if="route.meta.title">{{ route.meta.title }}</el-breadcrumb-item>
        </el-breadcrumb>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.layout {
  min-height: 100vh;
}
.aside {
  border-right: 1px solid var(--el-border-color-light);
}
.brand {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 56px;
  padding: 0 16px;
  font-weight: 600;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.menu {
  border-right: none;
}
.header {
  display: flex;
  align-items: center;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.main {
  background: var(--el-bg-color-page);
}
</style>
