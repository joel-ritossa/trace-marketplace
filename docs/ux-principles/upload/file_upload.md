# File Upload

Applies to: `/upload` (web), and conceptually mirrored by the stage-2 sync CLI.

```yaml
principle:
  name: Fail Before the Network
  rule: >
    Validate everything that can be validated client-side before POST:
    file selected, single file, .json extension, size under the limit.
    Violations render inline at the drop zone with the actual limit stated
    ("Max 10 MB; this file is 38 MB"), and the submit stays disabled until
    fixable problems are fixed.
  rationale: >
    Error prevention (Nielsen #5) beats good error messages. The upload
    rate bucket is deliberately tight; burning a rate-limited request on a
    file that was always going to fail is a double penalty.
  examples:
    positive:
      - "Oversize file rejected at drop with size shown vs limit"
    negative:
      - "Submit always enabled; size error arrives as a 413 after upload"
  validation:
    - client_side_size_and_type_checks_before_post
    - limit_violations_state_actual_limit_and_actual_value
  sources:
    - "Nielsen heuristic #5: Error prevention"
    - "Material Design: file upload validation timing"
```

```yaml
principle:
  name: Drop Zone Plus Picker, States Visible
  rule: >
    The upload affordance is a large drop zone that is also a click-to-browse
    target, stating accepted format ("one OTLP JSON file") and size limit in
    its idle copy. Drag-over, file-selected (name + size, removable), and
    uploading states are visually distinct.
  rationale: >
    Drag-and-drop alone is undiscoverable and inaccessible; a picker alone
    wastes the natural gesture for files developers already have in a
    folder. Constraints in idle copy prevent the most common failures
    before they happen.
  examples:
    positive:
      - "'Drop your trace file here or browse — one .json file, up to N MB'"
    negative:
      - "Bare 'Choose file' button with constraints only in error messages"
  validation:
    - drop_zone_doubles_as_keyboard_accessible_picker
    - accepted_format_and_limit_in_idle_copy
  sources:
    - "NN/g: drag-and-drop needs a visible alternative"
    - "IBM Carbon: file uploader pattern"
```

```yaml
principle:
  name: Duplicate Is Information, Not Failure
  rule: >
    A duplicate upload (sha-256 match) renders as a distinct neutral state:
    "already uploaded" with a link to the existing upload and its traces —
    not styled as an error, not silently treated as success.
  rationale: >
    Dedupe is a feature (it makes CLI re-syncs idempotent). Users re-upload
    to check whether something is in the system; the answer is "yes, here"
    — punishing red styling teaches users dedupe is a malfunction.
  examples:
    positive:
      - "Neutral banner: 'This file was already uploaded on May 4' linking to the existing upload"
    negative:
      - "Red 'Upload failed: duplicate_upload' with no link"
  validation:
    - duplicate_state_visually_distinct_from_failure
    - duplicate_state_links_to_existing_upload
  sources:
    - "Shopify Polaris: informational vs critical banner semantics"
    - "docs/spec/stage-1/4_pages.md: duplicate state with link"
```
