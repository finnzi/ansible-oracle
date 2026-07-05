# ansible-oracle

Ansible playbooks and roles for managing Oracle 19c databases on Oracle Linux
9: single-instance and Data Guard configurations, Oracle Restart (Grid
Infrastructure standalone), out-of-place home patching, and a Docker-based lab
to test the whole thing end to end.

## Status: vertical slice

This repository is delivered as a **complete, runnable vertical slice**:

- ✅ **Lab** — three systemd-enabled Oracle Linux 9 containers (2 DB nodes + 1
  observer), fixed IPs, `/etc/hosts` entries, no DNS required.
- ✅ **OS prep** — oracle user/groups, sysctl, limits, the per-instance
  directory tree (`/<inst>/{app,d01,a01,f01,r01}`, `/grid`).
- ✅ **DB software install** — silent out-of-place 19c install.
- ✅ **Instance + listener** — DBCA create, dedicated VIP listener with static
  SID_LIST, runtime params (sga/pga, archivelog, flashback, force logging),
  dedicated file paths for data/archive/flashback/redo.
- ✅ **Client service** — a dedicated `super_svc` service that always points at
  the current primary.
- ✅ **Standby-first patch detection** — `patch_standbyfirst_info` module
  parses the patch README and reports Data Guard Standby-First eligibility
  (the auto-detect-from-release-notes requirement).
- ✅ **Test suite** — pytest, green for the slice (OS, install, instance,
  Restart, parser unit tests).

Scaffolded (interfaces fixed, apply deferred to a later engagement):

- 🟡 **Oracle Restart (Grid) install** — `oracle_gi_install`. Restart
  registration in `oracle_restart_manage` detects absence and degrades
  gracefully; the Restart test skips honestly rather than fakes a pass.
- 🟡 **Data Guard** — `oracle_dataguard` (physical standby, broker, READ ONLY
  WITH APPLY, manual switchover).
- 🟡 **FSFO observer** — `oracle_observer` (client install + dgmgrl START
  OBSERVER IN BACKGROUND under systemd).
- 🟡 **Patch apply** — `oracle_patch` (detection is real; apply is stubbed).

## Quickstart

```bash
# 1. One-time: SSH key so Ansible can reach the containers as root.
ssh-keygen -t ed25519 -f ~/.ssh/lab_oracle -N ''

# 2. Python venv (uses the host's Python 3.14).
./scripts/bootstrap-venv.sh
source .venv/bin/activate

# 3. Bring up the lab (builds images, stages installers from ~/sources/oracle,
#    generates inventory/hosts.yml, updates /etc/hosts).
cd lab && ./scripts/build-images.sh && ./scripts/lab-up.sh && cd ..

# 4. Run the umbrella playbook (prep -> install -> create -> register -> test).
ansible-playbook playbooks/site.yml

# 5. Run the test suite on its own.
./scripts/run-tests.sh
```

## Repository layout

```
lab/              Docker lab (3 OL9 systemd containers) + bring-up scripts
inventory/        group_vars + a generated hosts.yml (gitignored)
playbooks/        site.yml + numbered 00-07 + 99-test
roles/            oracle_common, oracle_storage, oracle_network,
                  oracle_db_install, oracle_db_manage,
                  oracle_restart_manage, oracle_service_manage,
                  oracle_gi_install*, oracle_dataguard*,
                  oracle_observer*, oracle_patch*   (* = scaffolded)
library/          custom modules: patch_standbyfirst_info, oracle_db_facts,
                  oracle_session
tests/            pytest suite (conftest + test_01..07 + parser unit test)
scripts/          bootstrap-venv.sh, run-tests.sh
download/         staged Oracle installers (gitignored; symlinked from ~/sources/oracle)
```

See [`lab/README.md`](lab/README.md) for lab specifics and [`library/README.md`](library/README.md)
for the custom modules.

## How the project's requirements map to the code

| Requirement | Where |
|---|---|
| Single-instance **and** Data Guard | `oracle_db_manage` (single); `oracle_dataguard` (DG, scaffolded) |
| Oracle Restart support | `oracle_gi_install` (install), `oracle_restart_manage` (register) |
| Patch DB homes **and** Grid homes | `oracle_patch` (DB apply real-detection; apply stubbed); GI via same role `oracle_patch_target: grid` |
| Dedicated file paths (home/data/arch/flash/redo) | `inventory/group_vars/all.yml` `oracle_instances[*].dirs`; `oracle_storage`; `oracle_db_manage` DBCA response |
| Flashback/archivelog/redo toggles | `oracle_instances[*].{archivelog,flashback,force_logging}`; reconciled in `oracle_db_manage` |
| DG → multiple machines | `inventory/hosts.example.yml` `[primary]` + `[standby]`; `oracle_dataguard` |
| DG broker (FSFO) third server | `inventory/group_vars/observer.yml`; `oracle_observer` |
| Auto + manual switchover | `oracle_dataguard` `dg_action: switchover` (scaffolded) |
| Dedicated listener IP per node | `oracle_network`; `lab/scripts/update-hosts.sh` (`superdc1`/`superdc2`/`superdb`) |
| Standby READ ONLY WITH APPLY | `inventory/group_vars/standby.yml` `desired_open_mode`; `oracle_dataguard` |
| Standalone dedicated listener IP | `oracle_network` (`superdb.domain.is`) |
| Multiple instances per machine | `oracle_instances` is a list (super, duper, fluff, …); every role loops it |
| Tunable sga/pga + settings | `oracle_instances[*].memory`; `oracle_db_manage` reconciliation |
| Idempotent | every role gathers facts / probes before acting |
| Oracle home paths `/super/app/oracle/db_homeN` | `oracle_instances[*].db_homes` |
| Grid paths `/grid/19c/gi_homeN` | `oracle_instances[*].gi_homes` |
| Register instance with Restart | `oracle_restart_manage` (`srvctl add database/instance/listener`) |
| Dedicated client service | `oracle_service_manage` (`super_svc`) |
| Tests for Restart/DG/switchover | `tests/test_04_restart.py` (green/skips-honestly); `test_05_dataguard.py` (skipped until DG) |
| Patch single + dual home | `oracle_patch` `oracle_patch_mode: inplace\|oop_dual` |
| Greenfield + brownfield | install roles are idempotent; `oracle_db_facts` lets manage roles detect pre-existing DBs |
| Standby-first patching (auto-detect) | `library/patch_standbyfirst_info.py` + unit tests; consumed by `oracle_patch` |
| Switch Oracle homes (dual-home) | `oracle_patch` (scaffolded): `srvctl modify database -oraclehome` |
| Lab in containers | `lab/` |
| `/etc/hosts` updates (no DNS) | `lab/scripts/update-hosts.sh` |
| Per-instance dir layout `/<inst>/{app,f01,r01,d01,a01}` | `oracle_storage`; `inventory/group_vars/all.yml` |
| Oracle Linux 9 (10 on roadmap) | `lab/Dockerfile.db` `FROM oraclelinux:9` |
| No ASM — filesystem only | `oracle_db_manage` `storageType=FS`; no ASM roles |
| `.venv` for Python | `scripts/bootstrap-venv.sh` |
| Scripts to build containers | `lab/scripts/build-images.sh`, `lab-up.sh` |

## Caveats

- Oracle Restart inside privileged Docker containers is a **lab-only
  affordance** and officially unsupported by Oracle. See `lab/README.md`.
- The 19.3 base install + DBCA on a container is slow (tens of minutes); the
  test suite uses generous timeouts.
- OL10 is on the roadmap; the Dockerfiles target OL9 today.

## License

MIT.
