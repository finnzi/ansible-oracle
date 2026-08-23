# ansible-oracle KVM Lab

The lab provisions three Oracle Linux VMs with libvirt/KVM. It replaces the
old privileged-container approach because Oracle Restart and host cgroups were
not a reliable or safe fit for this repo.

KVM/libvirt is the only supported lab backend in this repository. Docker,
Compose, and Containerfile lab artifacts are intentionally absent.

## Topology

| VM/VIP | IP | Hostname(s) | Purpose |
|---|---:|---|---|
| `ansible-oracle-lab-superdb1` | `192.168.87.11` | `superdb1.domain.is` | Primary or standalone DB host |
| standalone listener VIP | `192.168.87.21` | `superdb.domain.is` | Standalone listener address |
| standalone listener VIP | `192.168.87.22` | `duperdb.domain.is` | Additional standalone listener address |
| standalone listener VIP | `192.168.87.23` | `fluffdb.domain.is` | Additional standalone listener address |
| Data Guard primary listener VIP | `192.168.87.31` | `superdc1.domain.is` | Primary listener address |
| `ansible-oracle-lab-superdb2` | `192.168.87.12` | `superdb2.domain.is` | Data Guard standby host |
| Data Guard standby listener VIP | `192.168.87.32` | `superdc2.domain.is` | Standby listener address |
| `ansible-oracle-lab-observer` | `192.168.87.13` | `observer.domain.is` (`observer1` in Ansible inventory) | FSFO observer |

The libvirt network is `ansible-oracle-lab` on `192.168.87.0/24`, with fixed
DHCP leases for the VM MAC addresses. Listener names use dedicated VIPs that
the `oracle_network` role assigns inside the guest before starting listeners.

## Host Requirements

Install the equivalent of these packages for your distribution:

- `libvirt` / `libvirtd`
- `qemu-img`
- `genisoimage`
- `curl`
- OpenSSH client
- `rsync` if using `prepare-host-fedora.sh` to stage Oracle media

The scripts use `qemu:///system` because the lab needs a bridged/NAT libvirt
network with fixed DHCP leases. Your user must have permission to manage system
libvirt domains and networks. On Fedora, that usually means installing the
libvirt/QEMU packages, starting the modular libvirt sockets, adding your user to
the relevant groups, and then logging out/in:

```bash
./lab/scripts/prepare-host-fedora.sh
```

The manual equivalent for host setup is:

```bash
sudo systemctl enable --now virtlogd.socket virtqemud.socket virtnetworkd.socket virtstoraged.socket
sudo usermod -aG libvirt,kvm "$USER"
```

If the script changes your group membership, log out and back in before running
`lab-up.sh`. For a temporary current-shell refresh, run `newgrp libvirt`.
`id -nG` must show `libvirt` in the current shell before `qemu:///system` is
likely to work without sudo on the default Fedora setup. Verify system libvirt
access with:

```bash
id -nG
virsh -c qemu:///system list --all
```

`qemu:///session` is not the default because session libvirt cannot create the
bridged/NAT lab network on this host without elevated privileges. The lab needs
system libvirt so `superdb1`, `superdb2`, and `observer` can keep stable
addresses that the inventory and `/etc/hosts` block agree on.

## Images

By default the lab uses Oracle Linux 9:

```bash
./lab/scripts/lab-up.sh
```

To try Oracle Linux 10:

```bash
LAB_OS_VERSION=10 ./lab/scripts/lab-up.sh
```

OL10 is treated as an experiment until a full Oracle Database 19c install and
patch proof is run with supported media. The lab can discover and render OL10
KVM images, and preflight/render-config prints an explicit warning that full
Oracle Database 19c proof is still the OL9 path in this repo.

`fetch-base-image.sh` tries to discover the latest x86_64 KVM qcow2 image from
Oracle's Linux cloud images page at
`https://yum.oracle.com/oracle-linux-templates.html`. If Oracle changes that
page, set an explicit URL:

```bash
ORACLE_LINUX_IMAGE_URL=https://yum.oracle.com/templates/OracleLinux/.../image.qcow2 \
  ./lab/scripts/fetch-base-image.sh
```

Downloaded base images are stored under `${LAB_STATE_DIR}/images`. VM overlay
disks and cloud-init seed ISOs are stored under `${LAB_STATE_DIR}`. By default
that is `/var/tmp/ansible-oracle-lab`, because system libvirt runs QEMU as an
unprivileged service user that cannot usually traverse a private home directory.
Override `LAB_STATE_DIR` only with a path system QEMU can traverse and read.

## Oracle Media

Oracle installers and patches are expected under `~/sources/oracle`. Set
`SOURCES_DIR` to override this. The directory is mounted read-only into every VM
at `/u01/stage` through a libvirt filesystem mount.

Preflight requires the lab media files named in `inventory/group_vars/all.yml`:

- `V982063-01-Oracle.19c.Database.Enterprise.Edition.zip`
- `V982064-01-Oracle.19c.Database.Client.zip`
- `V982068-01-Oracle.19c.Grid.Infrastructure.zip`
- `p6880880_190000_Linux-x86-64.zip`
- `p39062931_190000_Linux-x86-64.zip` (19.31 DB RU combo)
- `p39062956_190000_Linux-x86-64.zip` (19.31 GI RU combo)
- `p39618649_190000_Linux-x86-64.zip` (19.32 DB RU combo)
- `p39618711_190000_Linux-x86-64.zip` (19.32 GI RU combo)
- `info.txt`

For OS-only lab work without Oracle media, set `LAB_ALLOW_MISSING_MEDIA=1`.

