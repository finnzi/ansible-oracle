"""Remaining-gates runbook contract checks."""
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_remaining_gates_documents_standbyfirst_media_and_apply_flow():
    runbook = (REPO_ROOT / "REMAINING_GATES.md").read_text(encoding="utf-8")

    assert "playbooks/07-patch-standbyfirst-media.yml" in runbook
    assert "oracle_patch_standbyfirst_media_require_eligible=true" in runbook
    assert "playbooks/07-patch-standbyfirst.yml" in runbook
    assert "-e oracle_patch_zip=/u01/stage/<eligible-standby-first-db-ru.zip>" in runbook
    assert "oracle_patch_standbyfirst_execute=true" in runbook
    assert "oracle_patch_standbyfirst_confirm=PATCH_STANDBY_FIRST" in runbook
    assert "MaxAvailability" in runbook
    assert "READ ONLY WITH APPLY" in runbook
    assert "refuses execution" in runbook


def test_remaining_gates_documents_fsfo_readiness_gate_and_destructive_confirm():
    runbook = (REPO_ROOT / "REMAINING_GATES.md").read_text(encoding="utf-8")

    assert "playbooks/08-failover-reinstate.yml" in runbook
    assert "oracle_failover_reinstate_execute=true" in runbook
    assert (
        "oracle_failover_reinstate_confirm=DESTROY_PRIMARY_AND_REINSTATE"
        in runbook
    )
    assert "must fail before `virsh destroy`" in runbook
    assert "refuses to destroy the primary VM" in runbook
    assert "validates `virsh dominfo` for the primary VM" in runbook
    assert "destroys the current primary VM" in runbook


def test_readme_and_goal_audit_link_remaining_gates_runbook():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    audit = (REPO_ROOT / "GOAL_AUDIT.md").read_text(encoding="utf-8")

    assert "REMAINING_GATES.md" in readme
    assert "REMAINING_GATES.md" in audit
