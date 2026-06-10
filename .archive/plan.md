# Trace Marketplace Plan

## Purpose

This is the execution spine for taking Trace Marketplace from concept to a runnable local deployment. Each phase should produce enough clarity to support the next phase without turning planning into a second implementation.

The order is intentionally iterative:

1. Define what the product is proving.
2. Define who uses it and what they need to do.
3. Define the trace data lifecycle.
4. Design the database and API around that lifecycle.
5. Define pages around the flows and API states.
6. Build one complete vertical slice.
7. Package the local deployment and demo path.

## Phase Overview

| Phase | Focus | Primary Outputs | Status |
|---|---|---|---|
| [01 Product Thesis](docs/phases/01-product-thesis/README.md) | What the project must prove and what is intentionally out of scope. | Product thesis, demo success criteria, scope boundaries. | Started |
| [02 User Types And Flows](docs/phases/02-user-types-and-flows/README.md) | Who contributes, finds, inspects, evaluates, and downloads trace data. | User types, happy paths, edge states, handoff points. | Started |
| [03 Data Lifecycle](docs/phases/03-data-lifecycle/README.md) | How raw traces become validated, normalized, searchable, inspectable records. | Data lifecycle, canonical trace shape, privacy and provenance rules. | Next |
| [04 DB And API Design](docs/phases/04-db-api-design/README.md) | How storage, access, ingestion, search, and listing behavior are represented. | Tables, API endpoints, job states, error contracts. | Pending |
| [05 Page Definitions](docs/phases/05-page-definitions/README.md) | What screens exist and what each screen must show or let the user do. | Route map, page responsibilities, UI states. | Pending |
| [06 Vertical Slice](docs/phases/06-vertical-slice/README.md) | First end-to-end implementation path. | Upload, validate, store, inspect, search, list, and download one synthetic trace. | Pending |
| [07 Local Deployment](docs/phases/07-local-deployment/README.md) | How someone runs and evaluates the project locally. | Setup docs, seed fixtures, smoke test, local demo script. | Pending |

## Decision Gates

Confirm these before implementation starts:

- First supported demo trace format.
- Whether Postgres is the only required local infrastructure dependency.
- Whether uploads are private by default with explicit sharing or listing.
- Whether raw prompt and output text is excluded from search by default.
- Whether lightweight local identity is enough for contributor and consumer flows.
- Whether ingestion runs in a separate worker or inline during local development.

Accepted answers belong in [docs/decisions](docs/decisions/README.md). Unresolved questions belong in [docs/questions](docs/questions/).

## Working Rules

- Keep product, architecture, UX, and data-model decisions explicit before building against them.
- Preserve raw trace provenance while making safe derived metadata searchable.
- Use synthetic or explicitly scrubbed examples in committed fixtures and docs.
- Prefer one strong vertical slice over broad but shallow placeholder surfaces.
- Update this plan when a phase is completed or when the sequence changes.
