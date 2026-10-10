<template>
  <div class="wm-page">
    <el-card shadow="never">
      <template #header>
        <div class="wm-title">提交需求（PRD → 前端工程）</div>
      </template>

      <el-form :model="form" label-width="110px">
        <el-form-item label="任务标题">
          <el-input v-model="form.title" placeholder="如：用户管理后台" clearable />
        </el-form-item>

        <el-form-item label="产品线">
          <el-select v-model="form.project_id" placeholder="选择产品线" clearable>
            <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>

        <el-form-item label="目标端">
          <el-checkbox-group v-model="form.target_platforms">
            <el-checkbox label="web">Web</el-checkbox>
            <el-checkbox label="mp-weixin">小程序</el-checkbox>
            <el-checkbox label="h5">H5</el-checkbox>
          </el-checkbox-group>
        </el-form-item>

        <el-form-item label="PRD 内容">
          <el-input
            v-model="form.prd"
            type="textarea"
            :rows="10"
            placeholder="粘贴 PRD 内容，或上传 .md / .txt 文件"
          />
        </el-form-item>

        <el-form-item label="上传 PRD">
          <el-upload :auto-upload="false" :limit="1" :on-change="onFileChange" accept=".md,.txt">
            <el-button>选择文件</el-button>
          </el-upload>
        </el-form-item>

        <el-form-item label="设计稿说明">
          <el-input
            v-model="form.design_note"
            type="textarea"
            :rows="3"
            placeholder="如：列表页包含搜索区、表格、分页；表单页含新增弹窗"
          />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="submitting" @click="submit">提交任务</el-button>
          <el-button @click="reset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '@/api'

const router = useRouter()
const submitting = ref(false)
const projects = ref<{ id: number; name: string }[]>([])
const file = ref<File | null>(null)

const form = reactive({
  title: '',
  project_id: null as number | null,
  target_platforms: ['web'],
  prd: '',
  design_note: '',
})

const onFileChange = (uploadFile: { raw: File }) => {
  file.value = uploadFile.raw
}

const submit = async () => {
  if (!form.prd.trim() && !file.value) {
    ElMessage.warning('请填写 PRD 内容或上传文件')
    return
  }
  submitting.value = true
  try {
    let response
    if (file.value) {
      const payload = new FormData()
      payload.append('prd_file', file.value)
      payload.append('title', form.title)
      payload.append('target_platforms', form.target_platforms.join(','))
      payload.append('design_note', form.design_note)
      response = await api.uploadTask(payload)
    } else {
      response = await api.createTask({ ...form })
    }
    ElMessage.success('任务已提交，进入队列执行')
    router.push(`/tasks/${response.data.task_id}`)
  } catch (error) {
    ElMessage.error(`提交失败：${error}`)
  } finally {
    submitting.value = false
  }
}

const reset = () => {
  form.title = ''
  form.prd = ''
  form.design_note = ''
  form.project_id = null
  form.target_platforms = ['web']
  file.value = null
}

onMounted(async () => {
  try {
    const { data } = await api.projects()
    projects.value = data
  } catch {
    projects.value = []
  }
})
</script>

<style scoped>
.wm-page {
  padding: 4px;
}
.wm-title {
  font-size: 16px;
  font-weight: 600;
}
</style>
