<template>
  <div class="wm-page">
    <el-card shadow="never">
      <template #header>
        <div class="wm-header">
          <span class="wm-title">基准回归（Benchmark）</span>
          <div class="wm-actions">
            <el-input v-model="tag" placeholder="运行标签，如 prompt-v2" style="width: 200px" clearable />
            <el-button type="primary" :loading="running" @click="run">运行基准回归</el-button>
            <el-button :disabled="running" @click="load">刷新</el-button>
          </div>
        </div>
      </template>

      <el-alert
        v-if="regression"
        :type="regressionType"
        :closable="false"
        show-icon
        :title="regressionText"
        class="wm-alert"
      />
      <el-alert
        v-else
        type="info"
        :closable="false"
        show-icon
        title="尚无基准回归结果。点击「运行基准回归」在评估数据集上跑一轮，用于回答“新版本有没有变好”。"
      />
    </el-card>

    <template v-if="overall.samples">
      <el-row :gutter="12" class="wm-row">
        <el-col :span="4" v-for="card in metricCards" :key="card.label">
          <el-card shadow="never" class="wm-stat">
            <div class="wm-stat__label">{{ card.label }}</div>
            <div class="wm-stat__value">{{ card.value }}</div>
          </el-card>
        </el-col>
      </el-row>

      <el-row :gutter="12" class="wm-row">
        <el-col :span="10">
          <el-card shadow="never">
            <template #header><div class="wm-subtitle">分层指标</div></template>
            <el-table :data="levelRows" border>
              <el-table-column prop="label" label="复杂度" min-width="120" />
              <el-table-column prop="samples" label="样本" width="70" />
              <el-table-column prop="avg_total_score" label="综合分" width="90" />
              <el-table-column prop="hard_gate_pass_rate" label="Hard Gate" width="100">
                <template #default="{ row }">{{ row.hard_gate_pass_rate }}%</template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-col>

        <el-col :span="14">
          <el-card shadow="never">
            <template #header><div class="wm-subtitle">样本明细</div></template>
            <el-table :data="records" border>
              <el-table-column prop="title" label="样本" min-width="120" />
              <el-table-column prop="level" label="复杂度" width="100" />
              <el-table-column prop="total_score" label="综合分" width="90" />
              <el-table-column prop="requirement_score" label="需求" width="80" />
              <el-table-column prop="engineering_score" label="工程" width="80" />
              <el-table-column label="Hard Gate" width="100">
                <template #default="{ row }">
                  <el-tag :type="row.hard_gate_passed ? 'success' : 'danger'" size="small">
                    {{ row.hard_gate_passed ? '通过' : '未通过' }}
                  </el-tag>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-col>
      </el-row>
    </template>

    <el-card shadow="never" class="wm-card" v-if="history.length">
      <template #header><div class="wm-subtitle">回归历史</div></template>
      <el-table :data="history" border>
        <el-table-column prop="run_id" label="运行编号" min-width="150" />
        <el-table-column prop="tag" label="标签" min-width="120" />
        <el-table-column prop="generated_at" label="时间" min-width="190" />
        <el-table-column label="综合分" width="100">
          <template #default="{ row }">{{ row.overall?.avg_total_score }}</template>
        </el-table-column>
        <el-table-column label="对比上次" width="120">
          <template #default="{ row }">
            <span v-if="row.regression?.baseline">基线</span>
            <span v-else>{{ fmtDelta(row.regression?.total_delta) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/api'

const tag = ref('')
const running = ref(false)
const overall = ref<Record<string, any>>({})
const byLevel = ref<Record<string, any>>({})
const records = ref<any[]>([])
const regression = ref<Record<string, any> | null>(null)
const history = ref<any[]>([])

const metricCards = computed(() => [
  { label: '样本数', value: overall.value.samples },
  { label: '平均综合分', value: overall.value.avg_total_score },
  { label: 'Hard Gate 通过率', value: `${overall.value.hard_gate_pass_rate}%` },
  { label: '期望覆盖率', value: `${overall.value.avg_expected_coverage}%` },
  { label: '自修复比例', value: `${overall.value.self_repair_rate}%` },
  { label: '转人工比例', value: `${overall.value.human_intervention_rate}%` },
])

const levelRows = computed(() =>
  Object.values(byLevel.value || {}).map((item: any) => ({ label: item.label, ...item })),
)

const regressionType = computed(() => {
  if (!regression.value) return 'info'
  if (regression.value.baseline) return 'info'
  return (regression.value.total_delta || 0) < 0 ? 'warning' : 'success'
})

const regressionText = computed(() => {
  const reg = regression.value
  if (!reg) return ''
  if (reg.baseline) return `基线运行：${reg.message}`
  const warn = reg.comparable === false ? '（两次样本集不同，仅供参考）' : ''
  return `回归对比（基线 ${reg.previous_run}）${warn}：${reg.verdict}，综合分 ${fmtDelta(reg.total_delta)}`
})

const fmtDelta = (value: number | undefined) => {
  if (value === undefined || value === null) return '-'
  return value > 0 ? `+${value}` : `${value}`
}

const applyPayload = (data: any) => {
  overall.value = data.summary?.overall || {}
  byLevel.value = data.summary?.by_level || {}
  records.value = data.records || []
  regression.value = data.regression || null
}

const load = async () => {
  try {
    const { data } = await api.latestBenchmark()
    applyPayload(data)
  } catch {
    overall.value = {}
  }
  const historyRes = await api.benchmarkHistory()
  history.value = (historyRes.data.items || []).slice().reverse()
}

const run = async () => {
  running.value = true
  try {
    const { data } = await api.runBenchmark({ tag: tag.value })
    applyPayload(data)
    ElMessage.success(`基准回归完成：${data.run_id}`)
    await load()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '基准回归执行失败')
  } finally {
    running.value = false
  }
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
.wm-actions {
  display: flex;
  gap: 8px;
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
.wm-alert {
  margin-bottom: 4px;
}
</style>
