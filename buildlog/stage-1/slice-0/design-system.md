# Design System Integration (shadcn/ui)

Follow-up pass after the audit: wire DESIGN.md into a real component layer
before Slice 1 UI work starts.

## Decision

- **shadcn/ui** (radix flavor) as the component implementation layer — copied
  into `src/components/ui/`, owned by us, no runtime library lock-in. Full
  design systems (MUI/Chakra/Mantine) were rejected: they'd fight DESIGN.md
  for source-of-truth. Headless-only (Radix/React Aria) was rejected as more
  styling work than the trial warrants.
- Contract: **DESIGN.md decides how things look** (tokens + adaptation
  rules), **shadcn decides how components behave** (a11y, focus, keyboard),
  **CSS variables in `globals.css` are the bridge**.
- Icons: `lucide-react` (installed with shadcn). Scaffold SVGs deleted.
- App surfaces are light-only per the adaptation section; the `.dark` class
  is never set (the `@custom-variant` pins `dark:` styles to it, so they
  stay dormant instead of following the OS scheme).

## Changes

- `shadcn init` in `apps/web` (components.json, `lib/utils.ts` (`cn`), deps:
  radix-ui, cva, clsx, tailwind-merge, lucide-react, tw-animate-css).
- `globals.css`: shadcn semantic variables resolved to DESIGN.md hex tokens
  (canvas/ink/hairline/mute/error etc., `--radius` 8px so `rounded-md` lands
  on the 6px nav scale); a second `@theme` block adds the domain tokens —
  status palette (`status-ok`, `warning-*`, `error-*`, `link-*`) and the
  span-kind palette (`span-llm`, `span-agent`, `span-tool`, `span-retriever`,
  `span-embedding`, `span-other`). Unused sidebar/chart variables dropped.
- Hand-rolled `Button`/`Input` replaced by shadcn versions; consumers updated
  (`auth-form` uses `size="lg"`, sign-out uses `variant="outline" size="sm"`).
- `AGENTS.md` engineering rule added: components come from shadcn, themed via
  the globals.css variables; lucide for icons; light-only.

## UI Polish Pass

Applied the new system to the Slice 0 surfaces (and dropped the dev demo UI):

- **Ping demo page removed.** `api-roundtrip.tsx` deleted along with its ping
  types; the `/v1/dev/*` API routes and worker task stay (flag-gated,
  curl-able). `apiFetch` and the `Me` type remain — Slice 1 uses them.
- **Auth pages**: `ex-auth-form-card` chrome — canvas card on a
  `canvas-soft` page (new `--color-canvas-soft` token), labeled inputs
  (shadcn `label` added), link-colored switch links, errors in `error-deep`.
- **App shell**: 64px canvas header on hairline border per `nav-bar`, email
  as mono caption, outline sign-out; content on the `canvas-soft` ladder.
- **Home page**: "Traces" heading + `ex-empty-state-card` empty state
  (lucide `ScrollText`), explicitly the slot Slice 1's upload/list fills.

## Outcome

Verified 2026-06-10: lint + build pass; rebuilt web container; in-browser
checks of sign-in, sign-out, and the authenticated home page — all render
with DESIGN.md tokens (Geist faces, ink primary CTA, hairline borders,
canvas-soft surface ladder).
