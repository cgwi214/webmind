"""Vue3 + Element Plus 工程代码生成。

输入：需求 JSON（页面 / 字段 / 功能）
输出：可直接 npm install && npm run dev 的前端工程文件字典 {相对路径: 内容}

团队模板路径：src/views / src/mock / src/router / src/api，全部使用组件白名单内的组件。
"""

from __future__ import annotations

import re
from typing import Any

# 中文页面名 → 英文标识符（用于生成组件文件名）
_KEYWORD_MAP = {
    "用户": "User",
    "会员": "Member",
    "订单": "Order",
    "商品": "Product",
    "库存": "Stock",
    "角色": "Role",
    "权限": "Permission",
    "部门": "Department",
    "日志": "Log",
    "消息": "Message",
    "活动": "Activity",
    "数据": "Data",
    "报表": "Report",
    "配置": "Config",
    "设置": "Setting",
    "列表": "List",
    "表单": "Form",
    "详情": "Detail",
    "登录": "Login",
    "首页": "Home",
    "仪表盘": "Dashboard",
    "任务": "Task",
    "文件": "File",
    "评论": "Comment",
}

_TYPE_KEYWORDS = {
    "table": ("列表", "表格", "管理", "list", "table"),
    "form": ("表单", "新增", "编辑", "申请", "form"),
    "detail": ("详情", "明细", "detail"),
    "config": ("配置", "设置", "config", "setting"),
    "login": ("登录", "注册", "login"),
    "dashboard": ("仪表盘", "看板", "统计", "概览", "dashboard"),
}

_FUNCTION_KEYWORDS = {
    "搜索": "search",
    "查询": "search",
    "新增": "create",
    "创建": "create",
    "编辑": "edit",
    "修改": "edit",
    "删除": "delete",
    "导出": "export",
    "导入": "import",
    "重置": "reset",
    "上传": "upload",
}


def to_identifier(name: str, index: int, suffix: str = "") -> str:
    """把中文/英文页面名转成 PascalCase 组件名。"""
    if re.fullmatch(r"[A-Za-z0-9_\- ]+", name or ""):
        parts = [p for p in re.split(r"[\s_\-]+", name.strip()) if p]
        ident = "".join(p[:1].upper() + p[1:] for p in parts)
    else:
        ident = "".join(_KEYWORD_MAP.get(ch, "") for ch in name if ch in _KEYWORD_MAP)
    if not ident:
        ident = f"Page{index + 1}"
    return f"{ident}{suffix}"


def detect_type(name: str, declared: str = "") -> str:
    if declared in _TYPE_KEYWORDS:
        return declared
    lowered = (name or "").lower()
    for page_type, keywords in _TYPE_KEYWORDS.items():
        if any(key in lowered for key in keywords):
            return page_type
    return "table"


def _normalize_fields(page: dict[str, Any]) -> list[dict[str, Any]]:
    fields = page.get("fields") or []
    normalized: list[dict[str, Any]] = []
    for field in fields:
        if isinstance(field, str):
            normalized.append({"name": field, "label": field, "type": "string"})
        elif isinstance(field, dict):
            normalized.append(
                {
                    "name": field.get("name") or "field",
                    "label": field.get("label") or field.get("name") or "field",
                    "type": field.get("type") or "string",
                    "required": bool(field.get("required", False)),
                    "options": field.get("options") or [],
                }
            )
    if not normalized:
        normalized = [
            {"name": "name", "label": "名称", "type": "string", "required": True, "options": []},
            {"name": "status", "label": "状态", "type": "enum", "required": False, "options": ["启用", "禁用"]},
            {"name": "createdAt", "label": "创建时间", "type": "date", "required": False, "options": []},
        ]
    return normalized


def _functions(page: dict[str, Any]) -> list[str]:
    funcs = set()
    for item in page.get("functions") or []:
        text = str(item)
        for keyword, code in _FUNCTION_KEYWORDS.items():
            if keyword in text:
                funcs.add(code)
    for keyword, code in _FUNCTION_KEYWORDS.items():
        if keyword in (page.get("name") or ""):
            funcs.add(code)
    if not funcs:
        funcs = {"search", "create", "edit", "delete"}
    return sorted(funcs)


