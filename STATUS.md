# Status - ansible-oracle

Last updated after the lab migration began.

## Goal

This repo is intended to manage Oracle Database installations, upgrades,
Oracle Restart, Data Guard, Fast-Start Failover observer nodes, and patching.
The test environment is now being moved from Docker containers to KVM VMs after
the container lab proved unsafe and unreliable on the host.
Data Guard configurations must use MAXIMUM AVAILABILITY protection mode.

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
  - `observer` VM reserved for FSFO observer work.
  - DB home install with OPatch/RU handling.
  - DBCA-created `super` database under `/super`.
  - Listener and `super_svc` client service reachable from the control host.
  - Oracle Restart/Grid install on `superdb1`, with CSS, listener, database,
    and `super_svc` registered and managed by Restart.
  - Restart ownership is verified by stopping/starting `super` through `srvctl`
    and waiting for SQL readiness.
  - Oracle Restart/Grid install on `superdb2`, with the DB home present and no
    accidental standalone database created.
  - ARCHIVELOG and FORCE LOGGING enabled.
- Data Guard preparation:
  - Primary/standby listener aliases `superdc1.domain.is` and
    `superdc2.domain.is` are represented in lab host maps with dedicated VIPs.
  - Per-host instance overrides are wired but remain dormant until
    `dataguard: true`, preserving standalone behavior.
  - Static `_DGMGRL` listener service and broker TNS alias rendering are ready
    for the physical standby/broker slice.

## Not Yet Proven End To End

- Full `playbooks/site.yml` including Data Guard/observer/patch stages.
- Physical standby creation, Data Guard broker configuration, MAXIMUM
  AVAILABILITY enforcement, read-only apply, switchover, and FSFO.
- Actual patch apply and dual-home switch.

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
