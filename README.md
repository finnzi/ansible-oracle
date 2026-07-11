# ansible-oracle

Ansible playbooks and roles for managing Oracle 19c databases on Oracle Linux:
single-instance and Data Guard configurations, Oracle Restart, Oracle home
patching, and a KVM/libvirt lab for testing the automation end to end.

## Current Status

KVM/libvirt is the supported lab path. The repository has moved away from
privileged containers and now provisions three Oracle Linux cloud-image VMs:

- `superdb1` - primary or standalone DB node
- `superdb2` - Data Guard standby DB node
- `observer` - Fast-Start Failover observer node

Implemented:

- OS prep roles for Oracle users, groups, limits, sysctl, sudoers, and the
  per-instance filesystem layout.
- DB home install, standalone instance creation, listener, and `super_svc`
  service verified in the KVM lab.
- Oracle Restart/Grid install path, Restart registration, systemd OHASD stack
  startup, CSS autostart, and stop/start recovery verified on the KVM primary.
- Restart-managed `super_svc` client service registered with role `PRIMARY` on
  both Data Guard members, running only on the current primary.
- Standby-candidate baseline on `superdb2`: Restart online, DB home present,
  Grid disk owned for ASM metadata, no standalone database created, and a
  NOMOUNT RMAN auxiliary reachable through `super_sby_dgb`.
- Physical standby creation on `superdb2` via RMAN active duplicate, registered
  with Oracle Restart as `super_sby`.
- Data Guard broker configuration `dg_super`, with SYNC transport,
  `MAXIMUM AVAILABILITY` protection mode/protection level, and the standby open
  `READ ONLY WITH APPLY`.
- Goal requirement: Data Guard availability mode is Maximum Availability. All
  Data Guard proof and patching flows should preserve that unless deliberately
  changed by a future task.
- Manual broker switchover and automatic standby target selection, verified by
  switching from `super` to `super_sby` and back while preserving
  `READ ONLY WITH APPLY`.
- Observer-node Oracle Client installation, broker TNS aliases, FSFO enablement,
  and foreground systemd observer ownership verified from the third KVM VM.
- Opt-in FSFO failover/reinstate rehearsal playbook with a safe readiness-only
  default and explicit destructive confirmation gate; the execute-without-
  confirmation path is verified to refuse before `virsh destroy`.
- Live FSFO promotion and auto-reinstate verified during an OHASD recovery
  test: `super_sby` was promoted, `super` rejoined as a synchronized physical
  standby, and broker switchover restored `super` as primary.
- Primary-side Data Guard preparation: broker start enabled, standby file
  management set to `AUTO`, FAL/DG config parameters rendered, and standby
  redo logs placed under `/super/r01`.
- Filesystem-only database-file placement verified in the KVM lab: no database
  file paths are ASM-backed, data/temp files live under `/super/d01`, archive
  destination is `/super/a01`, FRA is `/super/f01`, and online redo members
  live under `/super/r01`.
- Live multi-instance primary host proof: `superdb1` now runs Maximum
  Availability Data Guard primary `super`, standalone `duper` under `/duper`,
  and standalone `fluff` under `/fluff`. `duper` uses `LISTENER_DUPER`,
  `duper_svc`, `duperdb.domain.is` / `192.168.87.22`, and redo under
  `/duper/r01`; `fluff` uses `LISTENER_FLUFF`, `fluff_svc`,
  `fluffdb.domain.is` / `192.168.87.23`, and redo under `/fluff/r01`.
  The smoke create/Register reruns are idempotent.
- Data Guard and patching role interfaces.
- Data Guard prep wiring for dc1/dc2 listener identities, `_DGMGRL` static
  listener services, and broker TNS aliases.
- Dedicated listener VIPs in the KVM lab (`superdb`, `duperdb`, `fluffdb`,
  `superdc1`, `superdc2`) separate from VM management IPs.
- Multi-instance inventory example for `super`, `duper`, and `fluff`, with
  distinct filesystem trees, listener names/ports, services, and host-specific
  Data Guard overrides covered by unit tests.
- Focused multi-instance smoke vars for proving Maximum Availability Data Guard
  `super` plus standalone databases on the same primary host.
- Per-instance database settings: `oracle_instances[*].memory` controls
  `sga_target` / `pga_aggregate_target`, and `oracle_instances[*].parameters`
  applies validated custom `ALTER SYSTEM` settings. The live smoke proof
  verifies distinct `open_cursors` values on `duper` and `fluff`.
