"use client";

/**
 * Execution tree — React port of the legacy `renderInlineTree` /
 * `renderTreeNode` (`public/js/chat/tree-render.js`) plus the per-node
 * retry panel (`tree-retry.js`).
 *
 * Renders the `/run` execution DAG inside a runtime block: a
 * collapsible card whose body is a recursive node list. Each node row
 * can expand/collapse its children, be selected (opens the right-rail
 * Execution Detail via the legacy `window.showDetail`), and — for
 * non-LLM, non-running nodes — open a "modify" panel that re-runs the
 * node with edited params (`retry_node` WS action).
 *
 * State that was global in the vanilla version is now component-local:
 * `expanded` replaces `expandedNodes`, selection replaces
 * `selectedPath`, and the node objects are walked directly instead of
 * via the `_nodeCache` path map.
 */
import { useCallback, useEffect, useMemo, useState } from "react";

import { useSessionStore } from "@/lib/session-store";

interface TNode {
  path?: string;
  name?: string;
  status?: string;
  node_type?: string;
  params?: Record<string, unknown>;
  output?: unknown;
  raw_reply?: string;
  duration_ms?: number;
  start_time?: number;
  end_time?: number;
  error?: string;
  children?: TNode[];
}

function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n) + "…" : s;
}

function wsSend(payload: unknown): boolean {
  const w = window as Window & { ws?: WebSocket };
  if (!w.ws || w.ws.readyState !== WebSocket.OPEN) return false;
  w.ws.send(typeof payload === "string" ? payload : JSON.stringify(payload));
  return true;
}

function collectPaths(node: TNode, set: Set<string>): void {
  if (node.path) set.add(node.path);
  node.children?.forEach((c) => collectPaths(c, set));
}

/** A node is "running" only if its status says so AND it hasn't
 *  recorded an end — mirrors the legacy `_treeHasRunning` race guard. */
function treeHasRunning(node: TNode | undefined): boolean {
  if (!node) return false;
  const ended =
    (!!node.duration_ms && node.duration_ms > 0) ||
    (!!node.end_time && node.end_time > 0);
  if (node.status === "running" && !ended) return true;
  return (node.children ?? []).some(treeHasRunning);
}

const PARAM_SKIP = new Set(["runtime", "callback"]);

function filteredParams(params: Record<string, unknown> | undefined) {
  const out: Record<string, unknown> = {};
  if (params) {
    for (const k of Object.keys(params)) {
      if (!PARAM_SKIP.has(k)) out[k] = params[k];
    }
  }
  return out;
}

/** Strip `children` + runtime params for the Copy-JSON payload. */
function cleanForCopy(node: TNode): unknown {
  const c: Record<string, unknown> = {};
  for (const k of Object.keys(node)) {
    if (k === "children") continue;
    if (k === "params") {
      c.params = filteredParams(node.params);
    } else {
      c[k] = (node as Record<string, unknown>)[k];
    }
  }
  if (node.children && node.children.length) {
    c.children = node.children.map(cleanForCopy);
  }
  return c;
}

/* ---- retry panel --------------------------------------------------- */

/** Flatten params into dotted-key string fields, matching the legacy
 *  `_buildRetryFields` so `executeRetry`'s `key.split(".")` rebuild
 *  works unchanged. */
function flattenParams(
  params: Record<string, unknown>,
  prefix: string,
  out: { key: string; value: string; long: boolean }[],
): void {
  for (const k of Object.keys(params)) {
    if (PARAM_SKIP.has(k)) continue;
    const v = params[k];
    const fullKey = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === "object" && !Array.isArray(v)) {
      flattenParams(v as Record<string, unknown>, fullKey, out);
    } else {
      const vs = typeof v === "string" ? v : JSON.stringify(v);
      out.push({ key: fullKey, value: vs, long: vs.length > 60 || vs.includes("\n") });
    }
  }
}

