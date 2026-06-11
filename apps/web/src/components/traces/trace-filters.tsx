"use client";

import { ChevronDown, Plus, Search, SlidersHorizontal } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { FilterChips } from "@/components/traces/filter-chips";
import {
  LOOP_KIND_VALUES,
  OUTCOME_VALUES,
  PROVENANCE_VALUES,
  filterChips,
} from "@/components/traces/filter-state";
import { FAILURE_MODES, TASK_CATEGORIES, humanize } from "@/components/review/taxonomy";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { listMetricKeys, type TraceFilters, type TraceSort } from "@/lib/api/traces";
import { cn } from "@/lib/utils";

const SORT_OPTIONS: { value: TraceSort; label: string }[] = [
  { value: "created_at", label: "Newest" },
  { value: "duration_ms", label: "Longest" },
  { value: "span_count", label: "Most spans" },
];

const OUTCOME_OPTIONS = [...OUTCOME_VALUES];
const PROVENANCE_OPTIONS = [...PROVENANCE_VALUES];
const LOOP_KIND_OPTIONS = [...LOOP_KIND_VALUES];

const inputClass =
  "h-8 w-full rounded-md border bg-background px-2 text-xs text-foreground placeholder:text-muted-foreground";

/** A labeled panel field: label above control, full cell width. */
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex min-w-0 flex-col gap-1 text-xs text-muted-foreground">
      {label}
      {children}
    </label>
  );
}

function GroupLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="col-span-full mt-1 text-[11px] font-medium uppercase tracking-wider text-muted-foreground first:mt-0">
      {children}
    </p>
  );
}

function SelectField({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: string[];
}) {
  return (
    <Field label={label}>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={cn(inputClass, value === "" && "text-muted-foreground")}
      >
        <option value="">Any</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {humanize(option)}
          </option>
        ))}
        {value !== "" && !options.includes(value) && (
          // An active value the select can't author (a CSV from a stored
          // subscription or hand-edited URL) still renders honestly.
          <option value={value}>{humanize(value)}</option>
        )}
      </select>
    </Field>
  );
}

/** Tri-state signal filter: unset / true / false (false is a real filter). */
function BoolField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: boolean | undefined;
  onChange: (value: boolean | undefined) => void;
}) {
  return (
    <Field label={label}>
      <select
        value={value === undefined ? "" : String(value)}
        onChange={(e) => onChange(e.target.value === "" ? undefined : e.target.value === "true")}
        className={cn(inputClass, value === undefined && "text-muted-foreground")}
      >
        <option value="">Any</option>
        <option value="true">true</option>
        <option value="false">false</option>
      </select>
    </Field>
  );
}

/** Min-bound threshold control, ≥ affordance, no sliders (4_pages.md). */
function GteField({
  label,
  value,
  onChange,
  step,
  max,
}: {
  label: string;
  value: number | undefined;
  onChange: (value: number | undefined) => void;
  step?: string;
  max?: number;
}) {
  return (
    <Field label={`${label} ≥`}>
      <input
        type="number"
        min={0}
        max={max}
        step={step ?? "any"}
        value={value ?? ""}
        onChange={(e) => {
          const parsed = Number(e.target.value);
          onChange(e.target.value === "" || !Number.isFinite(parsed) ? undefined : parsed);
        }}
        className={inputClass}
      />
    </Field>
  );
}

/** The free-text half of the vocabulary, kept as raw input state so typing
 *  isn't clobbered by canonicalization (dates expand to ISO, etc.). */
export type FilterText = {
  q: string;
  provider: string;
  model: string;
  tool: string;
  from: string;
  to: string;
};

export function textFromFilters(filters: TraceFilters): FilterText {
  return {
    q: filters.q ?? "",
    provider: filters.provider ?? "",
    model: filters.model ?? "",
    tool: filters.tool ?? "",
    from: filters.from?.slice(0, 10) ?? "",
    to: filters.to?.slice(0, 10) ?? "",
  };
}

/** Raw text inputs folded into the structured filters. */
export function mergeText(filters: TraceFilters, text: FilterText): TraceFilters {
  return {
    ...filters,
    q: text.q.trim() || undefined,
    provider: text.provider.trim() || undefined,
    model: text.model.trim() || undefined,
    tool: text.tool.trim() || undefined,
    from: text.from ? `${text.from}T00:00:00Z` : undefined,
    to: text.to ? `${text.to}T23:59:59Z` : undefined,
  };
}

/** Search + filter bar shared by every list surface: a compact bar (search,
 *  Filters disclosure, sort) over a grouped panel carrying the full filter
 *  vocabulary; chips render every active predicate verbatim. The panel is an
 *  inline disclosure, not an overlay (routing law: dialogs are the only
 *  overlay UI). Text inputs debounce; everything else applies immediately. */
