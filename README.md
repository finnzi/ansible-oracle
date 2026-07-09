# ansible-oracle

Ansible playbooks and roles for managing Oracle 19c databases on Oracle Linux:
single-instance and Data Guard configurations, Oracle Restart, Oracle home
patching, and a KVM/libvirt lab for testing the automation end to end.

## Current Status

This repository is a vertical slice plus scaffolding. The lab has been moved
away from privileged containers and now provisions three KVM VMs from Oracle
Linux cloud images:

- `superdb1` - primary or standalone DB node
- `superdb2` - future Data Guard standby
- `observer` - Fast-Start Failover observer node

Implemented:

- OS prep roles for Oracle users, groups, limits, sysctl, sudoers, and the
  per-instance filesystem layout.
- DB home install, standalone instance creation, listener, and `super_svc`
  service verified in the KVM lab.
- Oracle Restart/Grid install path, Restart registration, and stop/start recovery
  verified on the KVM primary.
- Restart-managed `super_svc` client service.
- Standby-candidate baseline on `superdb2`: Restart online, DB home present,
  Grid disk owned for ASM metadata, no standalone database created, and a
  NOMOUNT RMAN auxiliary reachable through `super_sby_dgb`.
- Physical standby creation on `superdb2` via RMAN active duplicate, registered
  with Oracle Restart as `super_sby`.
- Data Guard broker configuration `dg_super`, with SYNC transport,
  `MAXIMUM AVAILABILITY` protection mode/protection level, and the standby open
  `READ ONLY WITH APPLY`.
- Goal requirement: Data Guard availability mode is Maximum Availability.
- Manual broker switchover and automatic standby target selection, verified by
  switching from `super` to `super_sby` and back while preserving
  `READ ONLY WITH APPLY`.
- Observer-node Oracle Client installation, broker TNS aliases, FSFO enablement,
  and foreground systemd observer ownership verified from the third KVM VM.
- Primary-side Data Guard preparation: broker start enabled, standby file
  management set to `AUTO`, FAL/DG config parameters rendered, and standby
  redo logs placed under `/super/r01`.
- Data Guard and patching role interfaces.
- Data Guard prep wiring for dc1/dc2 listener identities, `_DGMGRL` static
  listener services, and broker TNS aliases.
- Dedicated listener VIPs in the KVM lab (`superdb`, `superdc1`, `superdc2`)
  separate from VM management IPs.
- Standby-first patch eligibility parser with unit coverage.
- DB-home patch inventory and in-place apply path: expected RU IDs are derived
  from the staged patch README metadata, OPatch inventory is checked on both DB
  VMs, brownfield DB homes can be discovered from `/etc/oratab` or supplied via
  `oracle_patch_extra_homes`, and the current 19.31 RU convergence is verified
  as idempotent.
- SSH-based pytest helpers that run against the KVM lab VMs.

Still scaffolded or not yet proven end to end:

- Destructive automatic failover simulation and reinstate workflow.
- Grid-home patch application and dual-home switch.

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

# Optional: override the libvirt-readable VM state path.
# export LAB_STATE_DIR=/var/tmp/ansible-oracle-lab

# On Fedora, this installs/starts libvirt and stages Oracle media for system QEMU.
# If it adds your user to libvirt/kvm groups, log out and back in before continuing.
./lab/scripts/prepare-host-fedora.sh

# Manual equivalent for host setup:
# sudo systemctl enable --now virtlogd.socket virtqemud.socket virtnetworkd.socket virtstoraged.socket
# sudo usermod -aG libvirt,kvm "$USER"
# Then log out and back in before continuing.

# Check host prerequisites before creating any lab state.
./lab/scripts/preflight.sh

# Optional: render and validate libvirt XML/cloud-init artifacts offline.
./lab/scripts/render-config.sh --validate

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
| Single-instance and Data Guard | `oracle_db_manage`; `oracle_dataguard`; FSFO lifecycle in `oracle_observer` |
| Oracle Restart support | `oracle_gi_install`; `oracle_restart_manage`; `tests/test_04_restart.py` |
| Patch DB homes and Grid homes | DB-home inventory/apply in `oracle_patch`; Grid-home apply remains pending |
| Dedicated home/data/archive/flashback/redo paths | `inventory/group_vars/all.yml`; `oracle_storage`; DBCA response |
| Flashback/archivelog/redo toggles | `oracle_instances[*]`; `oracle_db_manage` |
| Multi-machine Data Guard plus observer | `inventory/hosts.example.yml`; DG prep in `oracle_network`; DG/observer roles |
| Dedicated listener names/IPs | `oracle_network`; `lab/scripts/update-hosts.sh` |
| Multiple instances per host | `oracle_instances` list |
| Tunable memory/settings | `oracle_instances[*].memory`; `oracle_db_manage` |
| Dedicated client service | `oracle_service_manage` |
| Standby-first patch detection | `library/patch_standbyfirst_info.py` |
| KVM lab with fixed IPs and no DNS | `lab/scripts/lab-up.sh`; `lab/scripts/update-hosts.sh` |
| Oracle Linux 9 or 10 lab base | `LAB_OS_VERSION` and Oracle Linux cloud images |
| No ASM for database files | database files use filesystem paths; Grid uses a small lab ASM disk for Oracle Restart metadata |
| Python venv | `scripts/bootstrap-venv.sh` |

## License

MIT.
