"""Validation: analyzer-vs-human agreement over converted benchmark slices
(1_analysis.md Validation).

Two folds, both pure (no I/O, no LLM), each with its own labels sidecar
shape written by the benchmark converters in tools/:

- `agreement_report` (B4): outcome judge vs expert outcome labels
  (AgentRewardBench / AgentRx), parsed by `load_labels`.
- `metric_agreement_report`: family-3 metrics vs metric ground truth
  (HaluBench hallucination labels), parsed by `load_metric_labels`. Boolean
  critics fold to a confusion matrix; score metrics fold to per-class
  distributions plus a threshold-free AUC.

The `agreement` / `metrics-agreement` runner subcommands
(app/cli/analyze.py) join traces to labels and emit the reports — each
slice's "one command".
"""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from app.analysis.models import FAILURE_MODES, JudgeVerdict, MetricResult, SignalsResult
from app.analysis.routing import RoutingReason

HUMAN_OUTCOMES = ("success", "failure")
JUDGE_OUTCOMES = ("success", "failure", "indeterminate")


class TraceLabel(BaseModel):
    """Ground truth for one converted trace, keyed by source trace id.
    Human benchmark labels are binary — unjudgeable rows are excluded at
    conversion, so `indeterminate` never appears here."""

    dataset: str
    outcome: Literal["success", "failure"]
    looping: bool | None = None
    side_effect: bool | None = None
    failure_categories: list[str] = []
    root_cause_category: str | None = None
    benchmark: str | None = None
    task_id: str | None = None
    agent: str | None = None


def load_labels(path: Path) -> dict[str, TraceLabel]:
    raw = json.loads(path.read_text())
    labels = {trace_id: TraceLabel.model_validate(entry) for trace_id, entry in raw.items()}
    for trace_id, label in labels.items():
        for category in [*label.failure_categories, label.root_cause_category]:
            if category is not None and category not in FAILURE_MODES:
                raise ValueError(f"unknown failure category {category!r} on {trace_id}")
    return labels


class AgreementEntry(BaseModel):
    label: TraceLabel
    signals: SignalsResult
    verdict: JudgeVerdict
    routing_reasons: list[RoutingReason]


class OutcomeAgreement(BaseModel):
    """Confusion is human outcome → judge outcome → count; judge nulls
    (judge never produced a label) count under "indeterminate"."""

    confusion: dict[str, dict[str, int]]
    decided: int
    decided_matches: int
    decided_agreement: float | None
    abstentions: int
    abstention_rate: float
    strict_agreement: float


class FailureModeAgreement(BaseModel):
    """Over traces whose ground truth is failure *and* carries categories
    (AgentRx). Match rates are over traces the judge both called failure
    and gave a failure_mode."""

    true_failures: int
    judge_called_failure: int
    classified: int
    root_cause_matches: int
    root_cause_match_rate: float | None
    any_category_matches: int
    any_category_match_rate: float | None


class RoutingStats(BaseModel):
    """The headline's second half: judge-wrong traces should carry routing
    reasons. Wrong = judge decided an outcome and it differs from human."""

    wrong: int
    wrong_routed: int
    wrong_routed_rate: float | None
    routed: int
    routed_rate: float


class LoopingCheck(BaseModel):
    """ARB's human looping annotation vs the deterministic has_retry_loop
    signal — the slice's signals sanity check. Null signals are excluded."""

    compared: int
    matches: int
    agreement: float | None
    human_yes_signal_no: int
    human_no_signal_yes: int


class CostStats(BaseModel):
    llm_calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float


