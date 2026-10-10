# Element Plus 组件库文档（团队可用组件白名单）

> 本文件是 RAG 组件知识库的一部分。页面生成 Agent 只能从本文与 company-components.md
> 中声明的组件里选择，不得虚构组件（防幻觉白名单机制）。

## el-table 表格

用于列表页的数据展示。

常用属性：
- `:data`：数据源数组
- `border`：是否带边框
- `stripe`：是否斑马纹
- `v-loading`：加载状态

示例：

```vue
<el-table :data="tableData" border stripe v-loading="loading">
  <el-table-column prop="name" label="名称" min-width="120" />
</el-table>
```

## el-table-column 表格列

定义在 el-table 内部。

常用属性：`prop`（字段名）、`label`（表头）、`width` / `min-width`、`fixed`（right/left）。
操作列使用 `<template #default="{ row }">` 插槽放置按钮。

## el-form 表单

用于搜索区与新增/编辑弹窗。

常用属性：`:model`（绑定对象）、`:rules`（校验规则）、`label-width`、`inline`（行内表单）。

## el-form-item 表单项

定义在 el-form 内部，属性：`label`、`prop`（校验字段名）。

## el-input 输入框

`v-model` 双向绑定，属性：`placeholder`、`clearable`、`type="textarea"`、`:rows`、`show-password`。

## el-select 下拉选择

配合 el-option 使用：

```vue
<el-select v-model="form.status" placeholder="请选择状态" clearable>
  <el-option label="启用" value="启用" />
</el-select>
```

## el-option 选项

定义在 el-select 内部，属性：`label`、`value`。

## el-button 按钮

属性：`type`（primary / success / danger / info）、`link`（文字按钮）、`@click` 事件。
列表页操作列统一使用 `link` 文字按钮。

## el-dialog 弹窗

新增/编辑表单容器，属性：`v-model`（显隐）、`title`、`width`。
底部操作区使用 `#footer` 插槽。

## el-pagination 分页

属性：`background`、`layout="total, sizes, prev, pager, next"`、`:total`、
`v-model:current-page`、`v-model:page-size`。

## el-card 卡片

页面容器，属性：`shadow="never"`，`#header` 插槽放置标题。

## el-date-picker 日期选择

属性：`type="date"`、`value-format="YYYY-MM-DD"`、`placeholder`。
列表搜索区与表单均使用 `YYYY-MM-DD` 格式。

## el-switch 开关

用于布尔字段，`v-model` 绑定 boolean 值。

## el-input-number 数字输入

用于数值字段，属性：`:min="0"`。

## el-descriptions 描述列表

详情页字段展示，属性：`:column="2"`、`border`。
子项使用 el-descriptions-item。

## el-descriptions-item 描述项

属性：`label`，内容用插槽或默认内容。

## el-row 栅格行

`:gutter` 控制间距，配合 el-col 使用。

## el-col 栅格列

`:span` 取值 0-24，常用 6 / 8 / 12。

## el-menu 菜单

侧边导航，属性：`router`（开启路由模式）、`:default-active`。

## el-menu-item 菜单项

属性：`index`（对应路由 path）。

## el-container 布局容器

页面骨架，配合 el-aside（侧边）、el-main（主区域）使用。

## el-aside 侧边栏

布局容器左侧区域，属性：`width`（如 `210px`）。通常放置 Logo 与 el-menu 导航。

## el-main 主内容区

布局容器右侧主区域，承载路由视图（`router-view`）。

## 团队约定

1. 列表页固定结构：卡片 → 搜索表单（最多 3 个字段）→ 表格 → 分页 → 新增/编辑弹窗
2. 所有请求先走 mock 数据，真实接口由工程师接入
3. 组件必须使用 `v-model` 绑定，禁止直接操作 DOM
4. 弹窗表单必须包含取消 / 确定两个按钮
