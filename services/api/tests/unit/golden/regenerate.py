"""Regenerate the importer golden files from fixtures/. Review every diff."""

import json
from pathlib import Path

from app.importers import otlp
from tests.unit.test_importer_golden import FIXTURES, FIXTURES_DIR, GOLDEN_DIR, result_to_dict


def main() -> None:
    for name in FIXTURES:
        payload = json.loads((FIXTURES_DIR / f"{name}.json").read_text())
        out = result_to_dict(otlp.import_payload(payload))
        path = GOLDEN_DIR / f"{name}.expected.json"
        path.write_text(json.dumps(out, indent=2) + "\n")
        print(f"wrote {path.relative_to(Path.cwd())}")


if __name__ == "__main__":
    main()
