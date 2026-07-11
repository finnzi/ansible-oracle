# Goal Audit - ansible-oracle

Source requirement: `/home/finnur/.codex/attachments/abed9c0e-80d5-475e-8b53-b82c69966e3f/pasted-text-1.txt`.

This audit records what is proven in the current repository and lab, and what
still depends on outside product support. It does not replace `STATUS.md`; it
is the requirement-by-requirement completion check. `REMAINING_GATES.md` keeps
the repeatable commands for the explicit destructive/safety-gated actions.

Goal update: Data Guard configurations must use Maximum Availability unless a
future task explicitly changes the desired protection mode.

## Status Key

- Proven: implemented and verified by current tests, live KVM evidence, or both.
- Partial: implemented, but not fully proven for every requested operating
  mode.
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
| Automatic failover | Proven | Live OHASD interruption triggered FSFO promotion and auto-reinstate; the confirmed VM-crash rehearsal destroyed the primary VM, promoted `super_sby`, restarted/reinstated `super`, switched back, and validated `READ ONLY WITH APPLY`. |
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
| Standby-first Data Guard patching when release notes allow | Proven | The staged combo is correctly rejected as a whole because of OJVM, while eligible DB RU component `39062931/39034528` was applied live through the confirmed standby-first flow: current standby target home patched/switched, broker switchover, datapatch on promoted primary, old primary patched/switched as new standby, Maximum Availability validated, and post-apply readiness passed. |
| Automatically read standby-first support from release notes | Proven | `library/patch_standbyfirst_info.py` parses README wording and staged zip directories; tests cover eligible, ineligible, corrupt, and current staged media. |
| Switch Oracle homes old-to-new | Proven | Standalone switch/switchback proven live; Data Guard old-to-new switching proven live through confirmed standby-first apply with both `super` and `super_sby` running from `/super/app/oracle/db_home2`. |

## Remaining Completion Gate

No current lab completion gate remains for the requested Oracle 19c / OL9
scope. Oracle Linux 10 remains partial only to the extent that Oracle 19c
certification/support for OL10 is an external product-support boundary.

## Latest Verification

- Final full KVM-backed pytest through `scripts/run-tests.sh` after aligning the
  live post-standby-first inventory and FSFO-safe Restart tests:
  `180 passed, 10 skipped`.
- Confirmed destructive standby-first DB RU component apply on 2026-07-11:
  `scripts/run-standbyfirst-apply.sh --execute --confirm PATCH_STANDBY_FIRST
  --expected-primary super_sby --expected-standby super --no-restore-primary`
  completed with `failed=0` after resuming the intentionally interrupted lab
  state. The play installed/patched/switched `super` to `db_home2`, switched
  over to `super`, ran datapatch and validated `DBA_REGISTRY_SQLPATCH`, verified
  `super_sby` target-home patch inventory, reconciled listeners/broker members,
  validated `MaxAvailability`, and the helper postcheck passed with
  `primary=super`, `standby=super_sby`, and standby `READ ONLY WITH APPLY`.
- FSFO was restored after the manual recovery window: `oracle-fsfo-observer`
  was restarted, broker returned `Configuration Status: SUCCESS`, FSFO is
  enabled in Zero Data Loss Mode, active target is `super_sby`, and observer is
  `ansible_observer`.
- Full safe remaining-gates wrapper after the confirmed standby-first apply:
  `scripts/check-remaining-gates.sh --prove-confirmation-gate` passed the media
  scan, selected-component readiness, missing-confirmation refusal, FSFO
  readiness, and libvirt primary-VM readiness without destructive actions.
- Live component-aware standby-first media scan on 2026-07-10:
  `playbooks/07-patch-standbyfirst-media.yml -e
  oracle_patch_standbyfirst_media_require_eligible=true` reported `eligible=0`
  for whole zips and eligible DB RU component `39062931/39034528`.
- Live component-aware standby-first readiness on 2026-07-10:
  `playbooks/07-patch-standbyfirst.yml -e
  oracle_patch_apply_component_path=39062931/39034528` passed with
  `primary=super`, `standby=super_sby`, and `protection=MaxAvailability`.
- Live non-destructive selected-component role convergence on 2026-07-10:
  `playbooks/07-patch.yml -e
  oracle_patch_apply_component_path=39062931/39034528` derived expected patch
  ID `39034528`, found current homes already patched, and completed with
  `changed=0`.
- Full KVM-backed pytest after component-aware standby-first media support:
  `172 passed, 9 skipped`.
- Live standby-first readiness after adding restore-primary cleanup:
  `playbooks/07-patch-standbyfirst.yml -e
  oracle_patch_apply_component_path=39062931/39034528` completed with
  `changed=0`; the restore phase remained gated because
  `oracle_patch_standbyfirst_execute=false`.
- Full KVM-backed pytest after adding restore-primary cleanup:
  `172 passed, 9 skipped`.
- Live standby-first readiness after adding the execution-plan report:
  `playbooks/07-patch-standbyfirst.yml -e
  oracle_patch_apply_component_path=39062931/39034528` reported
  `current_primary=super`, `current_standby=super_sby`, `protection=MaxAvailability`,
  selected component `39062931/39034528`, and per-host target homes with
  `changed=0`.
- Full KVM-backed pytest after adding the standby-first execution-plan report:
  `172 passed, 9 skipped`.
- Live safety proof for the final standby-first command shape without
  `PATCH_STANDBY_FIRST`: pytest verified the staged-component command with
  `oracle_patch_dual_home_suffix=db_home2`,
  `oracle_patch_standbyfirst_execute=true`, and
  `oracle_patch_standbyfirst_restore_primary=true` refuses before broker
  discovery, target-home installation, patching, switchover, datapatch, or
  restore-primary cleanup.
