# Status - ansible-oracle

Last updated after the lab migration began.

## Goal

This repo is intended to manage Oracle Database installations, upgrades,
Oracle Restart, Data Guard, Fast-Start Failover observer nodes, and patching.
The test environment is now being moved from Docker containers to KVM VMs after
the container lab proved unsafe and unreliable on the host.

## Current Lab Direction

The supported lab path is now KVM/libvirt:

- Three VMs: `superdb1`, `superdb2`, and `observer`.
- Fixed libvirt DHCP leases on `192.168.87.0/24`.
- Oracle Linux cloud image backing disks, defaulting to OL9 with `LAB_OS_VERSION`
  available for OL10 experiments.
- Cloud-init seed ISOs for hostnames and root SSH.
- `~/sources/oracle` mounted read-only at `/u01/stage`.
- Generated `inventory/hosts.yml`.
- `/etc/hosts` block for `superdb.domain.is`, `superdc1.domain.is`,
  `superdc2.domain.is`, and observer hostnames when permissions allow.

## Implemented Pieces

- KVM lab scripts:
  - `lab/scripts/fetch-base-image.sh`
  - `lab/scripts/lab-up.sh`
  - `lab/scripts/lab-down.sh`
  - `lab/scripts/update-hosts.sh`
- SSH-based pytest execution against the primary VM.
- Inventory defaults for the KVM fixed IPs.
- Existing Ansible role scaffolding for OS prep, storage, DB home install,
  network/listener, DB create/manage, Restart, Data Guard, observer, service,
  and patching.
- Standby-first patch parser and its unit tests.

## Not Yet Proven End To End

- A live KVM lab boot on this host.
- Full `playbooks/site.yml` convergence on the VMs.
- Oracle binary install, DBCA instance creation, listener/service checks,
  Restart registration, Data Guard, observer, and patch apply.

## Useful Commands

```bash
ssh-keygen -t ed25519 -f ~/.ssh/lab_oracle -N ''
./scripts/bootstrap-venv.sh && source .venv/bin/activate
./lab/scripts/lab-up.sh
ansible-playbook playbooks/site.yml
./scripts/run-tests.sh
```

Set `SOURCES_DIR` if Oracle media is not under `~/sources/oracle`. Set
`ORACLE_LINUX_IMAGE_URL` if Oracle's yum image index cannot be discovered.
