"""Offline analysis runner — the B-stream dev/test surface (1_analysis.md).

Fixture mode runs the stage-1 importer over OTLP JSON files (multi-trace
files fan out per trace) and needs no platform env; DB mode loads normalized
rows by trace id. Results are `AnalyzerRun` envelopes / `RenderedTrace`
models dumped as JSON to stdout or --out.

    python -m app.cli.analyze run --analyzer signals fixtures/agent-session.json
    python -m app.cli.analyze run --analyzer all --trace-id <uuid> --out out/
    python -m app.cli.analyze render devdata/*.json --out out/
    python -m app.cli.analyze signals-report devdata/*.json
    python -m app.cli.analyze route fixtures/*.json
    python -m app.cli.analyze agreement devdata/benchmarks/arb/traces/*.json \
        --labels devdata/benchmarks/arb/labels.json --out out/arb/
    python -m app.cli.analyze metrics-agreement devdata/benchmarks/halubench/traces/*.json \
        --labels devdata/benchmarks/halubench/labels.json --out out/halubench/ \
        --metrics hallucination,faithfulness
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from pydantic import BaseModel

from app.analysis import (
    ANALYZERS,
    JUDGE_VERSION,
    AnalysisSettings,
    JudgeVerdict,
    RendererConfig,
    RoutingReason,
    SignalsResult,
    TraceInput,
    llm_configured,
    render_trace,
    route,
    run_analyzer,
    run_judge,
    run_metric_set,
)
from app.analysis.metrics import METRIC_RUNNERS, METRIC_VERSIONS
from app.analysis.models import MetricResult
from app.analysis.signals import run_signals
from app.analysis.validation import (
    AgreementEntry,
    MetricEntry,
    agreement_report,
    load_labels,
    load_metric_labels,
    metric_agreement_report,
)


def _load_fixture(path: Path) -> list[tuple[str, TraceInput]]:
    """(identifier, trace) per trace in the file, via the ingestion importer."""
    from app.importers.otlp import import_payload
    from app.redaction import OFFLINE_SALT

    payload = json.loads(path.read_text())
    result = import_payload(payload, redaction_salt=OFFLINE_SALT)
    return [(f"{path.stem}_{t.source_trace_id}", TraceInput.from_import(t)) for t in result.traces]


async def _load_db(trace_id: str) -> list[tuple[str, TraceInput]]:
    # Lazy imports: only DB mode needs platform settings/env.
    from app.clients import db
    from app.queries.analysis import fetch_trace_input

    await db.open_pool()
    try:
        trace = await fetch_trace_input(db.pool(), trace_id)
        if trace is None:
            print(f"trace {trace_id} not found", file=sys.stderr)
            raise SystemExit(1)
        return [(trace_id, trace)]
    finally:
        await db.close_pool()


async def _load(args: argparse.Namespace) -> list[tuple[str, TraceInput]]:
    if args.trace_id:
        return await _load_db(args.trace_id)
    loaded = []
    for path in args.paths:
        loaded.extend(_load_fixture(Path(path)))
    return loaded


def _emit(identifier: str, suffix: str, model: BaseModel, out_dir: str | None) -> None:
    text = model.model_dump_json(indent=2)
    if out_dir:
        target = Path(out_dir) / f"{identifier}_{suffix}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + "\n")
        print(target)
    else:
        print(text)


async def _cmd_render(args: argparse.Namespace) -> int:
    config = RendererConfig.from_settings(AnalysisSettings())
    for identifier, trace in await _load(args):
        _emit(identifier, "render", render_trace(trace, config), args.out)
    return 0


async def _cmd_run(args: argparse.Namespace) -> int:
    settings = AnalysisSettings()
    if args.analyzer != "all" and args.analyzer not in ANALYZERS:
        known = ", ".join(sorted(ANALYZERS))
        print(f"unknown analyzer {args.analyzer!r} (known: {known}, all)", file=sys.stderr)
        return 2
    # "all" = the production set in run order (signals, judge, then the
    # enabled metrics concurrently via run_metric_set) — same as the worker,
    # never the registry wholesale (the stub is a harness fixture;
    # ANALYSIS_METRICS filters metrics here too).
    if args.analyzer == "all":
        for identifier, trace in await _load(args):
            for spec in (ANALYZERS["signals"], ANALYZERS["judge"]):
                run = await run_analyzer(spec, trace, settings)
                if run is None:
                    print(f"{identifier}: {spec.name} not applicable, skipped", file=sys.stderr)
                    continue
                _emit(identifier, spec.name, run, args.out)
            for run in await run_metric_set(trace, settings):
                _emit(identifier, run.analyzer, run, args.out)
        return 0
    spec = ANALYZERS[args.analyzer]
    for identifier, trace in await _load(args):
        run = await run_analyzer(spec, trace, settings)
        if run is None:
            print(f"{identifier}: {spec.name} not applicable, skipped", file=sys.stderr)
            continue
        _emit(identifier, spec.name, run, args.out)
    return 0


async def _cmd_signals_report(args: argparse.Namespace) -> int:
    """Per-field hit rates over a trace set — the B1 promotion-list evidence
    (1_analysis.md: promotion is hit-rate gated). Counts only, no content.
    Calls the analyzer directly: the report needs the typed result, not the
    persistence envelope `run_analyzer` produces."""
    settings = AnalysisSettings()
    results: list[SignalsResult] = []
    for _, trace in await _load(args):
        results.append(await run_signals(trace, settings))
    total = len(results)
    print(f"traces: {total}")
    print(f"{'field':<24} {'non-null':>14} {'truthy':>14}")
    for field in SignalsResult.model_fields:
        values = [getattr(r, field) for r in results]
        non_null = sum(v is not None for v in values)
        truthy = sum(bool(v) for v in values if v is not None)
        rate = f"{non_null}/{total} ({non_null / total:4.0%})" if total else "0/0"
        truthy_rate = f"{truthy}/{total} ({truthy / total:4.0%})" if total else "0/0"
        print(f"{field:<24} {rate:>14} {truthy_rate:>14}")
    return 0


class RouteReport(BaseModel):
    """`route` subcommand output: the full HIL pipeline for one trace —
    signals, the final (capped) verdict, and the routing reasons.

    `judge_version`/`judge_model` stamp what produced the verdict, so a
    cached report from one prompt/ensemble version is never silently
    compared against another (the agreement cache keys on them)."""

    signals: SignalsResult
    verdict: JudgeVerdict
    routing_reasons: list[RoutingReason]
    judge_version: str | None = None
    judge_model: str | None = None


async def _route_one(trace: TraceInput, settings: AnalysisSettings) -> RouteReport | None:
    """signals + judge (finalized) + routing for one trace — the shared
    pipeline behind `route` and `agreement`. None = judge keyless-skipped."""
    signals = await run_signals(trace, settings)
    verdict = await run_judge(trace, settings, signals)
    if verdict is None:
        return None
    reasons = route(signals, verdict, settings.confidence_threshold)
    return RouteReport(
        signals=signals,
        verdict=verdict,
        routing_reasons=reasons,
        judge_version=JUDGE_VERSION,
        judge_model=settings.judge_model,
    )


async def _cmd_route(args: argparse.Namespace) -> int:
    settings = AnalysisSettings()
    for identifier, trace in await _load(args):
        report = await _route_one(trace, settings)
        if report is None:
            print(f"{identifier}: judge skipped (LLM not configured)", file=sys.stderr)
            continue
        _emit(identifier, "route", report, args.out)
    return 0


def _load_cached_report(cache_path: Path) -> RouteReport | None:
    """A usable cache entry: parses *and* matches the current judge version.
    A stale or corrupt entry (interrupted write, older prompt rev) re-judges
    rather than contaminating the fold."""
    if not cache_path.exists():
        return None
    try:
        report = RouteReport.model_validate_json(cache_path.read_text())
    except ValueError:
        print(f"discarding corrupt cache entry {cache_path.name}", file=sys.stderr)
        return None
    if report.judge_version != JUDGE_VERSION:
        print(
            f"discarding stale cache entry {cache_path.name} "
            f"(judge v{report.judge_version} ≠ v{JUDGE_VERSION})",
            file=sys.stderr,
        )
        return None
    return report


async def _cmd_agreement(args: argparse.Namespace) -> int:
    """B4: judge a converted benchmark slice and fold agreement vs its
    ground-truth sidecar. Per-trace verdicts cache in --out (RouteReport
    JSON, version-stamped, skipped when present and current), so an
    interrupted run resumes and a prompt rev never reuses old verdicts; the
    report is recomputed from cache + labels every time. Per-trace failures
    (a transient provider error mid-run) drop that trace from the fold and
    flip the exit code — re-running judges only the missing traces."""
    settings = AnalysisSettings()
    if not llm_configured(settings.judge_model):
        print("agreement needs a configured LLM (judge model key missing)", file=sys.stderr)
        return 1
    labels = load_labels(Path(args.labels))
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(args.concurrency)

    async def judge_one(identifier: str, trace: TraceInput) -> tuple[str, RouteReport]:
        cache_path = out_dir / f"{identifier}_route.json"
        cached = _load_cached_report(cache_path)
        if cached is not None:
            return trace.source_trace_id, cached
        async with semaphore:
            report = await _route_one(trace, settings)
            assert report is not None  # llm_configured checked above
            # Atomic publish: a kill mid-write must not leave a truncated
            # JSON that poisons the next resume.
            tmp_path = cache_path.with_suffix(".json.tmp")
            tmp_path.write_text(report.model_dump_json(indent=2) + "\n")
            tmp_path.replace(cache_path)
            print(f"judged {identifier}", file=sys.stderr)
            return trace.source_trace_id, report

    loaded = await _load(args)
    missing = [i for i, t in loaded if t.source_trace_id not in labels]
    if missing:
        print(f"no label for: {', '.join(missing)} (converter/labels mismatch)", file=sys.stderr)
        return 2
    results = await asyncio.gather(*(judge_one(i, t) for i, t in loaded), return_exceptions=True)
    judged = [r for r in results if isinstance(r, tuple)]
    failures = [r for r in results if isinstance(r, BaseException)]
    for (identifier, _), result in zip(loaded, results, strict=True):
        if isinstance(result, BaseException):
            print(f"failed {identifier}: {result}", file=sys.stderr)
    if not judged:
        print("no traces judged successfully; no report", file=sys.stderr)
        return 1
    entries = [
        AgreementEntry(
            label=labels[trace_id],
            signals=report.signals,
            verdict=report.verdict,
            routing_reasons=report.routing_reasons,
        )
        for trace_id, report in judged
    ]
    report = agreement_report(
        entries, judge_version=JUDGE_VERSION, judge_model=settings.judge_model
    )
    (out_dir / "report.json").write_text(report.model_dump_json(indent=2) + "\n")
    print(report.render_text())
    print(f"\nreport written to {out_dir / 'report.json'}")
    if failures:
        print(
            f"{len(failures)}/{len(loaded)} traces failed and are excluded; re-run to retry them",
            file=sys.stderr,
        )
        return 1
    return 0


class MetricsReport(BaseModel):
    """`metrics-agreement` per-trace cache: name → result (None = the
    metric abstained — a computed outcome worth caching, not a gap).
    `metric_versions`/`model` stamp what produced each result, so a prompt
    rev on one metric invalidates only that metric's cache entries."""

    results: dict[str, MetricResult | None]
    metric_versions: dict[str, str] = {}
    model: str | None = None


