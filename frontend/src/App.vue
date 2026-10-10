<template>
  <el-container class="wm-layout">
    <el-aside width="210px" class="wm-aside">
      <div class="wm-logo">WebMind</div>
      <el-menu router :default-active="$route.path">
        <el-menu-item index="/create">提交需求</el-menu-item>
        <el-menu-item index="/tasks">任务列表</el-menu-item>
        <el-menu-item index="/evaluation">评估看板</el-menu-item>
        <el-menu-item index="/benchmark">基准回归</el-menu-item>
      </el-menu>
      <div class="wm-backend">
        <div class="wm-backend__title">运行后端</div>
        <div v-for="(value, key) in backends" :key="key" class="wm-backend__item">
          {{ key }}：{{ value }}
        </div>
      </div>
    </el-aside>

    <el-container>
      <el-main class="wm-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import api from '@/api'

const backends = ref<Record<string, string>>({})

onMounted(async () => {
  try {
    const { data } = await api.health()
    backends.value = {
      数据库: data.backends.database,
      文档库: data.backends.doc_store,
      缓存: data.backends.cache,
      模型: data.llm.mock_mode ? '本地启发式' : data.llm.model,
    }
  } catch {
    backends.value = { 状态: '后端未连接' }
  }
})
</script>

<style scoped>
.wm-layout {
  min-height: 100vh;
}
.wm-aside {
  border-right: 1px solid #ebeef5;
  padding-top: 8px;
}
.wm-logo {
  height: 48px;
  line-height: 48px;
  text-align: center;
  font-size: 18px;
  font-weight: 600;
}
.wm-main {
  background: #f5f7fa;
}
.wm-backend {
  margin: 16px 12px;
  padding: 10px;
  background: #f5f7fa;
  border-radius: 6px;
  font-size: 12px;
  color: #606266;
}
.wm-backend__title {
  font-weight: 600;
  margin-bottom: 6px;
}
.wm-backend__item {
  line-height: 20px;
}
</style>
