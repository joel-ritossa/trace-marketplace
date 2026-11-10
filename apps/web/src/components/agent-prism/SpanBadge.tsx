import type { TraceSpanCategory } from "@evilmartians/agent-prism-types";

import cn from "classnames";

import { Badge, type BadgeProps } from "./Badge";
import { getSpanCategoryLabel, SPAN_KIND_DOT } from "./shared";

export interface SpanBadgeProps
  extends Omit<BadgeProps, "label" | "iconStart" | "iconEnd"> {
  category: TraceSpanCategory;
}

/** Span kind as a neutral pill with the span-kind palette dot (DESIGN.md:
 *  hue on the dot, never as a fill). */
export const SpanBadge = ({ category, className, ...props }: SpanBadgeProps) => (
  <Badge
    className={cn("bg-secondary text-foreground/75 rounded-full !px-1.5", className)}
    iconStart={<span className={cn("block size-1.5 rounded-full", SPAN_KIND_DOT[category])} />}
    {...props}
    unstyled
    label={getSpanCategoryLabel(category)}
  />
);