function RetryPanel({
  node,
  onClose,
}: {
  node: TNode;
  onClose: () => void;
}) {
  const fields = useMemo(() => {
    const out: { key: string; value: string; long: boolean }[] = [];
    flattenParams(filteredParams(node.params), "", out);
    return out;
  }, [node.params]);
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(fields.map((f) => [f.key, f.value])),
  );
  const sessionId = useSessionStore((s) => s.currentSessionId);

  function execute() {
    if (node.status === "running" || !node.path) return;
    const params: Record<string, unknown> = {};
    for (const f of fields) {
      const raw = values[f.key] ?? "";
      let parsed: unknown;
      try {
        parsed = JSON.parse(raw);
      } catch {
        parsed = raw;
      }
      const parts = f.key.split(".");
      let obj = params;
      for (let i = 0; i < parts.length - 1; i++) {
        if (typeof obj[parts[i]] !== "object" || obj[parts[i]] == null) {
          obj[parts[i]] = {};
        }
        obj = obj[parts[i]] as Record<string, unknown>;
      }
      obj[parts[parts.length - 1]] = parsed;
    }
    onClose();
    if (!sessionId) return;
    wsSend({
      action: "retry_node",
      node_path: node.path,
      session_id: sessionId,
      params,
    });
  }

  return (
    <div className="retry-panel" style={{ display: "block" }}>
      <div
        style={{
          marginBottom: 6,
          color: "var(--text-secondary)",
          fontSize: 11,
        }}
      >
        Modify <b>{node.name}</b> with:
      </div>
      {fields.length === 0 ? (
        <div
          style={{
            color: "var(--text-muted)",
            fontSize: 11,
            marginBottom: 6,
          }}
        >
          No editable parameters
        </div>
      ) : (
        fields.map((f) => (
          <div className="retry-field" key={f.key}>
            <label className="retry-field-label">{f.key}</label>
            {f.long ? (
              <textarea
                className="retry-field-input"
                value={values[f.key] ?? ""}
                onChange={(e) =>
                  setValues((v) => ({ ...v, [f.key]: e.target.value }))
                }
              />
            ) : (
              <input
                className="retry-field-input"
                value={values[f.key] ?? ""}
                onChange={(e) =>
                  setValues((v) => ({ ...v, [f.key]: e.target.value }))
                }
              />
            )}
          </div>
        ))
      )}
      <div className="retry-panel-actions">
        <button className="retry-exec-btn" onClick={execute}>
          {"▶ Execute"}
        </button>
        <button className="retry-cancel-btn" onClick={onClose}>
          Cancel
        </button>
      </div>
    </div>
  );
}

/* ---- node row ------------------------------------------------------ */

interface RowCtx {
  expanded: Set<string>;
  toggle: (path: string) => void;
  selectedPath: string | null;
  select: (node: TNode) => void;
  retryOpen: Set<string>;
  toggleRetry: (path: string) => void;
  paused: boolean;
  /** Re-render tick — bumped every second so running durations advance. */
  tick: number;
}

