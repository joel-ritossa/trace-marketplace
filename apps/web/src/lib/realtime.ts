"use client";

import { useEffect, useRef } from "react";
import { createClient } from "@/lib/supabase/client";

/** Supabase Realtime as an invalidation signal only (4_pages.md Cross-Cutting):
 *  change events on the caller's own rows trigger `onChange` (throttled — a
 *  big CLI sync flips many rows fast, and the first event in a burst must
 *  still fire within the window, never starve); event payloads are never
 *  consumed as data, the API stays the single read path. Delivery is
 *  RLS-checked against the subscriber, so no owner filter is needed. A failed
 *  or absent socket degrades silently to refetch-on-navigation. */
export function useRealtimeRefetch(table: string, onChange: () => void) {
  const onChangeRef = useRef(onChange);
  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  useEffect(() => {
    const supabase = createClient();
    let timer: ReturnType<typeof setTimeout> | null = null;
    const channel = supabase
      .channel(`invalidate:${table}`)
      .on("postgres_changes", { event: "*", schema: "public", table }, () => {
        if (timer) return; // a refetch is already scheduled; coalesce
        timer = setTimeout(() => {
          timer = null;
          onChangeRef.current();
        }, 500);
      })
      .subscribe();
    return () => {
      if (timer) clearTimeout(timer);
      void supabase.removeChannel(channel);
    };
  }, [table]);
}
