# Status - ansible-oracle

Last updated after the lab migration began.

## Goal

This repo is intended to manage Oracle Database installations, upgrades,
Oracle Restart, Data Guard, Fast-Start Failover observer nodes, and patching.
The test environment is now being moved from Docker containers to KVM VMs after
the container lab proved unsafe and unreliable on the host.
Goal requirement: Data Guard availability mode is Maximum Availability
(`MAXIMUM AVAILABILITY` protection mode).

## Current Lab Direction

The supported lab path is now KVM/libvirt:

- Three VMs: `superdb1`, `superdb2`, and `observer`.
- Fixed libvirt DHCP leases on `192.168.87.0/24`.
- Dedicated listener VIPs on the same lab subnet:
  - `192.168.87.21` for `superdb.domain.is`.
  - `192.168.87.31` for `superdc1.domain.is`.
  - `192.168.87.32` for `superdc2.domain.is`.
- Oracle Linux cloud image backing disks, defaulting to OL9 with `LAB_OS_VERSION`
  available for OL10 experiments.
- Cloud-init seed ISOs for hostnames and root SSH.
- Root disks grow on first boot, and DB VMs get a dedicated `vdb` Grid disk for
  Oracle Restart metadata.
- `~/sources/oracle` mounted read-only at `/u01/stage`.
- Generated `inventory/hosts.yml`.
- `/etc/hosts` block for `superdb.domain.is`, `superdc1.domain.is`,
  `superdc2.domain.is`, and observer hostnames when permissions allow.

## Implemented Pieces

- KVM lab scripts:
  - `lab/scripts/preflight.sh`
  - `lab/scripts/prepare-host-fedora.sh`
  - `lab/scripts/render-config.sh`
  - `lab/scripts/fetch-base-image.sh`
  - `lab/scripts/lab-up.sh`
  - `lab/scripts/lab-down.sh`
  - `lab/scripts/update-hosts.sh`
- SSH-based pytest execution against the primary VM.
- Preflight checks for host tools, libvirt access, SSH key, source media
  readability, and required Oracle installer/patch files.
- Inventory defaults for the KVM fixed IPs.
- Existing Ansible role scaffolding for OS prep, storage, DB home install,
  network/listener, DB create/manage, Restart, Data Guard, observer, service,
  and patching.
- Standby-first patch parser and its unit tests.
- Live KVM lab boot and standalone database slice on this host:
  - `superdb1` primary/standalone DB host.
  - `superdb2` prepared DB host for the future standby.
  - `observer` VM used as the FSFO observer candidate.
  - DB home install with OPatch/RU handling.
  - DBCA-created `super` database under `/super`.
  - Listener and `super_svc` client service reachable from the control host.
  - Oracle Restart/Grid install on `superdb1`, with CSS, listener, database,
    and `super_svc` registered and managed by Restart.
  - Restart ownership is verified by stopping/starting `super` through `srvctl`
    and waiting for SQL readiness.
  - Oracle Restart/Grid install on `superdb2`, with the DB home present and no
    accidental standalone database created.
  - Standby auxiliary preparation on `superdb2`: `initsuper.ora`, matching
    password file, `/etc/oratab` entry, and NOMOUNT instance reachable through
    `super_sby_dgb` for the RMAN duplicate path.
  - Physical standby creation on `superdb2` through RMAN active duplicate from
    `superdb1`, with the standby registered in Oracle Restart as `super_sby`
    with the `LISTENER_SUPER` listener resource.
  - Primary-side Data Guard preparation on `superdb1`: `dg_broker_start=TRUE`,
    `standby_file_management=AUTO`, FAL/DG config parameters set, broker-managed
    `SYNC AFFIRM` transport to `super_sby_dgb`, and standby redo logs created
    under `/super/r01`.
  - Data Guard broker configuration `dg_super`, with protection mode and level
    at `MAXIMUM AVAILABILITY` and the standby open `READ ONLY WITH APPLY`.
  - Manual broker switchover and automatic standby target selection have been
    verified in both directions: `super` -> `super_sby` -> `super`, with the
    resulting standby reopened `READ ONLY WITH APPLY`.
  - Observer-node Oracle Client Administrator home, broker TNS aliases, FSFO
    enablement, and foreground systemd observer ownership are managed by
    `oracle_observer`; DGMGRL FSFO status is verified from the third KVM VM.
  - ARCHIVELOG and FORCE LOGGING enabled.
