"""Remaining-gates runbook contract checks."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_remaining_gates_documents_standbyfirst_media_and_apply_flow():
    runbook = (REPO_ROOT / "REMAINING_GATES.md").read_text(encoding="utf-8")

    assert "scripts/run-standbyfirst-apply.sh" in runbook
    assert "playbooks/07-patch-standbyfirst-media.yml" in runbook
    assert "oracle_patch_standbyfirst_media_require_eligible=true" in runbook
    assert "playbooks/07-patch-standbyfirst.yml" in runbook
    assert "-e oracle_patch_zip=/u01/stage/<eligible-standby-first-db-ru.zip>" in runbook
    assert "-e oracle_patch_apply_component_path=39062931/39034528" in runbook
    assert "oracle_patch_dual_home_suffix=db_home2" in runbook
    assert "oracle_patch_standbyfirst_execute=true" in runbook
    assert "oracle_patch_standbyfirst_restore_primary=true" in runbook
    assert "oracle_patch_standbyfirst_confirm=PATCH_STANDBY_FIRST" in runbook
    assert "MaxAvailability" in runbook
    assert "READ ONLY WITH APPLY" in runbook
    assert "refuses execution before broker discovery" in runbook
    assert "confirmation token omitted" in runbook
    assert "phase-specific OPatch inventory" in runbook
    assert "DBA_REGISTRY_SQLPATCH" in runbook
    assert "SQL patch registry" in runbook


def test_remaining_gates_documents_proven_fsfo_rehearsal_command():
    runbook = (REPO_ROOT / "REMAINING_GATES.md").read_text(encoding="utf-8")

    assert "Proven: Destructive FSFO Failover/Reinstate Rehearsal" in runbook
    assert "playbooks/08-failover-reinstate.yml" in runbook
    assert "oracle_failover_reinstate_execute=true" in runbook
    assert (
        "oracle_failover_reinstate_confirm=DESTROY_PRIMARY_AND_REINSTATE"
        in runbook
    )
    assert "must fail before `virsh destroy`" in runbook
    assert "refuses to destroy the primary VM" in runbook
    assert "validates `virsh dominfo` for the primary VM" in runbook
    assert "validated the standby as `READ ONLY WITH APPLY`" in runbook


def test_readme_and_goal_audit_link_remaining_gates_runbook():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    audit = (REPO_ROOT / "GOAL_AUDIT.md").read_text(encoding="utf-8")
    runbook = (REPO_ROOT / "REMAINING_GATES.md").read_text(encoding="utf-8")

    assert "REMAINING_GATES.md" in readme
    assert "REMAINING_GATES.md" in audit
    assert "scripts/check-remaining-gates.sh" in readme
    assert "scripts/check-remaining-gates.sh" in runbook
    assert "scripts/run-standbyfirst-apply.sh" in readme
    assert "scripts/run-standbyfirst-apply.sh" in runbook


def test_remaining_gates_safe_check_script_dry_run():
    script = REPO_ROOT / "scripts/check-remaining-gates.sh"
    text = script.read_text(encoding="utf-8")

    assert script.is_file()
    assert "playbooks/07-patch-standbyfirst-media.yml" in text
    assert "playbooks/07-patch-standbyfirst.yml" in text
    assert "playbooks/08-failover-reinstate.yml" in text
    assert "oracle_failover_reinstate_execute=true" not in text
    assert "PATCH_STANDBY_FIRST" not in text
    assert "DESTROY_PRIMARY_AND_REINSTATE" not in text

    result = subprocess.run(
        [str(script), "--dry-run"],
        cwd=REPO_ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "playbooks/07-patch-standbyfirst-media.yml" in result.stdout
    assert "playbooks/07-patch-standbyfirst.yml" in result.stdout
    assert "oracle_patch_apply_component_path=39062931/39034528" in result.stdout
    assert "oracle_patch_standbyfirst_expected_primary=super" in result.stdout
    assert "oracle_patch_standbyfirst_expected_standby=super_sby" in result.stdout
    assert "oracle_patch_standbyfirst_execute=true" not in result.stdout
    assert "playbooks/08-failover-reinstate.yml" in result.stdout
    assert "oracle_patch_standbyfirst_media_require_eligible=true" not in result.stdout
    assert "oracle_failover_reinstate_execute=true" not in result.stdout


def test_remaining_gates_safe_check_script_can_require_eligible_media():
    script = REPO_ROOT / "scripts/check-remaining-gates.sh"
    result = subprocess.run(
        [str(script), "--dry-run", "--require-eligible-media"],
        cwd=REPO_ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "oracle_patch_standbyfirst_media_require_eligible=true" in result.stdout
    assert "oracle_patch_standbyfirst_execute=true" not in result.stdout
    assert "oracle_failover_reinstate_execute=true" not in result.stdout


def test_remaining_gates_safe_check_script_can_disable_expected_roles():
    script = REPO_ROOT / "scripts/check-remaining-gates.sh"
    result = subprocess.run(
        [str(script), "--dry-run", "--no-standbyfirst-expected-roles"],
        cwd=REPO_ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "oracle_patch_standbyfirst_expected_primary=super" not in result.stdout
    assert "oracle_patch_standbyfirst_expected_standby=super_sby" not in result.stdout


def test_remaining_gates_safe_check_script_can_prove_confirmation_gate():
    script = REPO_ROOT / "scripts/check-remaining-gates.sh"
    result = subprocess.run(
        [str(script), "--dry-run", "--prove-confirmation-gate"],
        cwd=REPO_ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "Standby-first missing-confirmation refusal" in result.stdout
    assert "oracle_patch_dual_home_suffix=db_home2" in result.stdout
    assert "oracle_patch_standbyfirst_execute=true" in result.stdout
    assert "oracle_patch_standbyfirst_restore_primary=true" in result.stdout
    assert "PATCH_STANDBY_FIRST" not in result.stdout
    assert "DESTROY_PRIMARY_AND_REINSTATE" not in result.stdout


def test_remaining_gates_confirmation_gate_can_match_no_restore_shape():
    script = REPO_ROOT / "scripts/check-remaining-gates.sh"
    result = subprocess.run(
        [
            str(script),
            "--dry-run",
            "--prove-confirmation-gate",
            "--no-standbyfirst-restore-primary",
        ],
        cwd=REPO_ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "Standby-first missing-confirmation refusal" in result.stdout
    assert "oracle_patch_standbyfirst_execute=true" in result.stdout
    assert "oracle_patch_standbyfirst_restore_primary=true" not in result.stdout
    assert "PATCH_STANDBY_FIRST" not in result.stdout


def test_standbyfirst_apply_helper_refuses_without_execute():
    script = REPO_ROOT / "scripts/run-standbyfirst-apply.sh"
    assert os.access(script, os.X_OK)
    result = subprocess.run(
        [str(script)],
        cwd=REPO_ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode != 0
    assert "requires --execute" in result.stderr
    assert "oracle_patch_standbyfirst_execute=true" not in result.stdout


def test_standbyfirst_apply_helper_refuses_without_exact_confirmation():
    script = REPO_ROOT / "scripts/run-standbyfirst-apply.sh"
    result = subprocess.run(
        [str(script), "--dry-run", "--execute", "--confirm", "WRONG"],
        cwd=REPO_ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode != 0
    assert "requires --confirm PATCH_STANDBY_FIRST" in result.stderr
    assert "oracle_patch_standbyfirst_execute=true" not in result.stdout


def test_standbyfirst_apply_helper_dry_run_prints_preflight_and_final_apply():
    script = REPO_ROOT / "scripts/run-standbyfirst-apply.sh"
    result = subprocess.run(
        [str(script), "--dry-run", "--execute", "--confirm", "PATCH_STANDBY_FIRST"],
        cwd=REPO_ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "scripts/check-remaining-gates.sh" in result.stdout
    assert "--skip-fsfo" in result.stdout
    assert "--prove-confirmation-gate" in result.stdout
    assert "playbooks/07-patch-standbyfirst.yml" in result.stdout
    assert "oracle_patch_zip=/u01/stage/p39062931_190000_Linux-x86-64.zip" in result.stdout
    assert "oracle_patch_apply_component_path=39062931/39034528" in result.stdout
    assert "oracle_patch_dual_home_suffix=db_home2" in result.stdout
    assert "oracle_patch_standbyfirst_expected_primary=super" in result.stdout
    assert "oracle_patch_standbyfirst_expected_standby=super_sby" in result.stdout
    assert "oracle_patch_standbyfirst_execute=true" in result.stdout
    assert "oracle_patch_standbyfirst_restore_primary=true" in result.stdout
    assert "oracle_patch_standbyfirst_confirm=PATCH_STANDBY_FIRST" in result.stdout


def test_standbyfirst_apply_helper_no_restore_preflight_matches_final_shape():
    script = REPO_ROOT / "scripts/run-standbyfirst-apply.sh"
    result = subprocess.run(
        [
            str(script),
            "--dry-run",
            "--execute",
            "--confirm",
            "PATCH_STANDBY_FIRST",
            "--no-restore-primary",
        ],
        cwd=REPO_ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "--no-standbyfirst-restore-primary" in result.stdout
    assert "oracle_patch_standbyfirst_expected_primary=super" in result.stdout
    assert "oracle_patch_standbyfirst_expected_standby=super_sby" in result.stdout
    assert "oracle_patch_standbyfirst_execute=true" in result.stdout
    assert "oracle_patch_standbyfirst_restore_primary=true" not in result.stdout
    assert "oracle_patch_standbyfirst_confirm=PATCH_STANDBY_FIRST" in result.stdout
