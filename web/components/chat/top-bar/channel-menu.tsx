"use client";

/**
 * Channel menu — React port of `conversations.js::openChannelDropdown`.
 *
 * Opened by the topbar `<StatusBadge />`. Lists the enabled channel
 * accounts (WeChat / Discord / Telegram / Slack) grouped by platform,
 * plus a "Local" row for no binding. Picking one binds the current
 * conversation to that channel (`set_conversation_channel` over WS) —
 * or, for a brand-new chat with no session yet, stashes the choice on
 * `window._pendingChannelChoice` for the first message to carry.
 *
 * Channel-account data still comes from the legacy
 * `window.fetchChannelAccounts()` (a cached WS round-trip) — that data
 * helper migrates with the rest of the WS layer.
 */
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { useSessionStore } from "@/lib/session-store";
import { Badge } from "@/components/ui/badge";

interface ChannelAccount {
  channel: string;
  account_id: string;
  name?: string;
  enabled?: boolean;
}

interface ChannelWindow {
  fetchChannelAccounts?: () => Promise<ChannelAccount[]>;
  _currentChannelChoice?: () => { channel: string | null; account_id: string | null };
  _channelIcon?: (plat: string) => string;
  refreshChannelBadge?: () => void;
  conversations?: Record<string, { channel?: string | null; account_id?: string | null }>;
  _pendingChannelChoice?: { channel: string | null; account_id: string | null } | null;
  ws?: WebSocket;
}

const BRAND: Record<string, string> = {
  wechat: "WeChat",
  discord: "Discord",
  telegram: "Telegram",
  slack: "Slack",
};

function brandFor(plat: string): string {
  return BRAND[plat.toLowerCase()] || plat;
}

export function ChannelMenu({
  anchorRef,
  onClose,
}: {
  anchorRef: React.RefObject<HTMLElement | null>;
  onClose: () => void;
}) {
  const sessionId = useSessionStore((s) => s.currentSessionId);
  const [rows, setRows] = useState<ChannelAccount[] | null>(null);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const a = anchorRef.current;
    if (!a) return;
    const r = a.getBoundingClientRect();
    setPos({ left: r.left, top: r.bottom + 4 });
  }, [anchorRef]);

  useEffect(() => {
    const f = (window as unknown as ChannelWindow).fetchChannelAccounts;
    if (f) {
      f().then(
        (r) => setRows(r || []),
        () => setRows([]),
      );
    } else {
      setRows([]);
    }
  }, []);

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      const t = e.target as Node | null;
      if (!t) return;
      if (panelRef.current?.contains(t)) return;
      if (anchorRef.current?.contains(t)) return;
      onClose();
    }
    // Defer so the opening click doesn't immediately close it.
    const id = setTimeout(
      () => document.addEventListener("click", onDoc),
      0,
    );
    return () => {
      clearTimeout(id);
      document.removeEventListener("click", onDoc);
    };
  }, [anchorRef, onClose]);

  const w = window as unknown as ChannelWindow;
  const cur = w._currentChannelChoice?.() ?? {
    channel: null,
    account_id: null,
  };

  function pick(ch: string, acct: string) {
    onClose();
    if (sessionId) {
      if (w.ws && w.ws.readyState === WebSocket.OPEN) {
        w.ws.send(
          JSON.stringify({
            action: "set_conversation_channel",
            session_id: sessionId,
            channel: ch,
            account_id: acct,
          }),
        );
      }
      const conv = w.conversations?.[sessionId];
      if (conv) {
        conv.channel = ch || null;
        conv.account_id = ch && acct ? acct : null;
      }
    } else {
      w._pendingChannelChoice = {
        channel: ch || null,
        account_id: ch ? acct || null : null,
      };
    }
    w.refreshChannelBadge?.();
  }

  if (!pos || typeof document === "undefined") return null;

  // Group accounts by platform, preserving first-seen order.
  const enabled = (rows ?? []).filter((r) => r.enabled);
  const groups: { plat: string; accounts: ChannelAccount[] }[] = [];
  for (const r of enabled) {
    let g = groups.find((x) => x.plat === r.channel);
    if (!g) {
      g = { plat: r.channel, accounts: [] };
      groups.push(g);
    }
    g.accounts.push(r);
  }

  return createPortal(
    <div
      ref={panelRef}
      className="agent-selector model-dropdown channel-selector"
      style={{ position: "fixed", left: pos.left, top: pos.top }}
    >
      <div className="model-dd-group-label" style={{ paddingTop: 6 }}>
        <span>Conversation channel</span>
      </div>

      <div
        className={"model-dd-item" + (!cur.channel ? " active" : "")}
        onClick={() => pick("", "")}
      >
        <span className="model-dd-name">Local</span>
      </div>

      {rows !== null && enabled.length === 0 ? (
        <div
          className="model-dd-group-label"
          style={{ paddingTop: 10, fontSize: 11 }}
        >
          <a
            href="/settings"
            style={{ color: "var(--accent-blue)", textDecoration: "none" }}
          >
            Add a channel in Settings →
          </a>
        </div>
      ) : null}

      {groups.map((g) => (
        <div key={g.plat}>
          <div className="model-dd-group-label">
            <span
              className="provider-icon"
              style={{ width: 14, height: 14 }}
              dangerouslySetInnerHTML={{
                __html: w._channelIcon?.(g.plat) ?? "",
              }}
            />
            <span>{brandFor(g.plat)}</span>
          </div>
          {g.accounts.map((r) => {
            const active =
              r.channel === cur.channel && r.account_id === cur.account_id;
            const meta = r.name && r.name !== r.account_id ? r.name : "";
            return (
              <div
                key={r.channel + ":" + r.account_id}
                className={"model-dd-item" + (active ? " active" : "")}
                onClick={() => pick(r.channel, r.account_id)}
              >
                <span className="model-dd-name">{r.account_id}</span>
                {meta ? (
                  <div className="model-dd-caps">
                    <Badge
                      variant="secondary"
                      className="h-[18px] rounded-[4px] px-[5px] py-0 text-[12px] font-normal text-[var(--text-secondary)]"
                    >
                      {meta}
                    </Badge>
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      ))}
    </div>,
    document.body,
  );
}
