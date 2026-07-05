"""
test_06_observer.py — FSFO observer assertions.

SKIPPED in the slice (oracle_observer is scaffolded). Will assert, once
enabled: the observer process is running on the third node and DGMGRL
reports Fast-Start Failover ENABLED.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.scaffolded


def test_observer_process_running():
    pytest.skip(
        "FSFO observer is scaffolded. Will assert `pgrep -fa dmobserver` on the "
        "observer node and `dgmgrl ... SHOW FAST_START FAILOVER` reports enabled."
    )


def test_fast_start_failover_enabled():
    pytest.skip("Requires FSFO observer (scaffolded).")