class AgreementReport(BaseModel):
    traces: int
    datasets: list[str]
    # What produced the verdicts — prompt-rev comparisons key on these.
    judge_version: str | None = None
    judge_model: str | None = None
    outcome: OutcomeAgreement
    failure_mode: FailureModeAgreement | None
    routing: RoutingStats
    looping: LoopingCheck | None
    cost: CostStats

    def render_text(self) -> str:
        judge = f" — judge v{self.judge_version} ({self.judge_model})" if self.judge_version else ""
        lines = [
            f"Agreement report — {self.traces} traces ({', '.join(self.datasets)}){judge}",
            "",
            "Outcome (human × judge):",
        ]
        width = max(len(o) for o in JUDGE_OUTCOMES) + 2
        header = " " * 12 + "".join(o.rjust(width) for o in JUDGE_OUTCOMES)
        lines.append(header)
        for human in HUMAN_OUTCOMES:
            row = self.outcome.confusion.get(human, {})
            cells = "".join(str(row.get(judge, 0)).rjust(width) for judge in JUDGE_OUTCOMES)
            lines.append(f"  {human:<10}{cells}")
        lines.append(
            f"  decided agreement: {_pct(self.outcome.decided_agreement)}"
            f" ({self.outcome.decided_matches}/{self.outcome.decided})"
        )
        lines.append(
            f"  abstention rate:   {_pct(self.outcome.abstention_rate)}"
            f" ({self.outcome.abstentions}/{self.traces})"
        )
        lines.append(
            f"  strict agreement:  {_pct(self.outcome.strict_agreement)} (abstention = miss)"
        )
        if self.failure_mode is not None:
            fm = self.failure_mode
            lines += [
                "",
                "Failure mode (vs AgentRx annotations):",
                f"  judge called failure: {fm.judge_called_failure}/{fm.true_failures}"
                " true failures",
                f"  root-cause match:     {_pct(fm.root_cause_match_rate)}"
                f" ({fm.root_cause_matches}/{fm.classified})",
                f"  any-category match:   {_pct(fm.any_category_match_rate)}"
                f" ({fm.any_category_matches}/{fm.classified})",
            ]
        lines += [
            "",
            "Routing:",
            f"  judge-wrong traces routed to review: {_pct(self.routing.wrong_routed_rate)}"
            f" ({self.routing.wrong_routed}/{self.routing.wrong})",
            f"  overall routing rate: {_pct(self.routing.routed_rate)}"
            f" ({self.routing.routed}/{self.traces})",
        ]
        if self.looping is not None:
            lines += [
                "",
                "Looping signal vs human annotation:",
                f"  agreement: {_pct(self.looping.agreement)}"
                f" ({self.looping.matches}/{self.looping.compared})",
                f"  human-yes/signal-no: {self.looping.human_yes_signal_no},"
                f" human-no/signal-yes: {self.looping.human_no_signal_yes}",
            ]
        lines += [
            "",
            f"Cost: {self.cost.llm_calls} LLM calls,"
            f" {self.cost.input_tokens + self.cost.output_tokens} tokens,"
            f" ${self.cost.cost_usd:.2f}",
        ]
        return "\n".join(lines)


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def _fold_outcome(entries: list[AgreementEntry]) -> OutcomeAgreement:
    confusion: dict[str, dict[str, int]] = {
        h: dict.fromkeys(JUDGE_OUTCOMES, 0) for h in HUMAN_OUTCOMES
    }
    decided = matches = abstentions = 0
    for entry in entries:
        judged = entry.verdict.outcome or "indeterminate"
        confusion[entry.label.outcome][judged] += 1
        if judged == "indeterminate":
            abstentions += 1
        else:
            decided += 1
            matches += judged == entry.label.outcome
    total = len(entries)
    return OutcomeAgreement(
        confusion=confusion,
        decided=decided,
        decided_matches=matches,
        decided_agreement=_ratio(matches, decided),
        abstentions=abstentions,
        abstention_rate=abstentions / total,
        strict_agreement=matches / total,
    )


def _fold_failure_mode(entries: list[AgreementEntry]) -> FailureModeAgreement | None:
    annotated = [e for e in entries if e.label.outcome == "failure" and e.label.root_cause_category]
    if not annotated:
        return None
    called = [e for e in annotated if e.verdict.outcome == "failure"]
    classified = [e for e in called if e.verdict.failure_mode]
    root_matches = sum(e.verdict.failure_mode == e.label.root_cause_category for e in classified)
    any_matches = sum(
        e.verdict.failure_mode in e.label.failure_categories
        or e.verdict.failure_mode == e.label.root_cause_category
        for e in classified
    )
    return FailureModeAgreement(
        true_failures=len(annotated),
        judge_called_failure=len(called),
        classified=len(classified),
        root_cause_matches=root_matches,
        root_cause_match_rate=_ratio(root_matches, len(classified)),
        any_category_matches=any_matches,
        any_category_match_rate=_ratio(any_matches, len(classified)),
    )


