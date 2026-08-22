"""Unit tests for the KVM lab preflight shell helpers."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_MEDIA = [
    "info.txt",
    "V982063-01-Oracle.19c.Database.Enterprise.Edition.zip",
    "V982064-01-Oracle.19c.Database.Client.zip",
    "V982068-01-Oracle.19c.Grid.Infrastructure.zip",
    "p6880880_190000_Linux-x86-64.zip",
    "p39062931_190000_Linux-x86-64.zip",
    "p39062956_190000_Linux-x86-64.zip",
    "p39618649_190000_Linux-x86-64.zip",
    "p39618711_190000_Linux-x86-64.zip",
]

IGNORED_TREE_NAMES = {
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "download",
}

FORBIDDEN_CONTAINER_LAB_NAMES = {
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
    "containerfile",
}


def run_common(script: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    merged_env = os.environ.copy()
    merged_env.update(env or {})
    return subprocess.run(
        ["bash", "-lc", f"source lab/scripts/lib/common.sh; {script}"],
        cwd=REPO_ROOT,
        env=merged_env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def run_lab_script(
    script_name: str,
    *args: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    merged_env = os.environ.copy()
    merged_env.update(env or {})
    return subprocess.run(
        [str(REPO_ROOT / "lab/scripts" / script_name), *args],
        cwd=REPO_ROOT,
        env=merged_env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def write_fake_virsh(bin_dir: Path, body: str) -> None:
    virsh = bin_dir / "virsh"
    virsh.write_text(f"#!/usr/bin/env bash\nset -euo pipefail\n{body}\n", encoding="utf-8")
    virsh.chmod(0o755)


def test_repo_has_no_docker_or_compose_lab_artifacts():
    forbidden: list[str] = []
    for path in REPO_ROOT.rglob("*"):
        rel = path.relative_to(REPO_ROOT)
        if any(part in IGNORED_TREE_NAMES for part in rel.parts):
            continue
        if not path.is_file():
            continue
        lower_name = path.name.lower()
        lower_rel = rel.as_posix().lower()
        if lower_name in FORBIDDEN_CONTAINER_LAB_NAMES or "docker" in lower_rel:
            forbidden.append(rel.as_posix())

    assert forbidden == []


def test_required_media_list_is_complete():
    result = run_common("lab_required_media_files")
    inventory_defaults = (REPO_ROOT / "inventory/group_vars/all.yml").read_text(
        encoding="utf-8"
    )
    inventory_media = re.findall(
        r"(?:db_zip|gi_zip|client_zip|opatch_zip|db_ru_zip|gi_ru_zip|"
        r"db_ru_upgrade_zip|gi_ru_upgrade_zip): \"([^\"]+)\"",
        inventory_defaults,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == REQUIRED_MEDIA
    assert set(result.stdout.splitlines()) == {"info.txt", *inventory_media}


def test_preflight_sources_passes_when_required_media_exists(tmp_path: Path):
    sources = tmp_path / "oracle"
    sources.mkdir()
    sources.chmod(0o755)
    for filename in REQUIRED_MEDIA:
        (sources / filename).write_text(f"{filename}: test fixture\n", encoding="utf-8")

    result = run_common(
        "lab_preflight_sources",
        {
            "SOURCES_DIR": str(sources),
            "LAB_SKIP_SOURCE_ACCESS_CHECK": "1",
        },
    )

    assert result.returncode == 0, result.stderr
    assert "Oracle media missing" not in result.stderr


def test_preflight_sources_fails_when_required_media_is_missing(tmp_path: Path):
    sources = tmp_path / "oracle"
    sources.mkdir()
    sources.chmod(0o755)
    (sources / "info.txt").write_text("partial media\n", encoding="utf-8")

    result = run_common(
        "lab_preflight_sources",
        {
            "SOURCES_DIR": str(sources),
            "LAB_SKIP_SOURCE_ACCESS_CHECK": "1",
        },
    )

    assert result.returncode == 1
    assert "Oracle media missing" in result.stderr


def test_allow_missing_media_keeps_os_only_lab_possible(tmp_path: Path):
    missing_sources = tmp_path / "missing"

    result = run_common(
        "lab_preflight_sources",
        {
            "SOURCES_DIR": str(missing_sources),
            "LAB_ALLOW_MISSING_MEDIA": "1",
        },
    )

    assert result.returncode == 0, result.stderr
    assert "LAB_ALLOW_MISSING_MEDIA=1" in result.stderr


def test_default_lab_state_dir_is_libvirt_readable_var_tmp():
    result = run_common("printf '%s\\n' \"${LAB_STATE_DIR}\"")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "/var/tmp/ansible-oracle-lab"


def test_lab_up_waits_for_cloud_init_after_ssh():
    script = (REPO_ROOT / "lab/scripts/lab-up.sh").read_text(encoding="utf-8")
    common = (REPO_ROOT / "lab/scripts/lib/common.sh").read_text(encoding="utf-8")

    assert script.index('wait_for_ssh "$(vm_ip "${svc}")"') < script.index(
        'wait_for_cloud_init "$(vm_ip "${svc}")"'
    )
    assert "cloud-init complete" in script
    # timeout(1) cannot exec a bash function.
    assert "timeout" in common.split("wait_for_cloud_init()")[1].split("path_world_accessible")[0]
    assert 'ssh "${opts[@]}" "root@${host_ip}" cloud-init status --wait' in common
    assert "timeout" in common and 'timeout "${LAB_CLOUD_INIT_TIMEOUT:-30m}" \\\n    ssh_lab' not in common


def test_preflight_state_dir_fails_for_private_home_like_parent(tmp_path: Path):
    private_parent = tmp_path / "private"
    private_parent.mkdir()
    private_parent.chmod(0o700)

    result = run_common(
        "lab_preflight_state_dir",
        {"LAB_STATE_DIR": str(private_parent / "lab-state")},
    )

    assert result.returncode == 1
    assert "LAB_STATE_DIR is not traversable/readable" in result.stderr
    assert "LAB_STATE_DIR=/var/tmp/ansible-oracle-lab" in result.stderr


def test_preflight_libvirt_groups_passes_with_active_libvirt_group():
    result = run_common(
        "lab_preflight_libvirt_groups",
        {
            "LAB_ACTIVE_GROUPS": "finnur libvirt kvm",
            "VIRSH_URI": "qemu:///system",
        },
    )

    assert result.returncode == 0, result.stderr
    assert "active group present: libvirt" in result.stderr


def test_preflight_libvirt_groups_warns_without_active_libvirt_group():
    result = run_common(
        "lab_preflight_libvirt_groups",
        {
            "LAB_ACTIVE_GROUPS": "finnur kvm",
            "VIRSH_URI": "qemu:///system",
        },
    )

    assert result.returncode == 0, result.stderr
    assert "current shell is not in the active libvirt group" in result.stderr
    assert "sudo usermod -aG libvirt,kvm $USER" in result.stderr
    assert "newgrp libvirt" in result.stderr
    assert "id -nG" in result.stderr
    assert "Group membership is advisory" in result.stderr


def test_preflight_libvirt_groups_warns_without_active_kvm_group():
    result = run_common(
        "lab_preflight_libvirt_groups",
        {
            "LAB_ACTIVE_GROUPS": "finnur libvirt",
            "VIRSH_URI": "qemu:///system",
        },
    )

    assert result.returncode == 0, result.stderr
    assert "active group present: libvirt" in result.stderr
    assert "current shell is not in the active kvm group" in result.stderr
    assert "Group membership is advisory" in result.stderr


def test_preflight_libvirt_checks_domain_and_network_drivers(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_virsh(
        bin_dir,
        """
