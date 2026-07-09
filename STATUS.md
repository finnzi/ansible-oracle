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
- Multi-instance inventory example for `super`, `duper`, and `fluff`, with
  distinct filesystem trees, listener names/ports, services, and host-specific
  Data Guard overrides covered by unit tests.
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
  - Filesystem-only database-file placement verified in the KVM lab: no database
    file paths are ASM-backed, data/temp files live under `/super/d01`, archive
    destination is `/super/a01`, FRA is `/super/f01`, and online redo members
    live under `/super/r01`.
  - Data Guard broker configuration `dg_super`, with protection mode and level
    at `MAXIMUM AVAILABILITY` and the standby open `READ ONLY WITH APPLY`.
  - Manual broker switchover and automatic standby target selection have been
    verified in both directions: `super` -> `super_sby` -> `super`, with the
    resulting standby reopened `READ ONLY WITH APPLY`.
  - Observer-node Oracle Client Administrator home, broker TNS aliases, FSFO
    enablement, and foreground systemd observer ownership are managed by
    `oracle_observer`; DGMGRL FSFO status is verified from the third KVM VM.
  - `playbooks/08-failover-reinstate.yml` provides an opt-in destructive FSFO
    failover/reinstate rehearsal: readiness validation is the default, while
    crashing the current primary VM, waiting for automatic promotion, broker
    reinstate, and switchback require an explicit confirmation variable.
    The readiness-only path has been run live against the KVM lab with
    `changed=0`, and the live readiness test asserts FSFO is enabled,
    protection mode is `MaxAvailability`, the current primary is `super`, the
    active failover target is `super_sby`, and an observer is present.
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
    inventory suffix target, inventory-declared explicit path target, or
    existing brownfield explicit path target. Inventory-backed targets are
    installed before patch/switch; the patch role then verifies/patches the
    target home, compares Restart's registered Oracle home, modifies the
    Restart database/listener home when needed, restarts the database, and runs
    datapatch. The current lab verifies the idempotent current-home no-op path.
  - `playbooks/07-patch-dual-db-switchback.yml` provides a gated standalone
    rehearsal that installs an inventory suffix target or uses an existing
    explicit target path, switches Restart to it, validates the registered
    Oracle home, switches back to the actual Restart-registered original home,
    and validates again. Readiness-only mode can also discover
    Restart-registered databases and de-duplicate them against inventory.
    Destructive execution for discovered-only brownfield databases requires
    explicit Restart database names, explicit listener resource mappings,
    and explicit local SID mappings. By default, the playbook synthesizes a
    minimal installer inventory for discovered targets so it can install the
    target home before patching; operators can disable that and require the
    target home to exist ahead of time. The discovered target home is patched
    through `oracle_patch` extra-home handling before the direct Restart switch.
    Explicit discovered listener mappings are enforced strictly in both switch
    directions, and `datapatch` runs after the switched DB starts with the
    mapped SID.
    Before patching or switching discovered-only targets, the playbook verifies
    the current database reports `PRIMARY|MAXIMUM PERFORMANCE|0|0`, where the
    zeroes are the counts of configured standby archive destinations and Data
    Guard config peers; Data Guard databases must be modeled in inventory and
    patched through standby-first orchestration.
    The safe readiness path, including opt-in Restart discovery, has been run
    live in the current Data Guard lab with `changed=0`, and the live test now
    asserts the current lab reports `0` standalone candidates and `1` Data
    Guard target per DB host. Readiness reporting separates standalone
    candidates from Data Guard targets. Fixture-backed readiness tests also
    verify that explicitly discovered brownfield targets synthesize the
    expected installer inventory without calling `srvctl`, and that fixture
    data is rejected for destructive execution. Fixture entries marked as Data
    Guard are not reported as standalone install candidates.
  - `playbooks/07-patch-standbyfirst.yml` supports Data Guard standby-first
    patch orchestration mechanics for eligible DB patch bundles: precheck
    README eligibility, optional target-home staging on the current standby,
    patch/switch that standby home, validate `MAXIMUM AVAILABILITY` and
    `READ ONLY WITH APPLY`, switchover through broker, then optional target-home
    staging and patch/switch on the old primary as the new standby. The current
    staged OJVM+RU bundle is not standby-first eligible and is rejected before
    broker role discovery, target-home installation, DB-home patching,
    switchover, or datapatch; an eligible live RU apply remains not yet proven.
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

- Live destructive automatic failover simulation and reinstate execution.
- Live creation of multiple database instances on the same DB host.
- Live switch to a newly installed dual-home target before switching back.
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