def _fold_routing(entries: list[AgreementEntry]) -> RoutingStats:
    wrong = [
        e
        for e in entries
        if e.verdict.outcome in HUMAN_OUTCOMES and e.verdict.outcome != e.label.outcome
    ]
    wrong_routed = sum(bool(e.routing_reasons) for e in wrong)
    routed = sum(bool(e.routing_reasons) for e in entries)
    return RoutingStats(
        wrong=len(wrong),
        wrong_routed=wrong_routed,
        wrong_routed_rate=_ratio(wrong_routed, len(wrong)),
        routed=routed,
        routed_rate=routed / len(entries),
    )


def _fold_looping(entries: list[AgreementEntry]) -> LoopingCheck | None:
    compared = [
        e for e in entries if e.label.looping is not None and e.signals.has_retry_loop is not None
    ]
    if not compared:
        return None
    matches = sum(e.label.looping == e.signals.has_retry_loop for e in compared)
    return LoopingCheck(
        compared=len(compared),
        matches=matches,
        agreement=_ratio(matches, len(compared)),
        human_yes_signal_no=sum(e.label.looping and not e.signals.has_retry_loop for e in compared),
        human_no_signal_yes=sum(not e.label.looping and e.signals.has_retry_loop for e in compared),
    )


def _fold_cost(entries: list[AgreementEntry]) -> CostStats:
    votes = [vote for e in entries for vote in e.verdict.votes]
    return CostStats(
        llm_calls=len(votes),
        input_tokens=sum(v.input_tokens or 0 for v in votes),
        output_tokens=sum(v.output_tokens or 0 for v in votes),
        cost_usd=sum(v.cost_usd or 0.0 for v in votes),
    )


def agreement_report(
    entries: list[AgreementEntry],
    judge_version: str | None = None,
    judge_model: str | None = None,
) -> AgreementReport:
    if not entries:
        raise ValueError("no entries to fold")
    return AgreementReport(
        traces=len(entries),
        datasets=sorted({e.label.dataset for e in entries}),
        judge_version=judge_version,
        judge_model=judge_model,
        outcome=_fold_outcome(entries),
        failure_mode=_fold_failure_mode(entries),
        routing=_fold_routing(entries),
        looping=_fold_looping(entries),
        cost=_fold_cost(entries),
    )


# --- family-3 metric validation ---


class MetricTraceLabel(BaseModel):
    """Metric ground truth for one converted trace, keyed by source trace
    id. `hallucinated` grounds the hallucination critic directly and the
    faithfulness score inversely (faithful = not hallucinated)."""

    dataset: str
    hallucinated: bool
    source: str | None = None
    case_id: str | None = None


def load_metric_labels(path: Path) -> dict[str, MetricTraceLabel]:
    raw = json.loads(path.read_text())
    return {trace_id: MetricTraceLabel.model_validate(entry) for trace_id, entry in raw.items()}


class MetricEntry(BaseModel):
    """One trace's evaluated metrics: name → result, None where the metric
    abstained (inapplicable or failed open) — abstention is a tracked
    outcome, never silently dropped."""

    label: MetricTraceLabel
    results: dict[str, MetricResult | None]


class CriticAgreement(BaseModel):
    """Boolean critic vs human flag. Confusion is human → critic → count;
    critic abstentions (no result) count under "abstain". Precision/recall
    are on the positive (hallucinated) class; balanced accuracy averages
    the two class recalls — the honest headline on an imbalanced slice."""

    metric: str
    confusion: dict[str, dict[str, int]]
    decided: int
    decided_matches: int
    decided_agreement: float | None
    abstentions: int
    abstention_rate: float
    strict_agreement: float
    precision: float | None
    recall: float | None
    balanced_accuracy: float | None


