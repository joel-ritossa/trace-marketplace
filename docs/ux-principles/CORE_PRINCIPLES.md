# Core Principles

The product-agnostic laws this repository is derived from. Everything in the
category folders is one of these principles, adjudicated for a specific
surface. Use this file directly when a screen fits no archetype: reason from
here first, then propose new applied rules for the taxonomy.

Format per principle: the law, why it's true, where it came from, and where
this repo applies it.

---

## 1. System status is always visible

The interface never leaves the user guessing what state the system is in —
jobs show their real lifecycle, objects show their real state, filters show
their real scope. People form their model of a system from what it shows
them; invisible state produces wrong models, and wrong models produce errors
the user can't even perceive making.
— Nielsen heuristic #1.
Applied in: `global/feedback.md`, `upload/async_status.md`, `search/filtering.md` (active chips), `tables/trace_lists.md` (badges).

## 2. Never render a state the system isn't in

The stronger sibling of #1: no fabricated progress bars, no optimistic
"complete" before confirmation, no "pending" for things that will never
arrive, no enabled buttons that will 403. Trust is the accumulated history
of the UI telling the truth; one caught lie costs more than a hundred
honest "processing" states.
— Derived from Nielsen #1; reliability culture ("never lie to the operator").
Applied in: `upload/async_status.md`, `global/hierarchy.md` (entitlement flags), `anti-patterns/global.md` (fabricated_progress), ui-deltas §7 (pending vs skipped).

## 3. One primary action per state

Every screen state answers "what does this screen most want me to do" with
exactly one visually dominant action. Decision time grows with the number
of equally-weighted options (Hick's law), and a screen that won't choose
forces the user to choose for it — usually wrongly.
— Hick's law; Polaris button hierarchy.
Applied in: `global/hierarchy.md`, every archetype's `cta`/`action_matrix`.

## 4. Recognition over recall

Let users recognize things rather than remember them: build queries by
seeing results, not by authoring rules in the abstract; show the machine's
verdict rather than asking humans to judge blind; keep acquired-state
visible in lists so nobody re-checks. Working memory is the scarcest
resource in any interface.
— Nielsen heuristic #6.
Applied in: `search/saved_queries.md` (save the search you can see), `review-queue/labeling.md`, `marketplace/discovery.md`.

## 5. Error prevention beats error messages

Catch problems before they become errors: validate before the network,
disable-with-reason before 403, constrain inputs to valid values, separate
destructive actions spatially. A prevented error costs nothing; a
well-messaged error still costs the round trip.
— Nielsen heuristic #5.
Applied in: `upload/file_upload.md`, `forms/data_entry.md`, `forms/destructive_actions.md`.

## 6. When errors happen, they explain themselves

Specific, verbatim, at the point of failure, with the path to recovery.
The error message is the interface's half of a debugging conversation;
generic copy ends the conversation.
— Nielsen heuristic #9; NN/g error-message guidelines.
Applied in: `global/feedback.md` (verbatim errors — also normative spec here), `authentication/auth_flows.md` (with the enumeration-safety exception).

## 7. Friction is proportional to consequence, and asymmetric toward safety

Cheap, reversible acts are frictionless; consequential, irreversible acts
get deliberate friction; and between two directions of the same toggle, the
risk-increasing direction carries the weight. Friction is a budget — spend
it where consequence lives or it stops working everywhere.
— Apple HIG (proportional response); consent-UX practice.
Applied in: `forms/consent_confirmation.md` (list vs un-list), `forms/destructive_actions.md`, `marketplace/acquisition.md` (acquire is frictionless).

## 8. Confirmation is a scarce resource

Every unnecessary "are you sure?" trains users to dismiss dialogs on
autopilot, spending the attention needed when a dialog actually matters.
Confirm only destructive + hard-to-reverse; everything else gets easy
reversal instead. When you do confirm: name the object, state the real
consequence, use verb buttons.
— NN/g on confirmation dialogs and habituation.
Applied in: `forms/destructive_actions.md`, `anti-patterns/global.md` (excessive_confirmation).

## 9. Progressive disclosure: hide nothing, default-render little

Layer by depth — summary, structure, raw — each layer one interaction from
the last, every layer reachable. Collapsed never means buried: rolled-up
state (error counts) surfaces through the fold. This reconciles
completeness with scannability without paternalism.
— NN/g progressive disclosure; HIG inspectors.
Applied in: `global/progressive_disclosure.md`, `trace-inspection/span_tree.md` (error rollups), `trace-inspection/detail_panel.md`.

## 10. Feedback lives where the action happened

Success is shown by the acted-on object changing in place — badge flips,
button swaps, row updates. Detached feedback (toasts) may supplement but
never carries the only evidence, because state outlives transience and
users verify by looking at the thing, not at where a toast used to be.
— Nielsen #1 applied to actions; Material (snackbars are supplemental).
Applied in: `global/feedback.md`, `marketplace/acquisition.md` (acquire flips in place).

## 11. Empty states are onboarding

An empty collection is the product teaching itself: name what belongs here,
how it arrives, and link the one action that fills it. The first-run
experience of most products is a sequence of empty states; treat each as a
doorway, not a void. Corollary: no-results-while-filtered is a different
state — show the guilty query.
— Primer Blankslate; Polaris empty states.
Applied in: `global/state_handling.md`, every archetype's `empty_cta`.

## 12. One vocabulary, one pattern per problem

The same concept has the same name everywhere (UI copy = filter language =
spec nouns); the same problem gets the same interaction everywhere (one
filter component, one badge system, one resolve view). Every synonym and
every parallel pattern is a fact the user must learn twice and the codebase
must maintain twice.
— Nielsen heuristic #4; AGENTS.md "consistency beats local cleverness".
Applied in: `global/information_architecture.md` (vocabulary), `search/filtering.md` (one filter UI), `review-queue/labeling.md` (relabel reuses resolve).

## 13. Density is calibrated to task mode

Scanning/inspection surfaces are dense (compact rows, monospace, maximal
information per viewport); decision surfaces are sparse (few elements, one
question). One density everywhere fails both modes. Chrome never taxes the
dense surfaces — content gets the width.
— Apple HIG information density; Fluent density modes.
Applied in: `global/hierarchy.md`, `navigation/app_shell.md` (top bar, not sidebar), `review-queue/labeling.md` (evidence beside verdict).

## 14. Structure mirrors the user's model, not the system's

Organize by intent and possession (mine / everyone's / acquired), not by
role, table, or implementation. One object, one canonical page. Derived
data is labeled as derived — the user's model must include the system's
own uncertainty.
— NN/g information architecture; Rosenfeld & Morville.
Applied in: `global/information_architecture.md`, `navigation/routing.md` (URL carries view state), `product-map.yaml` (organized by intent).

---

These fourteen are the test for new applied rules: a candidate rule that
can't be traced back to one of them (or to normative spec) is probably
taste, not principle — challenge it before encoding it.