if [ "$1" = "--connect" ] && [ "$3" = "list" ]; then
  exit 0
fi
if [ "$1" = "--connect" ] && [ "$3" = "net-list" ]; then
  exit 0
fi
exit 2
""",
    )

    result = run_common(
        "lab_preflight_libvirt",
        {"PATH": f"{bin_dir}:{os.environ['PATH']}"},
    )

    assert result.returncode == 0, result.stderr
    assert "libvirt domain driver reachable" in result.stderr
    assert "libvirt network driver reachable" in result.stderr


def test_preflight_libvirt_reports_missing_network_driver(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_virsh(
        bin_dir,
        """
if [ "$1" = "--connect" ] && [ "$3" = "list" ]; then
  exit 0
fi
if [ "$1" = "--connect" ] && [ "$3" = "net-list" ]; then
  exit 1
fi
exit 2
""",
    )

    result = run_common(
        "lab_preflight_libvirt",
        {"PATH": f"{bin_dir}:{os.environ['PATH']}"},
    )

    assert result.returncode == 1
    assert "libvirt domain driver reachable" in result.stderr
    assert "cannot access libvirt network driver" in result.stderr
    assert "sudo systemctl enable --now virtnetworkd.socket" in result.stderr


def test_preflight_resources_reports_requested_guest_memory():
    result = run_common(
        "lab_requested_memory_mib",
        {
            "LAB_DB_MEMORY_MIB": "12288",
            "LAB_OBSERVER_MEMORY_MIB": "4096",
        },
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "28672"


def test_preflight_resources_passes_when_host_memory_is_sufficient():
    result = run_common(
        "lab_preflight_resources",
        {
            "LAB_HOST_MEMORY_MIB": "32768",
            "LAB_HOST_NPROC": "12",
            "LAB_DB_MEMORY_MIB": "12288",
            "LAB_OBSERVER_MEMORY_MIB": "4096",
            "LAB_DB_VCPUS": "4",
            "LAB_OBSERVER_VCPUS": "2",
        },
    )

    assert result.returncode == 0, result.stderr
    assert "guest memory request fits host memory" in result.stderr
    assert "guest vCPU request" in result.stderr


def test_preflight_resources_fails_when_guest_memory_exceeds_host():
    result = run_common(
        "lab_preflight_resources",
        {
            "LAB_HOST_MEMORY_MIB": "8192",
            "LAB_DB_MEMORY_MIB": "12288",
            "LAB_OBSERVER_MEMORY_MIB": "4096",
        },
    )

    assert result.returncode == 1
    assert "configured guest memory exceeds host memory" in result.stderr
    assert "LAB_DB_MEMORY_MIB" in result.stderr
    assert "LAB_SKIP_RESOURCE_CHECK=1" in result.stderr


def test_preflight_resources_rejects_non_numeric_memory_setting():
    result = run_common(
        "lab_preflight_resources",
        {
            "LAB_HOST_MEMORY_MIB": "32768",
            "LAB_DB_MEMORY_MIB": "12g",
        },
    )

    assert result.returncode == 1
    assert "LAB_DB_MEMORY_MIB must be a positive integer" in result.stderr


def test_preflight_resources_can_be_skipped_for_manual_overcommit():
    result = run_common(
        "lab_preflight_resources",
        {
            "LAB_HOST_MEMORY_MIB": "8192",
            "LAB_DB_MEMORY_MIB": "12288",
            "LAB_OBSERVER_MEMORY_MIB": "4096",
            "LAB_SKIP_RESOURCE_CHECK": "1",
        },
    )

    assert result.returncode == 0, result.stderr
    assert "LAB_SKIP_RESOURCE_CHECK=1" in result.stderr


def test_lab_docs_include_libvirt_group_refresh_and_verification_commands():
    lab_readme = (REPO_ROOT / "lab/README.md").read_text(encoding="utf-8")
    quickstart = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    for text in (lab_readme, quickstart):
        assert 'sudo usermod -aG libvirt,kvm "$USER"' in text
        assert "newgrp libvirt" in text
        assert "id -nG" in text
        assert "virsh -c qemu:///system list --all" in text


def test_lab_docs_include_resource_preflight_controls():
    lab_readme = (REPO_ROOT / "lab/README.md").read_text(encoding="utf-8")

    assert "Preflight refuses to start the lab" in lab_readme
    assert "LAB_DB_MEMORY_MIB" in lab_readme
    assert "LAB_OBSERVER_MEMORY_MIB" in lab_readme
    assert "LAB_SKIP_RESOURCE_CHECK=1" in lab_readme


def test_prepare_host_fedora_help_is_safe():
    result = run_lab_script("prepare-host-fedora.sh", "--help")

    assert result.returncode == 0, result.stderr
    assert "--skip-package-install" in result.stdout
    assert "--skip-media-stage" in result.stdout


def test_lab_down_help_is_safe_and_documents_shutdown_controls(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    virsh_invocations = tmp_path / "virsh-invocations.log"
    write_fake_virsh(
        bin_dir,
        'printf "%s\\n" "$*" >> "${VIRSH_INVOCATIONS}"\nexit 99',
    )

    result = run_lab_script(
        "lab-down.sh",
        "--help",
        env={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "VIRSH_INVOCATIONS": str(virsh_invocations),
        },
    )

    assert result.returncode == 0, result.stderr
    assert "--purge" in result.stdout
    assert "--force" in result.stdout
    assert "LAB_SHUTDOWN_TIMEOUT_SECONDS" in result.stdout
    assert not virsh_invocations.exists()


def test_prepare_host_fedora_rejects_unknown_options():
    result = run_lab_script("prepare-host-fedora.sh", "--bogus")

    assert result.returncode == 1
    assert "Unknown option: --bogus" in result.stderr


def test_lab_down_times_out_without_destroying_domains(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    virsh_calls = tmp_path / "virsh-calls.log"
    write_fake_virsh(
        bin_dir,
        """