class ScoreAgreement(BaseModel):
    """0–1 score metric vs the binary human label. AUC is threshold-free
    (P(score on a faithful trace > score on a hallucinated one), ties ½);
    the best-threshold pair shows what a single cutoff could achieve."""

    metric: str
    scored: int
    abstentions: int
    faithful_mean: float | None
    hallucinated_mean: float | None
    auc: float | None
    best_threshold: float | None
    best_threshold_accuracy: float | None


class MetricAgreementReport(BaseModel):
    traces: int
    datasets: list[str]
    # What produced the results — prompt-rev comparisons key on these.
    metric_versions: dict[str, str] = {}
    model: str | None = None
    critics: list[CriticAgreement]
    scores: list[ScoreAgreement]
    cost: CostStats

    def render_text(self) -> str:
        model = f" — {self.model}" if self.model else ""
        lines = [
            f"Metric agreement report — {self.traces} traces ({', '.join(self.datasets)}){model}"
        ]
        for critic in self.critics:
            version = self.metric_versions.get(critic.metric)
            rev = f" v{version}" if version else ""
            lines += ["", f"{critic.metric}{rev} (human × critic):"]
            columns = ("true", "false", "abstain")
            width = max(len(c) for c in columns) + 2
            lines.append(" " * 14 + "".join(c.rjust(width) for c in columns))
            for human in ("true", "false"):
                row = critic.confusion.get(human, {})
                cells = "".join(str(row.get(c, 0)).rjust(width) for c in columns)
                lines.append(f"  human {human:<7}{cells}")
            lines += [
                f"  decided agreement: {_pct(critic.decided_agreement)}"
                f" ({critic.decided_matches}/{critic.decided})",
                f"  abstention rate:   {_pct(critic.abstention_rate)}"
                f" ({critic.abstentions}/{self.traces})",
                f"  strict agreement:  {_pct(critic.strict_agreement)} (abstention = miss)",
                f"  precision: {_pct(critic.precision)}  recall: {_pct(critic.recall)}"
                f"  balanced accuracy: {_pct(critic.balanced_accuracy)}",
            ]
        for score in self.scores:
            version = self.metric_versions.get(score.metric)
            rev = f" v{version}" if version else ""
            lines += [
                "",
                f"{score.metric}{rev} (score vs human label):",
                f"  scored: {score.scored}/{self.traces} (abstentions: {score.abstentions})",
                f"  mean score — faithful: {_num(score.faithful_mean)},"
                f" hallucinated: {_num(score.hallucinated_mean)}",
                f"  AUC: {_num(score.auc)}",
                f"  best threshold: {_num(score.best_threshold)}"
                f" → accuracy {_pct(score.best_threshold_accuracy)}",
            ]
        lines += [
            "",
            f"Cost: {self.cost.llm_calls} LLM calls,"
            f" {self.cost.input_tokens + self.cost.output_tokens} tokens,"
            f" ${self.cost.cost_usd:.2f}",
        ]
        return "\n".join(lines)


