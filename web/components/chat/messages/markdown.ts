/**
 * Markdown → HTML for chat bubbles.
 *
 * Reuses the legacy global `renderMd` (markdown-it + KaTeX, loaded by
 * the shared scripts in app-shell) so React bubbles render byte-for-
 * byte identically to the legacy stream — no second markdown engine.
 * Falls back to escaped plain text before that global exists (SSR /
 * first paint, or if the shared scripts failed to load).
 */
import { useEffect, useState } from "react";

export function renderMarkdown(src: string): string {
  if (typeof window !== "undefined") {
    const fn = (window as unknown as { renderMd?: (s: string) => string })
      .renderMd;
    if (typeof fn === "function") {
      try {
        return fn(src);
      } catch {
        /* fall through to escaped text */
      }
    }
  }
  return escapeHtml(src);
}

/**
 * Re-render gate for markdown.
 *
 * `renderMd` is installed by the shared scripts (app-shell) — an async
 * load that usually finishes *after* the first bubble paints. Without
 * this hook a bubble rendered early would keep its escaped-text
 * fallback forever. The hook flips to `true` once `renderMd` exists,
 * forcing the consuming bubble to re-render and pick up real markdown.
 */
export function useMarkdownReady(): boolean {
  const has = () =>
    typeof window !== "undefined" &&
    typeof (window as unknown as { renderMd?: unknown }).renderMd ===
      "function";
  const [ready, setReady] = useState<boolean>(has);

  useEffect(() => {
    if (ready) return;
    let cancelled = false;
    const w = window as unknown as {
      renderMd?: unknown;
      __sharedScriptsReady?: Promise<void>;
    };
    if (has()) {
      setReady(true);
      return;
    }
    const done = () => {
      if (!cancelled && has()) setReady(true);
    };
    w.__sharedScriptsReady?.then(done);
    // Poll as a backstop — the promise resolves before `renderMd` is
    // actually assigned in some load orderings.
    const t = setInterval(() => {
      if (has()) {
        done();
        clearInterval(t);
      }
    }, 120);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [ready]);

  return ready;
}

export function escapeHtml(s: string): string {
  return s.replace(
    /[&<>"']/g,
    (c) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[c] as string,
  );
}
