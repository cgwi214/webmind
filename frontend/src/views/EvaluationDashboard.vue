<template>
  <div class="wm-page">
    <el-card shadow="never">
      <template #header>
        <div class="wm-header">
          <span class="wm-title">评估看板</span>
          <div>
            <el-button type="primary" @click="load">刷新</el-button>
            <el-button @click="loadReport">生成报告</el-button>
          </div>
        </div>
      </template>

      <el-row :gutter="12" v-if="aggregate.total_tasks">
        <el-col :span="4" v-for="card in metricCards" :key="card.label">
          <el-card shadow="never" class="wm-stat">
            <div class="wm-stat__label">{{ card.label }}</div>
            <div class="wm-stat__value">{{ card.value }}</div>
          </el-card>
        </el-col>
      </el-row>
      <el-empty v-else description="暂无评估数据，请先在任务详情中执行评估" />
    </el-card>

    <el-row :gutter="12" class="wm-row" v-if="aggregate.total_tasks">
      <el-col :span="12">
        <el-card shadow="never">
          <template #header><div class="wm-subtitle">分项平均分</div></template>
          <el-table :data="scoreRows" border>
            <el-table-column prop="name" label="维度" width="140" />
            <el-table-column prop="score" label="得分" min-width="120">
              <template #default="{ row }">
                <el-progress :percentage="row.score" :stroke-width="12" />
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card shadow="never">
          <template #header><div class="wm-subtitle">错误分布 / 修正原因</div></template>
          <el-table :data="distributionRows" border>
            <el-table-column prop="name" label="类别" min-width="160" />
            <el-table-column prop="count" label="数量" width="90" />
            <el-table-column prop="ratio" label="占比" width="100" />
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="wm-card" v-if="suggestions.length">
      <template #header><div class="wm-subtitle">优化建议（评估 → 迭代闭环）</div></template>
      <el-alert
        v-for="item in suggestions"
        :key="item"
        :title="item"
        type="warning"
        :closable="false"
        class="wm-suggestion"
      />
    </el-card>

    <el-card shadow="never" class="wm-card" v-if="reportContent">
      <template #header><div class="wm-subtitle">评估报告（Markdown）</div></template>
      <pre class="wm-report">{{ reportContent }}</pre>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import api from '@/api'

const aggregate = ref<Record<string, any>>({})
const errorAnalysis = ref<Record<string, any>>({})
const feedback = ref<Record<string, any>>({})
const suggestions = ref<string[]>([])
const reportContent = ref('')

const metricCards = computed(() => [
  { label: '任务数', value: aggregate.value.total_tasks },
  { label: '构建成功率', value: `${aggregate.value.code_success_rate}%` },
  { label: '平均综合分', value: aggregate.value.avg_total_score },
  { label: '平均耗时', value: `${aggregate.value.avg_execution_time}s` },
  { label: '自修复任务', value: aggregate.value.self_repair_tasks },
  { label: '转人工任务', value: aggregate.value.human_intervention_tasks },
])

const scoreRows = computed(() => [
  { name: '代码可用性', score: Math.round(aggregate.value.avg_code_score || 0) },
  { name: '页面还原度', score: Math.round(aggregate.value.avg_visual_score || 0) },
  { name: '需求理解', score: Math.round(aggregate.value.avg_requirement_score || 0) },
  { name: 'Agent 执行', score: Math.round(aggregate.value.avg_agent_score || 0) },
  { name: '工程规范', score: Math.round(aggregate.value.avg_engineering_score || 0) },
])

const distributionRows = computed(() => {
  const rows: { name: string; count: number; ratio: string }[] = []
  const errors = errorAnalysis.value.distribution || {}
  for (const [name, count] of Object.entries(errors)) {
    const total = Object.values(errors as Record<string, number>).reduce((a, b) => a + b, 0) || 1
    rows.push({
      name: `错误 · ${name}`,
      count: count as number,
      ratio: `${(((count as number) / total) * 100).toFixed(1)}%`,
    })
  }
  const fb = feedback.value.distribution || {}
  const fbTotal = feedback.value.total || 1
  for (const [name, count] of Object.entries(fb)) {
    rows.push({
      name: `修正 · ${name}`,
      count: count as number,
      ratio: `${(((count as number) / fbTotal) * 100).toFixed(1)}%`,
    })
  }
  return rows
})

const load = async () => {
  const { data } = await api.dashboard()
  aggregate.value = data.aggregate || {}
  errorAnalysis.value = data.error_analysis || {}
  feedback.value = data.feedback || {}
  suggestions.value = data.suggestions || []
}

const loadReport = async () => {
  const { data } = await api.report()
  reportContent.value = data.content
}

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
.wm-subtitle {
  font-size: 14px;
  font-weight: 600;
}
.wm-stat__label {
  font-size: 12px;
  color: #909399;
}
.wm-stat__value {
  font-size: 20px;
  font-weight: 600;
  margin-top: 6px;
}
.wm-row {
  margin-top: 12px;
}
.wm-card {
  margin-top: 12px;
}
.wm-suggestion {
  margin-bottom: 8px;
}
.wm-report {
  max-height: 360px;
  overflow: auto;
  background: #f5f7fa;
  padding: 12px;
  font-size: 12px;
}
</style>
