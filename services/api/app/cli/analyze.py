"""Offline analysis runner — the B-stream dev/test surface (1_analysis.md).

Fixture mode runs the stage-1 importer over OTLP JSON files (multi-trace
files fan out per trace) and needs no platform env; DB mode loads normalized
rows by trace id. Results are `AnalyzerRun` envelopes / `RenderedTrace`
models dumped as JSON to stdout or --out.

    python -m app.cli.analyze run --analyzer stub fixtures/agent-session.json
    python -m app.cli.analyze run --analyzer all --trace-id <uuid> --out out/
    python -m app.cli.analyze render devdata/*.json --out out/
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from pydantic import BaseModel

from app.analysis import (
    ANALYZERS,
    AnalysisSettings,
    RendererConfig,
    TraceInput,
    render_trace,
    run_analyzer,
)


def _load_fixture(path: Path) -> list[tuple[str, TraceInput]]:
    """(identifier, trace) per trace in the file, via the ingestion importer."""
    from app.importers.otlp import import_payload

    payload = json.loads(path.read_text())
    result = import_payload(payload)
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
    specs = list(ANALYZERS.values()) if args.analyzer == "all" else [ANALYZERS[args.analyzer]]
    for identifier, trace in await _load(args):
        for spec in specs:
            run = await run_analyzer(spec, trace, settings)
            if run is None:
                print(f"{identifier}: {spec.name} not applicable, skipped", file=sys.stderr)
                continue
            _emit(identifier, spec.name, run, args.out)
    return 0


def _add_input_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("paths", nargs="*", help="OTLP JSON fixture files")
    parser.add_argument("--trace-id", help="load one trace from the local DB instead of files")
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

    args = parser.parse_args()
    if bool(args.paths) == bool(args.trace_id):
        parser.error("provide fixture paths or --trace-id (exactly one input source)")
    raise SystemExit(asyncio.run(args.handler(args)))


if __name__ == "__main__":
    main()