def _input_control(field: dict[str, Any], model: str) -> str:
    ftype = field["type"]
    if ftype == "enum":
        options = "".join(
            f'          <el-option label="{opt}" value="{opt}" />\n' for opt in (field["options"] or ["启用", "禁用"])
        )
        return f'        <el-select v-model="{model}" placeholder="请选择{field["label"]}" clearable>\n{options}        </el-select>'
    if ftype == "date":
        return (
            f'        <el-date-picker v-model="{model}" type="date" '
            f'placeholder="请选择{field["label"]}" value-format="YYYY-MM-DD" />'
        )
    if ftype == "number":
        return f'        <el-input-number v-model="{model}" :min="0" />'
    if ftype == "boolean":
        return f'        <el-switch v-model="{model}" />'
    if ftype == "text":
        return f'        <el-input v-model="{model}" type="textarea" :rows="3" placeholder="请输入{field["label"]}" />'
    return f'        <el-input v-model="{model}" placeholder="请输入{field["label"]}" clearable />'


def _table_columns(fields: list[dict[str, Any]]) -> str:
    lines = []
    for field in fields:
        if field["type"] == "text":
            continue
        width = ' width="180"' if field["type"] == "date" else ' min-width="120"'
        lines.append(f'        <el-table-column prop="{field["name"]}" label="{field["label"]}"{width} />')
    return "\n".join(lines)


def _form_items(fields: list[dict[str, Any]], model: str) -> str:
    lines = []
    for field in fields:
        fname = field["name"]
        label = field["label"]
        prop = ' prop="%s"' % fname if model == "form" else ""
        control = _input_control(field, "%s.%s" % (model, fname))
        lines.append(
            '        <el-form-item label="%s"%s>\n%s\n        </el-form-item>'
            % (label, prop, control)
        )
    return "\n".join(lines)


def _mock_rows(fields: list[dict[str, Any]], rows: int = 8) -> str:
    lines = []
    for i in range(1, rows + 1):
        values = []
        for field in fields:
            if field["type"] == "number":
                values.append(f"{field['name']}: {i * 10}")
            elif field["type"] == "enum":
                values.append(f"{field['name']}: '{field['options'][0] if field['options'] else '启用'}'")
            elif field["type"] == "date":
                values.append(f"{field['name']}: '2026-0{(i % 9) + 1}-1{i % 10}'")
            elif field["type"] == "boolean":
                values.append(f"{field['name']}: {str(i % 2 == 0).lower()}")
            else:
                values.append(f"{field['name']}: '{field['label']}-{i}'")
        lines.append("  { id: %d, %s }," % (i, ", ".join(values)))
    return "\n".join(lines)


# ---------------- 页面模板 ----------------

_TABLE_PAGE = """<template>
  <div class="wm-page">
    <el-card shadow="never">
      <template #header>
        <div class="wm-page__title">__PAGE_NAME__</div>
      </template>

      <el-form :inline="true" :model="query" class="wm-search">
__SEARCH_ITEMS__
        <el-form-item>
__SEARCH_BUTTONS__
        </el-form-item>
      </el-form>

      <el-table :data="tableData" v-loading="loading" border stripe>
__COLUMNS__
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDialog(row)">编辑</el-button>
            <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        class="wm-pagination"
        background
        layout="total, sizes, prev, pager, next"
        :total="total"
        v-model:current-page="query.page"
        v-model:page-size="query.size"
      />
    </el-card>

    <el-dialog v-model="dialogVisible" :title="form.id ? '编辑' : '新增'" width="560px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="96px">
__FORM_ITEMS__
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitForm">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance } from 'element-plus'
import { mockRows } from '@/mock/__MOCK_FILE__'

interface Row {
  id: number
  [key: string]: unknown
}

const loading = ref(false)
const dialogVisible = ref(false)
const formRef = ref<FormInstance>()
const tableData = ref<Row[]>([])
const total = ref(0)

const query = reactive({ page: 1, size: 10 })
const form = reactive<Record<string, unknown>>({})
const rules = reactive({})

const fetchList = async () => {
  loading.value = true
  try {
    // TODO 接入真实接口，当前为 mock 数据
    const start = (query.page - 1) * query.size
    tableData.value = mockRows.slice(start, start + query.size) as Row[]
    total.value = mockRows.length
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  query.page = 1
  fetchList()
}

const handleReset = () => {
  Object.keys(query).forEach((key) => {
    if (key !== 'page' && key !== 'size') delete (query as Record<string, unknown>)[key]
  })
  handleSearch()
}

const openDialog = (row?: Row) => {
  Object.keys(form).forEach((key) => delete form[key])
  if (row) Object.assign(form, row)
  dialogVisible.value = true
}

const submitForm = async () => {
  await formRef.value?.validate()
  ElMessage.success(form.id ? '编辑成功' : '新增成功')
  dialogVisible.value = false
  fetchList()
}

const handleDelete = async (row: Row) => {
  await ElMessageBox.confirm('确认删除该条记录？', '提示', { type: 'warning' })
  ElMessage.success(`已删除 #${row.id}`)
  fetchList()
}

onMounted(fetchList)
</script>

<style scoped>
.wm-page {
  padding: 16px;
}
.wm-page__title {
  font-size: 16px;
  font-weight: 600;
}
.wm-search {
  padding-top: 8px;
}
.wm-pagination {
  margin-top: 16px;
  justify-content: flex-end;
}
</style>
"""

