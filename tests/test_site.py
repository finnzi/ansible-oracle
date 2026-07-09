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
    assert "Data Guard configurations must use MAXIMUM AVAILABILITY" in status
    assert "protection mode: always MAXIMUM AVAILABILITY" in dg_defaults
    assert (
        "Project goal update: Data Guard availability mode is required to be\n"
        "Maximum Availability."
        in status
    )
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