printf '%s\\n' "$*" >> "${VIRSH_CALL_LOG}"
case "${3:-}" in
  dominfo)
    exit 0
    ;;
  domstate)
    printf 'running\\n'
    ;;
  shutdown)
    exit 0
    ;;
  net-info)
    exit 1
    ;;
  *)
    exit 0
    ;;
esac
""",
    )
    (bin_dir / "sleep").write_text(
        "#!/usr/bin/env bash\nexit 0\n", encoding="utf-8"
    )
    (bin_dir / "sleep").chmod(0o755)

    result = run_lab_script(
        "lab-down.sh",
        env={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "LAB_SHUTDOWN_TIMEOUT_SECONDS": "1",
            "VIRSH_CALL_LOG": str(virsh_calls),
        },
    )

    calls = virsh_calls.read_text(encoding="utf-8").splitlines()
    assert result.returncode != 0, (
        "lab-down unexpectedly succeeded; virsh calls:\\n" + "\\n".join(calls)
    )
    assert not any(" destroy " in call for call in calls), (
        "lab-down invoked virsh destroy:\\n" + "\\n".join(calls)
    )


def test_lab_down_global_deadline_includes_discovery_before_waiting(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    clock = tmp_path / "epoch-clock"
    clock.write_text("100\n", encoding="utf-8")
    sleep_calls = tmp_path / "sleep-calls.log"

    (bin_dir / "date").write_text(
        """#!/usr/bin/env bash
