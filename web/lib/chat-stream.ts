/**
 * Chat-stream WS reducer.
 *
 * Translates the backend's chat WebSocket protocol into session-store
 * mutations — the data half of the React message-stream port. Pure:
 * call `applyChatWsMessage(msg)` with a parsed `{ type, data }`
 * envelope and it updates `messagesById` / `messageOrder`.
 *
 * NOT attached to a socket here. Phase 3 (cutover) wires it onto the
 * shared `window.ws` and removes the legacy `chat-ws.js` renderer.
 * Until then this module is dormant — building it is additive and
 * leaves the live (legacy) chat untouched.
 *
 * Protocol (mirrors `public/js/chat/chat-ws.js`):
 *   chat_ack       { session_id, msg_id }
 *       → the user turn registered; create the assistant reply
 *         placeholder so streaming deltas have somewhere to land.
 *   chat_response  { type, msg_id, session_id, ... }
 *       type === "stream_event"  { event: { type, ... } }
 *           text        → append to reply.content
 *           thinking    → append to reply.thinking
 *           tool_use    → push a ChatToolCall (status "running")
 *           tool_result → fill the matching tool's result + status
 *       type === "result" | "error" | "cancelled"
 *           → finalize the reply (status + any final text)
 *   other chat_response types (status / tree_update / context_stats /
 *   user_message / follow_up_question) are NOT message-stream concerns
 *   and are left to their own handlers.
 */

import { useSessionStore, type ChatMsg, type ChatToolCall } from "./session-store";

interface StreamEvent {
  type: "text" | "thinking" | "tool_use" | "tool_result";
  text?: string;
  tool?: string;
  input?: string;
  tool_call_id?: string;
  result?: string;
  is_error?: boolean;
  elapsed?: number;
}

interface ChatResponseData {
  type: string;
  msg_id?: string;
  session_id?: string;
  function?: string;
  display?: "runtime" | "normal";
  event?: StreamEvent;
  content?: string;
  text?: string;
  cancelled?: boolean;
  context_tree?: unknown;
  /** Live execution tree carried by `tree_update` envelopes. */
  tree?: unknown;
  usage?: unknown;
  attempts?: { content: string; timestamp: number; tree?: unknown; usage?: unknown }[];
  current_attempt?: number;
}

interface WsEnvelope {
  type: string;
  data?: unknown;
}

/** Store key for an assistant turn's reply bubble. The user turn is
 *  keyed by its bare `msg_id`; the reply gets a `_reply` suffix so the
 *  two never collide in `messagesById`. */
function replyId(msgId: string): string {
  return `${msgId}_reply`;
}

export function applyChatWsMessage(msg: WsEnvelope): void {
  if (msg.type === "chat_ack") {
    handleAck(msg.data as { session_id?: string; msg_id?: string });
    return;
  }
  if (msg.type === "chat_response") {
    handleResponse(msg.data as ChatResponseData);
  }
}

/** A `chat_ack` only tells us which conversation the turn belongs to —
 *  for a brand-new chat that's the first time the server-assigned id is
 *  known. The assistant reply bubble is NOT created here: doing so
 *  would land it in `messageOrder` before the user turn (whose
 *  `user_message` broadcast can arrive either side of the ack). The
 *  reply is created lazily on the first stream event / result instead,
 *  by which point the user turn is already in place. */
function handleAck(d: { session_id?: string; msg_id?: string } | undefined): void {
  if (!d?.session_id) return;
  useSessionStore.getState().setCurrentConv(d.session_id);

  // The server does NOT echo a web-originated user turn back as a
  // `user_message` broadcast (only channel/peer turns get that). So the
  // user bubble is created here, from the text the composer stashed on
  // `window.__pendingUserText` just before sending. `chat_ack.msg_id`
  // IS the user turn's id — keying it here lets the reply (`_reply`
  // suffix) and the later result anchor to the same turn.
  const w = window as unknown as { __pendingUserText?: string };
  const text = w.__pendingUserText;
  if (d.msg_id && typeof text === "string" && text) {
    w.__pendingUserText = undefined;
    const isRun = /^(run|create|fix)\s/i.test(text);
    appendLocalUserTurn(
      d.session_id,
      d.msg_id,
      text,
      isRun ? "runtime" : undefined,
    );
    // Create the reply bubble right away (after the user turn, so the
    // order is right) — gives an immediate typing indicator / pending
    // runtime block instead of a gap until the first stream event.
    const rid = replyId(d.msg_id);
    ensureReply(d.session_id, rid);
    if (isRun) {
      useSessionStore
        .getState()
        .updateMessage(d.session_id, rid, { display: "runtime" });
    }
  }
}

/** Fetch the assistant reply bubble, creating it on first use. Keeps
 *  reply creation after the user turn in `messageOrder`. */
function ensureReply(sid: string, rid: string): ChatMsg {
  const store = useSessionStore.getState();
  const existing = store.messagesById[rid];
  if (existing) return existing;
  store.appendMessage(sid, {
    id: rid,
    role: "assistant",
    content: "",
    status: "streaming",
  });
  return useSessionStore.getState().messagesById[rid];
}

