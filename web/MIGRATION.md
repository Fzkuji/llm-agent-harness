# 消息流 React 迁移 — 交接文档

新会话直接说「读 web/MIGRATION.md，继续 Phase 3」即可。

## 目标

把 `/chat` 的消息流渲染从 legacy vanilla JS(`public/js/chat/chat.js` +
`chat-ws.js`)迁到 React。**只迁消息气泡渲染**,`chat-ws.js` 里非渲染的
handler(token badge、执行树、branch、follow-up)保留。

## 已完成(已提交)

- **Phase 1** — store + WS reducer。`web/lib/session-store.ts`(`messagesById` /
  `messageOrder`、`ChatMsg` / `ChatToolCall`、`useMessageIds` / `useMessageById`)、
  `web/lib/chat-stream.ts`(`applyChatWsMessage` reducer:`chat_ack` /
  `chat_response` 的 `stream_event` / `result` / `error` / `cancelled` /
  `user_message`;`appendLocalUserTurn` helper)。
- **Phase 2** — React 组件,`web/components/chat/messages/`:`message-list.tsx`、
  `user-bubble.tsx`、`assistant-bubble.tsx`、`thinking-block.tsx`、
  `tool-card.tsx`、`runtime-block.tsx`、`use-stick-to-bottom.ts`、
  `markdown.ts`(含 `useMarkdownReady` hook)。复用 legacy CSS 类
  (`.message`、`.chat-stream-body`、`.chat-thinking`、`.chat-tools` 等,
  全部在 `web/app/styles/05-chat.css`,按 `data-collapsed` 属性折叠)。
  组件已逐个视觉验证过(预览路由已删)。

reducer + 组件这条链路是好的,起点干净。

## 待做 — Phase 3 切换(原子的)

消息流是一个原子单位:用户/助手气泡在同一个有序容器 `#chatMessages` 里交错,
没法按气泡类型分步迁。要换就整体换。五处协调改动:

1. **喂 store(WS)** — `public/js/chat/init.js` 的 `handleMessage`,对
   `chat_ack` 和 `chat_response` 两个 envelope 额外调 `applyChatWsMessage(msg)`
   (从 React 侧 import,或挂个 `window.__applyChatWsMessage`)。

2. **喂 store(历史)** — `public/js/shared/conversations.js` 的
   `renderSessionMessages(conv)`(约 line 1196)改成把 `conv.messages` 映射成
   `ChatMsg[]` 灌进 `setMessages(sessionId, ...)`,不再 build DOM。注意
   legacy message 形状有 `msg.blocks`(thinking/tools 结构),映射逻辑参考
   `chat-ws.js:426` `_renderAssistantBlocks`。

3. **喂 store(本地发送)** — composer 发送路径
   (`web/components/chat/composer/legacy-send.ts` 或 `chat.js sendMessage`)
   调 `appendLocalUserTurn`,让用户气泡立即出现。

4. **挂 MessageList** — `web/components/page-shell.tsx` 的
   `stripLegacyChatChrome()`(约 line 100-135,已经在那里建
   `#composer-mount` / `#welcome-mount` / `#topbar-mount`)加一个
   `#messages-mount` 占位 div(放在 `#chatMessages` 里),app-shell.tsx
   的 `findMounts` effect(约 line 132-155)加上找它,portal
   `<MessageList sessionId={...}/>` 进去。

5. **掐掉旧渲染** — 把 legacy 的消息气泡渲染函数改成 no-op,但**保留**
   非渲染 handler。要掐的:`chat.js` 的 `addUserMessage` /
   `addAssistantPlaceholder` / `addAssistantMessage` / `addRuntimeBlockPending`;
   `chat-ws.js` 的 `_renderChatStreamEvent`(stream 渲染)/
   `_handleInboundUserMessage`(DOM 部分)/ `_renderAssistantBlocks`;
   `conversations.js renderSessionMessages` 的 DOM build;
   `init.js _handleRunningTask` 里 `_chat` 的 ghost 气泡(line 360-393)。
   **保留**:`chat-ws.js` 的 `_handleContextStats`、`_handleStatusResponse`、
   `_handleTreeUpdate`、`_handleRetryResult`、`_handleFollowUpQuestion`。

## 关键文件 + 行号

| 文件 | 作用 |
|---|---|
| `public/js/chat/init.js` | WS 创建(line 26)、`handleMessage` envelope dispatch(58-305)、`_handleRunningTask`(355) |
| `public/js/chat/chat-ws.js` | `handleChatResponse`(3-126)、`_renderChatStreamEvent`(273)、`_renderAssistantBlocks`(426) |
| `public/js/chat/chat.js` | `sendMessage` / `addUserMessage` / `addAssistantPlaceholder` / runtime block builders |
| `public/js/shared/conversations.js` | `renderSessionMessages`(1189)、`newSession`(1037)、`_clearChatMessages`(新加的 helper) |
| `public/js/shared/helpers.js` | `appendToChat` → `#chatMessages`(116)、`setWelcomeVisible`(127)、`renderMd`(20) |
| `web/components/page-shell.tsx` | `stripLegacyChatChrome` 建 mount 占位(100-135) |
| `web/components/app-shell.tsx` | `findMounts` portal 挂载(132-155)、pathname effect(160-218) |
| `web/lib/chat-stream.ts` | reducer |
| `web/components/chat/messages/` | React 组件 |

## 协议(reducer 已按此解析)

- envelope `{type, data}`。`type` = `chat_ack` / `chat_response` / `session_loaded` / ...
- `chat_response` 的 `data.type` = `stream_event` / `result` / `error` /
  `cancelled` / `user_message` / `context_stats` / `status` / `tree_update` /
  `retry_result` / `follow_up_question`
- `stream_event` 的 `data.event.type` = `text` / `thinking` / `tool_use` /
  `tool_result` / `status`
- 助手回复在 store 里 key 为 `<msg_id>_reply`,用户回合 key 为裸 `msg_id`

## 坑

- `chat-ws.js` 远不止渲染消息——删整个文件会废掉 token badge、执行树、
  attempt 导航、follow-up、branch 同步、peer 消息。只能 no-op 渲染函数。
- `#chatMessages` 不能 `innerHTML = ''` 清空——会销毁 React portal 的
  `#welcome-mount`(已修过一次,见 `_clearChatMessages`)。MessageList 的
  `#messages-mount` 同理。
- `html { font-size: 14px }`,Tailwind 的 rem 全部 ×0.875,像素值要写死
  arbitrary value(`h-[32px]`)。
- runtime block(`/run` 的执行块)带执行树、attempt 导航、footer,最复杂,
  `RuntimeBlock` 组件目前是简化版,Phase 3 要补全或保留 legacy runtime 渲染。
- retry / branch / follow-up 这些边角只有真跑才暴露,必须在 live chat 上联调。

## 开发流程

改完 web 源码:`cd web && npm run build`,然后
`OPENPROGRAM_WEB_PORT=3000 python -m openprogram worker restart`(web 在
:3000,backend 在 :8109)。改 `public/js/*` 不用 build,但要重启 worker +
浏览器硬刷新。
