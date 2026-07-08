"""Unit tests for the KVM lab preflight shell helpers."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_MEDIA = [
    "info.txt",
    "V982063-01-Oracle.19c.Database.Enterprise.Edition.zip",
    "V982064-01-Oracle.19c.Database.Client.zip",
    "V982068-01-Oracle.19c.Grid.Infrastructure.zip",
    "p6880880_190000_Linux-x86-64.zip",
    "p39062931_190000_Linux-x86-64.zip",
    "p39062956_190000_Linux-x86-64.zip",
]


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


def test_required_media_list_is_complete():
    result = run_common("lab_required_media_files")
    inventory_defaults = (REPO_ROOT / "inventory/group_vars/all.yml").read_text(
        encoding="utf-8"
    )
    inventory_media = re.findall(
        r"(?:db_zip|gi_zip|client_zip|opatch_zip|db_ru_zip|gi_ru_zip): \"([^\"]+)\"",
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


def test_prepare_host_fedora_help_is_safe():
    result = run_lab_script("prepare-host-fedora.sh", "--help")

    assert result.returncode == 0, result.stderr
    assert "--skip-package-install" in result.stdout
    assert "--skip-media-stage" in result.stdout


def test_prepare_host_fedora_rejects_unknown_options():
    result = run_lab_script("prepare-host-fedora.sh", "--bogus")

    assert result.returncode == 1
    assert "Unknown option: --bogus" in result.stderr


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

    domain_xml = (state_dir / "vms/superdb1.xml").read_text(encoding="utf-8")
    assert "superdb1-grid.qcow2" in domain_xml
    assert "<target dev='vdb' bus='virtio'/>" in domain_xml
    observer_xml = (state_dir / "vms/observer.xml").read_text(encoding="utf-8")
    assert "observer-grid.qcow2" not in observer_xml

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