function handleResponse(d: ChatResponseData | undefined): void {
  if (!d || !d.msg_id) return;
  // Stream / result envelopes don't always carry `session_id` — the
  // legacy renderer only ever keyed off `msg_id`. Fall back to the
  // store's current conversation (set by the preceding `chat_ack`).
  const sid =
    d.session_id || useSessionStore.getState().currentSessionId || undefined;
  if (!sid) return;

  // A user turn — either echoed back by the server or broadcast from a
  // peer. Keyed by the bare `msg_id` (the reply takes the `_reply`
  // suffix), so it never collides with its own assistant bubble.
  if (d.type === "user_message") {
    handleUserMessage(sid, d);
    return;
  }

  const rid = replyId(d.msg_id);

  // Live execution tree for a streaming `/run` — store it on the reply
  // so <RuntimeBlock />'s <ExecutionTree /> renders it as it grows.
  if (d.type === "tree_update" && d.tree) {
    ensureReply(sid, rid);
    useSessionStore.getState().updateMessage(sid, rid, {
      display: "runtime",
      function: d.function,
      contextTree: d.tree as never,
    });
    return;
  }

  if (d.type === "stream_event" && d.event) {
    // A `/run` turn: tag the reply as a runtime turn up front so
    // <MessageList /> routes it to <RuntimeBlock />, which renders the
    // `#runtime_pending` host the legacy CLI/tree stream handlers
    // target. `_chat` / `chat` are plain chat — left as assistant.
    const isRuntime =
      d.display === "runtime" ||
      (!!d.function && d.function !== "_chat" && d.function !== "chat");
    if (isRuntime) {
      ensureReply(sid, rid);
      useSessionStore.getState().updateMessage(sid, rid, {
        display: "runtime",
        function: d.function,
      });
    }
    applyStreamEvent(sid, rid, d.event);
    return;
  }
  if (d.type === "result" || d.type === "error" || d.type === "cancelled") {
    finalize(sid, rid, d);
  }
}

function handleUserMessage(sid: string, d: ChatResponseData): void {
  if (!d.msg_id) return;
  const store = useSessionStore.getState();
  if (store.messagesById[d.msg_id]) return;
  store.appendMessage(sid, {
    id: d.msg_id,
    role: "user",
    content: d.content ?? d.text ?? "",
    display: d.display === "runtime" ? "runtime" : undefined,
    status: "done",
  });
}

/**
 * Optimistically add the just-sent user turn to the store so the
 * bubble appears immediately — before the server echoes it back.
 * The composer's send path calls this; the later `user_message` /
 * `chat_ack` for the same id is de-duped by id.
 */
export function appendLocalUserTurn(
  sessionId: string,
  msgId: string,
  text: string,
  display?: "runtime" | "normal",
): void {
  const store = useSessionStore.getState();
  if (store.messagesById[msgId]) return;
  store.appendMessage(sessionId, {
    id: msgId,
    role: "user",
    content: text,
    display: display === "runtime" ? "runtime" : undefined,
    status: "done",
  });
}

function applyStreamEvent(sid: string, rid: string, evt: StreamEvent): void {
  const store = useSessionStore.getState();
  const cur = ensureReply(sid, rid);

  switch (evt.type) {
    case "text":
      store.updateMessage(sid, rid, {
        content: cur.content + (evt.text ?? ""),
        status: "streaming",
      });
      break;
    case "thinking":
      store.updateMessage(sid, rid, {
        thinking: (cur.thinking ?? "") + (evt.text ?? ""),
        status: "streaming",
      });
      break;
    case "tool_use": {
      const tools: ChatToolCall[] = [...(cur.tools ?? [])];
      tools.push({
        id: evt.tool_call_id || `t_${Date.now()}_${tools.length}`,
        tool: evt.tool || "?",
        input: evt.input ?? "",
        status: "running",
      });
      store.updateMessage(sid, rid, { tools, status: "streaming" });
      break;
    }
    case "tool_result": {
      const tools = (cur.tools ?? []).map((t): ChatToolCall =>
        t.id === evt.tool_call_id
          ? {
              ...t,
              result: evt.result ?? "",
              isError: !!evt.is_error,
              status: evt.is_error ? "error" : "done",
            }
          : t,
      );
      store.updateMessage(sid, rid, { tools });
      break;
    }
  }
}

function finalize(sid: string, rid: string, d: ChatResponseData): void {
  const store = useSessionStore.getState();
  const cur = ensureReply(sid, rid);

  const status: ChatMsg["status"] =
    d.type === "error"
      ? "error"
      : d.type === "cancelled" || d.cancelled
        ? "cancelled"
        : "done";

  const patch: Partial<ChatMsg> = { status, rawType: d.type };
  if (d.function) patch.function = d.function;
  if (d.display) patch.display = d.display;
  // A `/run` result carries the execution tree, usage and attempt
  // history that the runtime block renders in its body / footer.
  if (d.context_tree) patch.contextTree = d.context_tree as never;
  if (d.usage) patch.usage = d.usage;
  if (d.attempts) patch.attempts = d.attempts as never[];
  if (typeof d.current_attempt === "number") {
    patch.current_attempt = d.current_attempt;
  }

  // `result` carries the full final text. Streaming usually already
  // built `content` delta-by-delta; only fall back to the result's
  // text when nothing streamed (e.g. a non-streaming run).
  const finalText = d.content ?? d.text;
  if (finalText && !cur.content) patch.content = finalText;

  // Any tool still "running" at terminal time gets closed out — no
  // tool_result will arrive after the turn ends.
  if (cur.tools?.some((t) => t.status === "running")) {
    patch.tools = cur.tools.map((t): ChatToolCall =>
      t.status === "running" ? { ...t, status: "done" } : t,
    );
  }

  store.updateMessage(sid, rid, patch);
}
