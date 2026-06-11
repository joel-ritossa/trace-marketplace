"""trace-sync: upload local trace files to the Trace Marketplace (5_cli.md).

    trace-sync sync <paths...>    upload every new trace file, print results, exit
    trace-sync watch <paths...>   same loop, then upload files as they appear

Config: TRACE_API_URL / TRACE_API_KEY env vars, overridable by flags.
"""

import argparse
import os
import sys
from pathlib import Path

from trace_sync.client import FatalError, SyncClient
from trace_sync.run import EXIT_UNRUNNABLE, run_sync, run_watch

DEFAULT_API_URL = "http://localhost:8000"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trace-sync",
        description="Upload local trace files to the Trace Marketplace.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("sync", "upload every new trace file under the paths, then exit"),
        ("watch", "sync, then stay alive and upload files as they appear or change"),
    ):
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("paths", nargs="+", type=Path, help="files or directories to sync")
        cmd.add_argument(
            "--api-url",
            default=os.environ.get("TRACE_API_URL", DEFAULT_API_URL),
            help=f"API base URL (env TRACE_API_URL, default {DEFAULT_API_URL})",
        )
        cmd.add_argument(
            "--api-key",
            default=os.environ.get("TRACE_API_KEY"),
            help="API key minted in /settings (env TRACE_API_KEY)",
        )
        cmd.add_argument(
            "--since-hours",
            type=float,
            default=None,
            help="only consider files modified in the last N hours (default: all)",
        )
    return parser


def main() -> None:
    # Line-buffer even when piped/redirected so watch-mode result lines land
    # in logs as they happen, not on exit.
    sys.stdout.reconfigure(line_buffering=True)
    args = _parser().parse_args()
    if not args.api_key:
        print(
            "no API key: set TRACE_API_KEY or pass --api-key (mint one in /settings)",
            file=sys.stderr,
        )
        sys.exit(EXIT_UNRUNNABLE)
    missing = [p for p in args.paths if not p.exists()]
    if missing:
        print(f"path not found: {', '.join(str(p) for p in missing)}", file=sys.stderr)
        sys.exit(EXIT_UNRUNNABLE)

    client = SyncClient(args.api_url, args.api_key)
    try:
        client.preflight()
        run = run_watch if args.command == "watch" else run_sync
        sys.exit(run(client, args.paths, args.since_hours))
    except FatalError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(EXIT_UNRUNNABLE)
    finally:
        client.close()


if __name__ == "__main__":
    main()
