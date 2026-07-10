"""Goal-audit contract checks."""
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_goal_audit_tracks_original_scope_and_remaining_gates():
    audit = (REPO_ROOT / "GOAL_AUDIT.md").read_text(encoding="utf-8")

    assert "pasted-text-1.txt" in audit
    for requirement in [
        "Replace unsafe Docker/container lab with KVM/libvirt VMs",
        "Oracle Linux 10 where supported",
        "Data Guard availability mode Maximum Availability",
        "No ASM for database files",
        "Multiple DB instances per machine",
        "Dedicated patch playbooks",
        "Standby-first Data Guard patching when release notes allow",
        "Automatically read standby-first support from release notes",
    ]:
        assert requirement in audit

    assert "Explicit destructive FSFO rehearsal" in audit
    assert "DESTROY_PRIMARY_AND_REINSTATE" in audit
    assert "Live eligible standby-first patch apply" in audit
    assert "currently reports zero staged" in audit
    assert "PATCH_STANDBY_FIRST" in audit


def test_goal_audit_does_not_claim_external_gates_are_complete():
    audit = (REPO_ROOT / "GOAL_AUDIT.md").read_text(encoding="utf-8")

    assert "| Automatic failover | Partial |" in audit
    assert (
        "| Standby-first Data Guard patching when release notes allow | External gate |"
        in audit
    )
    assert "VM-crash branch is intentionally unrun" in audit
    assert "live eligible-RU apply requires suitable standalone DB RU media" in audit
