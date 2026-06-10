# Decisions

Settled product, architecture, data, and UX decisions for Trace Marketplace live here.

Use this folder when a decision has been made and future readers need to understand what changed, why it was chosen, and what would cause us to revisit it.

## Index

- [001_v1_user_types.md](001_v1_user_types.md): v1 has two product user types: trace contributor and trace consumer.
- [002_initial_stack_baseline.md](002_initial_stack_baseline.md): initial repo stack uses Next.js, FastAPI, Supabase, and Docker Compose with several implementation choices deferred.

## Conventions

- Copy [0_TEMPLATE.md](0_TEMPLATE.md) for new decisions.
- Use numbered filenames such as `001_short_title.md`.
- Keep each decision short enough to audit in a few minutes.
- Link related research, open questions, implementation PRs, or docs when useful.
- Mark replaced decisions as `Superseded` and link to the newer decision instead of deleting history.