export function TraceFiltersBar({
  filters,
  onChange,
  sort,
  onSortChange,
}: {
  filters: TraceFilters;
  onChange: (filters: TraceFilters) => void;
  sort: TraceSort;
  onSortChange: (sort: TraceSort) => void;
}) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState(() => textFromFilters(filters));
  const lastEmitted = useRef<string | null>(null);

  // Reseed local text state when the URL changes from outside the bar
  // (chip removal, back button) — but never clobber mid-typing edits.
  const propKey = JSON.stringify([
    filters.q,
    filters.provider,
    filters.model,
    filters.tool,
    filters.from,
    filters.to,
  ]);
  useEffect(() => {
    if (propKey !== lastEmitted.current) {
      setText(textFromFilters(filters));
      lastEmitted.current = propKey;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [propKey]);

  const filtersRef = useRef(filters);
  const onChangeRef = useRef(onChange);
  useEffect(() => {
    filtersRef.current = filters;
    onChangeRef.current = onChange;
  }, [filters, onChange]);

  useEffect(() => {
    const handle = setTimeout(() => {
      const cur = filtersRef.current;
      const next = mergeText(cur, text);
      // No-op emits are skipped — the mount/reseed pass must not reach the
      // URL writer, which rebuilds params and would drop ?page.
      if (
        next.q === cur.q &&
        next.provider === cur.provider &&
        next.model === cur.model &&
        next.tool === cur.tool &&
        next.from === cur.from &&
        next.to === cur.to
      ) {
        return;
      }
      lastEmitted.current = JSON.stringify([
        next.q,
        next.provider,
        next.model,
        next.tool,
        next.from,
        next.to,
      ]);
      onChangeRef.current(next);
    }, 300);
    return () => clearTimeout(handle);
  }, [text]);

  const set = (patch: Partial<TraceFilters>) => onChange({ ...filters, ...patch });

  // The panel's active count — search lives in the bar, so it doesn't count.
  const panelCount = filterChips(filters).filter((chip) => chip.key !== "q").length;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={text.q}
            onChange={(e) => setText({ ...text, q: e.target.value })}
            placeholder="Search traces…"
            className="h-8 w-72 pl-8 text-xs"
          />
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
        >
          <SlidersHorizontal data-slot="icon" />
          Filters
          {panelCount > 0 && (
            <span className="rounded-full bg-secondary px-1.5 font-mono text-[10px] leading-4 text-foreground">
              {panelCount}
            </span>
          )}
          <ChevronDown
            data-slot="icon"
            className={cn("transition-transform", open && "rotate-180")}
          />
        </Button>
        <label className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
          Sort
          <select
            value={sort}
            onChange={(e) => onSortChange(e.target.value as TraceSort)}
            className="h-8 rounded-md border bg-background px-2 text-xs text-foreground"
          >
            {SORT_OPTIONS.map(({ value, label }) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {open && (
        <FilterFields
          filters={filters}
          set={set}
          text={text}
          setText={setText}
          className="grid-cols-2 rounded-lg border bg-background p-4 sm:grid-cols-3 lg:grid-cols-5"
        />
      )}

      <FilterChips filters={filters} onChange={onChange} />
    </div>
  );
}

/** The full structured-filter vocabulary as a labeled field grid — the bar's
 *  disclosure panel and the new-subscription dialog render the same fields. */
export function FilterFields({
  filters,
  set,
  text,
  setText,
  className,
}: {
  filters: TraceFilters;
  set: (patch: Partial<TraceFilters>) => void;
  text: FilterText;
  setText: (next: FilterText) => void;
  className?: string;
}) {
  return (
    <div className={cn("grid gap-x-4 gap-y-3", className)}>
      <GroupLabel>Trace</GroupLabel>
      <Field label="Provider">
        <input
          value={text.provider}
          onChange={(e) => setText({ ...text, provider: e.target.value })}
          placeholder="e.g. openai"
          className={inputClass}
        />
      </Field>
      <Field label="Model">
        <input
          value={text.model}
          onChange={(e) => setText({ ...text, model: e.target.value })}
          placeholder="e.g. gpt-4o"
          className={inputClass}
        />
      </Field>
      <Field label="Tool">
        <input
          value={text.tool}
          onChange={(e) => setText({ ...text, tool: e.target.value })}
          placeholder="e.g. web_search"
          className={inputClass}
        />
      </Field>
      <Field label="Started on or after">
        <input
          type="date"
          value={text.from}
          onChange={(e) => setText({ ...text, from: e.target.value })}
          className={inputClass}
        />
      </Field>
      <Field label="Started on or before">
        <input
          type="date"
          value={text.to}
          onChange={(e) => setText({ ...text, to: e.target.value })}
          className={inputClass}
        />
      </Field>

      <GroupLabel>Analysis</GroupLabel>
      <SelectField
        label="Outcome"
        value={filters.outcome ?? ""}
        onChange={(v) => set({ outcome: v || undefined })}
        options={OUTCOME_OPTIONS}
      />
      <SelectField
        label="Failure mode"
        value={filters.failure_mode ?? ""}
        onChange={(v) => set({ failure_mode: v || undefined })}
        options={FAILURE_MODES.map((m) => m.value)}
      />
      <SelectField
        label="Task category"
        value={filters.task_category ?? ""}
        onChange={(v) => set({ task_category: v || undefined })}
        options={TASK_CATEGORIES}
      />
      <SelectField
        label="Outcome provenance"
        value={filters.outcome_provenance ?? ""}
        onChange={(v) => set({ outcome_provenance: v || undefined })}
        options={PROVENANCE_OPTIONS}
      />
      <GteField
        label="Outcome confidence"
        value={filters.outcome_confidence_gte}
        onChange={(v) => set({ outcome_confidence_gte: v })}
        step="0.05"
        max={1}
      />

      <GroupLabel>Quality metrics</GroupLabel>
      <MetricBuilder filters={filters} set={set} />

      <GroupLabel>Signals &amp; counts</GroupLabel>
      <Field label="Errors">
        <label className="flex h-8 cursor-pointer items-center gap-2 rounded-md border bg-background px-2 text-xs text-muted-foreground">
          <input
            type="checkbox"
            checked={filters.has_errors === true}
            onChange={(e) => set({ has_errors: e.target.checked || undefined })}
            className="size-3 accent-foreground"
          />
          has errors
        </label>
      </Field>
      <SelectField
        label="Loop kind"
        value={filters.loop_kind ?? ""}
        onChange={(v) => set({ loop_kind: v || undefined })}
        options={LOOP_KIND_OPTIONS}
      />
      <BoolField
        label="Retry loop"
        value={filters.has_retry_loop}
        onChange={(v) => set({ has_retry_loop: v })}
      />
      <BoolField
        label="Recovered from error"
        value={filters.recovered_from_error}
        onChange={(v) => set({ recovered_from_error: v })}
      />
      <BoolField
        label="Truncation suspected"
        value={filters.truncation_suspected}
        onChange={(v) => set({ truncation_suspected: v })}
      />
      <GteField
        label="Category confidence"
        value={filters.task_category_confidence_gte}
        onChange={(v) => set({ task_category_confidence_gte: v })}
        step="0.05"
        max={1}
      />
      <GteField
        label="Duration (ms)"
        value={filters.duration_ms_gte}
        onChange={(v) => set({ duration_ms_gte: v })}
      />
      <GteField
        label="Total tokens"
        value={filters.total_tokens_gte}
        onChange={(v) => set({ total_tokens_gte: v })}
      />
      <GteField
        label="LLM calls"
        value={filters.llm_call_count_gte}
        onChange={(v) => set({ llm_call_count_gte: v })}
      />
      <GteField
        label="Tool calls"
        value={filters.tool_call_count_gte}
        onChange={(v) => set({ tool_call_count_gte: v })}
      />
    </div>
  );
}

/** metric ≥ bound builder: keys enumerated from observed data, not
 *  hardcoded (4_pages.md); each entry becomes its own removable chip. */
function MetricBuilder({
  filters,
  set,
}: {
  filters: TraceFilters;
  set: (patch: Partial<TraceFilters>) => void;
}) {
  const [metricKeys, setMetricKeys] = useState<string[]>([]);
  const [draft, setDraft] = useState({ name: "", bound: "" });

  useEffect(() => {
    listMetricKeys()
      .then(setMetricKeys)
      .catch(() => setMetricKeys([]));
  }, []);

  const add = () => {
    if (!draft.name || !draft.bound) return;
    const entry = `${draft.name}:${draft.bound}`;
    const metric = filters.metric ?? [];
    if (!metric.includes(entry)) set({ metric: [...metric, entry] });
    setDraft({ name: "", bound: "" });
  };

  return (
    <div className="col-span-2 flex items-end gap-1.5 sm:col-span-3">
      <Field label="Metric">
        <select
          value={draft.name}
          onChange={(e) => setDraft({ ...draft, name: e.target.value })}
          className={cn(inputClass, draft.name === "" && "text-muted-foreground")}
        >
          <option value="">Choose a metric</option>
          {metricKeys.map((key) => (
            <option key={key} value={key}>
              {humanize(key)}
            </option>
          ))}
        </select>
      </Field>
      <Field label="≥ bound">
        <input
          value={draft.bound}
          onChange={(e) => setDraft({ ...draft, bound: e.target.value.trim() })}
          onKeyDown={(e) => e.key === "Enter" && add()}
          placeholder="0.8 or true"
          className={inputClass}
        />
      </Field>
      <button
        type="button"
        aria-label="Add metric filter"
        onClick={add}
        disabled={!draft.name || !draft.bound}
        className="flex h-8 shrink-0 items-center rounded-md border bg-background px-2 text-muted-foreground transition-colors hover:text-foreground disabled:opacity-40"
      >
        <Plus className="size-3.5" />
      </button>
    </div>
  );
}

/** True when any filter is active — drives the no-results-for-query state. */
export function hasActiveFilters(filters: TraceFilters): boolean {
  return Object.values(filters).some(
    (v) => v !== undefined && v !== false && (!Array.isArray(v) || v.length > 0),
  );
}
