# Behavior-similarity run summary

## in_corpus

| method | P@5 inf | mAP inf | mAP rare | bench@5 | harness@5 |
|---|---|---|---|---|---|
| feat_cos | 0.4477 | 0.1646 | 0.1587 | 0.6553 | 0.71 |
| full_emb | 0.5989 | 0.2559 | 0.2578 | 0.9887 | 0.6867 |
| skel_emb | 0.583 | 0.2303 | 0.2432 | 0.8847 | 0.7313 |
| ngram_tfidf | 0.608 | 0.2061 | 0.2004 | 0.8787 | 0.762 |
| seq_align | 0.5875 | 0.2202 | 0.2185 | 0.8393 | 0.762 |
| win_chamfer | 0.6136 | 0.1878 | 0.1687 | 0.8813 | 0.742 |
| random | 0.2064 | 0.0926 | 0.0689 | 0.2015 | 0.3344 |

## cross_benchmark

| method | P@5 inf | mAP inf | mAP rare | bench@5 | harness@5 |
|---|---|---|---|---|---|
| feat_cos | 0.2841 | 0.116 | 0.0955 | 0.0 | 0.5487 |
| full_emb | 0.5477 | 0.1951 | 0.1803 | 0.0 | 0.5707 |
| skel_emb | 0.3648 | 0.1431 | 0.1294 | 0.0 | 0.62 |
| ngram_tfidf | 0.375 | 0.1497 | 0.1125 | 0.0 | 0.6647 |
| seq_align | 0.3432 | 0.13 | 0.1057 | 0.0 | 0.626 |
| win_chamfer | 0.3636 | 0.1274 | 0.0814 | 0.0 | 0.662 |
| random | 0.158 | 0.0734 | 0.0526 | 0.0 | 0.3205 |

## Blind pairwise precision

| selection | precision | n |
|---|---|---|
| feat_cos/all | 0.8 | 10 |
| feat_cos/cross | 0.3 | 10 |
| full_emb/all | 1.0 | 10 |
| full_emb/cross | 0.6 | 10 |
| skel_emb/all | 0.9 | 10 |
| skel_emb/cross | 0.2 | 10 |
| ngram_tfidf/all | 0.8 | 10 |
| ngram_tfidf/cross | 0.4 | 10 |
| seq_align/all | 0.9 | 10 |
| seq_align/cross | 0.3 | 10 |
| win_chamfer/all | 0.7 | 10 |
| win_chamfer/cross | 0.1 | 10 |
| random/control | 0.133 | 15 |
