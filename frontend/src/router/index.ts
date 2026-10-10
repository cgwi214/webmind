import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/tasks' },
  {
    path: '/create',
    name: 'create',
    component: () => import('@/views/TaskCreate.vue'),
  },
  {
    path: '/tasks',
    name: 'tasks',
    component: () => import('@/views/TaskList.vue'),
  },
  {
    path: '/tasks/:taskId',
    name: 'task-detail',
    component: () => import('@/views/TaskDetail.vue'),
  },
  {
    path: '/evaluation',
    name: 'evaluation',
    component: () => import('@/views/EvaluationDashboard.vue'),
  },
  {
    path: '/benchmark',
    name: 'benchmark',
    component: () => import('@/views/BenchmarkRun.vue'),
  },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