set -euo pipefail
if [ "${1:-}" = "+%s" ]; then
  cat "${LAB_FAKE_CLOCK}"
else
  /bin/date "$@"
fi
""",
        encoding="utf-8",
    )
    (bin_dir / "date").chmod(0o755)
    write_fake_virsh(
        bin_dir,
        """
case "${3:-}" in
  dominfo)
    now="$(<"${LAB_FAKE_CLOCK}")"
    printf '%s\\n' "$((now + 1))" > "${LAB_FAKE_CLOCK}"
    exit 0
    ;;
  domstate)
    printf 'running\\n'
    ;;
  shutdown)
    exit 0
    ;;
  net-info)
    exit 1
    ;;
  *)
    exit 0
    ;;
esac
""",
    )
    (bin_dir / "sleep").write_text(
        """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "${LAB_SLEEP_CALLS}"
exit 0
""",
        encoding="utf-8",
    )
    (bin_dir / "sleep").chmod(0o755)

    result = run_lab_script(
        "lab-down.sh",
        env={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "LAB_FAKE_CLOCK": str(clock),
            "LAB_SLEEP_CALLS": str(sleep_calls),
            "LAB_SHUTDOWN_TIMEOUT_SECONDS": "1",
        },
    )

    assert result.returncode != 0, result.stderr
    assert not sleep_calls.exists(), (
        "lab-down slept after the global deadline was exhausted:\\n"
        + result.stderr
    )


def test_lab_down_starts_all_graceful_shutdowns_before_waiting(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    call_log = tmp_path / "lab-down-calls.log"
    write_fake_virsh(
        bin_dir,
        """
printf '%s\\n' "virsh $*" >> "${LAB_DOWN_CALL_LOG}"
case "${3:-}" in
  dominfo)
    exit 0
    ;;
  domstate)
    printf 'running\\n'
    ;;
  shutdown)
    exit 0
    ;;
  net-info)
    exit 1
    ;;
  *)
    exit 0
    ;;
esac
""",
    )
    (bin_dir / "sleep").write_text(
        """#!/usr/bin/env bash
printf '%s\n' "sleep $*" >> "${LAB_DOWN_CALL_LOG}"
exit 0
""",
        encoding="utf-8",
    )
    (bin_dir / "sleep").chmod(0o755)

    result = run_lab_script(
        "lab-down.sh",
        env={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "LAB_SHUTDOWN_TIMEOUT_SECONDS": "1",
            "LAB_DOWN_CALL_LOG": str(call_log),
        },
    )

    calls = call_log.read_text(encoding="utf-8").splitlines()
    shutdown_calls = [
        (index, call)
        for index, call in enumerate(calls)
        if " shutdown ansible-oracle-lab-" in call
    ]
    expected_domains = {
        "ansible-oracle-lab-superdb1",
        "ansible-oracle-lab-superdb2",
        "ansible-oracle-lab-observer",
    }
    assert result.returncode != 0
    assert {call.split()[-1] for _, call in shutdown_calls} == expected_domains

    first_wait = next(
        index for index, call in enumerate(calls) if call.startswith("sleep ")
    )
    assert all(index < first_wait for index, _ in shutdown_calls), (
        "graceful shutdowns were not all initiated before waiting:\\n"
        + "\\n".join(calls)
    )


def test_lab_down_force_destroys_active_domains_without_waiting(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    virsh_calls = tmp_path / "virsh-calls.log"
    destroyed_domains = tmp_path / "destroyed-domains.log"
    sleep_calls = tmp_path / "sleep-calls.log"
    write_fake_virsh(
        bin_dir,
        """
printf '%s\n' "$*" >> "${VIRSH_CALL_LOG}"
case "${3:-}" in
  dominfo)
    exit 0
    ;;
  domstate)
    if grep -qx "${4}" "${DESTROYED_DOMAINS}" 2>/dev/null; then
      printf 'shut off\n'
    else
      printf 'running\n'
    fi
    ;;
  destroy)
    printf '%s\n' "${4}" >> "${DESTROYED_DOMAINS}"
    exit 0
    ;;
  net-info)
    exit 1
    ;;
  *)
    exit 0
    ;;
