"""Contract tests for scripts/run-tests.sh."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_script(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    merged_env = os.environ.copy()
    merged_env.update(env or {})
    return subprocess.run(
        [str(REPO_ROOT / "scripts/run-tests.sh"), *args],
        cwd=REPO_ROOT,
        env=merged_env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_run_tests_dry_run_exports_full_kvm_lab_defaults():
    result = run_script("--dry-run", "tests/test_site.py")

    assert result.returncode == 0, result.stderr
    assert "ORACLE_TEST_SSH_HOST=192.168.87.11" in result.stdout
    assert "ORACLE_TEST_STANDBY_SSH_HOST=192.168.87.12" in result.stdout
    assert "ORACLE_TEST_OBSERVER_SSH_HOST=192.168.87.13" in result.stdout
    assert "ANSIBLE_LOCAL_TEMP=/tmp/ansible-local" in result.stdout
    assert "ANSIBLE_SSH_CONTROL_PATH_DIR=/tmp/ansible-cp" in result.stdout
    assert "XDG_CACHE_HOME=/tmp/ansible-cache" in result.stdout
    assert "tests/test_site.py" in result.stdout


def test_run_tests_dry_run_honors_operator_overrides():
    result = run_script(
        "--dry-run",
        env={
            "ORACLE_TEST_STANDBY_SSH_HOST": "10.0.0.12",
            "ORACLE_TEST_OBSERVER_SSH_HOST": "10.0.0.13",
            "ANSIBLE_LOCAL_TEMP": "/tmp/custom-ansible",
        },
    )

    assert result.returncode == 0, result.stderr
    assert "ORACLE_TEST_STANDBY_SSH_HOST=10.0.0.12" in result.stdout
    assert "ORACLE_TEST_OBSERVER_SSH_HOST=10.0.0.13" in result.stdout
    assert "ANSIBLE_LOCAL_TEMP=/tmp/custom-ansible" in result.stdout


def test_run_tests_help_is_safe():
    result = run_script("--help")

    assert result.returncode == 0, result.stderr
    assert "Usage: scripts/run-tests.sh" in result.stdout
    assert "--dry-run" in result.stdout
