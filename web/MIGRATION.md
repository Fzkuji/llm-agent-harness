# Web 迁移 — 完成总结

聊天前端从「legacy vanilla JS + 全局 CSS」迁移到「React + TS + shadcn/ui」
已完成。本文件是收尾记录。

## 已完成

### 1. legacy JS 全部迁移

`public/js/` 整个目录删除。原 11 个 vanilla-JS 文件迁成 `web/lib/` 的 TS 模块:

```
chat/{chat,chat-ws,init}.js  → lib/legacy/chat-handlers.ts
shared/conversations.js      → lib/legacy/conversations.ts
shared/providers.js          → lib/legacy/providers.ts
shared/programs-panel.js     → lib/legacy/programs-panel.ts
shared/scrollbar.js          → lib/legacy/scrollbar.ts
shared/helpers.js            → lib/legacy/helpers.ts
shared/ui.js                 → lib/legacy/ui.ts
shared/state.js              → lib/legacy/state.ts
shared/history-graph.js      → lib/legacy/history-graph.ts
```

WebSocket 连接 + 全部消息分发在 `lib/use-ws.ts`。迁移后的模块仍通过
`window.*` 桥接(供 inline-onclick HTML / 模块间互调),由 `app-shell` /
`useWS` side-effect 导入;`app-shell` 的 `SHARED_JS` 已空。

### 2. shadcn/ui 组件落地

手写部件替换成 shadcn 组件:

```
<Dialog>   删除确认对话框
<Badge>    能力 / HEAD 标签
<Popover>  topbar 的 channel / branch / agent 三个下拉
<Switch>   provider / model 启用开关
<Button>   21 个文字操作按钮(设置 / programs / providers 区)
<Input>    6 个文字输入字段
```

`components/ui/popover.tsx` 是这次新加的 shadcn 组件。

### 3. CSS 收敛

`app/styles/` 从 7 个文件收到 3 个(`base` / `chat` / `detail` /
`right-dock`,去掉断档数字前缀);`02-sidebar` / `03-settings` /
`08-dropdown` 的规则随对应组件迁移而消除或并入 `base.css`。

## 还保留 bespoke 的(刻意不迁)

- 聊天消息气泡 / runtime 执行块 / 对话 DAG 图 / 执行详情面板 —— 应用
  独有的业务 UI,shadcn 没有对应组件。
- composer 的 fn-form(input/select/textarea 共用一套基础样式)、自定义
  下拉、欢迎页示例 chip、侧栏折叠钮 —— 内聚定制组件,换 shadcn 反而破坏
  内部一致性。
- `app/styles/base.css` 的 `:root` token —— 全局,shadcn 组件自身也依赖。

## 开发流程

改 `web` 源码 → `cd web && npm run build` → 仓库根
`OPENPROGRAM_WEB_PORT=3000 python -m openprogram worker restart`。
