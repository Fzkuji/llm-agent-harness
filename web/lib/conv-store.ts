import { create } from "zustand";
import { useShallow } from "zustand/react/shallow";

export type MessageStatus = "pending" | "streaming" | "done" | "error" | "cancelled";

export interface ChatMsg {
  id: string;                  // msg_id from server, or local generated for user msgs
  role: "user" | "assistant" | "system";
  content: string;
  status?: MessageStatus;
  function?: string;           // if this was /run
  display?: "runtime" | "normal";
  timestamp?: number;
  attempts?: { content: string; timestamp: number }[];
  current_attempt?: number;
}

export interface ConvSummary {
  id: string;
  title: string;
  created_at?: number;
}

interface RunningTask {
  conv_id: string;
  msg_id: string;
  func_name?: string;
  started_at?: number;
}

export interface TreeNode {
  id?: string;
  type?: string;
  name?: string;
  status?: string;
  inputs?: Record<string, unknown>;
  outputs?: unknown;
  elapsed_ms?: number;
  children?: TreeNode[];
  node_type?: string;
  _in_progress?: boolean;
  [k: string]: unknown;
}

/**
 * Normalized shape.
 *
 * ``messagesById`` holds every message ever observed, keyed by its id.
 * ``messageOrder[convId]`` holds the ordered id list for one
 * conversation. Split this way so a streaming delta only touches one
 * entry in ``messagesById`` and leaves ``messageOrder`` untouched —
 * components that subscribe to the id list (e.g. the scroll container)
 * don't re-render per token, only bubbles subscribed to *their own*
 * id do. Matches the pattern Claude.ai / ChatGPT webapps use.
 *
 * Cross-conversation cleanup: removing a conversation drops its ids
 * from the order map AND removes the referenced messages from
 * ``messagesById`` (no dangling entries).
 */
interface ConvState {
  /** WS status for UI. */
  wsStatus: "connecting" | "open" | "closed";
  /** Summary for sidebar Recents list. */
  conversations: Record<string, ConvSummary>;
  /** Every message ever loaded, keyed by id. */
  messagesById: Record<string, ChatMsg>;
  /** Ordered id list per conversation. */
  messageOrder: Record<string, string[]>;
  /** Currently active conversation id. */
  currentConvId: string | null;
  /** Currently running task (show Stop button). */
  runningTask: RunningTask | null;
  /** Paused flag. */
  paused: boolean;
  /** Provider info shown in header. */
  providerInfo: { provider?: string; model?: string; type?: string } | null;
  /** Latest live Context tree per conversation. */
  trees: Record<string, TreeNode>;
  setTree: (convId: string, tree: TreeNode) => void;

  setWsStatus: (s: ConvState["wsStatus"]) => void;
  setConversations: (list: ConvSummary[]) => void;
  upsertConversation: (c: ConvSummary) => void;
  removeConversation: (id: string) => void;
  clearConversations: () => void;
  setCurrentConv: (id: string | null) => void;
  setMessages: (convId: string, msgs: ChatMsg[]) => void;
  appendMessage: (convId: string, msg: ChatMsg) => void;
  updateMessage: (convId: string, msgId: string, patch: Partial<ChatMsg>) => void;
  /** Truncate messages at and after msgId. Used by retry to drop the
   *  stale reply before the new one streams in. */
  truncateFrom: (convId: string, msgId: string) => void;
  setRunningTask: (t: RunningTask | null) => void;
  setPaused: (p: boolean) => void;
  setProviderInfo: (p: ConvState["providerInfo"]) => void;
}

export const useConvStore = create<ConvState>((set) => ({
  wsStatus: "connecting",
  conversations: {},
  messagesById: {},
  messageOrder: {},
  currentConvId: null,
  runningTask: null,
  paused: false,
  providerInfo: null,
  trees: {},
  setTree: (convId, tree) =>
    set((s) => ({ trees: { ...s.trees, [convId]: tree } })),

  setWsStatus: (s) => set({ wsStatus: s }),

  setConversations: (list) =>
    set({
      conversations: Object.fromEntries(list.map((c) => [c.id, c])),
    }),

  upsertConversation: (c) =>
    set((s) => ({ conversations: { ...s.conversations, [c.id]: c } })),

  removeConversation: (id) =>
    set((s) => {
      const rest = { ...s.conversations };
      delete rest[id];
      const order = { ...s.messageOrder };
      const doomed = order[id] ?? [];
      delete order[id];
      const byId = { ...s.messagesById };
      for (const mid of doomed) delete byId[mid];
      return {
        conversations: rest,
        messageOrder: order,
        messagesById: byId,
        currentConvId: s.currentConvId === id ? null : s.currentConvId,
      };
    }),

  clearConversations: () =>
    set({
      conversations: {},
      messagesById: {},
      messageOrder: {},
      currentConvId: null,
    }),

  setCurrentConv: (id) => set({ currentConvId: id }),

  setMessages: (convId, msgs) =>
    set((s) => {
      // Drop any old ids for this conv so stale entries don't leak.
      const byId = { ...s.messagesById };
      for (const oldId of s.messageOrder[convId] ?? []) delete byId[oldId];
      for (const m of msgs) byId[m.id] = m;
      return {
        messagesById: byId,
        messageOrder: { ...s.messageOrder, [convId]: msgs.map((m) => m.id) },
      };
    }),

  appendMessage: (convId, msg) =>
    set((s) => ({
      messagesById: { ...s.messagesById, [msg.id]: msg },
      messageOrder: {
        ...s.messageOrder,
        [convId]: [...(s.messageOrder[convId] ?? []), msg.id],
      },
    })),

  updateMessage: (_convId, msgId, patch) =>
    set((s) => {
      const cur = s.messagesById[msgId];
      if (!cur) return {};
      return {
        messagesById: { ...s.messagesById, [msgId]: { ...cur, ...patch } },
      };
    }),

  truncateFrom: (convId, msgId) =>
    set((s) => {
      const order = s.messageOrder[convId];
      if (!order) return {};
      const idx = order.indexOf(msgId);
      if (idx < 0) return {};
      const dropped = order.slice(idx);
      const nextOrder = order.slice(0, idx);
      const byId = { ...s.messagesById };
      for (const d of dropped) delete byId[d];
      return {
        messagesById: byId,
        messageOrder: { ...s.messageOrder, [convId]: nextOrder },
      };
    }),

  setRunningTask: (t) => set({ runningTask: t }),
  setPaused: (p) => set({ paused: p }),
  setProviderInfo: (p) => set({ providerInfo: p }),
}));


/**
 * Subscribe to the id list for a conversation. Returns a stable array
 * reference as long as the id sequence hasn't changed — a streaming
 * content update on an existing message will NOT re-render consumers
 * of this hook.
 */
export function useMessageIds(convId: string | null): string[] {
  return useConvStore(
    useShallow((s) =>
      convId ? s.messageOrder[convId] ?? EMPTY_IDS : EMPTY_IDS
    )
  );
}

/**
 * Subscribe to one message. Re-renders only when that specific
 * message's entry changes — other messages streaming, ids being
 * added/removed etc. don't affect this hook's consumer.
 */
export function useMessageById(msgId: string): ChatMsg | undefined {
  return useConvStore((s) => s.messagesById[msgId]);
}

const EMPTY_IDS: string[] = [];
