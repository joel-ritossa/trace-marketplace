# Vendored: AgentPrism UI components

Source: https://github.com/evilmartians/agent-prism (`packages/ui`, v0.0.9 —
matching the `@evilmartians/agent-prism-types`/`-data` npm deps), pulled via
degit per upstream's distribution model. MIT licensed, Copyright 2025 Evil
Martians and contributors; full license text ships with the npm packages
(`node_modules/@evilmartians/agent-prism-types/LICENSE`).

Local modifications (kept minimal so upstream diffs stay readable):

- `theme/theme.css` — upstream keys light/dark off `prefers-color-scheme`;
  rewritten so light values live on `:root` and dark values on `.dark`,
  following the app's next-themes selector.
- `theme/tailwind-bridge.css` — generated Tailwind 4 `@theme` bridge for
  upstream's Tailwind 3 palette names.

This directory is excluded from this repo's eslint (see `eslint.config.mjs`);
evaluation notes and alternatives live in
`docs/follow-up/trace-viewer-alternatives.md`.
