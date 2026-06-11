"""Family 3 bucket-1 prompts: the owned critics (1_analysis.md). Sourced
per spec, no evaluator-framework dependency: helpfulness / harmfulness /
coherence adapted from LangChain's criteria-eval descriptions, hallucination
from openevals + RAGAS faithfulness framing, relevancy from RAGAS response
relevancy. Flag polarity is per-critic and stated in each prompt: true
flags the criterion's presence (helpful, coherent, relevant) or the defect's
presence (hallucination, harmfulness)."""
