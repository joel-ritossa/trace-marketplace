import { useEffect, useRef } from "react";
import { supabase } from "./supabase";

// supabase-js reuses channels by topic, so two subscribers to the same table
// (or a StrictMode remount racing its own async cleanup) would hit "cannot
// add postgres_changes callbacks after subscribe()". A unique topic per hook
// instance avoids it (the web's lib/realtime.ts does the same — its
// createBrowserClient is a singleton too).
let nextChannelId = 0;

/** Supabase Realtime as an invalidation signal only — mirrors the web's
 *  lib/realtime.ts: change events trigger a throttled refetch, payloads are
 *  never consumed as data, and a dead socket (or any setup failure) degrades
 *  silently to the fallback poll the callers keep running. */
export function useRealtimeRefetch(table: string, onChange: () => void) {
  const onChangeRef = useRef(onChange);
  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | null = null;
    try {
      const channel = supabase()
        .channel(`invalidate:${table}:${nextChannelId++}`)
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
        void supabase().removeChannel(channel);
      };
    } catch {
      // Realtime is an optimization; a throw here must never take the UI down.
      return () => {
        if (timer) clearTimeout(timer);
      };
    }
  }, [table]);
}
