"use client";

/**
 * Collapsible "Thinking" block — React port of the legacy
 * `.chat-thinking` scaffold. Reuses the legacy CSS (05-chat.css): the
 * fold state is driven entirely by the `data-collapsed` attribute, so
 * this component only flips that string and the stylesheet does the
 * show/hide.
 */
import { useState } from "react";

export function ThinkingBlock({
  text,
  streaming,
}: {
  text: string;
  streaming?: boolean;
}) {
  const [collapsed, setCollapsed] = useState(true);
  if (!text) return null;

  return (
    <div className="chat-thinking" data-collapsed={collapsed ? "1" : "0"}>
      <button
        type="button"
        className="chat-fold-btn"
        onClick={() => setCollapsed((c) => !c)}
        onMouseDown={(e) => e.preventDefault()}
      >
        <span className="chat-fold-caret">{"▶"}</span>
        <span className="chat-fold-label">Thinking</span>
        <span className="chat-fold-elapsed">{streaming ? "…" : ""}</span>
      </button>
      <div className="chat-fold-content">{text}</div>
    </div>
  );
}
