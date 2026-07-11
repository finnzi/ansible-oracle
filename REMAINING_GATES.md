# Gated Proofs Runbook

The normal KVM lab, Data Guard, observer, patch inventory, standalone dual-home
switchback, FSFO VM-crash rehearsal, standby-first readiness, staged-media
scans, and confirmed standby-first DB RU component apply are proven. This file
keeps the exact safe checks and opt-in destructive commands for repeating those
proofs.

Run the safe aggregate check at any time:

```bash
scripts/check-remaining-gates.sh
```

That command runs the read-only standby-first media scan, the selected-component
standby-first readiness path with execution-plan output, and the proven
non-destructive FSFO readiness/libvirt regression check. It also requires the
starting broker roles to be `super` primary and `super_sby` standby by default.
It does not pass any destructive execution confirmation variables.

To also prove the final standby-first command shape refuses without the
confirmation token, run:

```bash
scripts/check-remaining-gates.sh --prove-confirmation-gate
```

To run the confirmed staged-component apply through the guarded helper, use:

```bash
scripts/run-standbyfirst-apply.sh \
  --execute \
  --confirm PATCH_STANDBY_FIRST
```

That helper runs the safe standby-first media/readiness/missing-confirmation
preflight first, then passes the final confirmation token to
`playbooks/07-patch-standbyfirst.yml`. Its staged-component defaults are
`oracle_patch_dual_home_suffix=db_home2` and
`oracle_patch_standbyfirst_restore_primary=true`. It also requires the starting
broker roles to be `super` primary and `super_sby` standby by default; override
that only for a deliberate different lab state with `--expected-primary` and
`--expected-standby`. Pass `--no-restore-primary` only when leaving the Data
Guard roles swapped is the intended outcome; the helper mirrors that choice in
the safe preflight proof. After the confirmed apply succeeds, the helper runs
the safe readiness path again as a post-apply check; with `--no-restore-primary`,
that postcheck expects the original standby to be primary. Use
`--skip-postcheck` only if you need to run that final readiness check manually.

## 1. Eligible Standby-First Patch Apply

Current state: `/u01/stage` contains no fully Data Guard Standby-First
Installable patch zip. The staged 19.31 OJVM+DB RU bundle is intentionally
rejected as a whole because OJVM is not standby-first installable, but its DB RU
component `39062931/39034528` is reported as an eligible standby-first DB RU
component. That eligible component has been applied live through the guarded
standby-first helper.

Run the media scan:

```bash
env ANSIBLE_LOCAL_TEMP=/tmp/ansible-local \
  .venv/bin/ansible-playbook -i inventory/hosts.yml \
  playbooks/07-patch-standbyfirst-media.yml \
  -e oracle_patch_standbyfirst_media_require_eligible=true
```

Then run the readiness path without applying anything, using the eligible
`oracle_patch_zip` value printed by the media scan. For a whole eligible zip:

```bash
env ANSIBLE_LOCAL_TEMP=/tmp/ansible-local \
  .venv/bin/ansible-playbook -i inventory/hosts.yml \
  playbooks/07-patch-standbyfirst.yml \
  -e oracle_patch_zip=/u01/stage/<eligible-standby-first-db-ru.zip> \
  -e oracle_patch_standbyfirst_require_eligible=false
```

For the staged 19.31 combo's eligible DB RU component:

```bash
env ANSIBLE_LOCAL_TEMP=/tmp/ansible-local \
  .venv/bin/ansible-playbook -i inventory/hosts.yml \
  playbooks/07-patch-standbyfirst.yml \
  -e oracle_patch_zip=/u01/stage/p39062931_190000_Linux-x86-64.zip \
  -e oracle_patch_apply_component_path=39062931/39034528 \
  -e oracle_patch_standbyfirst_require_eligible=false
```

Only after the media scan reports an eligible zip or DB RU component and the
readiness path still validates Maximum Availability and `READ ONLY WITH APPLY`,
run the confirmed apply. The readiness path prints a standby-first execution
plan showing the current primary, current standby, selected media/component,
target homes, and restore-primary setting before any confirmed apply is run.

For a whole eligible zip:

```bash
env ANSIBLE_LOCAL_TEMP=/tmp/ansible-local \
  .venv/bin/ansible-playbook -i inventory/hosts.yml \
  playbooks/07-patch-standbyfirst.yml \
  -e oracle_patch_zip=/u01/stage/<eligible-standby-first-db-ru.zip> \
  -e oracle_patch_standbyfirst_execute=true \
  -e oracle_patch_standbyfirst_confirm=PATCH_STANDBY_FIRST
```

For the staged 19.31 combo's eligible DB RU component:

```bash
scripts/run-standbyfirst-apply.sh \
  --execute \
  --confirm PATCH_STANDBY_FIRST
```

Proven destructive run: on 2026-07-11 the helper completed a resumed
standby-first apply with `--expected-primary super_sby --expected-standby super
--no-restore-primary`, leaving the intended final lab state as `super` primary
and `super_sby` standby, both on `/super/app/oracle/db_home2`, with
`MaxAvailability`, standby `READ ONLY WITH APPLY`, SQL patch registry proof,
and a successful safe post-apply readiness check.

Expected safety behavior:

- Without an eligible zip or eligible DB RU component,
  `07-patch-standbyfirst-media.yml` fails before any database role change or
  patch apply when
  `oracle_patch_standbyfirst_media_require_eligible=true`.
- Without `oracle_patch_standbyfirst_confirm=PATCH_STANDBY_FIRST`,
  `07-patch-standbyfirst.yml` refuses execution before broker discovery,
  target-home installation, patching, switchover, datapatch, or restore-primary
  cleanup. The exact staged-component command shape is covered by pytest with
  the confirmation token omitted.
- The playbook requires Data Guard broker `MaxAvailability` before role changes.
- The guarded helper also passes expected starting roles, so the apply refuses
  before role changes if broker roles do not match the intended lab state.
- A successful confirmed run must prove phase-specific OPatch inventory on the
  current standby and new standby target homes. SQL patch registry proof must
  also show the promoted primary has every expected DB RU patch ID recorded as
  `SUCCESS` in `DBA_REGISTRY_SQLPATCH` after datapatch.
- With `oracle_patch_standbyfirst_restore_primary=true`, the playbook switches
  back to the original primary after both Data Guard homes are patched and
  validates the original primary plus `READ ONLY WITH APPLY` standby state.

## Proven: Destructive FSFO Failover/Reinstate Rehearsal

Current state: the readiness path, missing-confirmation refusal, and confirmed
VM-crash rehearsal are proven. The confirmed run destroyed
`ansible-oracle-lab-superdb1`, waited for FSFO to promote `super_sby`,
restarted and reinstated `super`, waited for FSFO synchronization, switched back
to `super`, and validated the standby as `READ ONLY WITH APPLY`.

Before the destructive rehearsal, run the readiness path:

```bash
env ANSIBLE_LOCAL_TEMP=/tmp/ansible-local \
  .venv/bin/ansible-playbook -i inventory/hosts.yml \
  playbooks/08-failover-reinstate.yml
```

You can also prove the confirmation gate without destroying the VM:

```bash
env ANSIBLE_LOCAL_TEMP=/tmp/ansible-local \
  .venv/bin/ansible-playbook -i inventory/hosts.yml \
  playbooks/08-failover-reinstate.yml \
  -e oracle_failover_reinstate_execute=true
```

That command must fail before `virsh destroy`.

The proven destructive rehearsal command is:

```bash
env ANSIBLE_LOCAL_TEMP=/tmp/ansible-local \
  .venv/bin/ansible-playbook -i inventory/hosts.yml \
  playbooks/08-failover-reinstate.yml \
  -e oracle_failover_reinstate_execute=true \
  -e oracle_failover_reinstate_confirm=DESTROY_PRIMARY_AND_REINSTATE
```

Expected safety behavior:

- The playbook validates FSFO enabled, `MaxAvailability`, current primary
  `super`, active target `super_sby`, and observer presence first.
- It validates `virsh dominfo` for the primary VM through the configured
  libvirt URI before any `virsh destroy` command can run.
- It refuses to destroy the primary VM unless
  `oracle_failover_reinstate_confirm=DESTROY_PRIMARY_AND_REINSTATE`.
- When confirmed, it destroys the current primary VM, waits for FSFO promotion,
  starts the old primary VM, runs broker reinstate, switches back to `super`,
  and validates the standby as `READ ONLY WITH APPLY`.