esac
""",
    )
    (bin_dir / "sleep").write_text(
        "#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> \"${SLEEP_CALL_LOG}\"\nexit 0\n",
        encoding="utf-8",
    )
    (bin_dir / "sleep").chmod(0o755)

    result = run_lab_script(
        "lab-down.sh",
        "--force",
        env={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "VIRSH_CALL_LOG": str(virsh_calls),
            "DESTROYED_DOMAINS": str(destroyed_domains),
            "SLEEP_CALL_LOG": str(sleep_calls),
        },
    )

    calls = (
        virsh_calls.read_text(encoding="utf-8").splitlines()
        if virsh_calls.exists()
        else []
    )
    expected_domains = {
        "ansible-oracle-lab-superdb1",
        "ansible-oracle-lab-superdb2",
        "ansible-oracle-lab-observer",
    }
    destroy_calls = [
        call for call in calls if " destroy ansible-oracle-lab-" in call
    ]

    assert result.returncode == 0, result.stderr
    assert {call.split()[-1] for call in destroy_calls} == expected_domains
    assert not any(" shutdown " in call for call in calls)
    assert not sleep_calls.exists() or sleep_calls.read_text(encoding="utf-8") == ""


def test_lab_down_waits_for_graceful_shutdown_without_destroying(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    state_dir = tmp_path / "domain-state"
    state_dir.mkdir()
    virsh_calls = tmp_path / "virsh-calls.log"
    sleep_calls = tmp_path / "sleep-calls.log"
    write_fake_virsh(
        bin_dir,
        """
printf '%s\n' "$*" >> "${VIRSH_CALL_LOG}"
case "${3:-}" in
  dominfo)
    exit 0
    ;;
  domstate)
    count_file="${DOMAIN_STATE_DIR}/${4}.count"
    count=0
    if [ -f "${count_file}" ]; then
      count="$(<"${count_file}")"
    fi
    count=$((count + 1))
    printf '%s\n' "${count}" > "${count_file}"
    if [ "${count}" -lt 3 ]; then
      printf 'running\n'
    else
      printf 'shut off\n'
    fi
    ;;
  shutdown)
    exit 0
    ;;
  net-info)
    exit 1
    ;;
  *)
    exit 0
    ;;
esac
""",
    )
    (bin_dir / "sleep").write_text(
        "#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> \"${SLEEP_CALL_LOG}\"\nexit 0\n",
        encoding="utf-8",
    )
    (bin_dir / "sleep").chmod(0o755)

    result = run_lab_script(
        "lab-down.sh",
        env={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "LAB_SHUTDOWN_TIMEOUT_SECONDS": "5",
            "VIRSH_CALL_LOG": str(virsh_calls),
            "DOMAIN_STATE_DIR": str(state_dir),
            "SLEEP_CALL_LOG": str(sleep_calls),
        },
    )

    calls = virsh_calls.read_text(encoding="utf-8").splitlines()
    assert result.returncode == 0, result.stderr
    assert sleep_calls.read_text(encoding="utf-8").splitlines()
    assert not any(" destroy " in call for call in calls)


def test_lab_down_shutdown_failure_is_visible_and_does_not_purge(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    state_dir = tmp_path / "lab-state"
    (state_dir / "vms").mkdir(parents=True)
    (state_dir / "seed").mkdir()
    marker = state_dir / "vms/keep-me.qcow2"
    marker.write_text("fixture\n", encoding="utf-8")
    virsh_calls = tmp_path / "virsh-calls.log"
    write_fake_virsh(
        bin_dir,
        """
printf '%s\n' "$*" >> "${VIRSH_CALL_LOG}"
case "${3:-}" in
  dominfo)
    exit 0
    ;;
  domstate)
    if [ "${4}" = "ansible-oracle-lab-superdb1" ]; then
      printf 'running\n'
    else
      printf 'shut off\n'
    fi
    ;;
  shutdown)
    if [ "${4}" = "ansible-oracle-lab-superdb1" ]; then
      printf 'simulated virsh shutdown failure for %s\n' "${4}" >&2
      exit 1
    fi
    exit 0
    ;;
  net-info)
    exit 1
    ;;
  *)
    exit 0
    ;;
