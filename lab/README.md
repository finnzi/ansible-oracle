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
- `p39062931_190000_Linux-x86-64.zip`
- `p39062956_190000_Linux-x86-64.zip`
- `info.txt`

For OS-only lab work without Oracle media, set `LAB_ALLOW_MISSING_MEDIA=1`.

With system libvirt, the QEMU process usually runs as an unprivileged service
user. If your home directory is private (`0700`), QEMU may not be able to
traverse `~/sources/oracle`. In that case, put the media somewhere libvirt can
read it and point `SOURCES_DIR` there, for example:

```bash
./lab/scripts/prepare-host-fedora.sh --skip-package-install
SOURCES_DIR=/var/lib/libvirt/ansible-oracle-sources ./lab/scripts/lab-up.sh
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

# Stop the VMs but keep disks.
./lab/scripts/lab-down.sh

# Remove VMs, VM disks, seed ISOs, libvirt network, and /etc/hosts block.
./lab/scripts/lab-down.sh --purge

# Switch host aliases from standalone to Data Guard naming.
./lab/scripts/update-hosts.sh --dg

# Include extra standalone listener aliases for multi-instance smoke runs.
./lab/scripts/update-hosts.sh --dg --multi
```

`lab-up.sh` also writes `inventory/hosts.yml` from
`inventory/hosts.example.yml` and writes a marked `/etc/hosts` block if direct
write access or passwordless sudo is available. If not, it prints the block to
add manually.

`lab-up.sh` runs the same preflight checks first. Use `preflight.sh` directly
when preparing a host or debugging permissions.

## Notes

- Root disks default to `120G` qcow2 overlays. Override with
  `LAB_ROOT_DISK_SIZE`.
- DB VMs also get a small Grid disk at `vdb` for Oracle Restart metadata.
  Override with `LAB_GRID_DISK_SIZE`.
- DB nodes default to `12288` MiB and 4 vCPUs. Override with
  `LAB_DB_MEMORY_MIB` and `LAB_DB_VCPUS`.
- The observer defaults to `4096` MiB and 2 vCPUs. Override with
  `LAB_OBSERVER_MEMORY_MIB` and `LAB_OBSERVER_VCPUS`.
- Preflight refuses to start the lab when configured guest memory exceeds
  visible host memory. Lower `LAB_DB_MEMORY_MIB` / `LAB_OBSERVER_MEMORY_MIB`,
  or set `LAB_SKIP_RESOURCE_CHECK=1` only when you intentionally allow host
  memory overcommit.
