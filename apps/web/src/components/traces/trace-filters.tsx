"use client";

import { ChevronDown, Search, SlidersHorizontal } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { FilterChips } from "@/components/traces/filter-chips";
import {
  LOOP_KIND_VALUES,
  OUTCOME_VALUES,
  csvValues,
  filterChips,
  toCsv,
} from "@/components/traces/filter-state";
import { MultiSelect, type MultiSelectGroup } from "@/components/traces/multi-select";
import { Switch } from "@/components/ui/switch";
import {
  FAILURE_MODES,
  TASK_CATEGORY_PICKER_GROUPS,
  humanize,
} from "@/components/review/taxonomy";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  listSkillValues,
  type SkillValue,
  type TraceFilters,
  type TraceScope,
  type TraceSort,
} from "@/lib/api/traces";
import { cn } from "@/lib/utils";

const SORT_OPTIONS: { value: TraceSort; label: string }[] = [
  { value: "created_at", label: "Newest" },
  { value: "duration_ms", label: "Longest" },
  { value: "span_count", label: "Most spans" },
];

const OUTCOME_OPTIONS = [...OUTCOME_VALUES];
const LOOP_KIND_OPTIONS = [...LOOP_KIND_VALUES];
const FAILURE_MODE_GROUPS: MultiSelectGroup[] = [{ values: FAILURE_MODES.map((m) => m.value) }];

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

// Radix Select has no empty value: "Any" travels as a sentinel.
const ANY = "__any";

/** The one single-select: the shadcn Select at the panel's input height. */
function PanelSelect({
  value,
  onChange,
  options,
  "aria-label": ariaLabel,
}: {
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  "aria-label"?: string;
}) {
  // An active value the select can't author (a stored subscription, a
  // hand-edited URL) still renders honestly.
  const all =
    value !== "" && !options.some((o) => o.value === value)
      ? [...options, { value, label: humanize(value) }]
      : options;
  return (
    <Select value={value === "" ? ANY : value} onValueChange={(v) => onChange(v === ANY ? "" : v)}>
      <SelectTrigger
        size="sm"
        aria-label={ariaLabel}
        className={cn("h-8 w-full text-xs", value === "" && "text-muted-foreground")}
      >
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ANY} className="text-xs">
          Any
        </SelectItem>
        {all.map((o) => (
          <SelectItem key={o.value} value={o.value} className="text-xs">
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
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
      <PanelSelect
        value={value}
        onChange={onChange}
        options={options.map((o) => ({ value: o, label: humanize(o) }))}
      />
    </Field>
  );
}

/** Tri-state signal filter: unset / yes / no (no is a real filter). */
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
      <PanelSelect
        value={value === undefined ? "" : String(value)}
        onChange={(v) => onChange(v === "" ? undefined : v === "true")}
        options={[
          { value: "true", label: "Yes" },
          { value: "false", label: "No" },
        ]}
      />
    </Field>
  );
}

/** Skills used in the session (a fact, not a judge label): options from the
 *  values endpoint, most-used first, as "name · count". */
function SkillsField({
  scope,
  value,
  onChange,
}: {
  scope: TraceScope;
  value: string[];
  onChange: (value: string[]) => void;
}) {
  const [values, setValues] = useState<SkillValue[]>([]);
  useEffect(() => {
    let cancelled = false;
    listSkillValues(scope)
      .then((v) => !cancelled && setValues(v))
      .catch(() => !cancelled && setValues([]));
    return () => {
      cancelled = true;
    };
  }, [scope]);
  const counts = new Map(values.map((v) => [v.name, v.trace_count]));
  return (
    <Field label="Skills">
      <MultiSelect
        groups={[{ values: values.map((v) => v.name) }]}
        value={value}
        onChange={onChange}
        placeholder="Any"
        format={(name) => (counts.has(name) ? `${name} · ${counts.get(name)}` : name)}
        hint={(name) => name}
        empty="No skills found in these traces"
      />
    </Field>
  );
}

/** Min-bound threshold control, ≥ affordance, no sliders (4_pages.md). */
function GteField({
  label,
  value,
  onChange,
  scale = 1,
}: {
  label: string;
  value: number | undefined;
  onChange: (value: number | undefined) => void;
  // Display units per stored unit (minutes for a ms filter: 60_000).
  scale?: number;
}) {
  return (
    <Field label={`${label} ≥`}>
      <input
        type="number"
        min={0}
        step="any"
        value={value === undefined ? "" : value / scale}
        onChange={(e) => {
          const parsed = Number(e.target.value);
          onChange(
            e.target.value === "" || !Number.isFinite(parsed) ? undefined : Math.round(parsed * scale),
          );
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
  scope = "mine",
}: {
  filters: TraceFilters;
  onChange: (filters: TraceFilters) => void;
  sort: TraceSort;
  onSortChange: (sort: TraceSort) => void;
  scope?: TraceScope;
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
        <span className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
          Sort
          <Select value={sort} onValueChange={(v) => onSortChange(v as TraceSort)}>
            <SelectTrigger size="sm" aria-label="Sort" className="h-8 text-xs text-foreground">
              <SelectValue />
            </SelectTrigger>
            <SelectContent align="end">
              {SORT_OPTIONS.map(({ value, label }) => (
                <SelectItem key={value} value={value} className="text-xs">
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </span>
      </div>

      {open && (
        <FilterFields
          filters={filters}
          set={set}
          text={text}
          setText={setText}
          scope={scope}
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
  scope = "mine",
}: {
  filters: TraceFilters;
  set: (patch: Partial<TraceFilters>) => void;
  text: FilterText;
  setText: (next: FilterText) => void;
  className?: string;
  // Which traces the skills options come from.
  scope?: TraceScope;
}) {
  return (
    <div className={cn("grid gap-x-4 gap-y-3", className)}>
      {/* Session facts first (what happened, incl. skills and deterministic
          signals); the judge's labels apart from them. */}
      <GroupLabel>Session</GroupLabel>
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

      <SkillsField
        scope={scope}
        value={csvValues(filters.skill)}
        onChange={(v) => set({ skill: toCsv(v) })}
      />
      <Field label="Errors">
        <span className="flex h-8 items-center gap-2 text-xs text-foreground">
          <Switch
            checked={filters.has_errors === true}
            onCheckedChange={(checked) => set({ has_errors: checked || undefined })}
          />
          Only traces with errors
        </span>
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
        label="Duration (min)"
        value={filters.duration_ms_gte}
        onChange={(v) => set({ duration_ms_gte: v })}
        scale={60_000}
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

      <GroupLabel>Judge labels</GroupLabel>
      <SelectField
        label="Outcome"
        value={filters.outcome ?? ""}
        onChange={(v) => set({ outcome: v || undefined })}
        options={OUTCOME_OPTIONS}
      />
      <Field label="Task category">
        <MultiSelect
          groups={TASK_CATEGORY_PICKER_GROUPS}
          value={csvValues(filters.task_category)}
          onChange={(v) => set({ task_category: toCsv(v) })}
          placeholder="Any"
        />
      </Field>
      <Field label="Failure mode">
        <MultiSelect
          groups={FAILURE_MODE_GROUPS}
          value={csvValues(filters.failure_mode)}
          onChange={(v) => set({ failure_mode: toCsv(v) })}
          placeholder="Any"
        />
      </Field>

    </div>
  );
}

/** True when any filter is active — drives the no-results-for-query state. */
export function hasActiveFilters(filters: TraceFilters): boolean {
  return Object.values(filters).some((v) => v !== undefined && v !== false);
}
