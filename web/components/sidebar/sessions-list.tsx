"use client";

/**
 * Sessions list (the "Recents" panel in the sidebar).
 *
 * Reads conversations from `window.conversations` via `useLegacyGlobals`
 * — the legacy `init.js` is what populates that global from the
 * sessions_list / history_list WS events, so we piggy-back on it
 * instead of duplicating the WS handling here. Once the WSProvider
 * (which writes to useSessionStore) is wired into the layout, this
 * hook should switch to a store subscription.
 */

import { useRouter, usePathname } from "next/navigation";
import { useLegacyGlobals, useCurrentSessionId } from "./use-legacy-globals";
import styles from "./sidebar.module.css";

interface LegacyConv {
  id: string;
  title?: string;
  created_at?: number;
  channel?: string | null;
  account_id?: string | null;
  preview?: string | null;
  has_session?: boolean;
}

const CHANNEL_BRAND: Record<string, string> = {
  wechat: "WeChat",
  discord: "Discord",
  telegram: "Telegram",
  slack: "Slack",
};

function channelBrand(ch?: string | null): string {
  if (!ch) return "";
  return CHANNEL_BRAND[String(ch).toLowerCase()] || ch;
}

function channelPrefix(ch?: string | null, acct?: string | null): string {
  if (!ch) return "";
  const brand = channelBrand(ch);
  return acct ? `${brand} (${acct})` : brand;
}

function isPlaceholderTitle(t: string): boolean {
  if (!t) return true;
  if (t === "New conversation" || t === "Untitled") return true;
  return /^(wechat|discord|telegram|slack)\s*[:：]\s*\S{8,}/i.test(t);
}

function displayTitle(c: LegacyConv): string {
  const t = (c.title || "").trim();
  if (isPlaceholderTitle(t)) return "";
  return t.length > 30 ? t.slice(0, 30) + "…" : t;
}

function labelFor(c: LegacyConv): string {
  const prefix = channelPrefix(c.channel, c.account_id);
  let real = displayTitle(c);
  if (!real && c.preview) {
    const pv = String(c.preview).trim();
    real = pv.length > 30 ? pv.slice(0, 30) + "…" : pv;
  }
  if (prefix && real) return prefix + ": " + real;
  if (prefix) return prefix;
  if (real) return real;
  return c.title || "Untitled";
}

export function SessionsList() {
  const router = useRouter();
  const pathname = usePathname();
  const { conversations } = useLegacyGlobals();
  const currentId = useCurrentSessionId();

  const list = Object.values(conversations).sort(
    (a, b) => (b.created_at || 0) - (a.created_at || 0)
  );

  function switchTo(id: string) {
    if (id === currentId && pathname === "/s/" + id) return;
    router.push("/s/" + id);
  }

  function del(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    // Delegate to the legacy helper — it already handles the confirm
    // dialog, the WS `delete_session` action, the in-memory cleanup
    // and the redirect to /chat when the active conv is deleted.
    const w = window as unknown as { deleteSession?: (id: string) => void };
    if (typeof w.deleteSession === "function") w.deleteSession(id);
  }

  function clearAll() {
    const w = window as unknown as { clearAllSessions?: () => void };
    if (typeof w.clearAllSessions === "function") w.clearAllSessions();
  }

  if (list.length === 0) {
    return <div className={styles.empty}>No conversations yet</div>;
  }

  return (
    <>
      {list.map((c) => {
        const active = c.id === currentId;
        const label = labelFor(c);
        return (
          <ConvItem
            key={c.id}
            label={label}
            active={active}
            onClick={() => switchTo(c.id)}
            onDelete={(e) => del(c.id, e)}
          />
        );
      })}
      <div className={styles.clearAll} onClick={clearAll}>
        Clear all
      </div>
    </>
  );
}

/* Single row in the conversation list. Mirrors the legacy
   `.conv-item / .conv-title / .conv-del` triplet from 03-settings.css:
   32px-tall row with a title that fades on the right on hover so the
   absolutely-positioned delete button doesn't visually collide. */
function ConvItem({
  label,
  active,
  onClick,
  onDelete,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  onDelete: (e: React.MouseEvent) => void;
}) {
  // Pixel values are explicit (not `h-8`, `px-2`, etc.) because this
  // project's `html { font-size: 14px }` makes Tailwind's rem-based
  // scale 0.875× off — see the same note in FavoritesList.
  const base =
    "group relative flex h-[32px] shrink-0 cursor-pointer items-center" +
    " gap-[12px] overflow-hidden rounded-[6px] px-[8px] py-[6px]" +
    " text-fs-base leading-[20px] whitespace-nowrap" +
    " transition-colors duration-300 hover:bg-bg-hover";
  const colorCls = active
    ? "bg-bg-hover text-text-bright"
    : "text-text-primary";
  // The legacy `.conv-item:hover .conv-title` rule swaps the
  // text-overflow from ellipsis (rest) to clip + a fade-out gradient
  // mask so the delete button has visual headroom. Express the same
  // via group-hover arbitrary utilities — Tailwind has no built-in
  // for `mask-image` gradients.
  const maskOnHover =
    "group-hover:[text-overflow:clip]" +
    " group-hover:[-webkit-mask-image:linear-gradient(to_right,#000_78%,transparent_95%)]" +
    " group-hover:[mask-image:linear-gradient(to_right,#000_78%,transparent_95%)]" +
    " group-focus-within:[text-overflow:clip]" +
    " group-focus-within:[-webkit-mask-image:linear-gradient(to_right,#000_78%,transparent_95%)]" +
    " group-focus-within:[mask-image:linear-gradient(to_right,#000_78%,transparent_95%)]";
  return (
    <div
      className={`${base} ${colorCls}`}
      onClick={onClick}
      title={label}
    >
      <span
        className={`flex-1 overflow-hidden truncate text-fs-base leading-[20px] ${maskOnHover}`}
      >
        {label}
      </span>
      <span
        className="absolute right-[6px] top-1/2 hidden size-[20px] -translate-y-1/2
          items-center justify-center rounded-[4px] text-[12px]
          leading-none text-text-muted
          group-hover:flex hover:!bg-accent-red hover:!text-white"
        onClick={onDelete}
        title="Delete"
      >
        <svg
          width="10"
          height="10"
          viewBox="0 0 10 10"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
        >
          <line x1="2" y1="2" x2="8" y2="8" />
          <line x1="8" y1="2" x2="2" y2="8" />
        </svg>
      </span>
    </div>
  );
}
