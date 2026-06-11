"""Regenerate the importer + renderer + signals golden files from fixtures/.
Review every diff."""

import asyncio
import json
from pathlib import Path

from app.analysis import render_trace
from app.analysis.signals import run_signals
from app.importers import otlp
from app.redaction import OFFLINE_SALT
from tests.unit.analysis_factories import load_fixture_trace
from tests.unit.test_importer_golden import FIXTURES, FIXTURES_DIR, GOLDEN_DIR, result_to_dict
from tests.unit.test_renderer_golden import GOLDEN_CONFIG, RENDER_FIXTURES
from tests.unit.test_session_golden import SESSIONS, convert_session
from tests.unit.test_signals_golden import SIGNALS_FIXTURES, SIGNALS_SETTINGS


def main() -> None:
    for name in FIXTURES:
        payload = json.loads((FIXTURES_DIR / f"{name}.json").read_text())
        out = result_to_dict(otlp.import_payload(payload, redaction_salt=OFFLINE_SALT))
        path = GOLDEN_DIR / f"{name}.expected.json"
        path.write_text(json.dumps(out, indent=2) + "\n")
        print(f"wrote {path.relative_to(Path.cwd())}")

    for name in sorted(SESSIONS):
        out = result_to_dict(convert_session(name))
        path = GOLDEN_DIR / f"{name}.expected.json"
        path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
        print(f"wrote {path.relative_to(Path.cwd())}")

    for name in RENDER_FIXTURES:
        rendered = render_trace(load_fixture_trace(name), GOLDEN_CONFIG)
        path = GOLDEN_DIR / f"{name}.render.expected.json"
        path.write_text(json.dumps(rendered.model_dump(mode="json"), indent=2) + "\n")
        print(f"wrote {path.relative_to(Path.cwd())}")

    for name in SIGNALS_FIXTURES:
        result = asyncio.run(run_signals(load_fixture_trace(name), SIGNALS_SETTINGS))
        path = GOLDEN_DIR / f"{name}.signals.expected.json"
        path.write_text(json.dumps(result.model_dump(mode="json"), indent=2) + "\n")
        print(f"wrote {path.relative_to(Path.cwd())}")


if __name__ == "__main__":
    main()
