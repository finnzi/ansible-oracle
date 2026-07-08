# ansible-oracle

Ansible playbooks and roles for managing Oracle 19c databases on Oracle Linux:
single-instance and Data Guard configurations, Oracle Restart, out-of-place
home patching, and a KVM/libvirt lab for testing the automation end to end.

## Current Status

This repository is a vertical slice plus scaffolding. The lab has been moved
away from privileged containers and now provisions three KVM VMs from Oracle
Linux cloud images:

- `superdb1` - primary or standalone DB node
- `superdb2` - future Data Guard standby
- `observer` - future Fast-Start Failover observer

Implemented:

- OS prep roles for Oracle users, groups, limits, sysctl, sudoers, and the
  per-instance filesystem layout.
- DB home install, instance, listener, Restart registration, service, Data
  Guard, observer, and patching role interfaces.
- Standby-first patch eligibility parser with unit coverage.
- SSH-based pytest helpers that run against the KVM lab VMs.

Still scaffolded or not yet proven end to end:

- Oracle Restart/Grid installation.
- Data Guard creation, broker configuration, READ ONLY WITH APPLY, and
  switchover.
- FSFO observer installation.
- Actual patch application and dual-home switch.

## Quickstart

Install host prerequisites first. Package names vary by distribution, but the
lab expects `virsh`, `qemu-img`, `genisoimage`, `curl`, and a working system
libvirt daemon.

```bash
# One-time: key used for root SSH into the lab VMs.
ssh-keygen -t ed25519 -f ~/.ssh/lab_oracle -N ''

# Python venv for Ansible and pytest.
./scripts/bootstrap-venv.sh
source .venv/bin/activate

# Optional: pick OL10 instead of OL9.
# export LAB_OS_VERSION=10

# Optional: pin a known Oracle Linux KVM qcow2 image URL.
# export ORACLE_LINUX_IMAGE_URL=https://yum.oracle.com/templates/OracleLinux/...

# Check host prerequisites before creating any lab state.
./lab/scripts/preflight.sh

# Bring up the KVM lab. This creates inventory/hosts.yml and updates /etc/hosts
# if the current user can write it directly or via passwordless sudo.
./lab/scripts/lab-up.sh

# Run the umbrella playbook.
ansible-playbook playbooks/site.yml

# Run pytest against the lab.
./scripts/run-tests.sh
```

Oracle installers and patches are expected under `~/sources/oracle` by default
and are mounted read-only into the VMs at `/u01/stage`. Override with
`SOURCES_DIR=/path/to/oracle/sources`. For OS-only lab work without Oracle
media, set `LAB_ALLOW_MISSING_MEDIA=1`.

## Repository Layout

```text
lab/              KVM/libvirt lab scripts and docs
inventory/        group_vars plus generated hosts.yml
playbooks/        site.yml plus numbered playbooks 00-07 and 99-test
roles/            Oracle OS, storage, install, network, Restart, DG, observer,
                  service, and patch roles
library/          custom modules: patch_standbyfirst_info, oracle_db_facts,
                  oracle_session
tests/            pytest suite
scripts/          bootstrap-venv.sh, run-tests.sh
download/         reserved staging directory; large Oracle media is gitignored
```

See [lab/README.md](lab/README.md) for KVM lab details.

## Requirement Map

| Requirement | Where |
|---|---|
| Single-instance and Data Guard | `oracle_db_manage`; `oracle_dataguard` scaffold |
| Oracle Restart support | `oracle_gi_install`; `oracle_restart_manage` |
| Patch DB homes and Grid homes | `oracle_patch` |
| Dedicated home/data/archive/flashback/redo paths | `inventory/group_vars/all.yml`; `oracle_storage`; DBCA response |
| Flashback/archivelog/redo toggles | `oracle_instances[*]`; `oracle_db_manage` |
| Multi-machine Data Guard plus observer | `inventory/hosts.example.yml`; DG/observer roles |
| Dedicated listener names/IPs | `oracle_network`; `lab/scripts/update-hosts.sh` |
| Multiple instances per host | `oracle_instances` list |
| Tunable memory/settings | `oracle_instances[*].memory`; `oracle_db_manage` |
| Dedicated client service | `oracle_service_manage` |
| Standby-first patch detection | `library/patch_standbyfirst_info.py` |
| KVM lab with fixed IPs and no DNS | `lab/scripts/lab-up.sh`; `lab/scripts/update-hosts.sh` |
| Oracle Linux 9 or 10 lab base | `LAB_OS_VERSION` and Oracle Linux cloud images |
| No ASM | filesystem paths only; no ASM roles |
| Python venv | `scripts/bootstrap-venv.sh` |

## License

MIT.
