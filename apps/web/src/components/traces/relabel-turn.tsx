"use client";

import { useEffect, useState } from "react";
import { Tags } from "lucide-react";
import {
  FAILURE_MODES,
  OUTCOMES,
  TASK_CATEGORY_PICKER_GROUPS,
  humanize,
} from "@/components/review/taxonomy";
import { BusyLabel } from "@/components/traces/bulk-bar";
import { MultiSelect } from "@/components/traces/multi-select";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { errorText } from "@/lib/api/client";
import {
  relabelTurn,
  type Outcome,
  type TraceAnalysis,
  type TurnAnalysis,
} from "@/lib/api/traces";
import { cn } from "@/lib/utils";

type FailureDraft = { span_ids: string[]; reason: string };

/** Owner relabel of one turn (PUT .../turns/{n}/labels): the full label set
 *  replaces the turn's, which becomes human-labeled. Kept failure modes keep
 *  their cited spans; API errors show verbatim. Each new `openSignal` value
 *  opens the dialog (a relabel action elsewhere, e.g. the uncertain popover). */
export function RelabelTurn({
  traceId,
  turn,
  onSaved,
  openSignal = 0,
}: {
  traceId: string;
  turn: TurnAnalysis;
  onSaved: (analysis: TraceAnalysis) => void;
  openSignal?: number;
}) {
  const [open, setOpen] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [categories, setCategories] = useState<string[]>([]);
  const [failures, setFailures] = useState<Map<string, FailureDraft>>(new Map());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Seeded from the current labels each time the dialog opens.
  function onOpenChange(next: boolean) {
    if (next) {
      setOutcome(turn.outcome);
      setCategories(turn.labels.filter((l) => l.field === "task_category").map((l) => l.value));
      setFailures(
        new Map(
          turn.labels
            .filter((l) => l.field === "failure_mode")
            .map((l) => [l.value, { span_ids: l.span_ids, reason: l.reason ?? "" }]),
        ),
      );
      setError(null);
    }
    setOpen(next);
  }

  useEffect(() => {
    if (openSignal > 0) onOpenChange(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openSignal]);

  function toggleFailure(value: string, checked: boolean) {
    setFailures((prev) => {
      const next = new Map(prev);
      if (checked) {
        const original = turn.labels.find((l) => l.field === "failure_mode" && l.value === value);
        next.set(value, { span_ids: original?.span_ids ?? [], reason: original?.reason ?? "" });
      } else {
        next.delete(value);
      }
      return next;
    });
  }

  function setReason(value: string, reason: string) {
    setFailures((prev) => new Map(prev).set(value, { ...prev.get(value)!, reason }));
  }

  async function onSave() {
    if (outcome === null) return;
    setBusy(true);
    setError(null);
    try {
      const analysis = await relabelTurn(traceId, turn.turn_index, {
        outcome,
        task_categories: categories,
        failure_modes: [...failures].map(([value, draft]) => ({
          value,
          span_ids: draft.span_ids,
          reason: draft.reason.trim() || null,
        })),
      });
      onSaved(analysis);
      setOpen(false);
    } catch (err) {
      setError(errorText(err, "Could not save the labels — try again."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Button
        size="sm"
        variant="ghost"
        className="h-7 px-2 text-xs text-muted-foreground"
        onClick={() => onOpenChange(true)}
      >
        <Tags data-slot="icon" /> Relabel
      </Button>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Relabel turn {turn.turn_index + 1}</DialogTitle>
            <DialogDescription>
              Your labels replace the judge’s for this turn and are never re-judged.
            </DialogDescription>
          </DialogHeader>

          <div className="flex flex-col gap-4">
            <div>
              <p className="text-xs text-muted-foreground">Outcome</p>
              <div className="mt-1.5 grid grid-cols-2 gap-1.5 sm:grid-cols-4">
                {OUTCOMES.map(({ value, description }) => (
                  <button
                    key={value}
                    type="button"
                    title={description}
                    onClick={() => setOutcome(value)}
                    className={cn(
                      "rounded-md border px-2 py-1.5 text-xs font-medium transition-colors",
                      outcome === value
                        ? "border-foreground bg-foreground text-background"
                        : "text-muted-foreground hover:bg-accent hover:text-foreground",
                    )}
                  >
                    {humanize(value)}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <p className="text-xs text-muted-foreground">Task categories (at least one)</p>
              <MultiSelect
                groups={TASK_CATEGORY_PICKER_GROUPS}
                value={categories}
                onChange={setCategories}
                placeholder="Choose categories"
                aria-label="Task categories"
                className="mt-1.5"
              />
            </div>

            <div>
              <p className="text-xs text-muted-foreground">Failure modes (optional)</p>
              <ul className="mt-1.5 flex flex-col gap-2">
                {FAILURE_MODES.map(({ value, description }) => {
                  const draft = failures.get(value);
                  return (
                    <li key={value}>
                      <label className="flex cursor-pointer items-start gap-2 text-sm">
                        <Checkbox
                          checked={draft !== undefined}
                          onCheckedChange={(checked) => toggleFailure(value, checked === true)}
                          className="mt-0.5"
                        />
                        <span className="flex flex-col">
                          <span>{humanize(value)}</span>
                          <span className="text-xs text-muted-foreground">{description}</span>
                        </span>
                      </label>
                      {draft && (
                        <div className="mt-1.5 pl-6">
                          <Input
                            value={draft.reason}
                            onChange={(e) => setReason(value, e.target.value)}
                            placeholder="Reason (optional)"
                            className="h-8 text-xs"
                          />
                          {draft.span_ids.length > 0 && (
                            <p className="mt-1 text-xs text-muted-foreground">
                              Keeps {draft.span_ids.length} cited span
                              {draft.span_ids.length === 1 ? "" : "s"}.
                            </p>
                          )}
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>

            {error && <p className="text-sm text-error-deep">{error}</p>}
          </div>

          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              disabled={busy || outcome === null || categories.length === 0}
              onClick={onSave}
            >
              <BusyLabel busy={busy}>Save labels</BusyLabel>
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
