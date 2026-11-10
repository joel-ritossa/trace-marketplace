"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api/client";
import { getTrace, type TraceDetail } from "@/lib/api/traces";
import { useRealtimeRefetch } from "@/lib/realtime";

export type TraceLoadState =
  | { phase: "loading" }
  | { phase: "not-found" }
  | { phase: "error"; message: string }
  | { phase: "ready"; trace: TraceDetail };

/** One trace detail (metadata + analysis block), kept live: metadata and
 *  attempt flips land via "traces", the session roll-up via
 *  "trace_analysis", per-turn verdicts via "turn_analysis". `setTrace`
 *  applies a write's response without waiting for the refetch. */
export function useTraceDetail(traceId: string) {
  const [state, setState] = useState<TraceLoadState>({ phase: "loading" });
  const loadTicket = useRef(0);

  const load = useCallback(async () => {
    const ticket = ++loadTicket.current;
    try {
      const trace = await getTrace(traceId);
      if (ticket === loadTicket.current) setState({ phase: "ready", trace });
    } catch (err) {
      if (ticket !== loadTicket.current) return;
      if (err instanceof ApiError && err.status === 404) {
        setState({ phase: "not-found" });
      } else {
        // A failed background refetch must not blank a rendered trace.
        setState((prev) =>
          prev.phase === "ready"
            ? prev
            : {
                phase: "error",
                message: err instanceof ApiError ? err.message : "Could not load the trace.",
              },
        );
      }
    }
  }, [traceId]);

  useEffect(() => {
    void load();
  }, [load]);

  useRealtimeRefetch("traces", load);
  useRealtimeRefetch("trace_analysis", load);
  useRealtimeRefetch("turn_analysis", load);

  const setTrace = useCallback((trace: TraceDetail) => {
    setState((prev) => (prev.phase === "ready" ? { ...prev, trace } : prev));
  }, []);

  return { state, setTrace };
}