def _num(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _fold_critic_agreement(metric: str, entries: list[MetricEntry]) -> CriticAgreement:
    confusion = {h: {"true": 0, "false": 0, "abstain": 0} for h in ("true", "false")}
    tp = fp = tn = fn = 0
    for entry in entries:
        result = entry.results.get(metric)
        human = str(entry.label.hallucinated).lower()
        if result is None:
            confusion[human]["abstain"] += 1
            continue
        flag = bool(result.value)
        confusion[human][str(flag).lower()] += 1
        tp += flag and entry.label.hallucinated
        fp += flag and not entry.label.hallucinated
        tn += not flag and not entry.label.hallucinated
        fn += not flag and entry.label.hallucinated
    decided = tp + fp + tn + fn
    matches = tp + tn
    abstentions = len(entries) - decided
    positive_recall = _ratio(tp, tp + fn)
    negative_recall = _ratio(tn, tn + fp)
    balanced = (
        (positive_recall + negative_recall) / 2
        if positive_recall is not None and negative_recall is not None
        else None
    )
    return CriticAgreement(
        metric=metric,
        confusion=confusion,
        decided=decided,
        decided_matches=matches,
        decided_agreement=_ratio(matches, decided),
        abstentions=abstentions,
        abstention_rate=abstentions / len(entries),
        strict_agreement=matches / len(entries),
        precision=_ratio(tp, tp + fp),
        recall=positive_recall,
        balanced_accuracy=balanced,
    )


def _auc(faithful: list[float], hallucinated: list[float]) -> float | None:
    """Mann–Whitney AUC: P(faithful score > hallucinated score), ties ½.
    O(n·m) is fine at benchmark-slice sizes."""
    if not faithful or not hallucinated:
        return None
    wins = sum(1.0 if f > h else 0.5 if f == h else 0.0 for f in faithful for h in hallucinated)
    return wins / (len(faithful) * len(hallucinated))


def _best_threshold(
    faithful: list[float], hallucinated: list[float]
) -> tuple[float | None, float | None]:
    """The cutoff (score ≥ t → faithful) maximizing accuracy, swept over
    midpoints of adjacent distinct scores plus the extremes."""
    scores = sorted(set(faithful) | set(hallucinated))
    if not scores:
        return None, None
    midpoints = ((a + b) / 2 for a, b in zip(scores, scores[1:], strict=False))
    candidates = [scores[0] - 0.01, *midpoints, scores[-1] + 0.01]
    total = len(faithful) + len(hallucinated)
    best_t, best_acc = None, -1.0
    for t in candidates:
        correct = sum(f >= t for f in faithful) + sum(h < t for h in hallucinated)
        if correct / total > best_acc:
            best_t, best_acc = t, correct / total
    return best_t, best_acc


def _fold_score_agreement(metric: str, entries: list[MetricEntry]) -> ScoreAgreement:
    faithful: list[float] = []
    hallucinated: list[float] = []
    for entry in entries:
        result = entry.results.get(metric)
        if result is None:
            continue
        (hallucinated if entry.label.hallucinated else faithful).append(float(result.value))
    scored = len(faithful) + len(hallucinated)
    best_t, best_acc = _best_threshold(faithful, hallucinated)
    return ScoreAgreement(
        metric=metric,
        scored=scored,
        abstentions=len(entries) - scored,
        faithful_mean=sum(faithful) / len(faithful) if faithful else None,
        hallucinated_mean=sum(hallucinated) / len(hallucinated) if hallucinated else None,
        auc=_auc(faithful, hallucinated),
        best_threshold=best_t,
        best_threshold_accuracy=best_acc,
    )


def _fold_metric_cost(entries: list[MetricEntry]) -> CostStats:
    calls = [
        call
        for entry in entries
        for result in entry.results.values()
        if result is not None
        for call in result.calls
    ]
    return CostStats(
        llm_calls=len(calls),
        input_tokens=sum(c.input_tokens or 0 for c in calls),
        output_tokens=sum(c.output_tokens or 0 for c in calls),
        cost_usd=sum(c.cost_usd or 0.0 for c in calls),
    )


def metric_agreement_report(
    entries: list[MetricEntry],
    metric_names: list[str],
    metric_versions: dict[str, str] | None = None,
    model: str | None = None,
) -> MetricAgreementReport:
    """Fold evaluated metrics against the sidecar. Boolean-valued metrics
    land in the critic section, float-valued in the score section; a metric
    every trace abstained on still reports (as all-abstain), so a broken
    predicate is visible rather than silent."""
    if not entries:
        raise ValueError("no entries to fold")
    critics: list[CriticAgreement] = []
    scores: list[ScoreAgreement] = []
    for name in metric_names:
        values = [e.results[name].value for e in entries if e.results.get(name) is not None]
        if values and all(isinstance(v, float) and not isinstance(v, bool) for v in values):
            scores.append(_fold_score_agreement(name, entries))
        else:
            critics.append(_fold_critic_agreement(name, entries))
    return MetricAgreementReport(
        traces=len(entries),
        datasets=sorted({e.label.dataset for e in entries}),
        metric_versions=metric_versions or {},
        model=model,
        critics=critics,
        scores=scores,
        cost=_fold_metric_cost(entries),
    )