- Data Guard preparation:
  - `playbooks/05-dataguard.yml` applies Data Guard listener mode before
    primary prep, so `superdb1` binds `superdc1.domain.is` / `192.168.87.31`
    and `superdb2` binds `superdc2.domain.is` / `192.168.87.32`.
  - Per-host instance overrides are wired but remain dormant until
    Data Guard mode is active, preserving standalone behavior.
  - Static `_DGMGRL` listener services, broker TNS aliases, primary
    `local_listener` registration on `superdc1.domain.is`, standby SYSDBA
    connectivity on `super_sby_dgb`, and physical standby role are verified in
    the KVM lab.
- Oracle home patching:
  - `playbooks/07-patch.yml` derives expected DB RU patch IDs from the staged
    patch README metadata, checks OPatch inventory on both DB VMs, and contains
    the in-place OPatch/opatchauto/datapatch apply path for homes missing the
    expected patch.
  - `playbooks/07-patch-grid.yml` derives expected Grid patch IDs from the
    staged GI RU OPatch inventory metadata, checks Grid OPatch inventory on
    both DB VMs, and contains the in-place opatchauto apply path for homes
    missing the expected patch set.
  - `playbooks/07-patch-dual-db.yml` supports DB dual-home mode against an
    existing configured target home: the role verifies/patches the target home,
    compares Restart's registered Oracle home, modifies the Restart
    database/listener home when needed, restarts the database, and runs
    datapatch. The current lab verifies the idempotent current-home no-op path.
  - `playbooks/07-patch-standbyfirst.yml` supports Data Guard standby-first
    patch orchestration for eligible DB patch bundles: precheck README
    eligibility, patch current standby hosts, switchover through broker, then
    patch the old primary as the new standby. The current staged OJVM+RU bundle
    is not standby-first eligible and is rejected before touching DB homes.
  - Brownfield DB homes can be discovered from `/etc/oratab` or supplied via
    `oracle_patch_extra_homes`; brownfield Grid homes can be discovered from
    `/etc/oracle/olr.loc` or supplied via `oracle_patch_extra_grid_homes`.
    Duplicate home paths are deduplicated before inventory/apply.
  - The current lab converges the 19.31 DB RU (`39034528`) as an idempotent
    no-op on both DB homes and the 19.31 GI RU component set as an idempotent
    no-op on both Grid homes.
- Umbrella site orchestration now imports the non-destructive flow through Data
  Guard Maximum Availability, FSFO observer setup, DB/Grid patch inventory, and
  current-home dual-home validation. Standby-first patching remains a dedicated
  opt-in playbook because it can switch broker roles and apply patches.
- Live full `playbooks/site.yml` run verified on the KVM lab on 2026-07-09,
  including Data Guard Maximum Availability, FSFO observer setup, DB/Grid patch
  inventory, current-home dual-home validation, and embedded pytest
  (`97 passed, 6 skipped`).

## Not Yet Proven End To End

- Destructive automatic failover simulation and reinstate workflow.
- Automated staging/install of a new dual-home target before switching.
- Live standby-first patch apply with an actually eligible DB RU.

## Host Findings From This Run

- `virsh` and QEMU are installed.
- `virt-install` and `cloud-localds` are not installed; the lab no longer
  depends on them after switching to direct libvirt XML and `genisoimage`.
- `qemu:///session` can connect, but a session libvirt NAT/bridge network cannot
  start on this host (`Operation not permitted`). The lab therefore targets
  `qemu:///system`.
- `/home/finnur` is private (`0700`), so system QEMU is unlikely to read
  `~/sources/oracle` through a 9p mount. The lab now checks this and asks for a
  libvirt-readable `SOURCES_DIR`.
- The required media files are present under `~/sources/oracle`; `info.txt`
  does not mention `p39062956_190000_Linux-x86-64.zip`, so preflight warns
  about that metadata mismatch.
- `sudo` is not available non-interactively here, so package installation and
  libvirt group/service changes need to be done by the user outside this agent
  session.
- The host had a stale unmarked Docker-era `/etc/hosts` entry for
  `superdb.domain.is` pointing at `172.28.0.11`. `update-hosts.sh` now scrubs
  known lab aliases before writing the KVM block, but applying it still needs
  root or passwordless sudo on the host.

## Useful Commands

```bash
ssh-keygen -t ed25519 -f ~/.ssh/lab_oracle -N ''
./scripts/bootstrap-venv.sh && source .venv/bin/activate
./lab/scripts/lab-up.sh
ansible-playbook playbooks/01-install-grid.yml --limit superdb1 -e oracle_gi_install_enabled=true
ansible-playbook playbooks/site.yml
./scripts/run-tests.sh
```

Set `SOURCES_DIR` if Oracle media is not under `~/sources/oracle`. Set
`ORACLE_LINUX_IMAGE_URL` if Oracle's yum image index cannot be discovered.
