"use client";

import { useCallback } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";

// All list endpoints cap limit at 100; the default matches the density rules.
export const PAGE_SIZES: readonly number[] = [25, 50, 100];
export const DEFAULT_PAGE_SIZE = 25;

/** `?page=N&size=M` as the canonical page state (URL carries view state —
 *  4_pages Cross-Cutting). Defaults (page 1, size 25) keep the URL clean. */
export function usePageParam() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  // Truncate to an integer so garbage like ?page=1.5 can't become an offset.
  const page = Math.max(1, Math.trunc(Number(searchParams.get("page") ?? "1")) || 1);
  const sizeRaw = Number(searchParams.get("size"));
  const pageSize = PAGE_SIZES.includes(sizeRaw) ? sizeRaw : DEFAULT_PAGE_SIZE;

  const setPage = useCallback(
    (next: number) => {
      const params = new URLSearchParams(searchParams);
      if (next <= 1) params.delete("page");
      else params.set("page", String(next));
      router.push(params.size > 0 ? `${pathname}?${params}` : pathname);
    },
    [searchParams, router, pathname],
  );

  // A size change re-slices the whole list, so the page resets with it.
  const setPageSize = useCallback(
    (next: number) => {
      const params = new URLSearchParams(searchParams);
      params.delete("page");
      if (next === DEFAULT_PAGE_SIZE) params.delete("size");
      else params.set("size", String(next));
      router.push(params.size > 0 ? `${pathname}?${params}` : pathname);
    },
    [searchParams, router, pathname],
  );

  return { page, setPage, pageSize, setPageSize };
}

/** Standard pager, no infinite scroll (4_pages). Hidden when the smallest
 *  page size would still fit everything; otherwise the size selector must
 *  stay reachable even when the current size yields a single page. */
export function Pager({
  page,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  onPageSizeChange?: (size: number) => void;
}) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  if (onPageSizeChange ? total <= PAGE_SIZES[0] : pageCount <= 1) return null;

  const from = (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <p className="text-sm text-muted-foreground">
        {from}–{to} of {total}
      </p>
      <div className="flex items-center gap-2">
        {onPageSizeChange && (
          <label className="mr-2 flex items-center gap-1.5 text-xs text-muted-foreground">
            <select
              value={pageSize}
              onChange={(e) => onPageSizeChange(Number(e.target.value))}
              aria-label="Results per page"
              className="h-7 rounded-md border bg-background px-1.5 text-xs text-foreground"
            >
              {PAGE_SIZES.map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
            per page
          </label>
        )}
        <Button
          variant="outline"
          size="icon-sm"
          aria-label="Previous page"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          <ChevronLeft />
        </Button>
        <span className="text-sm tabular-nums">
          Page {page} of {pageCount}
        </span>
        <Button
          variant="outline"
          size="icon-sm"
          aria-label="Next page"
          disabled={page >= pageCount}
          onClick={() => onPageChange(page + 1)}
        >
          <ChevronRight />
        </Button>
      </div>
    </div>
  );
}
