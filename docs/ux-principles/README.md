# UX Principles — Trace Marketplace

A machine-consumable UX constitution for coding agents working on this
product's frontend. Derived from the stage-1 spec (normative), stage-2
planning docs (under development), and authoritative UX sources (Nielsen
Norman Group, Material Design, Apple HIG, Primer, Polaris, Carbon, Fluent,
Atlassian) — reasoning extracted, not component APIs.

**Start here: [AGENT_RULES.md](AGENT_RULES.md)** — the procedure every agent
follows before implementing or reviewing UI.

The repo has two layers. [CORE_PRINCIPLES.md](CORE_PRINCIPLES.md) holds the
product-agnostic laws; the category folders hold those laws already
adjudicated for this product's surfaces — deliberately spec-shaped so they
are machine-checkable. Applied rules cite the core principle or spec rule
they derive from.

Scope: layout, hierarchy, navigation, workflows, discoverability, information
architecture, interaction design, decision-making. Visual styling (color,
type, spacing tokens) is owned by `DESIGN.md`, not this repo.

## Map

| Path | Contents |
|---|---|
| [product-map.yaml](product-map.yaml) | Phase-1 surface discovery: screens, workflows, shared patterns, cross-cutting spec rules |
| [CORE_PRINCIPLES.md](CORE_PRINCIPLES.md) | The 14 product-agnostic laws everything else derives from; reason from here for screens no archetype covers |
| [AGENT_RULES.md](AGENT_RULES.md) | The 8-step procedure; standing rules; authority order |
| `global/` | Hierarchy, IA, feedback, progressive disclosure, UI states — apply to every screen |
| `navigation/` | App shell, routing, deep links, return paths |
| `authentication/` | Auth flows, session expiry |
| `upload/` | File upload, async ingestion status |
| `tables/` | Trace lists (tables + cards), bulk selection (stage 2) |
| `search/` | Filtering (the shared filter language), saved queries / subscriptions (stage 2) |
| `trace-inspection/` | Span tree, span detail panel, metadata header — the core surface |
| `marketplace/` | Discovery cards, acquisition & download |
| `forms/` | Data entry, destructive actions, listing consent (product-critical) |
| `review-queue/` | HIL queue and resolve/labeling view (stage 2) |
| `notifications/` | Bell, feed, digests (stage 2) |
| `settings/` | API key management (stage 2) |
| `accessibility/` | Keyboard, color-independence, live regions |
| `anti-patterns/` | Global + product-specific anti-pattern libraries |
| `archetypes/` | Canonical layout skeletons per screen type (yaml) |
| `validation/` | Machine-reviewable checks per screen type (yaml) |

## Format conventions

- **Principles** (`<category>/*.md`): yaml blocks with `name`, `rule`,
  `rationale`, `examples` (positive/negative), `validation` (check ids),
  `sources`.
- **Anti-patterns** (`anti-patterns/*.md`): `name`, `description`,
  `consequence`, `fix`, `see` (owning principle file); `severity: spec_violation`
  where the failure breaks normative spec, not just judgment.
- **Archetypes** (`archetypes/*.yaml`): layout regions, state machines, action
  matrices, and a `must_load` manifest (principles, anti-patterns, checks).
- **Checks** (`validation/checks_by_screen.yaml`): boolean check ids grouped
  by screen type; `severity: spec` checks block, others are binding defaults.
  Check ids are defined in the principle files' `validation` lists.

## Maintenance

- Stage-2 surfaces (review queue, notifications, subscriptions, settings,
  bulk acquire) are written against the planning docs in
  `.archive/stage-2-planning/spec-shaping/`. When `docs/spec/stage-2/` is
  promoted, reconcile any drift — spec wins.
- A new screen type means a new archetype + a checks block + principle
  files, in the same pass as the feature.
- When a UX decision is made outside this repo (user discussion, audit
  finding), fold it in here in the same pass, mirroring how `docs/explainers/`
  is maintained.
