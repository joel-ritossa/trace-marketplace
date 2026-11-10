"use client";

import { useLayoutEffect, useRef, useState, type KeyboardEvent, type MouseEvent } from "react";
import { cn } from "@/lib/utils";

const CLAMP = {
  1: "line-clamp-1",
  2: "line-clamp-2",
  3: "line-clamp-3",
  6: "line-clamp-6",
} as const;

/** Prose clamped to a few lines that expands in place: click (or Enter /
 *  Space) shows the rest, again collapses it. The affordance — pointer,
 *  underline on hover, a trailing "less" when open — appears only when the
 *  text is actually clamped. A drag-select never toggles, so copying works.
 *  Not for row titles in dense tables (those keep truncate + title). */
export function ExpandableText({
  text,
  lines = 2,
  className,
}: {
  text: string;
  lines?: keyof typeof CLAMP;
  className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const [open, setOpen] = useState(false);
  const [clamped, setClamped] = useState(false);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || open) return;
    const measure = () => setClamped(el.scrollHeight > el.clientHeight + 1);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [open, text]);

  const interactive = clamped || open;
  function toggle(e: MouseEvent | KeyboardEvent) {
    // Inside rows and popovers the toggle is this text's own click.
    e.stopPropagation();
    if (e.type === "click" && window.getSelection()?.toString()) return;
    setOpen((v) => !v);
  }

  return (
    <span
      ref={ref}
      role={interactive ? "button" : undefined}
      tabIndex={interactive ? 0 : undefined}
      aria-expanded={interactive ? open : undefined}
      onClick={interactive ? toggle : undefined}
      onKeyDown={
        interactive
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                toggle(e);
              }
            }
          : undefined
      }
      title={clamped && !open ? "Show all" : undefined}
      className={cn(
        "block break-words",
        !open && CLAMP[lines],
        open && "whitespace-pre-line",
        interactive &&
          "cursor-pointer rounded-sm decoration-muted-foreground/50 underline-offset-2 hover:underline focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
        className,
      )}
    >
      {text}
      {open && <span className="ml-1 text-xs text-muted-foreground"> less</span>}
    </span>
  );
}
