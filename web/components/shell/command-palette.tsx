"use client";

import { Command } from "cmdk";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  History,
  MessageSquarePlus,
  Moon,
  PlayCircle,
  Search,
  Settings,
  Sun,
} from "lucide-react";
import { useTheme } from "next-themes";
import { api } from "@/lib/api";
import { useStore } from "@/lib/store";
import { Kbd } from "@/components/ui/kbd";
import { cn } from "@/lib/utils";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CommandPalette({ open, onOpenChange }: Props) {
  const router = useRouter();
  const { setTheme } = useTheme();
  const [query, setQuery] = useState("");
  const conversations = useStore((s) => s.conversations);

  const { data: functions = [] } = useQuery({
    queryKey: ["functions"],
    queryFn: () => api.listFunctions(),
    enabled: open,
  });

  const recents = useMemo(() => {
    return Object.values(conversations)
      .sort(
        (a, b) =>
          (b.updated_at ?? b.created_at ?? 0) - (a.updated_at ?? a.created_at ?? 0),
      )
      .slice(0, 6);
  }, [conversations]);

  function go(path: string, after?: () => void) {
    onOpenChange(false);
    router.push(path);
    after?.();
  }

  useEffect(() => {
    if (!open) setQuery("");
  }, [open]);

  return (
    <Command.Dialog
      open={open}
      onOpenChange={onOpenChange}
      label="Command palette"
      className={cn(
        "fixed left-1/2 top-[15vh] z-50 w-[calc(100vw-2rem)] max-w-xl -translate-x-1/2",
        "rounded-xl border border-(--border) bg-(--bg-surface) shadow-(--shadow-lg)",
        "data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95",
      )}
      shouldFilter
    >
      <Command.Input
        autoFocus
        value={query}
        onValueChange={setQuery}
        placeholder="Type a command, search programs, or pick a chat…"
        className={cn(
          "w-full border-b border-(--border) bg-transparent px-4 py-3 text-sm text-(--fg)",
          "placeholder:text-(--fg-subtle) focus:outline-none",
        )}
      />
      <Command.List className="scroll-y max-h-[60vh] p-1.5">
        <Command.Empty className="px-3 py-6 text-center text-sm text-(--fg-muted)">
          No results.
        </Command.Empty>

        <Command.Group heading="Actions" className="cmdk-group">
          <Item icon={MessageSquarePlus} label="New chat" shortcut="⌘N" onSelect={() => go("/chat")} />
          <Item icon={PlayCircle} label="Programs" onSelect={() => go("/programs")} />
          <Item icon={History} label="History" onSelect={() => go("/history")} />
          <Item icon={Settings} label="Settings" onSelect={() => go("/settings")} />
        </Command.Group>

        <Command.Group heading="Theme" className="cmdk-group">
          <Item icon={Sun} label="Light" onSelect={() => { setTheme("light"); onOpenChange(false); }} />
          <Item icon={Moon} label="Dark" onSelect={() => { setTheme("dark"); onOpenChange(false); }} />
          <Item icon={Search} label="System" onSelect={() => { setTheme("system"); onOpenChange(false); }} />
        </Command.Group>

        {recents.length > 0 && (
          <Command.Group heading="Recent chats" className="cmdk-group">
            {recents.map((c) => (
              <Item
                key={c.id}
                icon={Search}
                label={c.title || "Untitled"}
                onSelect={() => go(`/c/${c.id}`)}
              />
            ))}
          </Command.Group>
        )}

        {functions.length > 0 && (
          <Command.Group heading="Run a program" className="cmdk-group">
            {functions.slice(0, 24).map((fn) => (
              <Item
                key={fn.name}
                icon={PlayCircle}
                label={fn.name}
                hint={fn.category}
                onSelect={() => go(`/chat?prefill=${encodeURIComponent(`/run ${fn.name}`)}`)}
              />
            ))}
          </Command.Group>
        )}
      </Command.List>
    </Command.Dialog>
  );
}

function Item({
  icon: Icon,
  label,
  hint,
  shortcut,
  onSelect,
}: {
  icon: React.ComponentType<{ size?: number }>;
  label: string;
  hint?: string;
  shortcut?: string;
  onSelect: () => void;
}) {
  return (
    <Command.Item
      onSelect={onSelect}
      className={cn(
        "flex cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm",
        "data-[selected=true]:bg-(--bg-hover) data-[selected=true]:text-(--fg)",
        "text-(--fg-muted)",
      )}
    >
      <Icon size={14} />
      <span className="truncate">{label}</span>
      {hint && (
        <span className="ml-auto text-[11px] text-(--fg-subtle)">{hint}</span>
      )}
      {shortcut && (
        <Kbd className={cn("ml-auto", hint && "ml-2")}>{shortcut}</Kbd>
      )}
    </Command.Item>
  );
}
