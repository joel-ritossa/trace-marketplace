"""Derived analysis state: the one rule every surface shares
(2_data-model.md "Analysis state")."""

from app.queries.analysis import derive_state


def test_no_row_is_pending() -> None:
    assert derive_state(None, failed=False) == "pending"


def test_complete() -> None:
    assert derive_state("complete", failed=False) == "complete"


def test_skipped() -> None:
    assert derive_state("skipped", failed=False) == "skipped"


def test_open_dead_letter_is_failed() -> None:
    assert derive_state(None, failed=True) == "failed"


def test_failed_rerun_beats_stale_row() -> None:
    """A dead-lettered re-run is the latest truth even when an older
    result row still exists."""
    assert derive_state("complete", failed=True) == "failed"
