# What does the judge see when a trace is rendered?

**One-line answer:** a rendering is a pure function of (trace, renderer
version, config) — a chronological OpenAI-style message list, hard-bounded to
a character budget, where the first user message, error spans, and the final
K steps survive first and every cut or elision is visibly marked.

This is the only trace-content surface that reaches an LLM (the outcome judge
in B2, quality critics in B3), so what it includes, what it drops, and how
reproducibly it does both are the questions that keep coming up.

## Mechanism

`render_trace(trace, config)` in `services/api/app/analysis/rendering.py`:

1. **Fixed messages.** A deterministic system header (trace name, status,
   span/error counts, duration, tools), then the first user message as a
   dedicated `user` message when one is extractable.
2. **One step per span**, chronological. Role maps from span kind (`llm` →
   assistant, `tool` → tool, else system). Every step carries a skeleton line
   — `[step i/N] kind name (status, duration)` — that survives all capping.
3. **Content extraction** (`content.py`) walks per-convention fallback
   chains, mirroring the importer's `mapping.py`: OTel GenAI
   `gen_ai.input/output.messages` → Traceloop flattened
   `gen_ai.prompt.N.*` → OpenInference `input.value`/`output.value` → span
   events. No extractable content fails open to a compact scalar-attribute
   summary, never a guess.
4. **Per-field caps first** (spec order): tool inputs/outputs truncated
   middle-out at `tool_field_cap_chars`, conversation content at the looser
   `conversation_cap_chars`, with an in-text `…[N chars truncated]…` marker
   (bare `…` when the cap is too small to fit the counted marker).
5. **Priority tiers:** must-haves are the first user message, all error
   spans, and the final K steps. If must-haves alone exceed the budget, the
   per-field caps halve (uniformly, so one config renders one way) down to a
   skeleton-only floor.
6. **Fill, then exact trim.** Remaining middle steps fill the leftover budget
   newest-first; elided ranges become explicit
   `[steps a-b elided (n steps)]` markers. Because marker costs shift as runs
   split, a final pass assembles the real message list and trims
   lowest-priority rendered steps — optional middles before pre-final-K error
   spans, oldest first — until the total is within budget.

`rendering_truncated` is set whenever any cap, halving, or elision fired, and
is stored with the judge's verdict.

## Determinism

Same trace + same config + same `RENDERER_VERSION` → byte-identical output.
Golden tests (`tests/unit/test_renderer_golden.py`) pin fixture renderings at
a fixed config; a golden diff without a `RENDERER_VERSION` bump is a contract
violation. Config values are env tunables (`ANALYSIS_RENDER_*`,
`.env.example`); changing them changes the rendering, by design.

## Caveats

- **The budget is chars, not tokens.** The env var speaks tokens (spec
  language) converted at ~4 chars/token (`config.CHARS_PER_TOKEN`) — a
  size/cost guard, not a hard model limit.
- **Under extreme budgets, pre-final-K error spans can be elided** (marked,
  never silent) — spec'd in `1_analysis.md` rendering. The first user
  message and the final K steps are never dropped, which is also the budget
  floor: with a degenerate config (budget smaller than K skeleton lines) the
  output runs over rather than dropping them.
- **The first user message follows the full fallback chain** (B4 pass 4):
  role-attributed input first (`gen_ai.*` structured or Traceloop flattened
  messages), then generic `input.value` — user-role mining when the value
  is a JSON message payload, the raw string as-is otherwise (the session
  importers' shape, where it *is* the ask). JSON payloads without user-role
  messages fail open to no dedicated user message; the content still
  appears on its span's step.
- One trace = one rendering unit; no session aggregation (extension).