- Standby-first patch eligibility parser and dedicated Data Guard standby-first
  orchestration playbook with unit/static coverage.
- DB-home and Grid-home patch inventory and in-place apply paths, plus DB
  dual-home Restart switching with automatic installation of inventory suffix
  and inventory-declared explicit-path target homes before patch/switch.
  `playbooks/07-patch-dual-db-switchback.yml` provides a gated standalone
  rehearsal that switches to an inventory suffix or existing explicit target
  path and back to the actual Restart-registered original home.
  Expected RU IDs are derived from staged patch metadata, OPatch inventory is
  checked on both DB VMs, brownfield DB homes can be discovered from `/etc/oratab`,
  brownfield Grid homes from `/etc/oracle/olr.loc`, and the current 19.31 RU
  convergence plus current-home dual mode are verified as idempotent.
- `playbooks/site.yml` imports the non-destructive umbrella flow through Data
  Guard, observer, DB/Grid patch inventory, and current-home dual-home
  validation. Standby-first patching remains in its dedicated playbook; it runs
  eligibility and broker/read-only readiness checks by default, and the
  install/patch/switchover/datapatch branch requires
  `oracle_patch_standbyfirst_execute=true` plus
  `oracle_patch_standbyfirst_confirm=PATCH_STANDBY_FIRST`.
- SSH-based pytest helpers that run against the KVM lab VMs.

## Remaining Explicit Gates

- Live standby-first patch apply with an eligible DB RU target; the staged
  OJVM+RU bundle is correctly rejected as a whole by the standby-first precheck
  before broker discovery, home installation, patching, switchover, or
  datapatch, while its DB RU component can be selected with
  `oracle_patch_apply_component_path=39062931/39034528`. For an eligible RU,
  the dedicated playbook is readiness-only unless explicitly
  confirmed with `oracle_patch_standbyfirst_execute=true` and
  `oracle_patch_standbyfirst_confirm=PATCH_STANDBY_FIRST`; lab proof runs can
  also set `oracle_patch_standbyfirst_restore_primary=true` to switch back to
  the original primary after patching both sites. The readiness-only
  path has been run live by disabling the eligibility failure while leaving
  execution false; it resolved the current broker roles, preserved Maximum
  Availability, validated the standby as `READ ONLY WITH APPLY`, and made no
  changes. `playbooks/07-patch-standbyfirst-media.yml` scans staged zip media
  and currently reports zero fully eligible zip candidates plus the eligible DB
  RU component inside the staged combo.

See `GOAL_AUDIT.md` for the requirement-by-requirement completion audit and
`REMAINING_GATES.md` for the exact commands behind the remaining explicit
action. To run the safe media scan, selected-component standby-first readiness
check, and proven FSFO readiness regression, use:

```bash
scripts/check-remaining-gates.sh
```

## Quickstart

Install host prerequisites first. Package names vary by distribution, but the
lab expects `virsh`, `qemu-img`, `genisoimage`, `curl`, and a working system
libvirt daemon.

```bash
# One-time: key used for root SSH into the lab VMs.
ssh-keygen -t ed25519 -f ~/.ssh/lab_oracle -N ''

# Optional: pick OL10 instead of OL9.
# export LAB_OS_VERSION=10

# Optional: pin a known Oracle Linux KVM qcow2 image URL.
# export ORACLE_LINUX_IMAGE_URL=https://yum.oracle.com/templates/OracleLinux/...

# Optional: override the libvirt-readable VM state path.
# export LAB_STATE_DIR=/var/tmp/ansible-oracle-lab

# On Fedora, this installs/starts libvirt and stages Oracle media for system QEMU.
# It also installs Python packages for the project venv. If it adds your user to
# libvirt/kvm groups, log out and back in before continuing.
./lab/scripts/prepare-host-fedora.sh

# Manual equivalent for host setup:
# sudo systemctl enable --now virtlogd.socket virtqemud.socket virtnetworkd.socket virtstoraged.socket
# sudo dnf install -y python3 python3-pip
# sudo dnf install -y python3.12 python3.12-pip   # if python3 is older than 3.12
# sudo usermod -aG libvirt,kvm "$USER"
# Then log out and back in before continuing, or run: newgrp libvirt
# Verify with: id -nG
# Verify libvirt access with: virsh -c qemu:///system list --all

# Python 3.12+ venv for Ansible and pytest.
./scripts/bootstrap-venv.sh
source .venv/bin/activate

# Check host prerequisites before creating any lab state.
./lab/scripts/preflight.sh

# Optional: render and validate libvirt XML/cloud-init artifacts offline.
./lab/scripts/render-config.sh --validate

# Bring up the KVM lab. This creates inventory/hosts.yml and updates /etc/hosts
# if the current user can write it directly or via passwordless sudo.
./lab/scripts/lab-up.sh

# Optional: print or apply Data Guard host aliases plus multi-instance listener
# aliases for duper/fluff on the control host.
./lab/scripts/update-hosts.sh --dg --multi --print

# Run the umbrella playbook.
ansible-playbook playbooks/site.yml

# Run pytest against the lab.
./scripts/run-tests.sh
```

