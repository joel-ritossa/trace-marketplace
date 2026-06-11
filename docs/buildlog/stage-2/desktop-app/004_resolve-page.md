# Desktop Tray App — Full-Page Resolve View

User feedback pass: (1) "I'm not seeing notifications" — diagnosed, no code
change: the app was running under `tauri dev`, where native notifications are
disabled by design (UNUserNotificationCenter needs a real `.app` bundle; see
002). The in-app tab and badge were healthy (local stack reachable, account
had unread rows). (2) Clicking Resolve should open the same view as the web's
`/review/[itemId]` page — evidence beside the verdict form — instead of the
old inline accordion form.

## Changes

- **Resolve page** (`ReviewItemPage.tsx`, new): plain-CSS port of the web's
  `review/resolve-view.tsx` — back link to the queue, trace name + "open
  trace page" link, machine context, verdict form (nothing pre-selected,
  partial answers fine, failure_mode only with a failure verdict),
  resolved/superseded panels, and "Resolve & next" walking the open queue
  newest-first via `listReviewItems(limit 2)`, same as the web.
- **Evidence pane** (`TraceEvidence.tsx`, `ConversationView.tsx`,
  `lib/conversation.ts`, `lib/traces.ts`, all new): ports the web's
  conversation reconstruction (span paging with 429 backoff, sequential
  llm/tool detail prefetch, structural dedupe, 200-span cap) and chat
  rendering. Deliberate divergence from the web: no raw span-tree/details
  toggle — that would drag the agent-prism component suite into the desktop
  bundle; the page links to the web trace page for raw span inspection.
- **Navigation** (`ReviewTab.tsx`): the queue now navigates to the item page
  (keyed by item id so "Resolve & next" gets a fresh form) instead of
  expanding an inline form; the inline `ResolveForm` is gone. Queue reload,
  60s fallback poll, and realtime invalidation unchanged.
- **Shared helper** (`lib/format.ts`): `formatDate` extracted from its three
  per-component copies; `getReviewItem` added to `lib/review.ts` (mirrors the
  web client).
- **Styles** (`styles.css`): `.page.wide` (full-width pages), `.resolve-grid`
  (evidence + 320px side column, stacking under 800px, evidence scrolling
  internally), `.label-list`, and the conversation bubble/tool/system-card
  ladder.

## Outcome

- `pnpm exec tsc --noEmit` passes; no linter errors.
- Click-through (queue → resolve page → resolve & next → back) left to
  interactive verification per the testing rules; the running `tauri dev`
  instance hot-reloads the change.
