"use client";

/**
 * User message bubble — React port of legacy `addUserMessage` markup.
 * Plain text content (escaped); user turns are never markdown-rendered.
 */
import type { ChatMsg } from "@/lib/session-store";

export function UserBubble({ msg }: { msg: ChatMsg }) {
  return (
    <div className="message user" data-msg-id={msg.id}>
      <div className="message-header">
        <div className="message-avatar user-avatar">U</div>
        <div className="message-sender">You</div>
      </div>
      <div className="message-content">{msg.content}</div>
    </div>
  );
}
