import axios from 'axios'

const http = axios.create({
  baseURL: '/api',
  timeout: 120000,
})

export interface TaskCreatePayload {
  prd: string
  title?: string
  project_id?: number | null
  target_platforms?: string[]
  design_note?: string
}

export interface TaskItem {
  task_id: string
  title: string
  status: string
  current_agent: string
  message: string
  confidence: number
  retry_count: number
  self_repair_count: number
  human_intervention: boolean
  target_platforms: string[]
  created_at: string | null
}

export const api = {
  health: () => http.get('/health'),

  projects: () => http.get('/projects'),

  createTask: (payload: TaskCreatePayload) => http.post('/task/create', payload),

  uploadTask: (form: FormData) =>
    http.post('/task/upload', form, { headers: { 'Content-Type': 'multipart/form-data' } }),

  listTasks: (status?: string) => http.get('/task/list', { params: { status } }),

  getTask: (taskId: string) => http.get(`/task/${taskId}`),

  getFiles: (taskId: string) => http.get(`/task/${taskId}/files`),

  downloadUrl: (taskId: string) => `/api/task/${taskId}/download`,

  confirmMerge: (taskId: string, payload: Record<string, unknown>) =>
    http.post(`/task/${taskId}/confirm`, payload),

  runEvaluation: (taskId: string) => http.post(`/evaluation/run/${taskId}`),

  getEvaluation: (taskId: string) => http.get(`/evaluation/result/${taskId}`),

  submitHumanReview: (taskId: string, payload: Record<string, unknown>) =>
    http.post(`/evaluation/human/${taskId}`, payload),

  dashboard: () => http.get('/evaluation/dashboard'),

  report: () => http.get('/evaluation/report'),

  runBenchmark: (payload: { sample_ids?: string[]; tag?: string }) =>
    http.post('/evaluation/benchmark/run', payload),

  latestBenchmark: () => http.get('/evaluation/benchmark/latest'),

  benchmarkHistory: () => http.get('/evaluation/benchmark/runs'),
}

export default api
