"""Umbrella playbook and project-goal contract checks."""
from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_site_imports_safe_end_to_end_flow_in_order():
    site = (REPO_ROOT / "playbooks/site.yml").read_text(encoding="utf-8")
    site_docs = list(yaml.safe_load_all(site))

    expected_imports = [
        "00-prep-os.yml",
        "01-install-grid.yml",
        "02-install-dbhome.yml",
        "03-create-instance.yml",
        "04-register-restart.yml",
        "05-dataguard.yml",
        "06-observer.yml",
        "07-patch.yml",
        "07-patch-grid.yml",
        "07-patch-dual-db.yml",
        "99-test.yml",
    ]
    positions = [
        site.index(f"import_playbook: {playbook}") for playbook in expected_imports
    ]

    assert positions == sorted(positions)
    assert "Configure Data Guard in Maximum Availability mode" in site
    assert "Scaffolded" not in site
    assert "07-patch-standbyfirst.yml" not in site
    assert "Standby-first patching intentionally remains an explicit opt-in" in site
    assert [
        play["ansible.builtin.import_playbook"] for play in site_docs[0]
    ] == expected_imports
    imports_by_file = {
        play["ansible.builtin.import_playbook"]: play for play in site_docs[0]
    }
    create_import = imports_by_file["03-create-instance.yml"]
    restart_import = imports_by_file["04-register-restart.yml"]
    for play in (create_import, restart_import):
        assert play["vars"]["oracle_network_dataguard_enabled"] is True
        assert play["vars"]["oracle_lab_host_map_mode"] == "dataguard"
    assert (
        restart_import["vars"]["oracle_restart_apply_instance_overrides_require_dataguard"]
        is False
    )


def test_test_playbook_runs_pytest_with_bounded_lab_environment():
    test_playbook = yaml.safe_load(
        (REPO_ROOT / "playbooks/99-test.yml").read_text(encoding="utf-8")
    )
    play = test_playbook[0]
    run_task = next(
        task for task in play["tasks"] if task["name"] == "Run pytest against the lab"
    )

    assert play["vars"]["oracle_test_timeout_seconds"] == 1800
    assert play["vars"]["oracle_test_environment"]["ANSIBLE_LOCAL_TEMP"] == "/tmp/ansible-local"
    assert (
        play["vars"]["oracle_test_environment"]["ANSIBLE_SSH_CONTROL_PATH_DIR"]
        == "/tmp/ansible-cp"
    )
    assert play["vars"]["oracle_test_environment"]["XDG_CACHE_HOME"] == "/tmp/ansible-cache"
    assert "timeout {{ oracle_test_timeout_seconds | int }}" in run_task["ansible.builtin.shell"]
    assert run_task["environment"] == "{{ oracle_test_environment }}"
    assert run_task["failed_when"] is False


def test_project_goal_pins_dataguard_maximum_availability():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    status = (REPO_ROOT / "STATUS.md").read_text(encoding="utf-8")
    dg_defaults = (
        REPO_ROOT / "roles/oracle_dataguard/defaults/main.yml"
    ).read_text(encoding="utf-8")
    dg_broker = (
        REPO_ROOT / "roles/oracle_dataguard/tasks/configure-broker.yml"
    ).read_text(encoding="utf-8")
    dg_broker_tasks = yaml.safe_load(dg_broker)

    assert (
        "Goal requirement: Data Guard availability mode is Maximum Availability."
        in readme
    )
    assert (
        "Goal requirement: Data Guard availability mode is Maximum Availability"
        in status
    )
    assert "protection mode: always MAXIMUM AVAILABILITY" in dg_defaults
    assert "`MAXIMUM AVAILABILITY` protection mode" in status
    set_mode_tasks = [
        task
        for task in dg_broker_tasks
        if task.get("name") == "Configure broker protection mode before FSFO is enabled"
    ]
    assert len(set_mode_tasks) == 1
    assert (
        "EDIT CONFIGURATION SET PROTECTION MODE AS MAXAVAILABILITY"
        in set_mode_tasks[0]["ansible.builtin.shell"]
    )


def test_readme_documents_custom_instance_parameters():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    status = (REPO_ROOT / "STATUS.md").read_text(encoding="utf-8")

    assert "## Instance Settings" in readme
    assert "oracle_instances[*].parameters" in readme
    assert "open_cursors" in readme
    assert "quote: true" in readme
    assert "oracle_instances[*].parameters" in status
    assert "open_cursors" in status
