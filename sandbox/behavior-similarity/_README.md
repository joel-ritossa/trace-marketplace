# Behavior Similarity Lab

Throwaway experiment, sibling of [anomaly-lab](../anomaly-lab/_README.md): given a trace, can we retrieve other traces that *behave* the same way — and can we discover recurring behavioral patterns across a corpus? Results in [_FINDINGS.md](_FINDINGS.md).

Anomaly-lab answered "is this trace far from everything?" (novelty). This lab answers the inverse, which is what a marketplace consumer actually asks: *"this trace shows a degenerate retry loop / a clean recovery / brute-force enumeration — find me more like it."* Novelty needs only a good outlier score; similarity needs the **neighborhood structure itself** to align with conduct, which is a strictly harder requirement.

## Research questions

1. **RQ1 — Representation:** which trace representation + similarity metric makes nearest neighbors share *behavior* rather than *topic*? (Anomaly-lab showed transcript embeddings are 98% benchmark-pure — a topic detector. Does that carry over to retrieval, and what beats it?)
2. **RQ2 — Locality:** behavior is often local (a retry loop in spans 40–60 of a 200-span trace). Do whole-trace representations dilute it, and does window-level matching recover it?
3. **RQ3 — Discovery:** can we go beyond query-by-example and enumerate the recurring behavioral motifs in a corpus, unsupervised?

## Data

Reuses anomaly-lab's corpus directly (`../anomaly-lab/data/`): 300 sessions stratified from [Exgentic/agent-llm-traces](https://huggingface.co/datasets/Exgentic/agent-llm-traces) (5 harnesses × 6 benchmarks × 7 models), with its transcript renderings, behavior skeletons, and both whole-trace embedding sets already computed.

## Ground truth: two-stage behavioral coding

No public dataset labels "behavior", so we construct a reference standard the way qualitative researchers do:

1. **Open coding** (`tag.py open`) — an LLM free-describes the conduct of a stratified sample of traces (no taxonomy imposed).
2. **Taxonomy** — the open codes are consolidated by hand into a small multi-label tag set (documented in `tag.py`, with the consolidation rationale).
3. **Closed coding** (`tag.py closed`) — the LLM applies the fixed taxonomy to all 300 traces.

Crucially, **no retrieval method sees the tags or any LLM output** — methods are purely geometric/statistical, so the tags are an independent reference, not a circular one. Residual risk: tagger errors are correlated with what's visible in a rendering; the blind pairwise eval (below) hedges this.

## Methods compared

All produce a 300×300 similarity matrix (`methods.py`):

| Method | Representation | Similarity |
|---|---|---|
| `feat_cos` | 5 robust-z numeric features (calls, tools, errors, tokens) | −euclidean |
| `full_emb` | whole-transcript embedding | cosine — *the topic baseline* |
| `skel_emb` | whole-skeleton embedding | cosine |
| `ngram_tfidf` | action-token n-grams (1–3), TF-IDF | cosine — order-aware-ish, no API |
| `seq_align` | action-token sequence (capped 600) | normalized indel similarity (rapidfuzz) — fully order-aware |
| `win_chamfer` | sliding-window skeleton embeddings | symmetric chamfer (mean of best-window matches) — locality-aware |

plus a hybrid grid: rank-average of every method pair, to test whether complementary signals compose (they did for novelty).

Action tokens (`common.py`) are the skeleton reduced further to a discrete alphabet: `A:TXT`, `CALL:<tool>`, `RES`/`RES_ERR` with size buckets, `FINISH_LEN`, `SPAN_ERR`. No natural language at all.

## Evaluation

- **Tag-based retrieval** (`evaluate.py`): for each query trace, do its top-k neighbors share behavior tags? Metrics: P@5 (any shared tag), macro mAP over informative tags, and rare-tag mAP (prevalence ≤ 10%) — rare tags are the marketplace's actual value case. Diagnostic: same-benchmark@5 (topic leak) and same-harness@5.
- **Blind pairwise verification** (`pair_eval.py`): each method's top retrieved pairs + random control pairs, judged blind by an LLM — "do these two traces share a distinctive behavioral pattern (conduct, not topic)?" Pairwise precision per method. This checks the methods against something other than our own tags.
- **Motif discovery** (`motifs.py`): HDBSCAN over window embeddings; clusters spanning many traces/benchmarks = candidate motifs, LLM-named from medoid windows. Evaluated qualitatively: are the motifs real, cross-topic, and would a consumer care?

## Pipeline

| Step | Script | Output (`data/`, git-ignored) |
|---|---|---|
| 1. Tokenize | `common.py` (library) | — |
| 2. Open-code | `tag.py open` | `open_codes.json` (60-trace stratified sample) |
| 3. Closed-code | `tag.py closed` | `tags.json` (300 traces × multi-label) |
| 4. Windows | `windows.py` | `windows.jsonl`, `window_embeddings.npy` |
| 5. Similarities | `methods.py` | `sims.npz` (six 300×300 matrices) |
| 6. Evaluate | `evaluate.py` | `eval.json` |
| 7. Pair-verify | `pair_eval.py` | `pair_eval.json` |
| 8. Motifs | `motifs.py` | `motifs.json` |
| 9. Report | `report.py` | `results/<UTC timestamp>/` (tracked: meta.json + summary.md) |

## Running

Needs `OPENAI_API_KEY` (env, `.env.local`, or `.env`):

```bash
uv run --with litellm --python 3.12 tag.py open
uv run --with litellm --python 3.12 tag.py closed
uv run --with numpy --python 3.12 windows.py
uv run --with numpy,scikit-learn,rapidfuzz --python 3.12 methods.py
uv run --with numpy --python 3.12 evaluate.py
uv run --with numpy,litellm --python 3.12 pair_eval.py
uv run --with numpy,scikit-learn,litellm --python 3.12 motifs.py
uv run --with numpy --python 3.12 report.py
```

Estimated API spend per full run: ~$1 (300 tag calls + ~140 pair judgments + ~15 motif namings + ~3k window embeddings, all gpt-5-mini / text-embedding-3-small).
