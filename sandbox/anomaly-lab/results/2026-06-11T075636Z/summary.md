# Run 2026-06-11T075636Z

| Method | behavioral P@10 | topical rate@10 |
|---|---|---|
| feat_z | 0.0 | 0.0 |
| feat_knn | 0.1 | 0.0 |
| full_knn | 0.1 | 0.0 |
| full_kmeans | 0.2 | 0.0 |
| skel_knn | 0.2 | 0.0 |
| skel_kmeans | 0.1 | 0.0 |
| skel_cluster_rarity | 0.2 | 0.0 |
| skel_combined | 0.5 | 0.0 |
| random_controls | 0.1 | 0.0 |

## Rare-but-clustered (human-transfer traces)

- `066de3655406_9950c2db` cluster_size=101 ranks: feat_z=112, feat_knn=134, full_knn=127, full_kmeans=150, skel_knn=158, skel_kmeans=98, skel_cluster_rarity=223, skel_combined=175
  - judge: This trace follows the common customer-simulation pattern seen in the comparables—simple account lookup info provided and then a transfer—so neither conduct nor topic is unusual.
- `18efd0e196b7_947c3c53` cluster_size=101 ranks: feat_z=113, feat_knn=132, full_knn=158, full_kmeans=117, skel_knn=173, skel_kmeans=133, skel_cluster_rarity=222, skel_combined=180
  - judge: (not in panel)

## Cost / latency

```json
{
 "eval": {
  "calls": 51,
  "cost_usd": 0.1444,
  "prompt_tokens": 362411,
  "completion_tokens": 26913,
  "latency_p50_s": 8.889,
  "latency_max_s": 22.967
 },
 "explain": {
  "calls": 3,
  "cost_usd": 0.0107,
  "prompt_tokens": 24557,
  "completion_tokens": 2291,
  "latency_p50_s": 12.75,
  "latency_max_s": 13.334
 }
}
```
