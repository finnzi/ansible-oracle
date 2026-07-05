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

- **Oracle Restart in containers is officially unsupported.** It works for a lab with the privileged+cgroup flags above, but Oracle Support will not bless it. The playbooks degrade gracefully and report Restart as the failing component if `ohasd` won't stabilize — see `tests/test_04_restart.py`.
- **OL10**: the Dockerfiles target Oracle Linux 9 (the tested base). OL10 is on the roadmap; once the 19c preinstall RPM is available for OL10, point `Dockerfile.db` at `oraclelinux:10`.
- The 19.3 base install + DBCA on a container is slow (tens of minutes) and disk-heavy. The test suite uses generous timeouts accordingly.
- Privileged containers can interfere with host cgroup views; run one lab at a time on a host.
