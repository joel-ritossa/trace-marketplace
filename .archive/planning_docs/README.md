# Docs

Project documentation for Trace Marketplace lives here. These docs should make product direction, architecture decisions, data-handling assumptions, and open questions easy to find without becoming a second implementation.

The top-level execution plan lives in [../plan.md](../plan.md).

## Structure

- [init-spec.md](init-spec.md): initial project brief, goal, scope, and deliverables.
- [expectations-synthesis.md](expectations-synthesis.md): current interpretation of the project expectations, demo flow, priorities, and working assumptions.
- [user-types-flows.md](user-types-flows.md): v1 product user types and flows used to define access and marketplace boundaries.
- [architecture-proposal.md](architecture-proposal.md): proposed Python plus Next.js TypeScript implementation architecture and code structure.
- [phases/](phases/): planning phases from product thesis through local deployment.
- [decisions/](decisions/): accepted decisions with enough context to audit later.
- [research/](research/): focused research notes that inform architecture or product decisions.
- [questions/](questions/): numbered open questions that need user, product, or architecture input before the answer is treated as settled.

## Conventions

- Keep root-level docs for durable product, architecture, setup, and data-handling guidance.
- Put settled decisions in `decisions/` using [decisions/0_TEMPLATE.md](decisions/0_TEMPLATE.md).
- Put exploratory technical research in `research/`, with a short summary entry in [research/README.md](research/README.md).
- Put unresolved material questions in `questions/` using numbered filenames such as `001_short_topic.md`.
- When a decision is made, update the durable root-level doc it affects and link back to supporting research or questions when useful.
- Use synthetic or explicitly scrubbed examples only. Do not commit secrets, credentials, private trace bodies, customer data, or long raw user content.
- Prefer concise docs with links between related files over duplicating the same guidance in multiple places.
