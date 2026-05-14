"use client";

import * as React from "react";
import * as SliderPrimitive from "@radix-ui/react-slider";

import { cn } from "@/lib/utils";

type SliderProps = React.ComponentPropsWithoutRef<
  typeof SliderPrimitive.Root
> & {
  /** Draw N evenly-spaced tick marks centred on each step position.
      When set, the ticks render as small circles in `bg-bg-tertiary`
      so they "punch through" the track. Pass `options.length` for a
      discrete step slider; omit / pass < 2 for a smooth slider. */
  stops?: number;
};

const Slider = React.forwardRef<
  React.ElementRef<typeof SliderPrimitive.Root>,
  SliderProps
>(({ className, stops, ...props }, ref) => (
  <SliderPrimitive.Root
    ref={ref}
    className={cn(
      "relative flex w-full touch-none select-none items-center",
      className,
    )}
    {...props}
  >
    <SliderPrimitive.Track className="relative h-[4px] w-full grow overflow-hidden rounded-full bg-bg-hover">
      <SliderPrimitive.Range className="absolute h-full bg-[var(--accent-blue)]" />
    </SliderPrimitive.Track>
    {stops && stops > 1
      ? Array.from({ length: stops }).map((_, i) => (
          <span
            key={i}
            // Each tick sits at the same x as the thumb-center for that
            // step. `calc(ratio * (100% - 14px) + 7px)` mirrors Radix's
            // own thumb-position math (14px thumb, half-width 7).
            // `translate(-50%, -50%)` then pulls the tick's own centre
            // onto that point. `pointer-events-none` keeps the track
            // click area uninterrupted.
            className={cn(
              "pointer-events-none absolute top-1/2 size-[6px] rounded-full",
              "-translate-x-1/2 -translate-y-1/2",
              "bg-bg-tertiary",
            )}
            style={{ left: `calc(${i / (stops - 1)} * (100% - 14px) + 7px)` }}
            aria-hidden="true"
          />
        ))
      : null}
    <SliderPrimitive.Thumb
      className={cn(
        "relative block size-[14px] rounded-full bg-[var(--accent-blue)]",
        "border-2 border-[var(--bg-tertiary)]",
        "shadow-[0_1px_2px_rgba(0,0,0,0.15)]",
        "transition-transform duration-150 ease-out",
        "hover:scale-110",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-blue)]/40",
        "disabled:pointer-events-none disabled:opacity-50",
      )}
    />
  </SliderPrimitive.Root>
));
Slider.displayName = SliderPrimitive.Root.displayName;

export { Slider };
