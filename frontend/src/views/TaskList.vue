<template>
  <div class="wm-page">
    <el-card shadow="never">
      <template #header>
        <div class="wm-header">
          <span class="wm-title">任务列表</span>
          <div>
            <el-select v-model="status" placeholder="状态筛选" clearable style="width: 160px">
              <el-option label="排队中" value="queued" />
              <el-option label="交付完成" value="delivered" />
              <el-option label="待人工" value="human_required" />
              <el-option label="需澄清" value="needs_clarification" />
              <el-option label="失败" value="failed" />
              <el-option label="已确认" value="confirmed" />
            </el-select>
            <el-button class="wm-refresh" type="primary" @click="load">刷新</el-button>
          </div>
        </div>
      </template>

      <el-table :data="tasks" v-loading="loading" border stripe>
        <el-table-column prop="title" label="任务" min-width="180" />
        <el-table-column prop="task_id" label="任务 ID" width="180" />
        <el-table-column label="状态" width="150">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="current_agent" label="当前 Agent" width="120" />
        <el-table-column label="置信度" width="100">
          <template #default="{ row }">{{ (row.confidence || 0).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="自修复" width="90">
          <template #default="{ row }">{{ row.self_repair_count }}</template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" min-width="180" />
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="$router.push(`/tasks/${row.task_id}`)">
              查看
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import api, { type TaskItem } from '@/api'

const tasks = ref<TaskItem[]>([])
const loading = ref(false)
const status = ref<string>('')

const statusLabel = (value: string) =>
  ({
    queued: '排队中',
    parsed: '解析完成',
    generated: '生成完成',
    reviewed: '审查通过',
    repairing: '自修复中',
    delivered: '已交付',
    needs_clarification: '需澄清',
    human_required: '待人工',
    failed: '失败',
    confirmed: '已确认',
  })[value] || value

const statusType = (value: string) => {
  if (['delivered', 'confirmed', 'reviewed'].includes(value)) return 'success'
  if (['repairing', 'queued', 'parsed', 'generated'].includes(value)) return 'primary'
  if (['needs_clarification', 'human_required'].includes(value)) return 'warning'
  return 'danger'
}

const load = async () => {
  loading.value = true
  try {
    const { data } = await api.listTasks(status.value || undefined)
    tasks.value = data.items
  } finally {
    loading.value = false
  }
}

watch(status, load)
onMounted(load)
</script>

<style scoped>
.wm-page {
  padding: 4px;
}
.wm-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.wm-title {
  font-size: 16px;
  font-weight: 600;
}
.wm-refresh {
  margin-left: 8px;
}
</style>
