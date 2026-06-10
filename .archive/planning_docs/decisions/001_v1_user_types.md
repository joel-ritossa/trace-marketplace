# Decision: V1 User Types

## Context

Trace Marketplace needs clear product actors before defining the first user flows. Modeling paid purchasers, admins, or moderators as first-version user types would add product surface before the upload, ingestion, search, inspection, and download foundation is settled.

## Decision

The first version has two product user types:

- Trace contributor
- Trace consumer

A paid purchaser is treated as a future specialization of trace consumer. Admin or moderation behavior is not modeled as a first-version user type unless later user flows require it.

See [../user-types-flows.md](../user-types-flows.md) for the working definitions.

## Rationale

The two-user-type model matches the core marketplace exchange without forcing premature decisions about payments, licensing, manual moderation, organization membership, or production administration.

It also keeps the first user flows centered on the highest-priority system foundation:

- Contributors provide and manage trace data.
- Consumers discover, inspect, and download allowed trace data.
- The system validates, preserves, parses, indexes, and exposes traces between those two sides.

## Consequences

- User-flow work can focus on contribution, discovery, inspection, and download.
- Local evaluation can remain simple because one person can exercise both contributor and consumer paths.
- Paid purchaser-specific and admin-specific flows remain out of scope until pricing, access requests, moderation, or operational controls become material.
- This decision should be revisited if paid marketplace behavior, manual moderation, or organization-level access control becomes part of the first version.
