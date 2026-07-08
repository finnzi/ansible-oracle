"""
test_05_dataguard.py — Data Guard assertions.

SKIPPED in the vertical slice: DG creation is scaffolded. These tests assert
the project requirements that will apply once DG lands:
  - broker protection mode is MAXIMUM AVAILABILITY.
  - standby is OPEN READ ONLY WITH APPLY (not MOUNTED).
  - DGMGRL reports the broker configuration healthy.
  - switchover swaps primary/standby roles.
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_dataguard_defaults_use_maximum_availability():
    defaults_text = (
        REPO_ROOT / "roles/oracle_dataguard/defaults/main.yml"
    ).read_text(encoding="utf-8")

    assert (
        "dg_protection_mode: MAXIMUM AVAILABILITY" in defaults_text
    )


@pytest.mark.scaffolded
def test_dataguard_role_present_or_skipped(db_connection):
    """In the slice there is no standby; skip cleanly with a clear reason."""
    cur = db_connection.cursor()
    cur.execute("SELECT database_role FROM v$database")
    role = cur.fetchone()[0]
    cur.close()
    if role == "PRIMARY" and not _dg_configured(db_connection):
        pytest.skip(
            "Data Guard not configured in this slice (oracle_dataguard is "
            "scaffolded). Re-run after DG lands to assert standby READ ONLY WITH APPLY."
        )


@pytest.mark.scaffolded
def test_standby_is_read_only_with_apply(db_connection):
    pytest.skip(
        "Standby open-mode assertion: requires Data Guard (scaffolded). "
        "Will assert open_mode == 'READ ONLY WITH APPLY'."
    )


@pytest.mark.scaffolded
def test_dgmgrrl_configuration_healthy():
    pytest.skip(
        "DGMGRL broker health assertion: requires Data Guard (scaffolded). "
        "Will run `dgmgrl ... SHOW CONFIGURATION`."
    )


@pytest.mark.scaffolded
def test_manual_switchover():
    pytest.skip(
        "Manual switchover assertion: requires Data Guard (scaffolded). "
        "Will run `dgmgrl ... SWITCHOVER TO super_sby` and assert role swap."
    )


def _dg_configured(conn) -> bool:
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT count(*) FROM v$database "
            "WHERE database_role IN ('PHYSICAL STANDBY','LOGICAL STANDBY')"
        )
        return cur.fetchone()[0] > 0
    except Exception:
        return False