def _load_cached_metrics(
    cache_path: Path, names: list[str], model: str
) -> dict[str, MetricResult | None]:
    """Cache entries usable under the current versions/model — per-metric,
    so iterating on one prompt never re-pays the others."""
    if not cache_path.exists():
        return {}
    try:
        report = MetricsReport.model_validate_json(cache_path.read_text())
    except ValueError:
        print(f"discarding corrupt cache entry {cache_path.name}", file=sys.stderr)
        return {}
    if report.model != model:
        return {}
    return {
        name: report.results[name]
        for name in names
        if name in report.results and report.metric_versions.get(name) == METRIC_VERSIONS[name]
    }


async def _cmd_metrics_agreement(args: argparse.Namespace) -> int:
    """Family-3 counterpart of `agreement`: run the requested metrics over a
    converted benchmark slice and fold agreement vs its metric ground-truth
    sidecar. Same cache discipline (version-stamped, atomic, resumable) at
    per-metric granularity; per-trace failures drop that trace from the fold
    and flip the exit code — re-running computes only what's missing."""
    settings = AnalysisSettings(metrics=args.metrics)  # validates the names
    names = settings.metric_names
    if not llm_configured(settings.judge_model):
        print("metrics-agreement needs a configured LLM (model key missing)", file=sys.stderr)
        return 1
    labels = load_metric_labels(Path(args.labels))
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(args.concurrency)

    async def evaluate_one(
        identifier: str, trace: TraceInput
    ) -> tuple[str, dict[str, MetricResult | None]]:
        cache_path = out_dir / f"{identifier}_metrics.json"
        results = _load_cached_metrics(cache_path, names, settings.judge_model)
        missing = [name for name in names if name not in results]
        if missing:
            async with semaphore:
                # Metrics are independent: settle all before raising the
                # first error (the worker's gather discipline).
                computed = await asyncio.gather(
                    *(METRIC_RUNNERS[name](trace, settings) for name in missing),
                    return_exceptions=True,
                )
                for result in computed:
                    if isinstance(result, BaseException):
                        raise result
                results |= dict(zip(missing, computed, strict=True))
                report = MetricsReport(
                    results=results,
                    metric_versions={name: METRIC_VERSIONS[name] for name in names},
                    model=settings.judge_model,
                )
                tmp_path = cache_path.with_suffix(".json.tmp")
                tmp_path.write_text(report.model_dump_json(indent=2) + "\n")
                tmp_path.replace(cache_path)
                print(f"evaluated {identifier} ({', '.join(missing)})", file=sys.stderr)
        return trace.source_trace_id, results

    loaded = await _load(args)
    unlabeled = [i for i, t in loaded if t.source_trace_id not in labels]
    if unlabeled:
        print(f"no label for: {', '.join(unlabeled)} (converter/labels mismatch)", file=sys.stderr)
        return 2
    outcomes = await asyncio.gather(
        *(evaluate_one(i, t) for i, t in loaded), return_exceptions=True
    )
    evaluated = [r for r in outcomes if isinstance(r, tuple)]
    failures = [r for r in outcomes if isinstance(r, BaseException)]
    for (identifier, _), outcome in zip(loaded, outcomes, strict=True):
        if isinstance(outcome, BaseException):
            print(f"failed {identifier}: {outcome}", file=sys.stderr)
    if not evaluated:
        print("no traces evaluated successfully; no report", file=sys.stderr)
        return 1
    entries = [
        MetricEntry(label=labels[trace_id], results=results) for trace_id, results in evaluated
    ]
    report = metric_agreement_report(
        entries,
        metric_names=names,
        metric_versions={name: METRIC_VERSIONS[name] for name in names},
        model=settings.judge_model,
    )
    (out_dir / "report.json").write_text(report.model_dump_json(indent=2) + "\n")
    print(report.render_text())
    print(f"\nreport written to {out_dir / 'report.json'}")
    if failures:
        print(
            f"{len(failures)}/{len(loaded)} traces failed and are excluded; re-run to retry them",
            file=sys.stderr,
        )
        return 1
    return 0


