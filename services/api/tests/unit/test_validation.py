"""B4 validation fold + labels sidecar (app/analysis/validation.py)."""

import json

import pytest

from app.analysis import JudgeVerdict, RoutingReason, SignalsResult
from app.analysis.models import JudgeVote, MetricCall, MetricResult
from app.analysis.validation import (
    AgreementEntry,
    AgreementReport,
    MetricAgreementReport,
    MetricEntry,
    MetricTraceLabel,
    TraceLabel,
    agreement_report,
    load_labels,
    load_metric_labels,
    metric_agreement_report,
)


def make_label(**overrides) -> TraceLabel:
    return TraceLabel(**{"dataset": "test", "outcome": "failure", **overrides})


def make_entry(
    *,
    human: str = "failure",
    judge: str | None = "failure",
    failure_mode: str | None = None,
    routed: bool = False,
    label: TraceLabel | None = None,
    signals: SignalsResult | None = None,
    votes: list[JudgeVote] | None = None,
) -> AgreementEntry:
    return AgreementEntry(
        label=label or make_label(outcome=human),
        signals=signals or SignalsResult(),
        verdict=JudgeVerdict(outcome=judge, failure_mode=failure_mode, votes=votes or []),
        routing_reasons=(
            [RoutingReason(code="outcome_indeterminate", message="m")] if routed else []
        ),
    )


# --- labels sidecar ---


def test_load_labels_round_trip(tmp_path):
    path = tmp_path / "labels.json"
    path.write_text(
        json.dumps(
            {
                "a" * 32: {"dataset": "arb", "outcome": "success", "looping": True},
                "b" * 32: {
                    "dataset": "agentrx",
                    "outcome": "failure",
                    "failure_categories": ["system_failure", "invalid_invocation"],
                    "root_cause_category": "system_failure",
                },
            }
        )
    )
    labels = load_labels(path)
    assert labels["a" * 32].outcome == "success"
    assert labels["a" * 32].looping is True
    assert labels["b" * 32].root_cause_category == "system_failure"


def test_load_labels_rejects_unknown_outcome(tmp_path):
    path = tmp_path / "labels.json"
    path.write_text(json.dumps({"a" * 32: {"dataset": "arb", "outcome": "maybe"}}))
    with pytest.raises(ValueError):
        load_labels(path)


def test_load_labels_rejects_unknown_failure_category(tmp_path):
    path = tmp_path / "labels.json"
    path.write_text(
        json.dumps(
            {
                "a" * 32: {
                    "dataset": "agentrx",
                    "outcome": "failure",
                    "root_cause_category": "gremlins",
                }
            }
        )
    )
    with pytest.raises(ValueError, match="gremlins"):
        load_labels(path)


# --- outcome fold ---


def test_outcome_confusion_and_agreement():
    entries = [
        make_entry(human="success", judge="success"),
        make_entry(human="success", judge="failure"),
        make_entry(human="failure", judge="failure"),
        make_entry(human="failure", judge="indeterminate"),
    ]
    outcome = agreement_report(entries).outcome
    assert outcome.confusion["success"]["success"] == 1
    assert outcome.confusion["success"]["failure"] == 1
    assert outcome.confusion["failure"]["failure"] == 1
    assert outcome.confusion["failure"]["indeterminate"] == 1
    assert outcome.decided == 3
    assert outcome.decided_matches == 2
    assert outcome.decided_agreement == pytest.approx(2 / 3)
    assert outcome.abstentions == 1
    assert outcome.abstention_rate == pytest.approx(1 / 4)
    assert outcome.strict_agreement == pytest.approx(2 / 4)


def test_outcome_null_judge_counts_as_abstention():
    outcome = agreement_report([make_entry(human="failure", judge=None)]).outcome
    assert outcome.confusion["failure"]["indeterminate"] == 1
    assert outcome.decided == 0
    assert outcome.decided_agreement is None
    assert outcome.strict_agreement == 0.0


def test_all_indeterminate_edge():
    entries = [make_entry(judge="indeterminate") for _ in range(3)]
    outcome = agreement_report(entries).outcome
    assert outcome.abstention_rate == 1.0
    assert outcome.decided_agreement is None


def test_empty_entries_rejected():
    with pytest.raises(ValueError):
        agreement_report([])


# --- failure-mode fold ---


