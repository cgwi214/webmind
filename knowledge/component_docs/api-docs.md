# 接口调用规范与 API 文档

> 页面生成时接口一律生成 mock 实现，真实接口由工程师接入。本文件用于约束生成代码的
> 请求层写法，避免生成不可维护的调用方式。

## 请求层约定

1. 统一封装在 `src/utils/request.ts`，业务页面不直接调用 axios
2. 接口地址统一以 `/api` 开头，禁止在页面里硬编码域名
3. 列表接口返回结构：`{ list: [], total: 0 }`
4. 所有请求必须处理 loading 与异常提示

## 列表查询接口

```
GET /api/{module}/list
参数：page, size, 以及搜索字段
返回：{ list: [...], total: number }
```

## 详情接口

```
GET /api/{module}/detail?id={id}
```

## 新增 / 编辑接口

```
POST /api/{module}/save
PUT  /api/{module}/update
```

## 删除接口

```
DELETE /api/{module}/delete?id={id}
```

## Mock 数据约定

- mock 文件放在 `src/mock/`，命名与页面组件对应（如 `UserListMock.ts`）
- mock 数据至少 8 条，字段与需求声明保持一致
- 页面通过 `import { mockRows } from '@/mock/xxx'` 引用，禁止内联长数组

## uni-app 端差异

- Web 端 axios → uni-app `uni.request`
- 请求封装见 `src/utils/request.ts`（多端适配 Agent 自动生成）
- 小程序端域名必须加入后台合法域名列表（人工操作）
