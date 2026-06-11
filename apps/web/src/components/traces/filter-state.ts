// One filter language, one artifact (4_pages.md): URL serialization and the
// chip model over TraceFilters, shared by search pages, subscription rows,
// and feed headers.

import type { TraceFilters, TraceSort } from "@/lib/api/traces";
import { filterParams } from "@/lib/api/traces";
import { humanize } from "@/components/review/taxonomy";

const STRING_KEYS = [
  "q",
  "provider",
  "model",
  "tool",
  "from",
  "to",
  "outcome",
  "failure_mode",
  "task_category",
  "loop_kind",
  "outcome_provenance",
  "failure_mode_provenance",
  "task_category_provenance",
] as const;

// Mirrors the backend's value validation (schemas/trace.py): strict sets for
// check-constrained vocabularies, slug shape for evolving taxonomies.
export const OUTCOME_VALUES = ["success", "failure", "indeterminate"] as const;
export const PROVENANCE_VALUES = ["machine", "human_confirmed", "human"] as const;
export const LOOP_KIND_VALUES = ["exact_repeat", "cycle", "stagnation"] as const;
const SLUG = /^[a-z][a-z0-9_]*$/;

const inSet = (allowed: readonly string[]) => (v: string) => allowed.includes(v);
const isSlug = (v: string) => SLUG.test(v);

// CSV fields validate per value; a single bad value drops the whole param
// (the API would 422 it — the URL is user input, so drop instead).
const STRING_VALUE_CHECKS: Partial<Record<(typeof STRING_KEYS)[number], (v: string) => boolean>> = {
  outcome: inSet(OUTCOME_VALUES),
  failure_mode: isSlug,
  task_category: isSlug,
  loop_kind: inSet(LOOP_KIND_VALUES),
  outcome_provenance: inSet(PROVENANCE_VALUES),
  failure_mode_provenance: inSet(PROVENANCE_VALUES),
  task_category_provenance: inSet(PROVENANCE_VALUES),
};

function validMetric(entry: string): boolean {
  const sep = entry.indexOf(":");
  if (sep <= 0 || !SLUG.test(entry.slice(0, sep))) return false;
  const bound = entry.slice(sep + 1);
  return bound === "true" || (bound.trim() !== "" && Number.isFinite(Number(bound)));
}

const BOOL_KEYS = ["has_errors", "has_retry_loop", "recovered_from_error", "truncation_suspected"] as const;

const NUMBER_KEYS = [
  "outcome_confidence_gte",
  "task_category_confidence_gte",
  "duration_ms_gte",
  "total_tokens_gte",
  "llm_call_count_gte",
  "tool_call_count_gte",
] as const;

/** URL search params → filters (the read half of the URL view-state law).
 *  Garbage values are dropped, never errored — the URL is user input, and
 *  anything the API would 422 must not reach it from here. */
export function paramsToFilters(params: URLSearchParams): TraceFilters {
  const filters: Record<string, unknown> = {};
  for (const key of STRING_KEYS) {
    const value = params.get(key);
    if (!value) continue;
    const check = STRING_VALUE_CHECKS[key];
    if (check && !value.split(",").every((v) => v.trim() === "" || check(v.trim()))) continue;
    filters[key] = value;
  }
  for (const key of BOOL_KEYS) {
    const value = params.get(key);
    if (value === "true") filters[key] = true;
    else if (value === "false" && key !== "has_errors") filters[key] = false;
  }
  for (const key of NUMBER_KEYS) {
    const raw = params.get(key);
    if (raw === null || raw.trim() === "") continue;
    const value = Number(raw);
    if (!Number.isFinite(value) || value < 0) continue;
    // Confidence bounds are 0–1 floats; the rest are non-negative ints.
    if (key.endsWith("confidence_gte") ? value <= 1 : Number.isInteger(value)) {
      filters[key] = value;
    }
  }
  const metric = params.getAll("metric").filter(validMetric);
  if (metric.length > 0) filters.metric = metric;
  return filters as TraceFilters;
}

/** Filters + sort → URL search params. The params are rebuilt from scratch —
 *  page is deliberately dropped (filter changes reset pagination). */
export function filtersToParams(filters: TraceFilters, sort: TraceSort): URLSearchParams {
  const params = filterParams(filters);
  if (sort !== "created_at") params.set("sort", sort);
  return params;
}

export type FilterChip = {
  key: keyof TraceFilters;
  /** For metric chips: which entry to remove. */
  value?: string;
  label: string;
};

const GTE_LABELS: Record<(typeof NUMBER_KEYS)[number], string> = {
  outcome_confidence_gte: "confidence",
  task_category_confidence_gte: "category confidence",
  duration_ms_gte: "duration ms",
  total_tokens_gte: "total tokens",
  llm_call_count_gte: "LLM calls",
  tool_call_count_gte: "tool calls",
};

/** Active predicates as chips, rendered verbatim (`faithfulness ≥ 0.8`). */
export function filterChips(filters: TraceFilters): FilterChip[] {
  const chips: FilterChip[] = [];
  for (const key of STRING_KEYS) {
    const value = filters[key];
    if (!value) continue;
    if (key === "q") chips.push({ key, label: `“${value}”` });
    else if (key === "from") chips.push({ key, label: `from ${value.slice(0, 10)}` });
    else if (key === "to") chips.push({ key, label: `to ${value.slice(0, 10)}` });
    else chips.push({ key, label: `${humanize(key)} = ${humanize(value)}` });
  }
  for (const key of BOOL_KEYS) {
    const value = filters[key];
    if (value === undefined || (key === "has_errors" && value !== true)) continue;
    chips.push({ key, label: `${humanize(key)} = ${value}` });
  }
  for (const key of NUMBER_KEYS) {
    const value = filters[key];
    if (value === undefined) continue;
    chips.push({ key, label: `${GTE_LABELS[key]} ≥ ${value}` });
  }
  for (const entry of filters.metric ?? []) {
    const [name, bound] = [entry.slice(0, entry.indexOf(":")), entry.slice(entry.indexOf(":") + 1)];
    chips.push({
      key: "metric",
      value: entry,
      label: bound === "true" ? `${humanize(name)} = true` : `${humanize(name)} ≥ ${bound}`,
    });
  }
  return chips;
}

/** Remove one chip's predicate from the filters. */
export function removeChip(filters: TraceFilters, chip: FilterChip): TraceFilters {
  if (chip.key === "metric") {
    const metric = (filters.metric ?? []).filter((m) => m !== chip.value);
    return { ...filters, metric: metric.length > 0 ? metric : undefined };
  }
  return { ...filters, [chip.key]: undefined };
}