def test_failure_mode_match_rates():
    label = make_label(
        dataset="agentrx",
        outcome="failure",
        failure_categories=["invalid_invocation", "system_failure"],
        root_cause_category="system_failure",
    )
    entries = [
        # root-cause + any match
        make_entry(label=label, judge="failure", failure_mode="system_failure"),
        # any-category match only
        make_entry(label=label, judge="failure", failure_mode="invalid_invocation"),
        # no match
        make_entry(label=label, judge="failure", failure_mode="guardrails_triggered"),
        # judge missed the failure entirely — excluded from match denominators
        make_entry(label=label, judge="success"),
    ]
    fm = agreement_report(entries).failure_mode
    assert fm is not None
    assert fm.true_failures == 4
    assert fm.judge_called_failure == 3
    assert fm.classified == 3
    assert fm.root_cause_matches == 1
    assert fm.root_cause_match_rate == pytest.approx(1 / 3)
    assert fm.any_category_matches == 2
    assert fm.any_category_match_rate == pytest.approx(2 / 3)


def test_failure_mode_none_without_category_labels():
    # ARB-only slices carry no categories — the section is absent, not zeroed.
    assert agreement_report([make_entry(human="failure", judge="failure")]).failure_mode is None


# --- routing fold ---


def test_routing_wrong_traces():
    entries = [
        make_entry(human="failure", judge="success", routed=True),  # wrong, routed
        make_entry(human="failure", judge="success", routed=False),  # wrong, missed
        make_entry(human="failure", judge="failure", routed=True),  # right, routed anyway
        make_entry(human="failure", judge="indeterminate", routed=True),  # abstain ≠ wrong
    ]
    routing = agreement_report(entries).routing
    assert routing.wrong == 2
    assert routing.wrong_routed == 1
    assert routing.wrong_routed_rate == pytest.approx(1 / 2)
    assert routing.routed == 3
    assert routing.routed_rate == pytest.approx(3 / 4)


def test_routing_no_wrong_traces():
    routing = agreement_report([make_entry(human="failure", judge="failure")]).routing
    assert routing.wrong == 0
    assert routing.wrong_routed_rate is None


# --- looping cross-check ---


def test_looping_cross_check():
    entries = [
        make_entry(label=make_label(looping=True), signals=SignalsResult(has_retry_loop=True)),
        make_entry(label=make_label(looping=True), signals=SignalsResult(has_retry_loop=False)),
        make_entry(label=make_label(looping=False), signals=SignalsResult(has_retry_loop=True)),
        # null signal excluded
        make_entry(label=make_label(looping=True), signals=SignalsResult()),
        # unlabeled excluded
        make_entry(signals=SignalsResult(has_retry_loop=True)),
    ]
    looping = agreement_report(entries).looping
    assert looping is not None
    assert looping.compared == 3
    assert looping.matches == 1
    assert looping.agreement == pytest.approx(1 / 3)
    assert looping.human_yes_signal_no == 1
    assert looping.human_no_signal_yes == 1


def test_looping_none_when_unlabeled():
    assert agreement_report([make_entry()]).looping is None


# --- cost fold + serialization ---


def test_cost_totals_from_votes():
    votes = [
        JudgeVote(
            call="outcome", value="failure", input_tokens=100, output_tokens=10, cost_usd=0.01
        ),
        JudgeVote(
            call="outcome", value="failure", input_tokens=200, output_tokens=20, cost_usd=None
        ),
    ]
    cost = agreement_report([make_entry(votes=votes)]).cost
    assert cost.llm_calls == 2
    assert cost.input_tokens == 300
    assert cost.output_tokens == 30
    assert cost.cost_usd == pytest.approx(0.01)


def test_metric_report_json_round_trip_and_text():
    entries = [
        metric_entry(hallucinated=True, flag=True, score=0.2),
        metric_entry(hallucinated=False, flag=False, score=0.9),
    ]
    report = metric_agreement_report(
        entries,
        metric_names=["hallucination", "faithfulness"],
        metric_versions={"hallucination": "1", "faithfulness": "1"},
        model="openai/gpt-5-mini",
    )
    restored = MetricAgreementReport.model_validate_json(report.model_dump_json())
    assert restored == report
    text = report.render_text()
    assert "hallucination v1 (human × critic)" in text
    assert "faithfulness v1 (score vs human label)" in text
    assert "Cost:" in text


def test_report_json_round_trip_and_text():
    entries = [
        make_entry(human="success", judge="success"),
        make_entry(
            label=make_label(
                dataset="agentrx", outcome="failure", root_cause_category="system_failure"
            ),
            judge="failure",
            failure_mode="system_failure",
            routed=True,
        ),
    ]
    report = agreement_report(entries)
    restored = AgreementReport.model_validate_json(report.model_dump_json())
    assert restored == report
    text = report.render_text()
    assert "Outcome (human × judge)" in text
    assert "Failure mode" in text
    assert "Routing" in text


# --- family-3 metric fold ---