_FORM_PAGE = """<template>
  <div class="wm-page">
    <el-card shadow="never">
      <template #header>
        <div class="wm-page__title">__PAGE_NAME__</div>
      </template>

      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px" class="wm-form">
__FORM_ITEMS__
        <el-form-item>
          <el-button type="primary" @click="submitForm">提交</el-button>
          <el-button @click="resetForm">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage, type FormInstance } from 'element-plus'

const formRef = ref<FormInstance>()
const form = reactive<Record<string, unknown>>(__FORM_DEFAULTS__)
const rules = reactive({})

const submitForm = async () => {
  await formRef.value?.validate()
  ElMessage.success('提交成功')
}

const resetForm = () => {
  formRef.value?.resetFields()
}
</script>

<style scoped>
.wm-page {
  padding: 16px;
}
.wm-form {
  max-width: 640px;
}
</style>
"""

_DETAIL_PAGE = """<template>
  <div class="wm-page">
    <el-card shadow="never">
      <template #header>
        <div class="wm-page__title">__PAGE_NAME__</div>
      </template>

      <el-descriptions :column="2" border>
__DESC_ITEMS__
      </el-descriptions>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { mockRows } from '@/mock/__MOCK_FILE__'

const detail = ref(mockRows[0] ?? {})
</script>

<style scoped>
.wm-page {
  padding: 16px;
}
</style>
"""

_LOGIN_PAGE = """<template>
  <div class="wm-login">
    <el-card class="wm-login__card" shadow="always">
      <template #header>
        <div class="wm-login__title">__PAGE_NAME__</div>
      </template>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="0">
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="请输入账号" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="form.password" type="password" placeholder="请输入密码" show-password />
        </el-form-item>
        <el-button type="primary" class="wm-login__submit" @click="submitForm">登录</el-button>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage, type FormInstance } from 'element-plus'

const formRef = ref<FormInstance>()
const form = reactive({ username: '', password: '' })
const rules = reactive({
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
})

const submitForm = async () => {
  await formRef.value?.validate()
  ElMessage.success('登录成功（mock）')
}
</script>

<style scoped>
.wm-login {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
}
.wm-login__card {
  width: 380px;
}
.wm-login__title {
  text-align: center;
  font-size: 18px;
  font-weight: 600;
}
.wm-login__submit {
  width: 100%;
}
</style>
"""

_CONFIG_PAGE = """<template>
  <div class="wm-page">
    <el-card shadow="never">
      <template #header>
        <div class="wm-page__title">__PAGE_NAME__</div>
      </template>

      <el-form :model="form" label-width="140px" class="wm-form">
__FORM_ITEMS__
        <el-form-item>
          <el-button type="primary" @click="save">保存配置</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

const saved = ref(false)
const form = reactive<Record<string, unknown>>(__FORM_DEFAULTS__)

const save = () => {
  saved.value = true
  ElMessage.success('配置已保存（mock）')
}
</script>

<style scoped>
.wm-page {
  padding: 16px;
}
.wm-form {
  max-width: 720px;
}
</style>
"""

