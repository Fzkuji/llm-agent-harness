# Web 迁移交接 — WS 层 slice F 余下部分

新会话直接说「读 web/MIGRATION.md,继续 slice F」即可。

分支:`phase3-message-flip`(领先 main 23 个 commit,全部 build 过、浏览器实测过)。
本地:`web` 跑在 `:3000`,backend `:8109`。

---

## 已完成(不要重做)

聊天页面用户能看到、能交互的一切都已经是 React:消息流 / 消息气泡 /
执行树(`<ExecutionTree>`)/ 消息悬浮操作栏(`<MessageActions>`)/
composer / 顶栏三个菜单(模型 `<AgentSelector>` / 分支 `<BranchMenu>` /
channel `<ChannelMenu>`)/ 右栏分支面板(`<BranchesPanel>`)/ welcome /
slash 菜单。

WebSocket **连接** 和 **25 种消息的分发** 都已经在 React 侧:
`web/lib/use-ws.ts` 的 `useWS` hook 拥有 socket(开/重连/keepalive/
teardown),它的 `dispatch()` 函数分发每一种消息类型。

已删除的 legacy 文件:`tree.js` `tree-render.js` `tree-retry.js`
`tree-log.js`、`message-actions.js` `message-actions-edit.js`
`message-actions-nav.js`。`public/js/chat/` 从 12 个文件减到 3 个。

---

## 当前架构 — 关键理解

`useWS` hook(`web/lib/use-ws.ts`)的 `dispatch(msg)`:
- 已迁的类型(pong / session_reload / branch_* / provider_* /
  agent_settings_changed / running_task / full_tree / event /
  functions_list / history_list / attempt_switched / channel_accounts /
  branches_list / branch_checked_out / session_loaded / sessions_list /
  session_channel_updated)→ 在 hook 里直接处理,大多是 `w.someGlobal?.()`
  调一个 legacy window 全局函数。
- chat_ack / chat_response → 先 `window.__applyChatWsMessage(msg)`
  喂 React store reducer,再调 `window._wsHandleChatAck/ChatResponse`。
- status → `window._wsHandleStatus(msg)`。

也就是说:**分发是 React 的,handler 函数体还是 legacy JS**,通过
`window.*` 全局被 hook 调用。slice F 余下的工作 = 把这些 handler 函数体
用 TS 重写、把 legacy 全局搬进 React store。这是纯内部重构,零行为变化。

---

## 还剩什么(slice F 余下部分)

### 进度

- **F1 已完成**(commit `b2d5236`)— send 路径归 React。`legacy-send.ts`
  直接发 `chat` WS payload,chat.js 删掉 `sendMessage` + bubble 构造函数。
- **F2 已完成**(commit `7d91297`)— chat-ws.js 精简成纯记账。删了 5 个
  no-op 桩 + `_handleInboundUserMessage` + legacy retry tree-push。
- **F3 起未做** —— 下面从「conversations.js 数据层」继续。

### 剩余 legacy 文件

```
public/js/chat/chat.js      176  retry 系列 / submitFollowUp / addAssistantMessage
public/js/chat/chat-ws.js   178  handleChatResponse 记账 + _handleContextStats
                                 / _handleStatusResponse / _handleFollowUpQuestion
public/js/chat/init.js      257  _wsHandleChatAck/ChatResponse/Status
                                 / _handleSessionsList / _handleRunningTask
                                 / setRunActive / _rehydrateToolsUI IIFE
public/js/shared/conversations.js  605  loadSessionData / renderSessionMessages
                                        / newSession / fetchBranches 等数据层
                                        / channel helpers / extractMessagesFromTree
                                        / handleAttemptSwitched
public/js/shared/state.js   48   全局变量:ws / trees / conversations
                                 / currentSessionId / _agentSettings
                                 / pendingResponses / isPaused / isRunning 等
public/js/shared/providers.js 282  loadProviders / loadAgentSettings
                                   / updateProviderBadge / updateAgentBadges
public/js/shared/ui.js      679  updateStatus / showDetail / popover 逻辑 / 等
public/js/shared/helpers.js 289  renderMd / escHtml / escAttr / scrollToBottom
                                 / setWelcomeVisible / appendToChat(已 no-op)
public/js/shared/history-graph.js 1245  右栏 DAG 图(SVG 渲染器,自包含)
public/js/shared/programs-panel.js 81  renderFunctions / loadProgramsMeta
public/js/shared/scrollbar.js 166  自定义滚动条
```

### 建议的子步骤(每步一轮、各自能独立验证、保持页面可用)

