"use client";

/**
 * Runtime block — a `/run <fn>` turn.
 *
 * Rather than re-implement the legacy execution-tree renderer, attempt
 * navigation and usage footer in React, this component delegates to the
 * legacy HTML builders (`buildRuntimeBlockHtml`, `renderInlineTree`,
 * `renderAttemptNav`, all globals defined by the chat-page scripts) and
 * injects the resulting markup. The builders emit inline `onclick`
 * handlers that point at other legacy globals (`toggleRuntimeBlock`,
 * `retryCurrentBlock`, tree node toggles), so collapse / retry / tree
 * interaction keep working without a React port.
 *
 * React owns the message ordering and lifecycle; the block's internals
 * stay legacy. While the turn is still streaming, the block renders a
 * pending placeholder carrying `id="runtime_pending"` so the legacy
 * stream/tree handlers can target it.
 */
import { useEffect, useRef } from "react";

import type { ChatMsg } from "@/lib/session-store";

interface RuntimeLegacyGlobals {
  buildRuntimeBlockHtml?: (
    fn: string,
    params: string,
    contentHtml: string,
    treeHtml: string,
    attemptNavHtml: string,
    rerunHtml: string,
    usage: unknown,
  ) => string;
  renderInlineTree?: (tree: unknown, id: string) => string;
  renderAttemptNav?: (fn: string, idx: number, total: number) => string;
  parseRunCommandForDisplay?: (cmd: string) => { funcName: string; params: string };
  renderMd?: (md: string) => string;
  escAttr?: (s: string) => string;
  updateTreeData?: (tree: unknown) => void;
}

function legacy(): RuntimeLegacyGlobals {
  return window as unknown as RuntimeLegacyGlobals;
}

/** Resolve the content + tree to display, honoring the selected
 *  attempt — mirrors legacy `_getDisplayContent`. */
function displayContent(msg: ChatMsg): { content: string; tree: unknown } {
  let content = msg.content || "";
  let tree: unknown = msg.contextTree || null;
  if (msg.attempts && msg.attempts.length > 0) {
    const idx = msg.current_attempt || 0;
    const att = msg.attempts[idx];
    if (att) {
      content = att.content || content;
      tree = att.tree || tree;
    }
  }
  return { content, tree };
}

export function RuntimeBlock({ msg }: { msg: ChatMsg }) {
  const ref = useRef<HTMLDivElement>(null);
  const streaming = msg.status === "streaming" || msg.status === "pending";

  const w = legacy();
  const fnName = msg.function || "";

  let html: string;
  if (streaming || !w.buildRuntimeBlockHtml) {
    // Pending: a minimal header + typing dots. The id lets the legacy
    // `_handleStreamEvent` / `_handleTreeUpdate` stream into this node.
    html =
      '<div class="runtime-block-header" onclick="toggleRuntimeBlock&&toggleRuntimeBlock(this)">' +
      '<span class="runtime-icon">&#9654;</span>' +
      '<span class="runtime-func">' +
      (fnName || "run") +
      "()</span></div>" +
      '<div class="runtime-block-body"><div class="runtime-block-content">' +
      '<div class="typing-indicator"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div>' +
      "</div></div>";
  } else {
    const { content, tree } = displayContent(msg);
    const contentHtml = w.renderMd ? w.renderMd(content) : content;
    let treeHtml = "";
    if (tree && w.renderInlineTree) {
      treeHtml = w.renderInlineTree(
        tree,
        "itree_" + (fnName || "result").replace(/[^a-zA-Z0-9]/g, "_"),
      );
      if (w.updateTreeData) w.updateTreeData(tree);
    }
    let attemptNavHtml = "";
    if (msg.attempts && msg.attempts.length > 1 && w.renderAttemptNav) {
      attemptNavHtml = w.renderAttemptNav(
        fnName,
        msg.current_attempt || 0,
        msg.attempts.length,
      );
    }
    const rerunHtml =
      fnName && w.escAttr
        ? '<button class="rerun-btn" onclick="retryCurrentBlock(\'' +
          w.escAttr(fnName) +
          "')\">&#8634; Retry</button>"
        : "";
    let params = "";
    if (w.parseRunCommandForDisplay) {
      params = w.parseRunCommandForDisplay(msg.content || "").params || "";
    }
    html = w.buildRuntimeBlockHtml(
      fnName,
      params,
      contentHtml,
      treeHtml,
      attemptNavHtml,
      rerunHtml,
      msg.usage,
    );
  }

  // KaTeX / markdown post-processing the legacy renderer applies after
  // injecting HTML — keep math + code highlighting consistent.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const renderMath = (window as unknown as { renderMathInElement?: (e: HTMLElement, o: unknown) => void })
      .renderMathInElement;
    if (renderMath) {
      try {
        renderMath(el, {
          delimiters: [
            { left: "$$", right: "$$", display: true },
            { left: "$", right: "$", display: false },
          ],
        });
      } catch {
        /* ignore */
      }
    }
  }, [html]);

  const cls = [
    "runtime-block",
    streaming ? "runtime-block-pending" : "",
    msg.status === "error" ? "error" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div
      ref={ref}
      className={cls}
      id={streaming ? "runtime_pending" : undefined}
      data-function={fnName || undefined}
      data-msg-id={msg.id}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
