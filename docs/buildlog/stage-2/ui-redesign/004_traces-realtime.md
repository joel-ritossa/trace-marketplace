# UI Redesign — Pass 004: Traces list + detail go realtime

User feedback: traces landing from a sync and analysis verdicts appearing did not show up live — the list and detail pages only refetched on navigation or filter changes, while `/uploads` and notifications were already realtime.

## Change

- Migration `00000000000014_traces_realtime.sql`: `traces` and `trace_analysis` join the `supabase_realtime` publication. Delivery is RLS-checked against the subscriber (owner-or-listed), the same read rule the surfaces already follow — listed-trace events reaching marketplace viewers is intended.
- `use-trace-list.ts`: `useRealtimeRefetch` on `traces` and `trace_analysis` drives the existing `reload`, so every list surface (traces, marketplace, library) re-runs its current query when rows land or verdicts flip. The stale page stays rendered until the refetch resolves — no flash.
- `TraceInspector` and `AnalysisSection`: fetch effects refactored into a reusable `load` with a ticket guard against stale responses; both subscribe (`traces` + `trace_analysis` — the header outcome badge joins from analysis, and the analysis panel's pending→complete flip is the headline case). A failed background refetch keeps the rendered data instead of blanking to an error; a 404 (trace deleted under you) honestly flips to not-found. `TraceMetaEditor` drafts are mount-initialized state, so background refetches don't clobber in-progress edits.
- Spec updated: `4_pages.md` cross-cutting realtime bullet now names the trace surfaces as wired.

## Outcome

Migration applied locally (`supabase migration up`); `tsc --noEmit` clean. `pnpm lint` has one pre-existing error in `trace-evidence.tsx` (`react-hooks/set-state-in-effect`), untouched by this pass.