Oracle installers and patches are expected under `~/sources/oracle` by default
and are mounted read-only into the VMs at `/u01/stage`. Override with
`SOURCES_DIR=/path/to/oracle/sources`. For OS-only lab work without Oracle
media, set `LAB_ALLOW_MISSING_MEDIA=1`.

## Instance Settings

Each entry in `oracle_instances` can tune memory and additional database
parameters. Numeric and boolean custom values are rendered unquoted; set
`quote: true` only for trusted string values that need an Oracle string literal.

```yaml
oracle_instances:
  - name: duper
    memory:
      sga_target: 1G
      pga_aggregate_target: 512M
    parameters:
      - name: open_cursors
        value: 450
        scope: BOTH
        sid: "*"
```

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
scripts/          bootstrap-venv.sh, run-tests.sh, check-remaining-gates.sh
download/         reserved staging directory; large Oracle media is gitignored
```

See [lab/README.md](lab/README.md) for KVM lab details.

## Requirement Map

| Requirement | Where |
|---|---|
| Single-instance and Data Guard | `oracle_db_manage`; `oracle_dataguard`; FSFO lifecycle in `oracle_observer` |
| Oracle Restart support | `oracle_gi_install`; `oracle_restart_manage`; `tests/test_04_restart.py` |
| Patch DB homes and Grid homes | DB/Grid in-place inventory/apply in `oracle_patch`; DB dual-home target install and Restart switch |
| Reversible standalone DB dual-home switch | `playbooks/07-patch-dual-db-switchback.yml` resolves readiness by default; confirmed execution requires explicit switchback confirmation |
| Dedicated home/data/archive/flashback/redo paths | `inventory/group_vars/all.yml`; `oracle_storage`; DBCA response |
| Flashback/archivelog/redo toggles | `oracle_instances[*]`; `oracle_db_manage` |
| Multi-machine Data Guard plus observer | `inventory/hosts.example.yml`; DG prep in `oracle_network`; DG/observer roles |
| Data Guard availability mode | `oracle_dataguard` sets broker protection mode to Maximum Availability |
| FSFO failover/reinstate rehearsal | `playbooks/08-failover-reinstate.yml` validates readiness by default; destructive VM crash/reinstate requires explicit confirmation |
| Dedicated listener names/IPs | `oracle_network`; `lab/scripts/update-hosts.sh` |
| Multiple instances per host | `oracle_instances` list; `inventory/examples/multi-instance.yml`; `inventory/examples/multi-instance-smoke.yml`; `tests/test_instance_overrides.py`; `tests/test_09_multi_instance.py` |
| Tunable memory/settings | `oracle_instances[*].memory`; `oracle_instances[*].parameters`; `oracle_db_manage` |
| Dedicated client service | `oracle_service_manage` |
| Standby-first patching | Detection and staged-media scan in `library/patch_standbyfirst_info.py`; readiness-first target-home staging and role-change orchestration in `playbooks/07-patch-standbyfirst.yml` with explicit execution confirmation; selectable eligible DB RU components use `oracle_patch_apply_component_path`; optional restore-primary cleanup uses `oracle_patch_standbyfirst_restore_primary`; live eligible-RU apply still pending |
| KVM lab with fixed IPs and no DNS | `lab/scripts/lab-up.sh`; `lab/scripts/update-hosts.sh` |
| Oracle Linux 9 or 10 lab base | `LAB_OS_VERSION` and Oracle Linux cloud images |
| No ASM for database files | DBCA uses `storageType=FS`; `oracle_db_manage` reconciles data/archive/FRA/redo paths; live tests assert no database file path starts with `+` |
| Python venv | `scripts/bootstrap-venv.sh` selects Python 3.12+ and can validate with `--check` |

## License

MIT.
