/**
 * Markdown → HTML for chat bubbles.
 *
 * Reuses the legacy global `renderMd` (markdown-it + KaTeX, loaded by
 * the shared scripts in app-shell) so React bubbles render byte-for-
 * byte identically to the legacy stream — no second markdown engine.
 * Falls back to escaped plain text before that global exists (SSR /
 * first paint, or if the shared scripts failed to load).
 */
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
