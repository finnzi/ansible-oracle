# Remaining Gates Runbook

The normal KVM lab, Data Guard, observer, patch inventory, standalone dual-home
switchback, FSFO VM-crash rehearsal, standby-first readiness, and staged-media
scans are already proven. One end-to-end gate remains: the confirmed
standby-first apply has not yet been run against an eligible target.

Run the safe aggregate check at any time:

```bash
scripts/check-remaining-gates.sh
```

That command runs the read-only standby-first media scan and keeps the proven
non-destructive FSFO readiness/libvirt regression check available. It does not
pass any destructive execution confirmation variables.

## 1. Eligible Standby-First Patch Apply

Current state: `/u01/stage` contains no fully Data Guard Standby-First
Installable patch zip. The staged 19.31 OJVM+DB RU bundle is intentionally
rejected as a whole because OJVM is not standby-first installable, but its DB RU
component `39062931/39034528` is reported as an eligible standby-first DB RU
component.

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
run the confirmed apply. For a whole eligible zip:

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
env ANSIBLE_LOCAL_TEMP=/tmp/ansible-local \
  .venv/bin/ansible-playbook -i inventory/hosts.yml \
  playbooks/07-patch-standbyfirst.yml \
  -e oracle_patch_zip=/u01/stage/p39062931_190000_Linux-x86-64.zip \
  -e oracle_patch_apply_component_path=39062931/39034528 \
  -e oracle_patch_standbyfirst_execute=true \
  -e oracle_patch_standbyfirst_confirm=PATCH_STANDBY_FIRST
```

Expected safety behavior:

- Without an eligible zip or eligible DB RU component,
  `07-patch-standbyfirst-media.yml` fails before any database role change or
  patch apply when
  `oracle_patch_standbyfirst_media_require_eligible=true`.
- Without `oracle_patch_standbyfirst_confirm=PATCH_STANDBY_FIRST`,
  `07-patch-standbyfirst.yml` refuses execution.
- The playbook requires Data Guard broker `MaxAvailability` before role changes.

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
