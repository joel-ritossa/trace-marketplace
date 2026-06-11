# Anomaly Lab

Throwaway experiment behind the [behavioral-novelty extension](../../docs/extensions/behavioral-novelty.md): can embedding-based novelty detection surface *rare agent behavior* in a trace corpus, and can an LLM explain what it found? Results in [_FINDINGS.md](_FINDINGS.md); per-run artifacts in `results/<timestamp>/`.

## The approaches

Industry context (2026): there is no single standard for agent-trace anomaly detection. Three families exist —

1. **Statistical baselining over behavioral features** (agentomaly/AMDM-style): outlier stats over call counts, tokens, duration, tool sets. Cheap and deterministic, but measures magnitude, not behavior.
2. **Embedding + geometry** (Clio / Arize Phoenix-style): embed traces, find outliers by distance/density. Caveat from the Clio literature: *clustering* structurally misses rare patterns — use raw kNN distance for the tail, not cluster membership.
3. **Trained trajectory verifiers** (TrajAD-style): specialized process-supervision models. Research-grade; out of scope here.

This lab tests family 2 with family 1 as the baseline, plus a contrastive-LLM explanation layer:

- **Feature baseline** — robust z-scored numerics (llm calls, tool calls, errors, tokens, tool-name count), kNN novelty in feature space.
- **Full-rendering embedding** — the trace rendered as a chronological message transcript, embedded (`text-embedding-3-small`), novelty = mean cosine distance to k=8 nearest neighbors.
- **Behavior-skeleton embedding** — same pipeline over a content-stripped rendering: roles, tool names, argument keys, result sizes, error markers, finish reasons. No natural-language content, so geometry can only encode *conduct*.
- **Contrastive explanation** — for a flagged trace, prompt an LLM with the trace plus its 3 nearest neighbors: "what does this one do behaviorally that the comparables don't?" — with an explicit out to say "nothing".

Headline result: full-rendering novelty ≈ topic rarity (benchmark purity 0.98); skeleton novelty is orthogonal to it (Spearman 0.02) and surfaces genuine behavioral anomalies; the contrastive layer produces grounded explanations and honestly rejects false positives. **What you embed determines what "anomalous" means.**

## Pipeline

| Step | Script | Output (`data/`, git-ignored) |
|---|---|---|
| 1. Fetch | `fetch_compact.py` | `traces.jsonl` — 300 sessions stratified from [Exgentic/agent-llm-traces](https://huggingface.co/datasets/Exgentic/agent-llm-traces) (5 harnesses × 6 benchmarks × 7 models), text bodies truncated |
| 2. Render | `render.py` | `renderings.jsonl` — transcript rendering + feature vector per session |
| 3. Embed | `embed.py` | `embeddings.npy`, `ids.json` |
| 4. Skeletonize | `skeleton.py` | `skeletons.jsonl`, `skeleton_embeddings.npy` |
| 5. Analyze | `analyze.py` | `novelty.json` — kNN novelty, neighbor purity, feature-baseline comparison, within-benchmark view |
| 6. Compare | `compare.py` | `skeleton_novelty.json` — full vs skeleton novelty head-to-head |
| 7. Explain | `explain.py` | `explanations.json` — contrastive explanations for hand-picked outliers |
| 8. Compare all methods | `methods.py` + `report.py` | `results/<UTC timestamp>/` (tracked) — adds k-means, HDBSCAN cluster-rarity, and the combined score; blind LLM eval panel → behavioral precision@10 per method; rare-but-clustered case study; cost/latency ledger |

`llm.py` wraps all chat calls via **litellm**, recording per-call latency, tokens, and cost into the run's `meta.json`.

## Results convention

Each `report.py` run writes `results/<UTC timestamp>/`:

- `meta.json` — git sha, dataset sampling, all params (k, cluster sizes, caps, models), eval design, LLM cost/latency ledger, wall time
- `scores.json` — every method's full score vector + top-10 sessions
- `eval.json` — blind judge verdicts, per-method precision, rare-but-clustered case study
- `explanations.json` — contrastive explanations for the winning method's top picks
- `summary.md` — human-readable rollup

Runs are tracked in git (aggregate metrics + session ids, no trace payloads), so approach iterations stay comparable across commits.

## Running

Steps 1–2 are stdlib-only (`python3 fetch_compact.py`, `python3 render.py`). The rest need numpy and an `OPENAI_API_KEY` (read from env or the repo's `.env.local`):

```bash
uv run --with numpy --python 3.12 embed.py
uv run --with numpy --python 3.12 skeleton.py
uv run --with numpy --python 3.12 analyze.py
uv run --with numpy --python 3.12 compare.py
uv run --with numpy --python 3.12 explain.py
uv run --with numpy,scikit-learn,litellm --python 3.12 report.py
```

API cost is trivial: ~600 embeddings + 4 `gpt-5-mini` calls (cents). Real benchmark data stays in `data/` (git-ignored per repo data-handling rules); only scripts and findings are tracked.
