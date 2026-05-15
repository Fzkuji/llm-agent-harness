import { useEffect, useRef } from "react";

/**
 * Keep a scroll container pinned to the bottom while its content
 * grows — unless the user has deliberately scrolled up.
 *
 * Height growth is detected with a ResizeObserver on every child plus
 * a MutationObserver for newly-added children. This covers both new
 * messages AND streamed text deltas inside an existing bubble, without
 * the caller needing to thread a dependency through.
 *
 * Scrolling up past 80px from the bottom "detaches"; the stream then
 * no longer yanks the viewport down until the user scrolls back.
 */
export function useStickToBottom() {
  const ref = useRef<HTMLDivElement>(null);
  const stuck = useRef(true);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const pin = () => {
      if (stuck.current) el.scrollTop = el.scrollHeight;
    };
    const onScroll = () => {
      const gap = el.scrollHeight - el.scrollTop - el.clientHeight;
      stuck.current = gap < 80;
    };
    el.addEventListener("scroll", onScroll, { passive: true });

    const ro = new ResizeObserver(pin);
    const observeChildren = () => {
      for (const child of Array.from(el.children)) ro.observe(child);
    };
    observeChildren();

    const mo = new MutationObserver(() => {
      observeChildren();
      pin();
    });
    mo.observe(el, { childList: true });

    return () => {
      el.removeEventListener("scroll", onScroll);
      ro.disconnect();
      mo.disconnect();
    };
  }, []);

  return ref;
}
