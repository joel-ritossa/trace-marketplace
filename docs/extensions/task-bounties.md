# Extension: Task Bounties

The demand side: a consumer registers a bounty — rule-based criteria over trace fields plus a description of what they want — and the system finds matching traces, historic and incoming, alerting the contributors who own them. Named in the spec's extension list (`docs/spec/stage-2/0_README.md`); ideation origin is session 5, **redesigned under the rule-based matching principle**: a bounty is a stored query, not a declared embedding cluster.

## Shape

- A bounty = `name` + free-text `brief` (human-readable: what the consumer wants and why) + a stored query in **the same filter vocabulary as `GET /v1/traces` and subscriptions** (`docs/spec/stage-2/3_api.md`). Any filterable field works, derived fields included: `tool_names` contains X AND `task_category = customer_ops` AND `outcome = success` AND `outcome_provenance != machine`.
- Structurally a subscription with one inversion: a subscription matches *listed* traces for its owner; a bounty matches **other users' traces, private ones included**, and alerts the *trace owner*, not the bounty owner.

## Matching and consent

Privacy semantics are the heart of the design (locked in the stage-2 requirements; restated in the spec's privacy decision):

- Matching runs over historic traces (backfill at registration) and incoming ones (the same event triggers as subscriptions: listed; analysis-complete — plus the analysis-complete trigger evaluated for private traces too, bounty-only).
- **Alerts go only to the trace owner** (`bounty_match` notification — an additive type per `docs/spec/stage-2/2_data-model.md`). The bounty owner never sees private matches, nor their existence: no counts, no "12 potential matches" — private means invisible.
- **Listing remains the consent act.** A private match produces an owner-side nudge ("N of your private traces match bounty X — list them to fulfill it"); fulfillment is the owner listing the trace, with the standard consent dialog. Nothing is ever auto-listed or auto-submitted.
- The bounty owner's view shows only listed matches, in a subscription-style feed with bulk acquire.

## Fulfillment ladder (session 5's cost ladder, rule-based)

1. **Backfill** — at registration, the stored query runs over listed traces: instant inventory if it exists.
2. **Continuous matching** — incoming listed traces match event-driven, exactly like subscriptions.
3. **Owner nudges** — private matches alert their owners; solicitation without publication.
4. **(Future) published bounties** — surfacing open bounties in the marketplace UI, and desktop prompts via the [desktop-notifications extension](../.archive/stage-2-planning/spec-shaping/requirements.md). Out of this extension's base form.

## Why extension, not base

- Base demand side is subscriptions over listed traces; bounties add private-trace scanning, a second notification audience, and a new consent surface — real scope and real privacy review.
- Its value depends on the derived-field vocabulary being expressive, so the judge must ship and prove its fields first.
- Pricing/premium mechanics are future-work narrative; the base form is a standing want-ad, no money involved.

## Open questions (settled if/when picked up)

- Is fulfillment plain listing, or listing + an explicit "submit to bounty" attach step (cleaner provenance of intent, one more click)?
- Bounty lifecycle: target count, expiry, close-out, and whether matches after close still notify owners.
- Nudge flood control: per-bounty digest, or fold into the existing per-upload digest mechanics.
- Whether the bounty brief is visible to nudged owners pre-listing (it must be — informed consent — but how much of the consumer's identity rides along).
