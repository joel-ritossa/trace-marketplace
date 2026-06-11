# Stage 2 Planning

Working area for figuring out stage 2 before it becomes a normative `spec/stage-2/`. Non-normative — like the rest of `.archive/`, nothing here is spec.

## Layout

| Path | What it is |
|---|---|
| [ideation/](ideation/README.md) | Raw ideation sessions 1–5, in order. Historical: how the direction evolved from "more marketplace features" to the data-engine + edge-sync shape. Superseded where it conflicts with `spec-shaping/`. |
| [spec-shaping/](spec-shaping/README.md) | Converging on the actual stage-2 requirements: what is concretely required vs. what still needs figuring out. Drill-deeper docs per topic land here. |
| [candidate-datasets.md](candidate-datasets.md) | Public dataset research for powering the stage-2 demo (clustering/labeling/judge validation corpora). Reference material. |

## Current status

Direction is finalized at the requirements level (see [spec-shaping/requirements.md](spec-shaping/requirements.md)): base = sync CLI → analysis with web human-in-the-loop → subscriptions + bulk acquire; extensions = task bounties, desktop notifications, derived-field similarity. Infra is being ironed out first; everything that *analyzes* traces (judging/labeling/evals) is an explicit placeholder pending its own discussion.
