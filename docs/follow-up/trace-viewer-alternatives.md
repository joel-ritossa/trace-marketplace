# Trace Viewer Alternatives

Slice 2 adopted [AgentPrism](https://github.com/evilmartians/agent-prism)
(Evil Martians) for the span tree + detail panel on `/traces/[traceId]`:
purpose-built for AI-agent traces, vendored shadcn-style into
`apps/web/src/components/agent-prism/`, themable via CSS tokens. The spike
passed (React 19/Next 16/Tailwind 4, light theme, full raw attributes), so it
won on time-to-value — not after a deep comparison. Worth revisiting.

## Why it might lose later

- **Alpha software.** Upstream marks APIs unstable. Vendoring insulates us
  from breakage but means we absorb maintenance; upstream fixes don't flow in
  automatically.
- **No virtualization.** Every visible span is in the DOM (~49 nodes per
  span card). At 3000 spans fully expanded, selection re-render was ~1.2s
  (dev build). Mitigated by shallow default expansion and the paginated
  spans API; would bite on a "expand all" of a huge trace.
- **Visual identity.** Tokens are bridged, but its component styling (cards,
  badges, timeline bars) isn't DESIGN.md-native. Acceptable now; a polish
  pass may fight it.

## Candidates if revisited

- **`@assistant-ui/react-o11y`** — headless Radix-style span-tree primitives
  (depth, collapse, time-range math), zero styling. More assembly, full
  DESIGN.md control, and we'd add our own virtualization.
- **Hand-rolled** — indented rows + percent-offset duration bars is
  ~200–300 lines (the Langfuse/Phoenix approach), trivially virtualized with
  `@tanstack/react-virtual`. Most control, most work.
- Re-check the ecosystem before building: this space is moving fast
  (AgentPrism itself appeared mid-2025).

## What would change the call

- Traces with tens of thousands of spans become a common case (virtualization
  becomes mandatory).
- A design pass wants the inspection surface fully on DESIGN.md tokens.
- Upstream AgentPrism stabilizes and ships virtualization — then re-vendor
  instead of replacing.