def _add_input_args(parser: argparse.ArgumentParser, out: bool = True) -> None:
    parser.add_argument("paths", nargs="*", help="OTLP JSON fixture files")
    parser.add_argument("--trace-id", help="load one trace from the local DB instead of files")
    if out:
        parser.add_argument("--out", help="write JSON files to this directory instead of stdout")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli.analyze", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="run an analyzer over traces")
    run_parser.add_argument("--analyzer", required=True, help="analyzer name, or 'all'")
    _add_input_args(run_parser)
    run_parser.set_defaults(handler=_cmd_run)

    render_parser = subparsers.add_parser("render", help="dump trace renderings")
    _add_input_args(render_parser)
    render_parser.set_defaults(handler=_cmd_render)

    report_parser = subparsers.add_parser(
        "signals-report", help="per-field signal hit rates over a trace set"
    )
    _add_input_args(report_parser, out=False)
    report_parser.set_defaults(handler=_cmd_signals_report)

    route_parser = subparsers.add_parser(
        "route", help="signals + judge + routing reasons per trace"
    )
    _add_input_args(route_parser)
    route_parser.set_defaults(handler=_cmd_route)

    agreement_parser = subparsers.add_parser(
        "agreement", help="judge a benchmark slice and report agreement vs human labels"
    )
    agreement_parser.add_argument("paths", nargs="*", help="converted OTLP JSON files")
    agreement_parser.add_argument("--labels", required=True, help="labels.json sidecar path")
    agreement_parser.add_argument(
        "--out", required=True, help="directory for per-trace verdict cache + report.json"
    )
    agreement_parser.add_argument(
        "--concurrency", type=int, default=4, help="traces judged in parallel"
    )
    agreement_parser.set_defaults(handler=_cmd_agreement, trace_id=None)

    metrics_parser = subparsers.add_parser(
        "metrics-agreement",
        help="run family-3 metrics over a benchmark slice and report agreement vs human labels",
    )
    metrics_parser.add_argument("paths", nargs="*", help="converted OTLP JSON files")
    metrics_parser.add_argument("--labels", required=True, help="labels.json sidecar path")
    metrics_parser.add_argument(
        "--out", required=True, help="directory for per-trace result cache + report.json"
    )
    metrics_parser.add_argument(
        "--metrics",
        default="hallucination,faithfulness",
        help="comma-separated metric names to evaluate",
    )
    metrics_parser.add_argument(
        "--concurrency", type=int, default=4, help="traces evaluated in parallel"
    )
    metrics_parser.set_defaults(handler=_cmd_metrics_agreement, trace_id=None)

    args = parser.parse_args()
    if bool(args.paths) == bool(args.trace_id):
        parser.error("provide fixture paths or --trace-id (exactly one input source)")
    raise SystemExit(asyncio.run(args.handler(args)))


if __name__ == "__main__":
    main()
