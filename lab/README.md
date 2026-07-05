# ansible-oracle lab

A three-node Docker lab for developing and testing the playbooks in this repo.
It exists so the playbooks can be exercised end-to-end against real Oracle
19c binaries without dedicated hardware or a DNS server.

## Nodes

| Service   | Container IP | Hostname(s)                       | Purpose                              |
|-----------|--------------|-----------------------------------|--------------------------------------|
| `superdb1`| 172.28.0.11  | `superdb1.domain.is`, `superdb.domain.is` (standalone VIP) | Primary / standalone DB. **Vertical slice target.** |
| `superdb2`| 172.28.0.12  | `superdb2.domain.is`, `superdc2.domain.is` (DG)            | Reserved: Data Guard standby.        |
| `observer`| 172.28.0.13  | `observer.domain.is`              | Reserved: FSFO broker observer.      |

## How it's put together

- **Base image**: `oraclelinux:9` (full, not slim) for DB nodes; `oraclelinux:9-slim` for the observer.
- **Systemd in a container**: each DB node runs `--privileged` with `/usr/sbin/init` as PID 1 and `/sys/fs/cgroup` mounted. This is what lets Oracle Restart (`ohasd`/`cssd`/`srvctl`) behave faithfully inside a container. **This is a lab-only affordance** — never run privileged containers like this in production.
- **No ASM**: the per-instance tree (`/super/{app,d01,a01,f01,r01}`, `/grid`) is bind-mounted Docker volumes on the filesystem, exactly as the project mandates.
- **Installers** are staged from `~/sources/oracle` into the host-side `../download/` directory (symlinks, not copies — the zips are multi-GB) and bind-mounted read-only into `/u01/stage` inside each container.

## Quickstart

```bash
# One-time: a dedicated SSH key so Ansible can reach the containers as root.
ssh-keygen -t ed25519 -f ~/.ssh/lab_oracle -N ''

# Build + bring up the lab, stage installers, generate inventory, update /etc/hosts.
./scripts/build-images.sh
./scripts/lab-up.sh

# Tear down (keeps data volumes):
./scripts/lab-down.sh
# Tear down AND delete data:
./scripts/lab-down.sh --purge
```

`lab-up.sh` also writes `inventory/hosts.yml` (from `hosts.example.yml`) and a
marked block into the host's `/etc/hosts`. To switch that block between the
standalone (`superdb.domain.is`) and the Data Guard (`superdc1`/`superdc2`)
hostnames, run `./scripts/update-hosts.sh --dg` (or `--clean` to remove).

## Caveats and known constraints

### OS version vs. Oracle 19.3 certification (read this first)

The Oracle 19.3 **base** installer was released in 2019 and is only certified
on Oracle Linux 7. It is **not** certified on OL8.x / OL9 / OL10:

- On those newer releases the installer NPEs in `supportedOSCheck` (their
  minor version isn't in the 2019 known-OS list), and even after bypassing
  that with `CV_ASSUME_DISTID=OL7`, the 19.3 linker fails against modern
  glibc/binutils (`libasmclntsh19.ohso` link error). The Oracle-blessed fix
  is to apply a 19.x Release Update at install time via `runInstaller -applyRU`.

- However, **systemd inside the container requires OL8 or newer** on a host
  that runs **cgroups v2 only** (this host: `stat -fc %T /sys/fs/cgroup` →
  `cgroup2fs`). OL7's systemd (v219, 2015) predates cgroup v2 and cannot
  manage processes on such a host, so sshd/ohasd never start under it. OL8's
  systemd (v239) supports cgroup v2 and works.

This creates a tension:

| Need                    | OL7 | OL8/9/10 |
|-------------------------|-----|----------|
| Oracle 19.3 base install (certified) | ✅ | ❌ (needs `-applyRU`) |
| systemd in container on cgroup-v2 host | ❌ | ✅ |
| Oracle Restart (ohasd)                | ❌ (no systemd) | ✅ |

The lab therefore ships the **OL8** image by default (so systemd and Oracle
Restart work). On OL8 the `oracle_db_install` role invokes the 19.3 installer
with `-applyRU <staged 19.31 RU>` to bridge the certification gap. In an
**offline lab the `-applyRU` path is flaky** — the installer's
`InstallerPatchJob` can exit without applying when it can't reach Oracle
Support metadata, leaving the home's binaries at 0 bytes.

### Resolution paths (pick one)

1. **Run the lab on a cgroup-v1 host** (e.g. an older kernel or `systemd.unified_cgroup_hierarchy=0`): switch `Dockerfile.db` to `FROM oraclelinux:7-slim` (the OL7 variant is kept in git history). 19.3 installs cleanly with no RU.
2. **Stage a pre-patched 19.x gold image** under `download/` and point `oracle_db_install` at it instead of the base zip — the binaries link on OL8 because the RU is already applied.
3. **Provide the lab network access** so the installer's `-applyRU` can resolve the patch metadata from Oracle Support; the OL8 path then completes.

`tests/test_02_install.py::test_oracle_binary_linked_or_report_gap` detects
which case applies and either asserts the binary is linked or skips with the
precise reason — it never fakes a pass.

### Other caveats

- **Oracle Restart in containers is officially unsupported.** It works for a lab with the privileged+cgroup flags above (OL8), but Oracle Support will not bless it. The playbooks degrade gracefully and report Restart as the failing component if `ohasd` won't stabilize — see `tests/test_04_restart.py`.
- The 19.3 base install + DBCA on a container is slow (tens of minutes) and disk-heavy. The test suite uses generous timeouts accordingly.
- Privileged containers can interfere with host cgroup views; run one lab at a time on a host.