With system libvirt, the QEMU process usually runs as an unprivileged service
user. Every parent directory must be traversable by that user. Thus, making
`~/sources/oracle` itself world-readable does not help when your home directory
is private (`0700`). Put the media somewhere libvirt can traverse and read.
`/var/lib/libvirt/ansible-oracle-sources` is the recommended permanent location;
a top-level `/sources` also works if its full path is readable, but is less
conventional.

When copying media into `/var/lib/libvirt/ansible-oracle-sources` from a home
directory, fix SELinux labels so guest `oracle` can read the 9p mount:

```bash
cp ~/sources/oracle/* /var/lib/libvirt/ansible-oracle-sources/
chmod a+rX /var/lib/libvirt/ansible-oracle-sources/*
chcon -t virt_var_lib_t /var/lib/libvirt/ansible-oracle-sources/*
# or: restorecon -v /var/lib/libvirt/ansible-oracle-sources/*
```

Files left with `user_home_t` may show mode `755` yet still return
`Permission denied` to non-owner guest users.

For example:

```bash
./lab/scripts/prepare-host-fedora.sh --skip-package-install
export SOURCES_DIR=/var/lib/libvirt/ansible-oracle-sources
./lab/scripts/preflight.sh
./lab/scripts/lab-up.sh
```

If your libvirt setup grants QEMU access another way, set
`LAB_SKIP_SOURCE_ACCESS_CHECK=1`.

## Commands

```bash
# Create the SSH key used by cloud-init for root login.
ssh-keygen -t ed25519 -f ~/.ssh/lab_oracle -N ''

# Fedora host setup, including libvirt/kvm groups and media staging.
./lab/scripts/prepare-host-fedora.sh

# Check host prerequisites without creating networks, disks, or VMs.
./lab/scripts/preflight.sh

# Render and validate libvirt XML/cloud-init artifacts without starting VMs.
./lab/scripts/render-config.sh --validate

# Bring up or start the lab.
./lab/scripts/lab-up.sh

# Run the full install, including Oracle Restart/Grid Infrastructure.
source .venv/bin/activate
ansible-playbook playbooks/site.yml -e oracle_gi_install_enabled=true

# Gracefully stop all VMs concurrently; wait up to the 10-minute global default.
./lab/scripts/lab-down.sh

# Override the global shutdown timeout (seconds; must be a positive integer).
LAB_SHUTDOWN_TIMEOUT_SECONDS=900 ./lab/scripts/lab-down.sh

# Immediately destroy active VMs, without waiting for graceful shutdown.
./lab/scripts/lab-down.sh --force

# Gracefully stop the VMs, then remove VMs, disks, seed ISOs, network, and hosts.
./lab/scripts/lab-down.sh --purge

# Immediately destroy active VMs, then remove the lab state and configuration.
./lab/scripts/lab-down.sh --purge --force

# Switch host aliases from standalone to Data Guard naming.
./lab/scripts/update-hosts.sh --dg

# Include extra standalone listener aliases for multi-instance smoke runs.
./lab/scripts/update-hosts.sh --dg --multi
```

`lab-up.sh` also writes `inventory/hosts.yml` from
`inventory/hosts.example.yml` and writes a marked `/etc/hosts` block if direct
write access or passwordless sudo is available. If not, it prints the block to
add manually.

`lab-down.sh` sends graceful shutdown requests to all active VMs before it
waits. The default is one global 10-minute timeout; set
`LAB_SHUTDOWN_TIMEOUT_SECONDS` to a different positive integer number of
seconds. A timeout or shutdown failure exits nonzero and leaves the VMs, lab
state, network, and `/etc/hosts` untouched. `--force` immediately destroys
active VMs. `--purge` performs the graceful shutdown before removing lab state;
`--purge --force` combines immediate destruction with removal.

On first boot, `lab-up.sh` waits for both SSH and cloud-init. This is expected
to take longer while the guest installs the packages required for the shared
read-only `/u01/stage` mount.

`lab-up.sh` runs the same preflight checks first. Use `preflight.sh` directly
when preparing a host or debugging permissions.

## Notes

- Root disks default to `250G` qcow2 overlays (enough for multi-instance dual
  homes plus RU upgrade workspace). Override with `LAB_ROOT_DISK_SIZE`.
  - **Host (repeatable):** `lab-up.sh` creates disks at that size and enlarges
    existing stopped-domain qcow2 files via `lab_ensure_root_disk_size`.
  - **Guest (repeatable):** `playbooks/00-prep-os.yml` → `oracle_common`
    `grow-root.yml` runs `growpart` on `/dev/vda4`, `pvresize`, `lvextend`, and
    `xfs_growfs` (idempotent). Cloud-init does the same on first boot.
  - If a VM is still running when the host disk is undersized, `lab-up` warns;
    stop the domain, re-run `lab-up`, then `ansible-playbook playbooks/00-prep-os.yml`.
- DB VMs also get a small Grid disk at `vdb` for Oracle Restart metadata.
  Override with `LAB_GRID_DISK_SIZE`.
- DB nodes default to `12288` MiB and 4 vCPUs. Override with
  `LAB_DB_MEMORY_MIB` and `LAB_DB_VCPUS`.
- The observer defaults to `4096` MiB and 2 vCPUs. Override with
  `LAB_OBSERVER_MEMORY_MIB` and `LAB_OBSERVER_VCPUS`.
- Cloud-init creates a persistent `2048` MiB `/swapfile` so Oracle Universal
  Installer and its nested `attachHome` sessions have deterministic prerequisite
  headroom. Override with `LAB_SWAP_SIZE_MIB`.
- Preflight refuses to start the lab when configured guest memory exceeds
  visible host memory. Lower `LAB_DB_MEMORY_MIB` / `LAB_OBSERVER_MEMORY_MIB`,
  or set `LAB_SKIP_RESOURCE_CHECK=1` only when you intentionally allow host
  memory overcommit.
