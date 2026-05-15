"use client";

/**
 * Runtime block — React port of the legacy `.runtime-block` scaffold
 * (chat.js `buildRuntimeBlockHtml`). Renders a `/run <fn>` turn: a
 * collapsible header with the function signature + a one-line preview,
 * and a body holding the `return:` output.
 *
 * Collapse is the legacy `.collapsed` class on `.runtime-block`
 * (05-chat.css hides the body/footer when present).
 */
import { useState } from "react";

import type { ChatMsg } from "@/lib/session-store";

import { renderMarkdown } from "./markdown";

/** Split a `run fn(args)` / `fn arg1 arg2` command into name + params
 *  for the header signature — mirrors `parseRunCommandForDisplay`. */
function parseRun(cmd: string): { fn: string; params: string } {
  const text = cmd.replace(/^(run|create|fix)\s+/i, "").trim();
  const paren = text.match(/^([\w.-]+)\s*\(([^]*)\)\s*$/);
  if (paren) return { fn: paren[1], params: paren[2] };
  const sp = text.indexOf(" ");
  if (sp < 0) return { fn: text, params: "" };
  return { fn: text.slice(0, sp), params: text.slice(sp + 1).trim() };
}

export function RuntimeBlock({ msg }: { msg: ChatMsg }) {
  const [collapsed, setCollapsed] = useState(false);
  const { fn, params } = parseRun(msg.function || msg.content || "");
  const html = renderMarkdown(msg.content || "");

  const preview =
    (msg.content || "").replace(/\s+/g, " ").trim().slice(0, 60) +
    ((msg.content || "").length > 60 ? "…" : "");

  const cls = [
    "runtime-block",
    collapsed ? "collapsed" : "",
    msg.status === "error" ? "error" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={cls} data-function={fn} data-msg-id={msg.id}>
      <div
        className="runtime-block-header"
        onClick={() => setCollapsed((c) => !c)}
      >
        <span className="runtime-icon">{"▶"}</span>
        <span className="runtime-func">
          {fn}
          {params ? (
            <>
              (<span className="runtime-params">{params}</span>)
            </>
          ) : (
            "()"
          )}
        </span>
        <span className="runtime-result-preview">{"-> " + preview}</span>
      </div>
      <div className="runtime-block-body">
        <div className="runtime-block-content">
          <div className="runtime-result">
            <span className="runtime-return-label">return:</span>
          </div>
          <div
            className="runtime-output"
            dangerouslySetInnerHTML={{ __html: html }}
          />
        </div>
      </div>
    </div>
  );
}
