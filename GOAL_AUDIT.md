# Goal Audit - ansible-oracle

Source requirement: `/home/finnur/.codex/attachments/abed9c0e-80d5-475e-8b53-b82c69966e3f/pasted-text-1.txt`.

This audit records what is proven in the current repository and lab, and what
still needs outside input or a deliberately destructive run. It does not replace
`STATUS.md`; it is the requirement-by-requirement completion check.
`REMAINING_GATES.md` has the exact commands for the remaining explicit actions.

Goal update: Data Guard configurations must use Maximum Availability unless a
future task explicitly changes the desired protection mode.

## Status Key

- Proven: implemented and verified by current tests, live KVM evidence, or both.
- Partial: implemented or scaffolded, but not fully proven for every requested
  operating mode.
- External gate: blocked by missing media or host/operator approval.
- Intentional unrun: available, gated, and tested for safety, but not executed
  because it destroys or disrupts live lab state.

## Requirement Matrix

| Requirement | Status | Current Evidence |
|---|---|---|
| Replace unsafe Docker/container lab with KVM/libvirt VMs | Proven | `lab/scripts/lab-up.sh`, direct libvirt XML/cloud-init, live `superdb1`/`superdb2`/`observer` lab, full SSH pytest runs, and a repository contract that forbids Docker/Compose lab artifacts. |
| Two DB VMs plus third observer/broker node | Proven | `inventory/hosts.yml`, `playbooks/site.yml`, observer role tests, and live FSFO observer checks. |
| Oracle Linux 9 cloud-image lab base | Proven | Current live lab runs on OL9 cloud images; `LAB_OS_VERSION` defaults to `9`. |
| Oracle Linux 10 where supported | Partial | `LAB_OS_VERSION=10` image discovery/rendering is tested offline, and preflight/render-config warn that OL10 is experimental; full Oracle 19c OL10 install is not claimed because certification/support depends on Oracle media and release support. |
| Host `/etc/hosts` aliases for lab DNS names | Proven | `lab/scripts/update-hosts.sh`, KVM fixed IPs, and live listener/VIP tests for `superdb`, `superdc1`, `superdc2`, `duperdb`, and `fluffdb`. |
| Databases installed under `/instancename` with `app`, `f01`, `r01`, `d01`, `a01` | Proven | Live `super`, `duper`, and `fluff` placement tests verify data, archive, FRA/flashback, and redo paths. |
| No ASM for database files | Proven | DBCA uses filesystem storage; live tests assert no DB file path starts with `+`. Grid/Restart metadata may use its own disk, but database files are filesystem-backed. |
| Python 3.12+ project venv | Proven | `scripts/bootstrap-venv.sh --check` and bootstrap tests enforce Python 3.12 or newer. |
| Single-instance databases | Proven | Standalone `duper` and `fluff` are live under `/duper` and `/fluff`, managed by Restart and services. |
| Data Guard databases | Proven | Live `super` / `super_sby` physical standby, broker config, SYNC transport, and Maximum Availability. |
| Data Guard availability mode Maximum Availability | Proven | Broker mode/level verified live as `MAXIMUM AVAILABILITY`; site and patch tests pin this requirement. |
| Oracle Restart/Grid support | Proven | Grid install, OHASD/CSS startup recovery, Restart database/listener/service registration, and srvctl stop/start tests. |
| Patch Oracle Database homes | Proven | DB RU inventory/apply path, expected patch derivation, resolved target summaries, and live idempotent 19.31 DB RU convergence. |
| Patch Oracle Grid homes | Proven | GI RU inventory/apply path, expected component derivation, resolved target summaries, and live idempotent 19.31 GI RU convergence. |
| Dedicated home/data/archive/flashback/redo paths | Proven | Inventory/roles plus live SQL/file placement checks. |
| Flashback/archive/redo toggles | Proven | Live `duper` and `fluff` prove different ARCHIVELOG, flashback, and force logging settings with redo under each instance tree. |
| Data Guard multiple machines | Proven | `super` primary on `superdb1`, `super_sby` physical standby on `superdb2`. |
| Third server for automatic failover observer | Proven | Observer VM has Oracle Client, broker aliases, systemd observer ownership, and FSFO enabled. |
| Automatic failover | Partial | Live OHASD interruption triggered FSFO promotion and auto-reinstate, but the dedicated destructive VM-crash rehearsal remains intentionally unrun. |
| Manual switchover | Proven | Broker switchover `super` -> `super_sby` -> `super` verified live. |
| Automatic switchover target selection | Proven | Broker switchover with `oracle_dataguard_switchover_target=auto` selects the current standby, is idempotent when the selected target is already primary, and restores `super` as primary after the proof. |
| Dedicated listener IPs for Data Guard and standalone DBs | Proven | `superdc1`, `superdc2`, `superdb`, `duperdb`, and `fluffdb` mappings/listeners tested. |
| Standby open read-only instead of not open | Proven | Live tests validate `READ ONLY WITH APPLY`. |
| Multiple DB instances per machine (`super`, `duper`, `fluff`) | Proven | Live multi-instance primary host proof with Restart/service ownership. |
| Tunable memory and DB settings | Proven | `oracle_instances[*].memory` drives `sga_target` and `pga_aggregate_target`; `oracle_instances[*].parameters` supports additional validated `ALTER SYSTEM` settings; live `super`, `duper`, and `fluff` tests verify configured values from `v$parameter`. |
| Idempotent playbooks | Proven | Site, create/register smoke, patch, Grid, and switchback paths have live idempotence checks where non-destructive. |
| Oracle DB homes like `/super/app/oracle/db_home1`, `/super/app/oracle/db_home2` | Proven | Current and target homes installed/patched/switched for standalone `fluff`; inventory supports suffix and explicit path homes. |
| Oracle Grid homes like `/grid/19c/gi_home1` | Proven | Grid home installed and patched at `/grid/19c/gi_home1`; brownfield discovery exists. |
| Register each database with Oracle Restart | Proven | Live `srvctl config database` tests verify `super`, `super_sby`, `duper`, and `fluff` registration names, homes, spfiles, roles, start options, services, and instances. |
| Dedicated client service to current primary | Proven | `super_svc` is verified live as running only on the current Data Guard primary before and after manual/automatic switchovers; standalone services are tested for `duper` and `fluff`. |
| Tests for Restart, Data Guard, switchover, patching, lab preflight | Proven | Pytest suite covers OS, install, instance, Restart, Data Guard, observer, patching, failover readiness, multi-instance, and lab tooling. |
| Dedicated patch playbooks | Proven | `07-patch.yml`, `07-patch-grid.yml`, `07-patch-dual-db.yml`, `07-patch-dual-db-switchback.yml`, `07-patch-standbyfirst.yml`, and `07-patch-standbyfirst-media.yml`. |
| Single-home patching | Proven | Current-home DB/Grid patch inventory/apply paths converge idempotently. |
| Dual-home DB patching and Oracle home switching | Proven for standalone | `fluff` live switch to `/fluff/app/oracle/db_home2` and switchback to `/fluff/app/oracle/db_home1`; Data Guard dual-home switches are routed to standby-first orchestration. |
| Greenfield and brownfield patching | Proven for inventory/discovery paths | Inventory-installed homes and Restart-discovered brownfield-style targets are reported with concrete names and home paths in the live readiness run; `/etc/oratab`, `/etc/oracle/olr.loc`, and explicit extra homes are supported. Destructive brownfield execution requires explicit names/mappings. |
| Standby-first Data Guard patching when release notes allow | External gate | Eligibility parser, media scanner, readiness path, confirmation gate, and orchestration are implemented. Current staged media reports `eligible=0`; live eligible-RU apply requires suitable standalone DB RU media. |
| Automatically read standby-first support from release notes | Proven | `library/patch_standbyfirst_info.py` parses README wording and staged zip directories; tests cover eligible, ineligible, corrupt, and current staged media. |
| Switch Oracle homes old-to-new | Proven for standalone, partial for Data Guard | Standalone switch/switchback proven live; Data Guard old-to-new path exists in standby-first playbook but live apply requires eligible media. |

