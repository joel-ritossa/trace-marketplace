# Explainers

Short canonical write-ups of system behaviors that come up in discussion
repeatedly — delivery guarantees, consistency rules, security boundaries.
Each answers one question well so it doesn't get re-derived from code every
time.

These are descriptive, not normative: `docs/spec/` defines what the system should
do; an explainer documents how the implemented system actually behaves and
why, with pointers into code. If they disagree, fix the code or the spec —
then the explainer.

## When to add or update

- **Add** one when a "how does X behave?" question recurs, or a design
  discussion produces an answer worth keeping. One topic per file,
  slug-named.
- **Update** in the same pass as any change that alters a documented
  behavior. A stale explainer is worse than none.
- Keep them scannable: lead with the one-line answer, then the mechanism,
  then honest caveats.

## Index

| Topic | Question it answers |
|---|---|
| [trace-upload-delivery-guarantee.md](trace-upload-delivery-guarantee.md) | Can an accepted upload be lost? What guarantees ingestion happens? |
