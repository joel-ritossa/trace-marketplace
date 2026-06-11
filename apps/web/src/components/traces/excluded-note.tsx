import { cn } from "@/lib/utils";

/** The filter-exclusion note (4_pages.md): analysis predicates honestly
 *  exclude not-yet-analyzed traces; say so instead of silently shrinking
 *  the result set. */
export function ExcludedNote({
  count,
  className,
}: {
  count: number | null | undefined;
  className?: string;
}) {
  if (!count) return null;
  return (
    <p className={cn("text-xs text-muted-foreground", className)}>
      {count} not-yet-analyzed trace{count === 1 ? "" : "s"} excluded by analysis filters.
    </p>
  );
}