## Remaining Completion Gates

1. Explicit destructive FSFO rehearsal:
   `playbooks/08-failover-reinstate.yml` can crash the primary VM, wait for FSFO
   promotion, reinstate, and switch back, but this branch requires
   `oracle_failover_reinstate_execute=true` and
   `oracle_failover_reinstate_confirm=DESTROY_PRIMARY_AND_REINSTATE`. The
   readiness path and missing-confirmation refusal are proven. The destructive
   VM-crash branch is intentionally unrun until explicitly confirmed by an
   operator.

2. Live eligible standby-first patch apply:
   `playbooks/07-patch-standbyfirst-media.yml` currently reports zero staged
   fully eligible standby-first patch zips. A live apply requires staging a
   standalone DB RU whose README marks every component as Data Guard
   Standby-First Installable, then running the confirmed standby-first path with
   `oracle_patch_standbyfirst_execute=true` and
   `oracle_patch_standbyfirst_confirm=PATCH_STANDBY_FIRST`.

## Latest Verification

- Full KVM-backed pytest after the standby-first staged-media scanner:
  `136 passed, 8 skipped`.
- Full KVM-backed pytest after the FSFO confirmation-gate proof:
  `131 passed, 8 skipped`.
- Full KVM-backed pytest after adding this goal audit:
  `139 passed, 7 skipped`.
- Full KVM-backed pytest after adding the remaining-gates runbook:
  `141 passed, 8 skipped`.
- Full KVM-backed pytest after adding the OL10 support-boundary warning:
  `144 passed, 8 skipped`.
- Full KVM-backed pytest after adding the no-Docker lab artifact guard:
  `145 passed, 8 skipped`.
- Full KVM-backed pytest after adding live memory-parameter assertions:
  `148 passed, 9 skipped`.
- Full KVM-backed pytest after adding live Data Guard service role assertions:
  `149 passed, 9 skipped`.
- Full KVM-backed pytest after adding custom per-instance DB parameters:
  `151 passed, 9 skipped`.
- Full KVM-backed pytest after adding live switchback target summaries:
  `151 passed, 9 skipped`.
- Full KVM-backed pytest after adding live Restart registration-detail checks:
  `155 passed, 9 skipped`.
- Full KVM-backed pytest after adding live patch target summaries:
  `156 passed, 8 skipped`.
- Full KVM-backed pytest after adding explicit automatic switchover audit row:
  `155 passed, 9 skipped`.
- Full KVM-backed pytest after documenting custom DB parameters:
  `156 passed, 9 skipped`.
- Full KVM-backed pytest after tightening libvirt group/session guidance:
  `157 passed, 9 skipped`.
- Full KVM-backed pytest after refreshing current KVM Data Guard lab docs:
  `158 passed, 9 skipped`.
- Full KVM-backed pytest after refreshing supported KVM lab status wording:
  `159 passed, 9 skipped`.
- Full KVM-backed pytest after adding eligible standby-first media command handoff:
  `159 passed, 9 skipped`.
- Full KVM-backed pytest after adding FSFO libvirt primary-VM readiness:
  `159 passed, 9 skipped`.
