# Remaining Gates Runbook

The normal KVM lab, Data Guard, observer, patch inventory, standalone dual-home
switchback, standby-first readiness, and staged-media scans are already proven.
Two end-to-end gates remain because they require either new Oracle media or an
explicit destructive lab action.

## 1. Eligible Standby-First Patch Apply

Current state: `/u01/stage` contains no fully Data Guard Standby-First
Installable patch zip. The staged 19.31 OJVM+DB RU bundle is intentionally
rejected because OJVM is not standby-first installable.

After staging a standalone DB RU zip whose README marks every component as Data
Guard Standby-First Installable, run:

```bash
env ANSIBLE_LOCAL_TEMP=/tmp/ansible-local \
  .venv/bin/ansible-playbook -i inventory/hosts.yml \
  playbooks/07-patch-standbyfirst-media.yml \
  -e oracle_patch_standbyfirst_media_require_eligible=true
```

Then run the readiness path without applying anything, using the eligible
`oracle_patch_zip` value printed by the media scan:

```bash
env ANSIBLE_LOCAL_TEMP=/tmp/ansible-local \
  .venv/bin/ansible-playbook -i inventory/hosts.yml \
  playbooks/07-patch-standbyfirst.yml \
  -e oracle_patch_zip=/u01/stage/<eligible-standby-first-db-ru.zip> \
  -e oracle_patch_standbyfirst_require_eligible=false
```

Only after the media scan reports at least one eligible zip and the readiness
path still validates Maximum Availability and `READ ONLY WITH APPLY`, run the
confirmed apply:

```bash
env ANSIBLE_LOCAL_TEMP=/tmp/ansible-local \
  .venv/bin/ansible-playbook -i inventory/hosts.yml \
  playbooks/07-patch-standbyfirst.yml \
  -e oracle_patch_zip=/u01/stage/<eligible-standby-first-db-ru.zip> \
  -e oracle_patch_standbyfirst_execute=true \
  -e oracle_patch_standbyfirst_confirm=PATCH_STANDBY_FIRST
```

Expected safety behavior:

- Without eligible media, `07-patch-standbyfirst-media.yml` fails before any
  database role change or patch apply when
  `oracle_patch_standbyfirst_media_require_eligible=true`.
- Without `oracle_patch_standbyfirst_confirm=PATCH_STANDBY_FIRST`,
  `07-patch-standbyfirst.yml` refuses execution.
- The playbook requires Data Guard broker `MaxAvailability` before role changes.

## 2. Destructive FSFO Failover/Reinstate Rehearsal

Current state: the readiness path and missing-confirmation refusal are proven,
and an OHASD interruption already proved FSFO promotion, auto-reinstate, and
switchback behavior. The dedicated VM-crash rehearsal has not been run because
it intentionally destroys the current primary VM.

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

The destructive rehearsal command is:

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
