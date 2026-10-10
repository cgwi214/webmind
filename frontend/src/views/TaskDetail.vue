<template>
  <div class="wm-page">
    <el-card shadow="never">
      <template #header>
        <div class="wm-header">
          <span class="wm-title">{{ task.title || '任务详情' }}</span>
          <div>
            <el-button @click="$router.push('/tasks')">返回</el-button>
            <el-button :disabled="!task.task_id" @click="loadFiles">刷新产物</el-button>
            <el-button
              type="success"
              :disabled="!files.zip_path"
              @click="download"
            >
              下载代码包
            </el-button>
          </div>
        </div>
      </template>

      <el-descriptions :column="3" border class="wm-desc">
        <el-descriptions-item label="任务 ID">{{ task.task_id }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="task.status === 'delivered' ? 'success' : 'primary'">
            {{ task.status }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="当前 Agent">{{ task.current_agent || '-' }}</el-descriptions-item>
        <el-descriptions-item label="置信度">{{ (task.confidence || 0).toFixed(2) }}</el-descriptions-item>
        <el-descriptions-item label="重试次数">{{ task.retry_count }}</el-descriptions-item>
        <el-descriptions-item label="自修复次数">{{ task.self_repair_count }}</el-descriptions-item>
        <el-descriptions-item label="目标端">
          {{ (task.target_platforms || []).join(' / ') }}
        </el-descriptions-item>
        <el-descriptions-item label="人工介入">
          {{ task.human_intervention ? '是' : '否' }}
        </el-descriptions-item>
        <el-descriptions-item label="错误信息">{{ task.error_message || '-' }}</el-descriptions-item>
      </el-descriptions>

      <el-alert
        v-if="task.message"
        :title="task.message"
        type="info"
        :closable="false"
        class="wm-alert"
      />
    </el-card>

    <el-row :gutter="12" class="wm-row">
      <el-col :span="8">
        <el-card shadow="never">
          <template #header><div class="wm-subtitle">生成文件</div></template>
          <el-menu :default-active="currentFile" @select="(v: string) => (currentFile = v)">
            <el-menu-item v-for="name in fileNames" :key="name" :index="name">
              {{ name }}
            </el-menu-item>
          </el-menu>
        </el-card>
      </el-col>

      <el-col :span="16">
        <el-card shadow="never">
          <template #header>
            <div class="wm-subtitle">代码预览 · {{ currentFile || '未选择' }}</div>
          </template>
          <pre class="wm-code">{{ files.files?.[currentFile] || '暂无内容' }}</pre>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="wm-card">
      <template #header>
        <div class="wm-header">
          <span class="wm-subtitle">质量评估</span>
          <div>
            <el-button type="primary" :loading="evaluating" @click="runEvaluation">
              执行评估
            </el-button>
            <el-button @click="loadEvaluation">查看结果</el-button>
          </div>
        </div>
      </template>

      <el-descriptions v-if="evaluation" :column="3" border>
        <el-descriptions-item label="综合得分">{{ evaluation.total_score }}</el-descriptions-item>
        <el-descriptions-item label="代码可用性">{{ evaluation.code_score }}</el-descriptions-item>
        <el-descriptions-item label="页面还原度">{{ evaluation.visual_score }}</el-descriptions-item>
        <el-descriptions-item label="需求理解">{{ evaluation.requirement_score }}</el-descriptions-item>
        <el-descriptions-item label="Agent 执行">{{ evaluation.agent_score }}</el-descriptions-item>
        <el-descriptions-item label="工程规范">{{ evaluation.engineering_score }}</el-descriptions-item>
        <el-descriptions-item label="Hard Gate">
          <el-tag :type="evaluation.hard_gate_passed ? 'success' : 'danger'">
            {{ evaluation.hard_gate_passed ? '通过' : '未通过' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="耗时">{{ evaluation.execution_time }} 秒</el-descriptions-item>
        <el-descriptions-item label="Token">
          {{ evaluation.input_tokens }} / {{ evaluation.output_tokens }}
        </el-descriptions-item>
      </el-descriptions>
      <el-empty v-else description="尚未执行评估" />
    </el-card>

    <el-card shadow="never" class="wm-card">
      <template #header><div class="wm-subtitle">人工评分（1~5 分）</div></template>
      <el-form :model="human" inline>
        <el-form-item label="视觉效果">
          <el-rate v-model="human.visual" :max="5" />
        </el-form-item>
        <el-form-item label="功能完整度">
          <el-rate v-model="human.completeness" :max="5" />
        </el-form-item>
        <el-form-item label="代码质量">
          <el-rate v-model="human.code_quality" :max="5" />
        </el-form-item>
        <el-form-item label="修改成本">
          <el-rate v-model="human.modification_cost" :max="5" />
        </el-form-item>
        <el-form-item label="业务符合度">
          <el-rate v-model="human.business_fit" :max="5" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="submitHuman">提交评分</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" class="wm-card">
      <template #header><div class="wm-subtitle">确认合并（填写修正原因）</div></template>
      <el-form :model="merge" inline>
        <el-form-item label="修正类型">
          <el-select v-model="merge.correction_type" style="width: 160px">
            <el-option label="无需修正" value="无需修正" />
            <el-option label="组件错了" value="组件错了" />
            <el-option label="布局差了" value="布局差了" />
            <el-option label="逻辑错了" value="逻辑错了" />
            <el-option label="样式微调" value="样式微调" />
          </el-select>
        </el-form-item>
        <el-form-item label="修改文件数">
          <el-input-number v-model="merge.modified_files" :min="0" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="merge.comment" placeholder="补充说明" />
        </el-form-item>
        <el-form-item>
          <el-button type="success" @click="confirmMerge">确认合并</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '@/api'

const route = useRoute()
const taskId = computed(() => String(route.params.taskId))

const task = ref<Record<string, any>>({})
const files = ref<Record<string, any>>({})
const evaluation = ref<Record<string, any> | null>(null)
const currentFile = ref('')
const evaluating = ref(false)

const human = ref({
  visual: 4,
  completeness: 4,
  code_quality: 4,
  modification_cost: 3,
  business_fit: 4,
})

const merge = ref({
  correction_type: '无需修正',
  modified_files: 0,
  comment: '',
})

const fileNames = computed(() => Object.keys(files.value.files || {}))

const loadTask = async () => {
  const { data } = await api.getTask(taskId.value)
  task.value = data
}

const loadFiles = async () => {
  try {
    const { data } = await api.getFiles(taskId.value)
    files.value = data
    if (!currentFile.value && fileNames.value.length) {
      currentFile.value = fileNames.value.find((n) => n.endsWith('.vue')) || fileNames.value[0]
    }
  } catch {
    files.value = {}
  }
}

const loadEvaluation = async () => {
  try {
    const { data } = await api.getEvaluation(taskId.value)
    evaluation.value = data
  } catch {
    evaluation.value = null
  }
}

const runEvaluation = async () => {
  evaluating.value = true
  try {
    const { data } = await api.runEvaluation(taskId.value)
    evaluation.value = data
    ElMessage.success('评估完成')
  } finally {
    evaluating.value = false
  }
}

const submitHuman = async () => {
  await api.submitHumanReview(taskId.value, { ...human.value })
  ElMessage.success('人工评分已提交')
}

const confirmMerge = async () => {
  await api.confirmMerge(taskId.value, { ...merge.value })
  ElMessage.success('已确认合并，修正记录已入库')
  loadTask()
}

const download = () => {
  window.open(api.downloadUrl(taskId.value), '_blank')
}

onMounted(async () => {
  await loadTask()
  await loadFiles()
  await loadEvaluation()
})
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
.wm-desc {
  margin-bottom: 12px;
}
.wm-alert {
  margin-bottom: 4px;
}
.wm-row {
  margin-top: 12px;
}
.wm-card {
  margin-top: 12px;
}
.wm-code {
  max-height: 420px;
  overflow: auto;
  background: #f5f7fa;
  padding: 12px;
  font-size: 12px;
  line-height: 1.6;
}
</style>
