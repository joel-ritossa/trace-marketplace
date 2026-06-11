# Agent Rules — How to Use This Repository

You are a coding agent about to plan, implement, or review frontend work in
Trace Marketplace. This repository is the UX constitution for that work.
**Never jump from requirements to implementation. Layout planning comes first.**

## Authority order

1. `docs/spec/stage-1/` (normative spec) — wins over everything, including this repo.
2. `DESIGN.md` — owns visual styling (tokens, type, color). This repo owns layout,
   hierarchy, navigation, interaction, and workflows. They don't overlap; if they
   seem to, DESIGN.md decides how things look, this repo decides how things work.
3. This repo — checks marked `severity: spec` restate normative spec rules; treat
   violations as blocking. Other checks are binding unless the user explicitly waives them.

## The procedure

Before implementing any UI:

1. **Determine screen type.** Match the work against `product-map.yaml`
   (screens, workflows, shared patterns). New screens get classified by intent
   and interaction pattern, not by which API they call.
2. **Load the archetype.** Read `archetypes/<type>.yaml`. It defines the
   canonical layout skeleton, state machine, and action matrix.
3. **Load the principles.** Read everything in the archetype's `must_load.principles`
   list, plus `global/*` (always applies).
4. **Load the anti-patterns.** Read `anti-patterns/global.md` and
   `anti-patterns/product_specific.md`; the archetype's `must_load.anti_patterns`
   names the highest-risk ones for this screen type.
5. **Load the validation checks.** Find your screen type in
   `validation/checks_by_screen.yaml` (universal block + your screen block).
6. **Produce a layout plan.** Before writing code, write down: the screen's full
   state set; the layout regions and what lives in each; the single primary action
   per state; the navigation in/out; which shared components are reused
   (filter component, badges, trace list, span tree — never re-implemented).
7. **Review the plan against the checks.** Walk every applicable check and
   anti-pattern against the plan. Fix the plan, not the code, when something fails.
8. **Generate code.** Implement the reviewed plan with shadcn/ui components and
   DESIGN.md tokens. Shared patterns come from the shared components directory.

When reviewing existing or generated UI, run steps 1, 4, 5, then verify each
check against the implementation. Report failures with the check id and the
principle file that defines it.

## Standing rules (apply even without loading anything)

- Exactly one primary action per screen state.
- Every trace rendering carries its `private`/`listed` badge.
- API error detail renders verbatim; no generic error copy when a reason exists.
- Action availability is a pure function of API entitlement flags
  (`is_owner` / `acquired` / `can_download`); the UI never invents access rules.
- Every data view implements loading, empty, results, and error states;
  searchable views add no-results-for-query showing the active filters.
- Disabled controls carry an inline reason.
- Confirmation dialogs only for destructive, hard-to-reverse actions —
  with named objects, real consequences, and verb buttons.
- Listing consent (private -> listed) is never weakened, bundled, or pre-checked.
- No state encoded by color alone; everything keyboard-operable.
- One filter component, one filter vocabulary, everywhere.

## When the repo doesn't answer

This repo has two layers: `CORE_PRINCIPLES.md` holds the product-agnostic
laws; the category folders hold those laws already adjudicated for specific
surfaces. Archetyped screens follow the applied rules directly.

If a screen fits no archetype, or two applied rules genuinely conflict for
your case: reason from `CORE_PRINCIPLES.md` first, draft the layout plan from
those laws, then resolve with the user (per `AGENTS.md`) and record the
outcome — a new applied-rule file or archetype, traceable to the core
principle it derives from. Never improvise in code, and never encode a rule
that traces back to neither a core principle nor normative spec.
