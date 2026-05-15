"use client";

/**
 * User message bubble — React port of legacy `addUserMessage` markup.
 * Plain text content (escaped); user turns are never markdown-rendered.
 *
 * The legacy hover action bar (copy / edit / retry / branch) is still
 * vanilla — `ensureMessageActions` wires it onto the bubble's DOM node
 * after mount, reusing the legacy implementation.
 */
import { useEffect, useRef } from "react";

import type { ChatMsg } from "@/lib/session-store";

export function UserBubble({ msg }: { msg: ChatMsg }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
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
  }, [msg.id]);

  return (
    <div className="message user" data-msg-id={msg.id} ref={ref}>
      <div className="message-header">
        <div className="message-avatar user-avatar">U</div>
        <div className="message-sender">You</div>
      </div>
      <div className="message-content">{msg.content}</div>
    </div>
  );
}