def metric_entry(
    *,
    hallucinated: bool,
    flag: bool | None = None,
    score: float | None = None,
    calls: list[MetricCall] | None = None,
) -> MetricEntry:
    results: dict[str, MetricResult | None] = {
        "hallucination": (
            MetricResult(metric="hallucination", value=flag, calls=calls or [])
            if flag is not None
            else None
        ),
        "faithfulness": (
            MetricResult(metric="faithfulness", value=score) if score is not None else None
        ),
    }
    return MetricEntry(
        label=MetricTraceLabel(dataset="halubench", hallucinated=hallucinated),
        results=results,
    )


def test_load_metric_labels_round_trip(tmp_path):
    path = tmp_path / "labels.json"
    path.write_text(
        json.dumps(
            {
                "a" * 32: {
                    "dataset": "halubench",
                    "hallucinated": True,
                    "source": "RAGTruth",
                    "case_id": "x",
                },
                "b" * 32: {"dataset": "halubench", "hallucinated": False},
            }
        )
    )
    labels = load_metric_labels(path)
    assert labels["a" * 32].hallucinated is True
    assert labels["a" * 32].source == "RAGTruth"
    assert labels["b" * 32].hallucinated is False


def test_critic_confusion_and_rates():
    entries = [
        metric_entry(hallucinated=True, flag=True),  # tp
        metric_entry(hallucinated=True, flag=False),  # fn
        metric_entry(hallucinated=False, flag=False),  # tn
        metric_entry(hallucinated=False, flag=False),  # tn
        metric_entry(hallucinated=False, flag=True),  # fp
        metric_entry(hallucinated=True),  # abstain
    ]
    report = metric_agreement_report(entries, metric_names=["hallucination"])
    (critic,) = report.critics
    assert critic.confusion["true"] == {"true": 1, "false": 1, "abstain": 1}
    assert critic.confusion["false"] == {"true": 1, "false": 2, "abstain": 0}
    assert critic.decided == 5
    assert critic.decided_matches == 3
    assert critic.decided_agreement == pytest.approx(3 / 5)
    assert critic.abstentions == 1
    assert critic.abstention_rate == pytest.approx(1 / 6)
    assert critic.strict_agreement == pytest.approx(3 / 6)
    assert critic.precision == pytest.approx(1 / 2)
    assert critic.recall == pytest.approx(1 / 2)
    assert critic.balanced_accuracy == pytest.approx((1 / 2 + 2 / 3) / 2)


def test_score_fold_auc_and_threshold():
    entries = [
        metric_entry(hallucinated=False, score=0.9),
        metric_entry(hallucinated=False, score=0.8),
        metric_entry(hallucinated=True, score=0.3),
        metric_entry(hallucinated=True, score=0.8),  # tie with one faithful
        metric_entry(hallucinated=True),  # abstain
    ]
    report = metric_agreement_report(entries, metric_names=["faithfulness"])
    (score,) = report.scores
    assert score.scored == 4
    assert score.abstentions == 1
    assert score.faithful_mean == pytest.approx(0.85)
    assert score.hallucinated_mean == pytest.approx(0.55)
    # pairs: (.9>.3)=1, (.9>.8)=1, (.8>.3)=1, (.8=.8)=.5 → 3.5/4
    assert score.auc == pytest.approx(3.5 / 4)
    assert score.best_threshold_accuracy == pytest.approx(3 / 4)


def test_score_fold_single_class_has_no_auc():
    entries = [metric_entry(hallucinated=True, score=0.2)]
    report = metric_agreement_report(entries, metric_names=["faithfulness"])
    (score,) = report.scores
    assert score.auc is None
    assert score.faithful_mean is None
    assert score.hallucinated_mean == pytest.approx(0.2)


def test_all_abstained_metric_still_reports():
    entries = [metric_entry(hallucinated=True), metric_entry(hallucinated=False)]
    report = metric_agreement_report(entries, metric_names=["faithfulness"])
    # No values to type the metric by — it lands in the critic section as
    # all-abstain, keeping a broken predicate visible.
    (critic,) = report.critics
    assert critic.abstentions == 2
    assert critic.decided == 0
    assert critic.decided_agreement is None


def test_metric_cost_totals():
    calls = [
        MetricCall(input_tokens=100, output_tokens=10, cost_usd=0.01),
        MetricCall(input_tokens=200, output_tokens=20, cost_usd=None),
    ]
    report = metric_agreement_report(
        [metric_entry(hallucinated=True, flag=True, calls=calls)],
        metric_names=["hallucination"],
    )
    assert report.cost.llm_calls == 2
    assert report.cost.input_tokens == 300
    assert report.cost.output_tokens == 30
    assert report.cost.cost_usd == pytest.approx(0.01)


def test_metric_empty_entries_rejected():
    with pytest.raises(ValueError):
        metric_agreement_report([], metric_names=["hallucination"])