function TreeNodeRow({ node, ctx }: { node: TNode; ctx: RowCtx }) {
  const path = node.path ?? "";
  const hasChildren = !!node.children && node.children.length > 0;
  const isExpanded = ctx.expanded.has(path);
  const isSelected = path === ctx.selectedPath;

  const hasFinished =
    (!!node.duration_ms && node.duration_ms > 0) ||
    (!!node.end_time && node.end_time > 0);
  const effectiveStatus =
    node.status === "running" && hasFinished ? "error" : node.status;
  const isCancelled =
    effectiveStatus === "error" &&
    typeof node.error === "string" &&
    /cancel/i.test(node.error);
  const displayStatus =
    ctx.paused && effectiveStatus === "running" ? "paused" : effectiveStatus;

  const icon =
    displayStatus === "success" ? (
      <span style={{ color: "var(--accent-green)" }}>{"✓"}</span>
    ) : isCancelled ? (
      <span style={{ color: "var(--text-muted)" }} title="Cancelled">
        {"◉"}
      </span>
    ) : displayStatus === "error" ? (
      <span style={{ color: "var(--accent-red)" }}>{"✗"}</span>
    ) : displayStatus === "paused" ? (
      <span style={{ color: "var(--accent-yellow)" }}>{"❙❙"}</span>
    ) : (
      <span className="pulse" style={{ color: "var(--accent-blue)" }}>
        {"●"}
      </span>
    );

  let dur = "";
  const running = displayStatus === "running" || displayStatus === "paused";
  if (node.duration_ms && node.duration_ms > 0) {
    dur =
      node.duration_ms >= 1000
        ? (node.duration_ms / 1000).toFixed(1) + "s"
        : Math.round(node.duration_ms) + "ms";
  } else if (running && node.start_time && node.start_time > 0) {
    const elapsed = Math.round(Date.now() / 1000 - node.start_time);
    dur = displayStatus === "paused" ? elapsed + "s (paused)" : elapsed + "s...";
  }

  const isExec = node.node_type === "exec";
  let preview = "";
  let output = "";
  if (isExec) {
    const execIn =
      (node.params && (node.params._content as string)) || "";
    const execOut =
      node.raw_reply ||
      (typeof node.output === "string" ? node.output : "");
    const inPart = execIn ? "→ " + truncate(execIn, 50) : "";
    const outPart = execOut ? " ← " + truncate(execOut, 50) : "";
    preview = (inPart + outPart).trim();
  } else if (node.output != null) {
    output =
      typeof node.output === "string"
        ? truncate(node.output, 80)
        : truncate(JSON.stringify(node.output), 80);
  }

  const canRetry =
    !isExec && node.name !== "chat_session" && node.status !== "running";

  return (
    <div className="tree-node">
      <div
        className={
          "node-row" +
          (isSelected ? " selected" : "") +
          (isExec ? " exec-row" : "")
        }
        onClick={() => ctx.select(node)}
      >
        <span
          className={
            "node-toggle " +
            (hasChildren ? (isExpanded ? "expanded" : "") : "leaf")
          }
          onClick={(e) => {
            e.stopPropagation();
            if (hasChildren) ctx.toggle(path);
          }}
        >
          {"▶"}
        </span>
        <span className="node-icon">{icon}</span>
        {isExec ? (
          <span className="llm-badge" title="LLM call">
            LLM
          </span>
        ) : (
          <span
            className="node-name"
            style={{ cursor: "pointer" }}
            title="View source"
            onClick={(e) => {
              e.stopPropagation();
              (
                window as unknown as { viewSource?: (n: string) => void }
              ).viewSource?.(node.name ?? "");
            }}
          >
            {node.name}
          </span>
        )}
        {!isExec && (
          <span
            className={
              "node-status " +
              displayStatus +
              (isCancelled ? " cancelled" : "")
            }
          >
            {isCancelled ? "cancelled" : displayStatus}
          </span>
        )}
        {dur ? <span className="node-duration">{dur}</span> : null}
        {preview ? (
          <span className="node-output-preview exec-preview">{preview}</span>
        ) : null}
        {output ? (
          <span className="node-output-preview">{output}</span>
        ) : null}
        {canRetry ? (
          <span
            className="retry-icon"
            title="Modify"
            onClick={(e) => {
              e.stopPropagation();
              ctx.toggleRetry(path);
            }}
          >
            modify
          </span>
        ) : null}
      </div>

      {canRetry && ctx.retryOpen.has(path) ? (
        <RetryPanel node={node} onClose={() => ctx.toggleRetry(path)} />
      ) : null}

      {hasChildren ? (
        <div className={"node-children" + (isExpanded ? "" : " collapsed")}>
          {node.children!.map((child, i) => (
            <TreeNodeRow key={child.path ?? i} node={child} ctx={ctx} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

/* ---- tree card ----------------------------------------------------- */

export function ExecutionDag({ tree }: { tree: TNode }) {
  const paused = useSessionStore((s) => s.paused);
  const [collapsed, setCollapsed] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(() => {
    const s = new Set<string>();
    collectPaths(tree, s);
    return s;
  });
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [retryOpen, setRetryOpen] = useState<Set<string>>(new Set());
  const [copied, setCopied] = useState(false);

  // Running nodes show a live "12s..." duration — re-render every
  // second while the tree still has one.
  const running = treeHasRunning(tree);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, [running]);

  const toggle = useCallback((path: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }, []);

  const toggleRetry = useCallback((path: string) => {
    setRetryOpen((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }, []);

  const select = useCallback((node: TNode) => {
    setSelectedPath(node.path ?? null);
    (
      window as unknown as { showDetail?: (n: unknown) => void }
    ).showDetail?.(node);
  }, []);

  function copy() {
    const json = JSON.stringify(cleanForCopy(tree), null, 2);
    const done = () => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    };
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(json).then(done, done);
    } else {
      done();
    }
  }

  const ctx: RowCtx = {
    expanded,
    toggle,
    selectedPath,
    select,
    retryOpen,
    toggleRetry,
    paused,
    tick,
  };

  return (
    <div className="inline-tree">
      <div
        className="inline-tree-header"
        onClick={() => setCollapsed((c) => !c)}
      >
        <span>
          {running ? (
            <span className="pulse" style={{ color: "var(--accent-blue)" }}>
              {"●"}
            </span>
          ) : (
            <span style={{ color: "var(--accent-cyan)" }}>{"◆"}</span>
          )}{" "}
          Execution DAG
        </span>
        <span className="inline-tree-actions">
          <button
            className={"inline-tree-copy" + (copied ? " copied" : "")}
            title="Copy tree as JSON"
            onClick={(e) => {
              e.stopPropagation();
              copy();
            }}
          >
            {copied ? "Copied" : "Copy JSON"}
          </button>
          <span
            className={"inline-tree-toggle" + (collapsed ? " collapsed" : "")}
          >
            {"▶"}
          </span>
        </span>
      </div>
      <div className={"inline-tree-body" + (collapsed ? " collapsed" : "")}>
        <TreeNodeRow node={tree} ctx={ctx} />
      </div>
    </div>
  );
}
