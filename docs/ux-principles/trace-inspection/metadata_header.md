# Trace Metadata Header

Applies to: `/traces/[traceId]` section 1 — header and metadata band.

```yaml
principle:
  name: Identity, State, Actions — One Band
  rule: >
    The header concentrates: trace name; status; visibility badge; the
    count trio (duration, spans, errors); and the action set for the
    caller's entitlement. Below it, a metadata block: provider, model,
    service, tools, tags, description, and provenance (source format,
    importer version, link to the originating upload). Stage 2 appends the
    label block (outcome, failure_mode, task_category with provenance +
    confidence). Body content (span tree) starts below this band.
  rationale: >
    Every visitor — owner, browser, acquirer — triages here: what is this,
    what state is it in, what can I do. Scattering identity or actions into
    the body forces scrolling before triage; provenance up front is what
    makes marketplace data trustworthy.
  examples:
    positive:
      - "GitHub PR header: title, state badge, meta, actions — then the diff"
    negative:
      - "Download buried at the page bottom; provenance only in a tooltip"
  validation:
    - name_status_visibility_counts_actions_above_fold
    - provenance_block_present_with_upload_link
  sources:
    - "IBM Carbon: page header pattern"
    - "docs/spec/stage-1/4_pages.md: header/metadata contents"
```

```yaml
principle:
  name: Counts Are Doors, Not Plaques
  rule: >
    Header counts that have a destination act like it: the error count
    links/scrolls to the first error span (or filters the tree to errors);
    the upload link opens the upload; tags act as marketplace filter links.
    Static numbers with obvious next questions are dead ends.
  rationale: >
    A header that says "12 errors" has already promised the user a path to
    them. Making counts navigable collapses the most common inspection
    loop (see error count -> find error spans) to one click.
  examples:
    positive:
      - "'12 errors' -> tree filtered/jumped to error spans"
    negative:
      - "Error count requiring manual scroll-and-hunt through 500 spans"
  validation:
    - error_count_navigates_to_error_spans
    - provenance_and_tags_are_links
  sources:
    - "NN/g: information scent — numbers imply drill-down"
    - "trace-inspection/span_tree.md: errors visible from orbit"
```

```yaml
principle:
  name: Editable Metadata Edits In Place
  rule: >
    Owner-editable fields (tags, description) edit inline in the header
    block — edit affordance visible on the field, save/cancel adjacent,
    optimistic update with error rollback. No separate "edit trace"
    page or modal for two fields.
  rationale: >
    Inline editing keeps the read view as the single layout (no duplicate
    edit-page rendering of the same data) and matches the scale of the
    change: editing a tag is a two-second act, not a form session.
  examples:
    positive:
      - "Click tag area -> chip input appears -> Enter saves, Esc cancels"
    negative:
      - "Edit button navigating to /traces/[id]/edit with a full form"
  validation:
    - tags_description_editable_inline_for_owner
    - edit_controls_invisible_to_non_owners
  sources:
    - "Atlassian Design System: inline edit pattern"
    - "Apple HIG: edit in place where the data lives"
```