_DASHBOARD_PAGE = """<template>
  <div class="wm-page">
    <el-row :gutter="16">
      <el-col v-for="card in cards" :key="card.title" :span="6">
        <el-card shadow="never" class="wm-stat">
          <div class="wm-stat__title">{{ card.title }}</div>
          <div class="wm-stat__value">{{ card.value }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="wm-table-card">
      <template #header>
        <div class="wm-page__title">__PAGE_NAME__</div>
      </template>
      <el-table :data="tableData" border stripe>
__COLUMNS__
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { mockRows } from '@/mock/__MOCK_FILE__'

const cards = ref([
  { title: '总访问量', value: '12,384' },
  { title: '新增用户', value: '1,204' },
  { title: '转化率', value: '23.6%' },
  { title: '活跃任务', value: '86' },
])
const tableData = ref(mockRows)
</script>

<style scoped>
.wm-page {
  padding: 16px;
}
.wm-stat__title {
  color: #909399;
  font-size: 13px;
}
.wm-stat__value {
  font-size: 24px;
  font-weight: 600;
  margin-top: 8px;
}
.wm-table-card {
  margin-top: 16px;
}
</style>
"""


# ---------------- 工程脚手架 ----------------

_PACKAGE_JSON = """{
  "name": "webmind-generated",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vue-tsc --noEmit && vite build",
    "preview": "vite preview",
    "lint": "eslint . --ext .ts,.vue"
  },
  "dependencies": {
    "@element-plus/icons-vue": "^2.3.1",
    "axios": "^1.7.2",
    "element-plus": "^2.7.5",
    "vue": "^3.4.31",
    "vue-router": "^4.3.3"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.0.5",
    "eslint": "^8.57.0",
    "prettier": "^3.3.2",
    "typescript": "^5.4.5",
    "vite": "^5.3.2",
    "vue-tsc": "^2.0.26"
  }
}
"""

_VITE_CONFIG = """import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
  },
})
"""

_INDEX_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>__PROJECT_NAME__</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
"""

_MAIN_TS = """import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'
import router from './router'

createApp(App).use(ElementPlus).use(router).mount('#app')
"""

_APP_VUE = """<template>
  <el-container class="wm-layout">
    <el-aside width="200px" class="wm-aside">
      <div class="wm-logo">__PROJECT_NAME__</div>
      <el-menu router :default-active="$route.path">
        <el-menu-item v-for="item in menus" :key="item.path" :index="item.path">
          {{ item.title }}
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const menus = ref(__MENUS__)
</script>

<style scoped>
.wm-layout {
  min-height: 100vh;
}
.wm-aside {
  border-right: 1px solid #ebeef5;
}
.wm-logo {
  height: 56px;
  line-height: 56px;
  text-align: center;
  font-weight: 600;
}
</style>
"""

_ROUTER_TS = """import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
__ROUTES__
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
"""

_MOCK_TS = """export interface MockRow {
  id: number
  [key: string]: unknown
}

export const mockRows: MockRow[] = [
__ROWS__
]
"""

_TSCONFIG = """{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "module": "ESNext",
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "preserve",
    "strict": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"]
    }
  },
  "include": ["src/**/*.ts", "src/**/*.vue", "vite.config.ts"]
}
"""

_README_MD = """# __PROJECT_NAME__

由 WebMind 自动生成的前端工程（Vue3 + TypeScript + Element Plus）。

## 启动

```bash
npm install
npm run dev
```

## 说明

