"use client";

import { useEffect } from "react";

export interface Shortcut {
  /** Lowercase key (e.g. "k"). */
  key: string;
  meta?: boolean;
  ctrl?: boolean;
  shift?: boolean;
  alt?: boolean;
  /** Allow firing when an input/textarea has focus. Default false. */
  allowInInput?: boolean;
  handler: (e: KeyboardEvent) => void;
}

const isInteractive = (el: EventTarget | null) => {
  if (!(el instanceof HTMLElement)) return false;
  if (el.isContentEditable) return true;
  const tag = el.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
};

/** Bind a list of shortcuts at the document level. */
export function useShortcuts(shortcuts: Shortcut[]) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target;
      const inInput = isInteractive(target);
      for (const s of shortcuts) {
        if (e.key.toLowerCase() !== s.key.toLowerCase()) continue;
        if (!!s.meta !== e.metaKey) continue;
        if (!!s.ctrl !== e.ctrlKey) continue;
        if (!!s.shift !== e.shiftKey) continue;
        if (!!s.alt !== e.altKey) continue;
        if (inInput && !s.allowInInput) continue;
        e.preventDefault();
        s.handler(e);
        return;
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [shortcuts]);
}
