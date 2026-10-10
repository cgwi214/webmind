# 公司私有组件库（wm- 前缀）

> 业务组件，优先级高于 Element Plus 基础组件：命中业务场景时必须优先使用 wm- 组件。

## wm-page-header 页面头

列表页 / 表单页统一的页头，含标题、返回按钮、右上角操作区。

属性：`title`、`show-back`、`subtitle`。

```vue
<wm-page-header title="用户列表" subtitle="共 128 条" />
```

## wm-status-tag 状态标签

把状态码渲染成约定颜色的标签。

属性：`status`（success / warning / danger / info）、`text`。

## wm-dict-select 字典下拉

从后端字典接口拉取选项，避免前端硬编码枚举。

属性：`dict-code`、`v-model`、`clearable`。

## wm-upload-file 文件上传

封装了公司 OSS 上传逻辑。

属性：`v-model`、`accept`、`max-size`、`limit`。
事件：`@success`、`@remove`。

## wm-crud-table 增删改查表格

内置搜索区 + 表格 + 分页 + 新增/编辑弹窗的一体化业务组件。

属性：`columns`、`api`、`search-fields`、`row-actions`。

## wm-amount 金额展示

按公司财务规范格式化金额（千分位 + 两位小数 + 货币符号）。

属性：`value`、`currency`。

## 使用约定

1. 枚举字段统一用 wm-dict-select，禁止在页面里写死选项
2. 状态展示统一用 wm-status-tag
3. 金额相关一律用 wm-amount
4. 标准 CRUD 页面优先用 wm-crud-table，减少生成代码量
