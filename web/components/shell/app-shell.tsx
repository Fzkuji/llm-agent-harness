"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ensureWS } from "@/lib/ws";
import { useShortcuts } from "@/lib/shortcuts";
import { Sidebar } from "./sidebar";
import { CommandPalette } from "./command-palette";

/**
 * Top-level chrome around every authenticated page. Owns the sidebar,
 * the persistent WebSocket, the command palette, and global shortcuts.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [paletteOpen, setPaletteOpen] = useState(false);

  useEffect(() => {
    ensureWS();
  }, []);

  useShortcuts([
    { key: "k", meta: true, allowInInput: true, handler: () => setPaletteOpen((o) => !o) },
    { key: "k", ctrl: true, allowInInput: true, handler: () => setPaletteOpen((o) => !o) },
    { key: "n", meta: true, handler: () => router.push("/chat") },
    { key: "n", ctrl: true, handler: () => router.push("/chat") },
    { key: "/", meta: true, handler: () => router.push("/chat") },
  ]);

  return (
    <div className="flex h-dvh w-screen overflow-hidden bg-(--bg-base) text-(--fg)">
      <Sidebar />
      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {children}
      </main>
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
    </div>
  );
}
