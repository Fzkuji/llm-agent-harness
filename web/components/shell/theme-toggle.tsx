"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { HoverTip } from "@/components/ui/tooltip";

const ORDER = ["system", "light", "dark"] as const;

export function ThemeToggle() {
  const { theme, setTheme, resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  if (!mounted) return <div className="h-7 w-7" />;

  const current = (theme ?? "system") as (typeof ORDER)[number];
  const Icon =
    current === "light" ? Sun : current === "dark" ? Moon : Monitor;

  function cycle() {
    const idx = ORDER.indexOf(current);
    setTheme(ORDER[(idx + 1) % ORDER.length]);
  }

  return (
    <HoverTip
      label={`Theme: ${current === "system" ? `system (${resolvedTheme})` : current}`}
    >
      <Button
        variant="ghost"
        size="icon-sm"
        onClick={cycle}
        aria-label="Toggle theme"
      >
        <Icon size={14} />
      </Button>
    </HoverTip>
  );
}