esac
""",
    )

    result = run_lab_script(
        "lab-down.sh",
        "--purge",
        env={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "LAB_STATE_DIR": str(state_dir),
            "VIRSH_CALL_LOG": str(virsh_calls),
        },
    )

    calls = virsh_calls.read_text(encoding="utf-8").splitlines()
    assert result.returncode != 0
    assert "simulated virsh shutdown failure" in result.stderr
    assert "Lab down." not in result.stderr
    assert not any(" destroy " in call for call in calls)
    assert not any(" undefine " in call for call in calls)
    assert marker.is_file()
    assert (state_dir / "seed").is_dir()


def test_lab_down_purge_undefine_failure_is_visible_and_does_not_cleanup(
    tmp_path: Path,
):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    state_dir = tmp_path / "lab-state"
    vm_dir = state_dir / "vms"
    seed_dir = state_dir / "seed"
    vm_dir.mkdir(parents=True)
    seed_dir.mkdir()
    vm_marker = vm_dir / "must-survive.qcow2"
    seed_marker = seed_dir / "must-survive.iso"
    vm_marker.write_text("fixture\n", encoding="utf-8")
    seed_marker.write_text("fixture\n", encoding="utf-8")
    virsh_calls = tmp_path / "virsh-calls.log"
    undefine_error = "simulated undefine failure"
    write_fake_virsh(
        bin_dir,
        f"""
printf '%s\\n' "$*" >> "${{VIRSH_CALL_LOG}}"
case "${{3:-}}" in
  dominfo)
    exit 0
    ;;
  domstate)
    printf 'shut off\\n'
    ;;
  undefine)
    printf '%s (%s)\\n' '{undefine_error}' "${{*:4}}" >&2
    exit 1
    ;;
  net-info)
    exit 0
    ;;
  net-destroy|net-undefine)
    printf 'network cleanup must not run\\n' >&2
    exit 1
    ;;
  *)
    exit 0
    ;;
esac
""",
    )

    result = run_lab_script(
        "lab-down.sh",
        "--purge",
        env={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "LAB_STATE_DIR": str(state_dir),
            "VIRSH_CALL_LOG": str(virsh_calls),
        },
    )

    calls = virsh_calls.read_text(encoding="utf-8").splitlines()
    assert result.returncode != 0
    assert undefine_error in result.stderr
    assert "Lab down." not in result.stderr
    expected_domains = {
        "ansible-oracle-lab-superdb1",
        "ansible-oracle-lab-superdb2",
        "ansible-oracle-lab-observer",
    }
    for domain in expected_domains:
        domain_undefines = [call for call in calls if f"undefine {domain} " in call]
        assert len(domain_undefines) == 2
    assert not any(" net-destroy " in call for call in calls)
    assert not any(" net-undefine " in call for call in calls)
    assert "Removing ansible-oracle block from /etc/hosts" not in result.stderr
    assert vm_marker.is_file()
    assert seed_marker.is_file()
    assert vm_dir.is_dir()
    assert seed_dir.is_dir()


@pytest.mark.parametrize("args", [(), ("--purge",)])
def test_lab_down_aborts_on_libvirt_connection_error_before_cleanup(
    tmp_path: Path, args: tuple[str, ...]
):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    state_dir = tmp_path / "lab-state"
    vm_dir = state_dir / "vms"
    seed_dir = state_dir / "seed"
    vm_dir.mkdir(parents=True)
    seed_dir.mkdir()
    vm_marker = vm_dir / "must-survive.qcow2"
    seed_marker = seed_dir / "must-survive.iso"
    vm_marker.write_text("fixture\n", encoding="utf-8")
    seed_marker.write_text("fixture\n", encoding="utf-8")
    virsh_calls = tmp_path / "virsh-calls.log"
    connection_error = "error: failed to connect to libvirt: permission denied"
    write_fake_virsh(
        bin_dir,
        f"""
printf '%s\\n' "$*" >> "${{VIRSH_CALL_LOG}}"
case "${{3:-}}" in
  dominfo)
    printf '%s\\n' '{connection_error}' >&2
    exit 1
    ;;
  *)
    exit 0
    ;;
esac
""",
    )

    result = run_lab_script(
        "lab-down.sh",
        *args,
        env={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "LAB_STATE_DIR": str(state_dir),
            "VIRSH_CALL_LOG": str(virsh_calls),
        },
    )

    calls = virsh_calls.read_text(encoding="utf-8").splitlines()
    assert result.returncode != 0
    assert connection_error in result.stderr
    assert "Removing ansible-oracle block from /etc/hosts" not in result.stderr
    assert not any(
        any(operation in call for operation in ("shutdown", "destroy", "undefine", "net-"))
        for call in calls
    )
    assert vm_marker.is_file()
    assert seed_marker.is_file()
    assert vm_dir.is_dir()
    assert seed_dir.is_dir()


def test_lab_down_purge_force_destroys_before_undefine_and_remove(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    state_dir = tmp_path / "lab-state"
    vm_dir = state_dir / "vms"
    seed_dir = state_dir / "seed"
    vm_dir.mkdir(parents=True)
    seed_dir.mkdir()
    vm_marker = vm_dir / "keep-until-undefine.qcow2"
    seed_marker = seed_dir / "keep-until-undefine.iso"
    vm_marker.write_text("fixture\n", encoding="utf-8")
    seed_marker.write_text("fixture\n", encoding="utf-8")
    virsh_calls = tmp_path / "virsh-calls.log"
    destroyed_domains = tmp_path / "destroyed-domains.log"
    write_fake_virsh(
        bin_dir,
        """