- Full KVM-backed pytest after adding the final-command missing-confirmation
  safety proof: `173 passed, 9 skipped`.
- Live safe remaining-gates wrapper check after extending
  `scripts/check-remaining-gates.sh`: with `--prove-confirmation-gate`, it ran
  the standby-first media scan, selected-component readiness, final-command
  missing-confirmation refusal, and FSFO readiness with no destructive
  confirmation variables.
- Full KVM-backed pytest after extending the safe remaining-gates wrapper:
  `174 passed, 9 skipped`.
- Repeat confirmed destructive FSFO rehearsal after the safe wrapper extension:
  destroyed the current primary VM, promoted `super_sby`, restarted and
  reinstated `super`, switched back to `super`, and validated the standby as
  `READ ONLY WITH APPLY` with `failed=0`.
- Post-rehearsal safe remaining-gates wrapper check: the media scan examined 6
  staged patch zips, found 2 eligible DB RU components, selected-component
  standby-first readiness still reported `current_primary=super`,
  `current_standby=super_sby`, and `protection=MaxAvailability`, the final
  command shape still refused without confirmation, and FSFO readiness remained
  non-destructive with `changed=0`.
- Full KVM-backed pytest after adding the guarded standby-first apply helper:
  `177 passed, 9 skipped`.
- Live no-restore standby-first missing-confirmation proof after mirroring the
  helper preflight: `scripts/check-remaining-gates.sh --skip-fsfo
  --prove-confirmation-gate --no-standbyfirst-restore-primary` reported
  `restore_original_primary=false`, retained `primary=super`,
  `standby=super_sby`, and `protection=MaxAvailability`, and refused at the
  confirmation gate before install, patch, switchover, datapatch, or restore.
- Live expected-role standby-first preflight proof: with expected
  `primary=super` and `standby=super_sby`, readiness passed and the final
  execute-shaped command still refused without confirmation; with expected
  `primary=not_super`, readiness failed at the expected-primary guard before
  install, patch, switchover, or datapatch.
- Full KVM-backed pytest after adding standby-first expected-role guards:
  `179 passed, 9 skipped`.
- Live safe remaining-gates wrapper check after defaulting expected roles:
  media scan, selected-component readiness, missing-confirmation refusal, and
  FSFO readiness all passed with default expected `primary=super` and
  `standby=super_sby`; no destructive confirmation variables were passed.
- Full KVM-backed pytest after defaulting the aggregate remaining-gates role
  guard: `180 passed, 9 skipped`.
- Live standby-first readiness after adding phase-specific OPatch inventory
  assertions: selected-component readiness still completed with no install,
  patch, switchover, or datapatch work, and the new post-patch inventory
  validation plays were skipped in readiness mode because execution groups were
  not created.
- Full KVM-backed pytest after adding phase-specific standby-first OPatch
  inventory assertions: `180 passed, 9 skipped`.
- Live standby-first readiness after adding the promoted-primary SQL patch
  registry assertion: media scan still reported eligible DB RU components,
  selected-component readiness still reported `current_primary=super`,
  `current_standby=super_sby`, and `protection=MaxAvailability`, the new SQL
  registry validation play was skipped in readiness mode because execution
  groups were not created, and the missing-confirmation proof still refused
  before install, patch, switchover, datapatch, or restore.
- Full KVM-backed pytest after adding the promoted-primary SQL patch registry
  assertion: `180 passed, 9 skipped`.
- Dry-run proof after adding the standby-first helper post-apply readiness
  check: the helper prints safe preflight, confirmed apply, and safe post-apply
  readiness commands; with `--no-restore-primary`, the postcheck expects
  `super_sby` primary and `super` standby.
- Live safe standby-first post-apply readiness command proof: the exact helper
  postcheck command completed with `current_primary=super`,
  `current_standby=super_sby`, `protection=MaxAvailability`, and standby
  `READ ONLY WITH APPLY`; no install, patch, switchover, datapatch, or restore
  tasks ran because execution groups were not created.
- Current full safe remaining-gates wrapper proof: media scan examined six
  staged patch zips and still found two eligible DB RU components, selected
  component readiness reported `super` primary, `super_sby` standby, and
  `MaxAvailability`, the execute-shaped standby-first command refused at the
  missing-confirmation gate, and FSFO/libvirt readiness passed without
  destructive actions.
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
- Live safe remaining-gates wrapper check after adding
  `scripts/check-remaining-gates.sh`: standby-first media scan reported
  `eligible=0`, and FSFO readiness/libvirt checks completed with no destructive
  tasks executed.
- Full KVM-backed pytest after adding the safe remaining-gates wrapper:
  `161 passed, 9 skipped`.
- Full KVM-backed pytest through `scripts/run-tests.sh` after adding full
  three-VM lab defaults and dry-run support: `165 passed, 8 skipped`.
- Full KVM-backed pytest through `scripts/run-tests.sh` after routing
  `playbooks/99-test.yml` through the same wrapper: `164 passed, 9 skipped`.
- Full KVM-backed pytest through `scripts/run-tests.sh` after adding KVM host
  resource preflight: `170 passed, 9 skipped`.
- Full KVM-backed pytest through `scripts/run-tests.sh` after removing stale
  scaffold-era wording from implemented roles and inventory: `171 passed, 9
  skipped`.
- Confirmed destructive FSFO VM-crash rehearsal after hardening the recovery
  path: `virsh destroy` stopped `ansible-oracle-lab-superdb1`, FSFO promoted
  `super_sby`, the playbook restarted and reinstated `super`, waited for FSFO
  synchronization, switched back to `super`, and completed with
  `failed=0`.
- Full KVM-backed pytest through `scripts/run-tests.sh` after the confirmed
  destructive FSFO rehearsal: `171 passed, 9 skipped`.
