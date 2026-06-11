"use client";

import { useCallback } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";

/** `?page=N` as the canonical page state (URL carries view state — 4_pages
 *  Cross-Cutting). Page 1 keeps the URL clean. */
export function usePageParam() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  // Truncate to an integer so garbage like ?page=1.5 can't become an offset.
  const page = Math.max(1, Math.trunc(Number(searchParams.get("page") ?? "1")) || 1);

  const setPage = useCallback(
    (next: number) => {
      const params = new URLSearchParams(searchParams);
      if (next <= 1) params.delete("page");
      else params.set("page", String(next));
      router.push(params.size > 0 ? `${pathname}?${params}` : pathname);
    },
    [searchParams, router, pathname],
  );

  return { page, setPage };
}

/** Standard pager, no infinite scroll (4_pages). Hidden when one page. */
export function Pager({
  page,
  pageSize,
  total,
  onPageChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
}) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  if (pageCount <= 1) return null;

  const from = (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);

  return (
    <div className="flex items-center justify-between">
      <p className="text-sm text-muted-foreground">
        {from}–{to} of {total}
      </p>
      <div className="flex items-center gap-2">
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
