# Notifications (Stage 2)

Applies to: bell + notifications list; types: `review_request`, `subscription_match` (later `bounty_match`).

```yaml
principle:
  name: Every Notification Is a Door to Its Object
  rule: >
    A notification names its type, its object, and the time, and clicking
    it lands on the object: review_request -> the review item (or queue
    group), subscription_match -> the trace (single) or the subscription
    feed (digest). No notification dead-ends in the list or opens a page
    where the user must re-find the subject.
  rationale: >
    Notifications are pure navigation: their entire value is collapsing
    "something happened" -> "I'm looking at it" to one click. A
    notification that doesn't link is just an anxiety generator.
  examples:
    positive:
      - "'12 traces need review from upload X' -> queue filtered to that upload"
      - "'New match for checkout failures' -> subscription feed with new-marker"
    negative:
      - "'You have new matches' landing on the generic subscriptions list"
  validation:
    - every_notification_links_to_its_object
    - notification_copy_names_object_and_type
  sources:
    - "Material Design: notification content and tap behavior"
    - ".archive/stage-2-planning/spec-shaping/infra.md §3"
```

```yaml
principle:
  name: Read State Is Calm and Cheap
  rule: >
    Unread count on the bell; unread items visually distinct (weight/dot,
    not screaming color); opening an item marks it read; mark-all-read is
    one action; read items remain listed (history, not inbox-zero). No
    sounds, no auto-opening panels, no browser-notification permission
    prompts in base.
  rationale: >
    The notification system serves two calm jobs (review nudges,
    subscription matches), both advisory. Aggressive unread mechanics turn
    a utility into a nag and train users to ignore the bell — killing the
    HIL loop the product depends on.
  examples:
    positive:
      - "GitHub notifications: quiet dot, persistent history, bulk mark-read"
    negative:
      - "Modal takeover: 'You have 3 new notifications!'"
  validation:
    - unread_count_on_bell
    - mark_all_read_available
    - read_items_remain_accessible
  sources:
    - "NN/g: notification fatigue and habituation"
    - "review-queue/queue.md: advisory, not blocking"
```

```yaml
principle:
  name: Digest by Source, Don't Firehose
  rule: >
    Burst events collapse at the source where designed (review_requests
    digest per upload, per spec) and the list groups same-type same-object
    runs visually. Per-match subscription notifications render grouped by
    subscription on the page even when stored individually.
  rationale: >
    The first CLI sync is the stress test: hundreds of traces -> analysis
    -> potentially hundreds of events in minutes. The user's first
    experience of notifications must not be a wall of 200 identical rows.
  examples:
    positive:
      - "'47 new matches · checkout failures' as one expandable group"
    negative:
      - "200 individual 'trace needs review' rows from one sync"
  validation:
    - review_requests_digested_per_upload
    - list_groups_by_subscription_and_type
  sources:
    - ".archive/stage-2-planning/spec-shaping/judging/README.md: flood control"
    - "Material Design: notification grouping"
```
