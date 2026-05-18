"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  ChevronsLeft,
  ChevronsRight,
  Command,
  History,
  MessageSquarePlus,
  PlayCircle,
  Search,
  Settings,
} from "lucide-react";
import { useStore } from "@/lib/store";
import { send } from "@/lib/ws";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { HoverTip } from "@/components/ui/tooltip";
import { Kbd } from "@/components/ui/kbd";
import { StatusPill } from "./status-pill";
import { ThemeToggle } from "./theme-toggle";

const NAV: Array<{
  href: string;
  label: string;
  icon: typeof MessageSquarePlus;
  matchPrefix?: string;
}> = [
  { href: "/programs", label: "Programs", icon: PlayCircle },
  { href: "/history", label: "History", icon: History },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const wsStatus = useStore((s) => s.wsStatus);
  const conversations = useStore((s) => s.conversations);
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    const v = window.localStorage.getItem("op:sidebar-collapsed");
    if (v === "1") setCollapsed(true);
  }, []);
  useEffect(() => {
    window.localStorage.setItem("op:sidebar-collapsed", collapsed ? "1" : "0");
  }, [collapsed]);

  useEffect(() => {
    if (wsStatus === "open") send({ action: "list_conversations" });
  }, [wsStatus]);

  const recent = useMemo(() => {
    return Object.values(conversations)
      .sort(
        (a, b) =>
          (b.updated_at ?? b.created_at ?? 0) - (a.updated_at ?? a.created_at ?? 0),
      )
      .slice(0, 14);
  }, [conversations]);

  return (
    <aside
      className={cn(
        "relative flex h-full shrink-0 flex-col border-r border-(--border) bg-(--bg-elevated) transition-[width]",
        collapsed ? "w-14" : "w-64",
      )}
    >
      {/* Brand row */}
      <div className="flex h-12 items-center gap-2 border-b border-(--border) px-3">
        {!collapsed && (
          <Link
            href="/chat"
            className="flex items-center gap-1.5 font-semibold tracking-tight text-(--fg)"
          >
            <span
              aria-hidden
              className="inline-block h-5 w-5 rounded-md bg-(--accent)"
            />
            <span className="text-sm">OpenProgram</span>
          </Link>
        )}
        <Button
          variant="ghost"
          size="icon-sm"
          className="ml-auto"
          onClick={() => setCollapsed((c) => !c)}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={collapsed ? "Expand" : "Collapse"}
        >
          {collapsed ? <ChevronsRight size={14} /> : <ChevronsLeft size={14} />}
        </Button>
      </div>

      {/* Primary actions */}
      <div className="flex flex-col gap-1 p-2">
        {collapsed ? (
          <HoverTip label="New chat" side="right" shortcut="⌘N">
            <Button asChild variant="default" size="icon" className="w-full">
              <Link href="/chat">
                <MessageSquarePlus size={16} />
              </Link>
            </Button>
          </HoverTip>
        ) : (
          <Button asChild variant="default" size="md" className="justify-start gap-2">
            <Link href="/chat">
              <MessageSquarePlus size={14} />
              New chat
              <Kbd className="ml-auto bg-transparent border-(--border-strong)/40">⌘N</Kbd>
            </Link>
          </Button>
        )}
        {collapsed ? (
          <HoverTip label="Search" side="right" shortcut="⌘K">
            <Button variant="ghost" size="icon" className="w-full">
              <Search size={14} />
            </Button>
          </HoverTip>
        ) : (
          <Button variant="ghost" size="md" className="justify-start gap-2">
            <Search size={14} />
            Search
            <Kbd className="ml-auto">⌘K</Kbd>
          </Button>
        )}
      </div>

      {/* Recent chats */}
      {!collapsed && (
        <div className="flex min-h-0 flex-1 flex-col">
          <div className="px-3 pb-1.5 pt-3 text-[10px] font-semibold uppercase tracking-[0.08em] text-(--fg-subtle)">
            Recent
          </div>
          <div className="scroll-y min-h-0 flex-1 px-1.5 pb-1.5">
            {recent.length === 0 ? (
              <div className="px-2 py-2 text-xs text-(--fg-subtle)">
                No conversations yet.
              </div>
            ) : (
              <ul className="space-y-px">
                {recent.map((c) => {
                  const active = pathname === `/c/${c.id}`;
                  return (
                    <li key={c.id}>
                      <Link
                        href={`/c/${c.id}`}
                        className={cn(
                          "block truncate rounded-md px-2 py-1.5 text-sm transition-colors",
                          active
                            ? "bg-(--bg-hover) text-(--fg)"
                            : "text-(--fg-muted) hover:bg-(--bg-hover) hover:text-(--fg)",
                        )}
                        title={c.title || "Untitled"}
                      >
                        {c.title || "Untitled"}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>
      )}

      {/* Secondary nav */}
      <nav className={cn("flex flex-col gap-0.5 border-t border-(--border) p-2")}>
        {NAV.map(({ href, label, icon: Icon, matchPrefix }) => {
          const active =
            pathname === href || (matchPrefix && pathname.startsWith(matchPrefix));
          return collapsed ? (
            <HoverTip key={href} label={label} side="right">
              <Link
                href={href}
                className={cn(
                  "flex h-8 w-full items-center justify-center rounded-md transition-colors",
                  active
                    ? "bg-(--bg-hover) text-(--fg)"
                    : "text-(--fg-muted) hover:bg-(--bg-hover) hover:text-(--fg)",
                )}
                aria-label={label}
              >
                <Icon size={14} />
              </Link>
            </HoverTip>
          ) : (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors",
                active
                  ? "bg-(--bg-hover) text-(--fg)"
                  : "text-(--fg-muted) hover:bg-(--bg-hover) hover:text-(--fg)",
              )}
            >
              <Icon size={14} />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Footer: status + theme */}
      <div
        className={cn(
          "flex items-center gap-2 border-t border-(--border) px-3 py-2",
          collapsed && "flex-col gap-1.5",
        )}
      >
        <StatusPill compact={collapsed} />
        <div className="ml-auto">
          <ThemeToggle />
        </div>
      </div>
    </aside>
  );
}
