"use client";

import { useStore } from "@/lib/store";
import { cn } from "@/lib/utils";

export function StatusPill({ compact = false }: { compact?: boolean }) {
  const status = useStore((s) => s.wsStatus);

  const label =
    status === "open" ? "Connected" : status === "connecting" ? "Connecting…" : "Offline";
  const dotColor =
    status === "open"
      ? "bg-(--success)"
      : status === "connecting"
        ? "bg-(--warn)"
        : "bg-(--danger)";

  return (
    <div
      className="flex items-center gap-2 text-xs text-(--fg-muted)"
      title={label}
    >
      <span
        className={cn(
          "inline-block h-1.5 w-1.5 shrink-0 rounded-full",
          dotColor,
          status === "connecting" && "animate-pulse",
        )}
      />
      {!compact && <span className="truncate">{label}</span>}
    </div>
  );
}
