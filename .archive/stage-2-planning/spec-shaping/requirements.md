# Stage 2 Requirements — Working Snapshot

What is concretely required vs. what still needs figuring out. Non-normative until promoted to `spec/stage-2/`.

## Product shape

Traces flow in passively (local sync CLI) → analyzed server-side, with a human-in-the-loop resolving uncertain outcomes via the web app → consumers discover traces through rule-based search/filters, subscribe to saved queries, and bulk-acquire matches. Extensions add the demand side (task bounties), desktop notifications, and richer derived fields for similarity.

## Locked decisions

| Decision | Resolution |
|---|---|
| Capture | Separate system from the webapp: a terminal-based sync CLI; user inputs path(s) to traces. **Watch mode is required, not an extension.** |
| Task clustering | **Dropped.** No mined task clusters, no learned per-task verifiers (future-work narrative only). Judging operates as generic outcome evals; discovery and matching are filter-based. |
| HIL surface | Web: in-app notifications + review queue. Desktop notifications are an extension (tied to the listener/CLI extension). |
| Subscriptions | Saved queries that notify on new matches. **No auto-acquire** — consumer multi-selects and bulk-acquires. |
| Search & matching principle | **All search and matching is deterministic/rule-based.** Non-determinism is allowed only in *field derivation*: analysis may produce tags/classifications/cases (e.g. anomaly categories) non-deterministically, and rules then match on those fields like any other column. No semantic/embedding search as a user-facing matching mechanism. |
| Label model | **Placeholder.** Binary vs graded vs something else — settled in the judging discussion. |
| Exports (SFT/trajectory/pairs) | **Deferred** to the judging/analysis discussion. |
| Privacy | Unchanged from stage 1: CLI uploads are private by default; listing remains the explicit consent act in the web app. Subscriptions match only listed traces. Bounty matching may scan private traces but alerts only the owner. |

## Base requirements

1. **Sync CLI.** Terminal tool, separate from the webapp. Input: path(s) to trace files. One-shot sync plus a required watch mode that uploads new traces as they appear. Authenticates with an API key (minted/managed in the webapp). Uploads via the existing upload API; server-side sha256 dedupe makes re-syncs idempotent.
2. **Analysis pipeline plumbing** (analyzers themselves are placeholders). Post-ingestion worker job(s) that run analysis over a trace and write derived results, including an outcome assessment and an uncertainty signal. Pluggable: the infra (job, storage of derived fields, uncertainty routing) is fixed; what the analyzers compute is decided in the judging discussion.
3. **Human-in-the-loop via web.** Uncertain outcomes generate in-app notifications and populate a review queue; the contributor resolves them in the webapp. Human answers are stored with provenance (human vs machine vs human-confirmed).
4. **Discovery, subscriptions, bulk acquire.** Rule-based filtering/search over listed traces (stage-1 search extended with derived/label fields once defined). A subscription is a saved query: backfill shows historic matches; new matches notify. Consumers multi-select and bulk-acquire from results/feed.

## Extensions

- **Task bounties.** Consumer registers a bounty defined by rule-based criteria over trace fields — including derived fields (e.g. `tool_names` contains HubSpot tools + derived task-category tag). Matching runs over historic and incoming traces, including contributors' private ones; matching contributors are alerted (alert goes only to the owner; listing is the consent act). In-app alerts in base form of the extension.
- **Desktop notifications.** OS-level delivery for HIL prompts and bounty alerts; ties into the CLI as the local channel.
- **Similar-trace subscriptions.** "Find/subscribe to traces like this one" — implemented within the rule-based principle: similarity comes from matching on non-deterministically derived categorization fields, not from embedding search. Depends on the derived-field vocabulary from the judging discussion.
- **On-demand enrichment.** Consumers trigger the extended (non-default) metric catalog on traces they care about; results land in the same analysis storage and become filterable. See `judging/3_quality-metrics.md`.

## Judging / analysis — high-level requirements (NOT defined)

Everything that actually analyzes trace content is a placeholder. What we know conceptually we need:

- **Human trace scoring** — the HIL input; humans score/label outcomes (and possibly more).
- **Deterministic analyzers** — heuristics over trace structure (status codes, error patterns, token/latency signals, etc.).
- **Non-deterministic LLM-as-judge evals** — model-based assessment of outcomes/behavior.
- **Derived categorization fields** — tags / classifications / cases (e.g. anomalies, anomaly cases, behavioral aspects) produced by analysis and exposed as rule-matchable fields. This is what makes similarity subscriptions and rich bounties definable. *What is valuable to derive* (anomalies? failure modes? task categories?) is a core open question.
- **Uncertainty signal** — whatever the analyzers are, they must emit a confidence/uncertainty measure that routes traces to the HIL queue.
- **Label provenance** — machine / human-confirmed / human, surfaced as a consumer-facing quality dimension.
- Possibly more ("and maybe other stuff").

Open questions for the dedicated judging discussion: the label model (binary/graded/other); the derived-field vocabulary and what's valuable; how human labels feed back into the judge; exports; how industry currently approaches trace evals/tagging (research needed).

## Known vs. open

| Area | State |
|---|---|
| Sync CLI, API keys | Concrete; iron out details in infra discussion. |
| Notifications, review-queue plumbing | Concrete; content of review items depends on label model. |
| Subscriptions, bulk acquire, rule-based matching | Concrete; field vocabulary grows after judging discussion. |
| Analysis pipeline plumbing | Concrete (job + derived storage + uncertainty routing); analyzers placeholder. |
| Judging/labeling/evals (all analysis content) | Open — dedicated discussion required. |
| Bounties, desktop notifications, similarity | Extensions; design known at sketch level, depend partly on derived fields. |
