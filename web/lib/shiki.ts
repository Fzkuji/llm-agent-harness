"use client";

/**
 * Shared lazy Shiki highlighter.
 *
 * `shiki` is large (~MB), so we only load it when the first code block
 * actually needs to render. We share one Highlighter instance across the
 * page and lazily register more languages on demand.
 */
import type { Highlighter } from "shiki";

let highlighter: Highlighter | null = null;
let booting: Promise<Highlighter> | null = null;
const loadedLangs = new Set<string>();

const CORE_LANGS = [
  "ts",
  "tsx",
  "js",
  "jsx",
  "py",
  "json",
  "bash",
  "shell",
  "yaml",
  "html",
  "css",
  "md",
  "rs",
  "go",
  "java",
  "c",
  "cpp",
  "sql",
  "diff",
  "toml",
];

/** Bundled themes (one each for dark/light). */
export const SHIKI_DARK = "github-dark-default";
export const SHIKI_LIGHT = "github-light-default";

export async function getHighlighter(): Promise<Highlighter> {
  if (highlighter) return highlighter;
  if (booting) return booting;
  booting = (async () => {
    const { createHighlighter } = await import("shiki");
    const h = await createHighlighter({
      themes: [SHIKI_DARK, SHIKI_LIGHT],
      langs: CORE_LANGS,
    });
    for (const l of CORE_LANGS) loadedLangs.add(l);
    highlighter = h;
    booting = null;
    return h;
  })();
  return booting;
}

export async function ensureLang(lang: string): Promise<void> {
  if (!lang) return;
  if (loadedLangs.has(lang)) return;
  const h = await getHighlighter();
  try {
    await h.loadLanguage(lang as never);
    loadedLangs.add(lang);
  } catch {
    /* unknown language — fall through to plain rendering */
  }
}
