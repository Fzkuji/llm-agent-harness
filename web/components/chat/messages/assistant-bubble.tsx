"use client";

/**
 * Assistant message bubble — React port of the legacy
 * `.message.assistant` + `.chat-stream-body` scaffold.
 *
 * Layout order matches chat-ws.js: Thinking block, then the Tool-calls
 * card, then the answer text. While the turn is still streaming with
 * nothing rendered yet, a typing indicator stands in.
 */
import { useEffect, useRef } from "react";

import type { ChatMsg } from "@/lib/session-store";

import { renderMarkdown, useMarkdownReady } from "./markdown";
import { ThinkingBlock } from "./thinking-block";
import { ToolsBlock } from "./tool-card";

function TypingIndicator() {
  return (
    <div className="typing-indicator">
      <div className="dot" />
      <div className="dot" />
      <div className="dot" />
    </div>
  );
}

export function AssistantBubble({ msg }: { msg: ChatMsg }) {
  // Subscribed so the bubble re-renders once `renderMd` lands and the
  // markdown can be rendered for real instead of escaped.
  useMarkdownReady();
  const streaming = msg.status === "streaming" || msg.status === "pending";
  const tools = msg.tools ?? [];
  const hasContent = !!msg.content;
  const empty = !hasContent && !msg.thinking && tools.length === 0;

  // Wire the legacy hover action bar onto the bubble once the turn is
  // settled (a streaming bubble has no actions yet). Re-run when the
  // turn finalizes so the bar reflects the final state.
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (streaming) return;
    const ensure = (window as unknown as {
      ensureMessageActions?: (el: HTMLElement) => void;
    }).ensureMessageActions;
    if (ensure && ref.current) {
      try {
        ensure(ref.current);
      } catch {
        /* ignore */
      }
    }
  }, [msg.id, streaming]);

  return (
    <div className="message assistant" data-msg-id={msg.id} ref={ref}>
      <div className="message-header">
        <div className="message-avatar bot-avatar">A</div>
        <div className="message-sender">Agentic</div>
      </div>

      {msg.status === "error" ? (
        <div className="error-content">{msg.content || "Request failed."}</div>
      ) : empty && streaming ? (
        <TypingIndicator />
      ) : (
        <div className="chat-stream-body">
          {msg.thinking ? (
            <ThinkingBlock text={msg.thinking} streaming={streaming} />
          ) : null}
          {tools.length > 0 ? <ToolsBlock tools={tools} /> : null}
          {hasContent ? (
            <div
              className="chat-text message-content"
              dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }}
            />
          ) : null}
        </div>
      )}
    </div>
  );
}
