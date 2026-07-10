"""FSFO failover/reinstate rehearsal playbook assertions."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _ansible_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("ANSIBLE_LOCAL_TEMP", "/tmp/ansible-local")
    env.setdefault("ANSIBLE_SSH_CONTROL_PATH_DIR", "/tmp/ansible-cp")
    env.setdefault("XDG_CACHE_HOME", "/tmp/ansible-cache")
    return env


def test_failover_reinstate_playbook_contract():
    playbook = (REPO_ROOT / "playbooks/08-failover-reinstate.yml").read_text(
        encoding="utf-8"
    )
    site = (REPO_ROOT / "playbooks/site.yml").read_text(encoding="utf-8")
    status = (REPO_ROOT / "STATUS.md").read_text(encoding="utf-8")

    assert "08-failover-reinstate.yml" not in site
    assert "oracle_failover_reinstate_execute: false" in playbook
    assert "DESTROY_PRIMARY_AND_REINSTATE" in playbook
    assert "Validate FSFO readiness before destructive rehearsal" in playbook
    assert "SHOW FAST_START FAILOVER" in playbook
    assert "Fast-Start Failover:[[:space:]]+Enabled" in playbook
    assert "Protection Mode:[[:space:]]+MaxAvailability" in playbook
    assert "Fast-Start Failover is enabled" in playbook
    assert "protection mode is MaxAvailability" in playbook
    assert "active failover target is" in playbook
    assert "and an observer is present" in playbook
    assert "Report readiness-only mode" in playbook
    assert "Fail when destructive rehearsal confirmation is missing" in playbook
    assert "Destroy current primary VM to trigger FSFO" in playbook
    assert "virsh" in playbook
    assert "destroy" in playbook
    assert "Wait for FSFO to promote target standby" in playbook
    assert "Start old primary VM for broker reinstate" in playbook
    assert "Wait for old primary VM SSH after restart" in playbook
    assert "REINSTATE DATABASE '{{ oracle_failover_original_primary }}'" in playbook
    assert "Switch back to original primary after reinstate through broker" in playbook
    assert "SWITCHOVER TO '{{ oracle_failover_original_primary }}'" in playbook
    assert "Validate original primary restored and standby read-only with apply" in playbook
    assert (
        "PHYSICAL STANDBY|READ ONLY WITH APPLY|MAXIMUM AVAILABILITY|MAXIMUM AVAILABILITY"
        in playbook
    )
    assert "A live OHASD interruption triggered FSFO promotion" in status
    assert "returned automatically as a synchronized physical standby" in status
    assert "The explicit destructive execution branch" in status


def test_failover_reinstate_playbook_syntax_check():
    ansible_playbook = REPO_ROOT / ".venv/bin/ansible-playbook"
    cmd = [
        str(ansible_playbook if ansible_playbook.exists() else "ansible-playbook"),
        "-i",
        "inventory/hosts.yml",
        "playbooks/08-failover-reinstate.yml",
        "--syntax-check",
    ]
    r = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=_ansible_subprocess_env(),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_failover_reinstate_readiness_playbook_converges_without_destructive_changes():
    ansible_playbook = REPO_ROOT / ".venv/bin/ansible-playbook"
    cmd = [
        str(ansible_playbook if ansible_playbook.exists() else "ansible-playbook"),
        "-i",
        "inventory/hosts.yml",
        "playbooks/08-failover-reinstate.yml",
    ]
    r = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=_ansible_subprocess_env(),
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "failed=0" in r.stdout
    assert "changed=0" in r.stdout
    assert "FSFO readiness validated" in r.stdout
    assert "Fast-Start Failover is enabled" in r.stdout
    assert "protection mode is MaxAvailability" in r.stdout
    assert "current primary is super" in r.stdout
    assert "active failover target is super_sby" in r.stdout
    assert "and an observer is present" in r.stdout
    assert "TASK [Destroy current primary VM to trigger FSFO]" in r.stdout
    assert "skipping: [observer1]" in r.stdout
