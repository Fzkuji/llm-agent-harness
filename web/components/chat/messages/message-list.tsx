"use client";

/**
 * Message list — the React message stream.
 *
 * Subscribes to the session store's per-conversation id list and
 * renders one bubble per id. Each `MessageRow` subscribes to *its own*
 * message entry (`useMessageById`), so a streaming delta re-renders
 * only the affected bubble — not the whole list.
 *
 * Phase 2: this component is built but not yet mounted. Phase 3 wires
 * it into the chat route in place of the legacy chat-ws.js renderer.
 */
import { memo } from "react";

import {
  useMessageById,
  useMessageIds,
  type ChatMsg,
} from "@/lib/session-store";

import { AssistantBubble } from "./assistant-bubble";
import { RuntimeBlock } from "./runtime-block";
import { UserBubble } from "./user-bubble";
import { useStickToBottom } from "./use-stick-to-bottom";

function dispatch(msg: ChatMsg) {
  if (msg.role === "system") {
    return <div className="message system">{msg.content}</div>;
  }
  if (msg.display === "runtime") {
    // A `/run` turn renders as ONE runtime block, owned by the
    // assistant reply (it carries the result + the `function`
    // signature). The paired user message only holds the raw command
    // — drop it so the command isn't shown twice.
    if (msg.role === "user") return null;
    return <RuntimeBlock msg={msg} />;
  }
  if (msg.role === "user") {
    return <UserBubble msg={msg} />;
  }
  return <AssistantBubble msg={msg} />;
}

const MessageRow = memo(function MessageRow({ id }: { id: string }) {
  const msg = useMessageById(id);
  if (!msg) return null;
  return dispatch(msg);
});

export function MessageList({ sessionId }: { sessionId: string | null }) {
  const ids = useMessageIds(sessionId);
  // The scroll container self-pins via a ResizeObserver on its
  // children, so streaming deltas and new messages both keep the view
  // at the bottom without a dependency being threaded here.
  const scrollRef = useStickToBottom();

  return (
    <div className="chat-messages" ref={scrollRef}>
      {ids.map((id) => (
        <MessageRow key={id} id={id} />
      ))}
    </div>
  );
}