1. **chat.js 的 send 路径** — `sendMessage` 现在被 composer 的
   `sendChatMessage` bridge(`web/components/chat/composer/legacy-send.ts`)
   通过 `window.sendMessage` 调用。`sendMessage` 真正需要做的只是
   `ws.send({action:'chat',...})` + `setRunning(true)`。把这段直接搬进
   `legacy-send.ts`(用 `useWS` 的 wsSend 或 `window.ws`),然后 `sendMessage`
   /`addUserMessage`/`addAssistantPlaceholder`/`addRuntimeBlockPending`/
   `buildRuntimeBlockHtml`/`addAssistantMessage` 这一串就能删——它们产生的
   DOM 早就被 `appendToChat`(no-op)丢弃了。`retryCurrentBlock` /
   `retryChatQuery` / `stopAndRetry` 还被 React 组件 `window.*` 调用,
   要么一起搬,要么留着。

2. **chat-ws.js 的 handler** — `handleChatResponse` 的「终结记账」段
   (往 `conversations[].messages` push、更新标题、`refreshTokenBadge`、
   `fetchBranches`)+ `_handleContextStats`(token badge,写 `#contextStats`
   + `window._renderTokenBadge`)+ `_handleStatusResponse` +
   `_handleFollowUpQuestion`(往 `#runtime_pending` 注入跟进输入框 —— 注意
   `#runtime_pending` 现在是 React `<RuntimeBlock>` 的节点)。把这些重写成
   React/store 逻辑或保留为 thin 函数。`_handleStreamEvent`/`_handleTreeUpdate`/
   `_handleRuntimeResult`/`_handleChatResult`/`_handleRetryResult` 已经是
   no-op 桩,可连同 `handleChatResponse` 的对应 dispatch 分支一起删。

3. **conversations.js 数据层** — `loadSessionData` / `renderSessionMessages`
   现在的核心作用是调 `window.__feedStoreFromConv(conv)` 把会话喂进 React
   store(其余是 history graph、run_active、pivot 滚动)。`_handleSessionsList`
   填 `window.conversations`(React 侧栏经 `useLegacyGlobals` 读它)。
   `fetchBranches` / `_onBranchesListMessage` 是分支数据层(`<BranchMenu>`/
   `<BranchesPanel>` 复用)。channel helpers(`fetchChannelAccounts` 等)被
   `<ChannelMenu>` 复用。把这些搬进 store / React query。

4. **state.js 全局并进 store** — `conversations` / `trees` / `_agentSettings`
   等全局是 1、2、3 步迁完后才能干净搬走的最后一环。`useLegacyGlobals`
   (`web/components/sidebar/use-legacy-globals.ts`)是 React 读这些全局的
   现有桥;迁完后换成 store 订阅、删掉这个桥。

5. **收尾** — 删 `init.js` / `chat.js` / `chat-ws.js` / `conversations.js`
   / `state.js`,从 `web/components/page-shell.tsx` 的 `JS_FILES_BY_PAGE`
   和 `web/components/app-shell.tsx` 的 `SHARED_JS` 里移除。
   `useWS` hook 的 `WsWindow` 接口里那些 `window.*` 字段也跟着删。
   `providers.js` / `ui.js` / `helpers.js` / `history-graph.js` /
   `programs-panel.js` / `scrollbar.js` 是否也迁,看精力 —— 它们不阻塞
   chat,history-graph 是个自包含的 1245 行 SVG 渲染器,单独评估。

### 注意的坑

- `appendToChat`(helpers.js)已经是 no-op —— legacy 的所有气泡构建函数
  还在跑,但 DOM 节点被丢弃。删它们时确认没有别的副作用(往
  `conversations[]` 写之类)。
- `#runtime_pending` 这个 id 现在由 React `<RuntimeBlock>` 在 streaming
  时渲染;legacy 若还往它注入会和 React 打架。
- 纯行为不变的重构,每步 build + 浏览器实测:加载会话 / 发普通 chat /
  `/run` / 重试 / 分支切换 / 新建会话。
- `git add` 要明确列文件 —— 仓库里有会话开始前就存在的、与本迁移无关的
  未提交改动(`pdf_figures` 等),别用 `git add -A` 把它们卷进 commit。

### 开发流程

改 `web` 源码:`cd web && npm run build`,然后
`OPENPROGRAM_WEB_PORT=3000 python -m openprogram worker restart`。
改 `public/js/*` 不用 build,但要 worker restart + 浏览器硬刷新。

---

## 建议

这个分支本身是个完整、测过、可用的里程碑 —— 可以先 merge 回 main 锁住,
再在新分支上做 slice F 余下部分(纯内部清理,零行为变化,不阻塞功能)。