- 页面数据当前为 `src/mock` 下的 mock 数据，需由工程师替换为真实接口
- 组件均来自组件白名单（Element Plus / 公司组件库）
- 生成结果为初稿，业务逻辑与视觉精调仍需人工确认
"""


def generate_page(page: dict[str, Any], index: int) -> tuple[str, str, str, dict[str, Any]]:
    """生成单个页面，返回 (组件名, 页面类型, SFC 内容, 元信息)。"""
    name = page.get("name") or f"页面{index + 1}"
    page_type = detect_type(name, page.get("type", ""))
    fields = _normalize_fields(page)
    funcs = _functions(page)
    component = to_identifier(name, index, suffix="View" if page_type != "login" else "")
    mock_file = to_identifier(name, index, suffix="Mock")

    search_fields = fields[:3]
    search_blocks = []
    for f in search_fields:
        control = _input_control(f, "query.%s" % f["name"])
        search_blocks.append(
            '        <el-form-item label="%s">\n%s\n        </el-form-item>' % (f["label"], control)
        )
    search_items = "\n".join(search_blocks)
    buttons = ['          <el-button type="primary" @click="handleSearch">查询</el-button>',
               '          <el-button @click="handleReset">重置</el-button>']
    if "create" in funcs:
        buttons.append('          <el-button type="success" @click="openDialog()">新增</el-button>')
    if "export" in funcs:
        buttons.append('          <el-button @click="handleSearch">导出</el-button>')
    search_buttons = "\n".join(buttons)

    form_items = _form_items(fields, "form")
    defaults = "{" + ", ".join(
        "'%s': %s" % (f["name"], "''" if f["type"] == "string" else "null") for f in fields
    ) + "}"

    if page_type == "table":
        content = (
            _TABLE_PAGE.replace("__PAGE_NAME__", name)
            .replace("__SEARCH_ITEMS__", search_items)
            .replace("__SEARCH_BUTTONS__", search_buttons)
            .replace("__COLUMNS__", _table_columns(fields))
            .replace("__FORM_ITEMS__", form_items)
            .replace("__MOCK_FILE__", mock_file)
        )
    elif page_type == "form":
        content = (
            _FORM_PAGE.replace("__PAGE_NAME__", name)
            .replace("__FORM_ITEMS__", form_items)
            .replace("__FORM_DEFAULTS__", defaults)
        )
    elif page_type == "detail":
        desc_items = "\n".join(
            '        <el-descriptions-item label="%s">{{ detail.%s }}</el-descriptions-item>'
            % (f["label"], f["name"])
            for f in fields
        )
        content = (
            _DETAIL_PAGE.replace("__PAGE_NAME__", name)
            .replace("__DESC_ITEMS__", desc_items)
            .replace("__MOCK_FILE__", mock_file)
        )
    elif page_type == "login":
        content = _LOGIN_PAGE.replace("__PAGE_NAME__", name)
    elif page_type == "config":
        content = (
            _CONFIG_PAGE.replace("__PAGE_NAME__", name)
            .replace("__FORM_ITEMS__", form_items)
            .replace("__FORM_DEFAULTS__", defaults)
        )
    else:
        content = (
            _DASHBOARD_PAGE.replace("__PAGE_NAME__", name)
            .replace("__COLUMNS__", _table_columns(fields))
            .replace("__MOCK_FILE__", mock_file)
        )

    meta = {
        "name": name,
        "type": page_type,
        "component": component,
        "mock_file": mock_file,
        "fields": fields,
        "functions": funcs,
        "path": f"/{'login' if page_type == 'login' else component.lower().replace('view', '') or 'home'}",
    }
    return component, page_type, content, meta


def generate_project(requirement: dict[str, Any], project_name: str = "WebMind 生成工程") -> dict[str, str]:
    """按需求 JSON 生成完整前端工程文件。"""
    pages = requirement.get("pages") or []
    if not pages:
        pages = [{"name": "示例列表页", "type": "table", "fields": [], "functions": []}]

    files: dict[str, str] = {}
    routes: list[str] = []
    menus: list[dict[str, str]] = []
    metas: list[dict[str, Any]] = []

    for index, page in enumerate(pages):
        component, page_type, content, meta = generate_page(page, index)
        files[f"src/views/{component}.vue"] = content
        files[f"src/mock/{meta['mock_file']}.ts"] = _MOCK_TS.replace(
            "__ROWS__", _mock_rows(meta["fields"])
        )
        path = meta["path"] if meta["path"].startswith("/") else f"/{meta['path']}"
        routes.append(
            f"  {{\n"
            f"    path: '{path}',\n"
            f"    name: '{component}',\n"
            f"    component: () => import('@/views/{component}.vue'),\n"
            f"  }},"
        )
        menus.append({"path": path, "title": meta["name"]})
        metas.append(meta)

    routes.append("  { path: '/', redirect: '%s' }," % (menus[0]["path"] if menus else "/"))

    files["package.json"] = _PACKAGE_JSON
    files["vite.config.ts"] = _VITE_CONFIG
    files["tsconfig.json"] = _TSCONFIG
    files["index.html"] = _INDEX_HTML.replace("__PROJECT_NAME__", project_name)
    files["src/main.ts"] = _MAIN_TS
    files["src/App.vue"] = _APP_VUE.replace("__PROJECT_NAME__", project_name).replace(
        "__MENUS__", str(menus).replace("'", "'")
    )
    files["src/router/index.ts"] = _ROUTER_TS.replace("__ROUTES__", "\n".join(routes))
    files["README.md"] = _README_MD.replace("__PROJECT_NAME__", project_name)
    files["webmind.meta.json"] = _meta_json(project_name, metas)

    return files


def _meta_json(project_name: str, metas: list[dict[str, Any]]) -> str:
    import json

    return json.dumps(
        {"project_name": project_name, "pages": metas, "generator": "WebMind Page Agent"},
        ensure_ascii=False,
        indent=2,
    )