printf '%s\n' "$*" >> "${VIRSH_CALL_LOG}"
case "${3:-}" in
  dominfo)
    exit 0
    ;;
  domstate)
    if [ -f "${DESTROYED_DOMAINS}" ] && grep -Fxq "${4}" "${DESTROYED_DOMAINS}"; then
      printf 'shut off\n'
    else
      printf 'running\n'
    fi
    ;;
  destroy)
    printf '%s\n' "${4}" >> "${DESTROYED_DOMAINS}"
    ;;
  undefine)
    if [ -f "${VM_MARKER}" ] && [ -f "${SEED_MARKER}" ]; then
      printf '%s\n' 'undefine-state-present' >> "${VIRSH_CALL_LOG}"
    else
      printf '%s\n' 'undefine-state-missing' >> "${VIRSH_CALL_LOG}"
    fi
    ;;
  net-info)
    exit 1
    ;;
  *)
    exit 0
    ;;
esac
""",
    )

    result = run_lab_script(
        "lab-down.sh",
        "--purge",
        "--force",
        env={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "LAB_STATE_DIR": str(state_dir),
            "VIRSH_CALL_LOG": str(virsh_calls),
            "DESTROYED_DOMAINS": str(destroyed_domains),
            "VM_MARKER": str(vm_marker),
            "SEED_MARKER": str(seed_marker),
        },
    )

    calls = virsh_calls.read_text(encoding="utf-8").splitlines()
    expected_domains = {
        "ansible-oracle-lab-superdb1",
        "ansible-oracle-lab-superdb2",
        "ansible-oracle-lab-observer",
    }
    destroy_indices = [
        index for index, call in enumerate(calls) if " destroy ansible-oracle-lab-" in call
    ]
    undefine_indices = [
        index for index, call in enumerate(calls) if " undefine ansible-oracle-lab-" in call
    ]

    assert result.returncode == 0, result.stderr
    assert {calls[index].split()[-1] for index in destroy_indices} == expected_domains
    assert len(undefine_indices) == len(expected_domains)
    assert max(destroy_indices) < min(undefine_indices)
    assert calls.count("undefine-state-present") == len(expected_domains)
    assert not any(" shutdown " in call for call in calls)
    assert not vm_dir.exists()
    assert not seed_dir.exists()


def test_prepare_host_fedora_installs_python_for_bootstrap():
    script = (REPO_ROOT / "lab/scripts/prepare-host-fedora.sh").read_text(
        encoding="utf-8"
    )

    assert "has_supported_python" in script
    assert "python3 \\" in script
    assert "python3-pip \\" in script
    assert "python3.12 python3.12-pip" in script
    assert "Python 3.12 or newer is still unavailable" in script


def test_render_config_writes_valid_lab_artifacts(tmp_path: Path):
    key_path = tmp_path / "lab_oracle"
    keygen = subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-f", str(key_path), "-N", ""],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert keygen.returncode == 0, keygen.stderr

    state_dir = tmp_path / "state"
    result = run_lab_script(
        "render-config.sh",
        "--validate",
        env={
            "LAB_STATE_DIR": str(state_dir),
            "ORACLE_LAB_SSH_KEY": str(key_path),
            "SOURCES_DIR": str(tmp_path / "missing-sources"),
        },
    )

    assert result.returncode == 0, result.stderr
    assert (state_dir / "network.xml").is_file()
    assert (state_dir / "vms/superdb1.xml").is_file()
    assert (state_dir / "vms/superdb2.xml").is_file()
    assert (state_dir / "vms/observer.xml").is_file()
    assert (state_dir / "seed/superdb1.iso").is_file()
    user_data = (state_dir / "seed/superdb1-user-data").read_text(encoding="utf-8")
    assert "growpart /dev/vda 4" in user_data
    assert "pvresize /dev/vda4" in user_data
    assert "lvextend -r -l +100%FREE /dev/vg_main/lv_root" in user_data
    assert "99-ansible-oracle-grid-asm.rules" in user_data
    assert "asmadmin" in user_data
    assert 'kernel-uek-modules-$(uname -r)' in user_data
    assert "qemu-guest-agent" in user_data
    assert "enable, --now, qemu-guest-agent" in user_data

    domain_xml = (state_dir / "vms/superdb1.xml").read_text(encoding="utf-8")
    assert "superdb1-grid.qcow2" in domain_xml
    assert "<target dev='vdb' bus='virtio'/>" in domain_xml
    assert "org.qemu.guest_agent.0" in domain_xml
    assert "<controller type='virtio-serial' index='0'/>" in domain_xml
    observer_xml = (state_dir / "vms/observer.xml").read_text(encoding="utf-8")
    assert "observer-grid.qcow2" not in observer_xml
    assert "org.qemu.guest_agent.0" in observer_xml

    iso_listing = subprocess.run(
        ["isoinfo", "-J", "-i", str(state_dir / "seed/superdb1.iso"), "-f"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert iso_listing.returncode == 0, iso_listing.stderr
    assert "/user-data" in iso_listing.stdout
    assert "/meta-data" in iso_listing.stdout


def test_update_hosts_standalone_uses_dedicated_listener_vip():
    result = run_lab_script("update-hosts.sh", "--print")
    script = (REPO_ROOT / "lab/scripts/update-hosts.sh").read_text(encoding="utf-8")

    assert result.returncode == 0
    assert "192.168.87.21  superdb.domain.is superdb" in result.stdout
    assert "192.168.87.11  superdb.domain.is superdb" not in result.stdout
    assert "superdb\\\\.domain\\\\.is" in script
    assert "$0 ~ \"(^|[[:space:]])(\" aliases \")([[:space:]]|$)\" {next}" in script


def test_update_hosts_dataguard_uses_dedicated_listener_vips():
    result = run_lab_script("update-hosts.sh", "--dg", "--print")

    assert result.returncode == 0
    assert "192.168.87.31  superdc1.domain.is superdc1" in result.stdout
    assert "192.168.87.32  superdc2.domain.is superdc2" in result.stdout
    assert "192.168.87.11  superdc1.domain.is" not in result.stdout
    assert "192.168.87.12  superdc2.domain.is" not in result.stdout


def test_update_hosts_multi_mode_adds_extra_listener_vips():
    result = run_lab_script("update-hosts.sh", "--dg", "--multi", "--print")
    script = (REPO_ROOT / "lab/scripts/update-hosts.sh").read_text(
        encoding="utf-8"
    )
    common = (REPO_ROOT / "lab/scripts/lib/common.sh").read_text(encoding="utf-8")

    assert result.returncode == 0
    assert "IP_DUPERDB=\"${LAB_NET_PREFIX}.22\"" in common
    assert "IP_FLUFFDB=\"${LAB_NET_PREFIX}.23\"" in common
    assert "192.168.87.22  duperdb.domain.is duperdb" in result.stdout
    assert "192.168.87.23  fluffdb.domain.is fluffdb" in result.stdout
    assert "duperdb\\\\.domain\\\\.is" in script
    assert "fluffdb\\\\.domain\\\\.is" in script


def test_oracle_linux_image_discovery_selects_latest_ol9_kvm_image():
    result = run_common(
        "discover_oracle_linux_image_url_from_page \"$(cat tests/fixtures/oracle-linux-templates.html)\"",
        {"LAB_OS_VERSION": "9"},
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == (
        "https://yum.oracle.com/templates/OracleLinux/OL9/u7/x86_64/"
        "OL9U7_x86_64-kvm-b289.qcow2"
    )


def test_oracle_linux_image_discovery_selects_ol10_kvm_image():
    result = run_common(
        "discover_oracle_linux_image_url_from_page \"$(cat tests/fixtures/oracle-linux-templates.html)\"",
        {"LAB_OS_VERSION": "10"},
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == (
        "https://yum.oracle.com/templates/OracleLinux/OL10/u1/x86_64/"
        "OL10U1_x86_64-kvm-b291.qcow2"
    )


def test_oracle_linux_image_discovery_returns_empty_string_without_match():
    result = run_common(
        "url=$(discover_oracle_linux_image_url_from_page 'no matching links'); printf '<%s>\\n' \"$url\"",
        {"LAB_OS_VERSION": "9"},
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "<>"


def test_lab_os_support_note_marks_ol9_as_default_path():
    result = run_common("lab_os_support_note", {"LAB_OS_VERSION": "9"})

    assert result.returncode == 0
    assert "Oracle Linux 9 lab OS selected" in result.stderr
    assert "not claimed" not in result.stderr


def test_lab_os_support_note_warns_that_ol10_is_experimental():
    result = run_common("lab_os_support_note", {"LAB_OS_VERSION": "10"})

    assert result.returncode == 0
    assert "LAB_OS_VERSION=10 selected" in result.stderr
    assert "discover/render OL10 KVM images" in result.stderr
    assert "full Oracle Database 19c install proof is not claimed" in result.stderr


def test_lab_os_support_note_warns_on_unknown_os_version():
    result = run_common("lab_os_support_note", {"LAB_OS_VERSION": "11"})

    assert result.returncode == 0
    assert "LAB_OS_VERSION=11 is outside the tested OL9 path" in result.stderr
    assert "Set ORACLE_LINUX_IMAGE_URL explicitly" in result.stderr
