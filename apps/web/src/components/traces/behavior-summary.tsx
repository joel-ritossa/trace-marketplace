import type { TraceAnalysis } from "@/lib/api/traces";

/** The behavior summary (machine-generated, descriptive): the gist up
 *  front, the step walkthrough behind a collapsed disclosure. Shared by the
 *  trace-detail Analysis section and the review resolve view; renders
 *  nothing when no summary exists (skipped, keyless, failed open). */
export function BehaviorSummary({ summary }: { summary: TraceAnalysis["summary"] }) {
  if (summary === null || (summary.gist === null && summary.steps.length === 0)) return null;
  return (
    <div>
      <h3 className="text-xs text-muted-foreground">What the agent did</h3>
      {summary.gist && <p className="mt-1 text-sm">{summary.gist}</p>}
      {summary.steps.length > 0 && (
        <details className="mt-1.5">
          <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground">
            Step walkthrough
          </summary>
          <ul className="mt-1.5 flex list-disc flex-col gap-1 pl-4 text-sm">
            {summary.steps.map((step, i) => (
              <li key={i}>{step}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
