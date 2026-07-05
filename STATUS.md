# Status — ansible-oracle

Snapshot of where this repository stands, what's verified, and the one
environmental blocker. Last updated after commit `f7abeb9`.

## What the repo is for (the goal)

An Ansible repository for managing Oracle 19c databases on Oracle Linux:

1. **Provision databases** — single-instance and Data Guard; Oracle Restart
   (Grid standalone); patching of DB homes and Grid homes; dedicated file
   paths for oracle home / data / archive / flashback / redo; toggles for
   flashback / archivelog / redo; multi-machine standby + a third FSFO
   observer node; automatic + manual switchover; per-node dedicated listener
   VIPs (`<name>db.domain.is` standalone, `<name>dc1`/`<name>dc2` DG);
   standby in READ ONLY WITH APPLY; multiple instances per machine; tunable
   sga/pga; idempotent; Oracle Restart registration; a dedicated client
   service; and a creative test suite (Restart, Dataguard, switchover).
2. **Patching playbooks** — single-home and dual-home (with home switching);
   greenfield + brownfield; standby-first patching auto-detected from the
   patch README; support switching the Oracle home.
3. **Lab** — Docker containers (2 DB + 1 observer), `/etc/hosts`-based name
   resolution (no DNS), per-instance `/<name>/{app,f01,r01,d01,a01}` layout,
   OL9 (and OL10 if supported), filesystem only (no ASM), a `.venv`, and
   scripts to build the containers.

## What's done and verified

**Repo scaffolding** — complete: `ansible.cfg`, `requirements.txt`,
`.ansible-lint`, `.yamllint`, `inventory/` (group_vars + `hosts.example.yml`),
`library/` (3 custom modules + README), `playbooks/` (`site.yml` + 00-07 + 99),
`roles/` (11 roles), `tests/` (conftest + 8 test files), `lab/` (Dockerfiles,
compose, 4 scripts + common.sh), `scripts/` (bootstrap-venv.sh, run-tests.sh),
top-level `README.md`.

**Lab bring-up** — verified live on this host:
- Builds 3 systemd-enabled OL8 containers (2 DB + observer) with fixed IPs.
- `~/sources/oracle` bind-mounted read-only at `/u01/stage` inside containers.
- `/etc/hosts` updated (via a transient privileged container, since the host
  has no passwordless sudo) so `superdb.domain.is` resolves on the host.
- Ansible reaches `superdb1` over SSH with the lab key; systemd is `running`.

**OS prep** — `00-prep-os.yml` converges cleanly on the live lab; **15/15 OS
tests PASS** against the running container (`tests/test_01_os.py`, previously
they skipped). Verified: oracle user/groups, the `/super/{app,d01,a01,f01,r01}`
tree with correct ownership, sysctl (kernel.sem = 1024 32000 100 128),
limits, sudoers, per-instance env fragments.

**Standby-first patch detection** — `library/patch_standbyfirst_info.py` is
**fully implemented and verified against the real staged patches**. It
correctly finds "This patch is Data Guard Standby-First Installable" in the
DB RU (39034528) and GI RU (39036936), and reports both 19.31 combo patches
as overall NOT eligible because OJVM (38906621) is bundled in — exactly
Oracle's rule. **13 unit tests pass** (incl. 2 against the real zips).

**Static gates** — all green: `ansible-lint` EXIT 0; 10/10 playbooks pass
`--syntax-check`; the full pytest run is **32 passed, 18 skipped, 0 failed**
against the live lab.

**Roles** — the slice roles (`oracle_common`, `oracle_storage`,
`oracle_network`, `oracle_db_install`, `oracle_db_manage`,
`oracle_restart_manage`, `oracle_service_manage`) are implemented. The
deferred roles (`oracle_gi_install`, `oracle_dataguard`, `oracle_observer`,
`oracle_patch`) are scaffolded with fixed interfaces.

## The blocker (one environmental conflict)

The Oracle 19.3 **base** software install cannot complete in this lab, and
the reason is a conflict between two hard constraints:

| Need | OL7 | OL8 / OL9 / OL10 |
|---|---|---|
| Oracle 19.3 base install (certified) | ✅ | ❌ needs `-applyRU` |
| systemd in container on this host (cgroup v2) | ❌ | ✅ |
| Oracle Restart (`ohasd`) | ❌ (no systemd) | ✅ |

- **Host is cgroups v2 only** (`stat -fc %T /sys/fs/cgroup` → `cgroup2fs`).
  OL7's systemd (v219, 2015) predates cgroup v2 and cannot manage processes
  in the container — sshd/ohasd never start under it. OL8's systemd (v239)
  supports cgroup v2 and works. So systemd needs OL8+.
- **Oracle 19.3 base (2019) is only certified on OL7.** On OL8 it NPEs in
  `supportedOSCheck` (newer minor version not in the 2019 known-OS list) and,
  after bypassing that with `CV_ASSUME_DISTID=OL7`, its linker fails against
  modern glibc/binutils (`libasmclntsh19.ohso` link error; `bin/oracle` and
  `bin/sqlplus` end up 0 bytes). Oracle's blessed fix is to apply a Release
  Update at install time via `runInstaller -applyRU <19.31 RU>`.
- **`-applyRU` silently exits without applying in this offline lab.** The
  installer's `InstallerPatchJob` writes only "The home patch status is
  clean" to its log and returns rc=255 with empty output. I confirmed this
  with the combo zip, the extracted combo dir, and the extracted inner
  DB-RU dir — all silent. It needs Oracle-Support metadata it can't reach
  offline. (Manual `opatch apply` can't bridge it either — chicken-and-egg:
  the home must be installed/registered before `opatch apply` works, but the
  install can't link without the RU.)

Everything downstream of the binary install is therefore blocked on this lab:
DBCA can't run (no `oracle`/`dbca`/`sqlplus` binaries), so the instance,
listener-via-DBCA, Restart registration, and the client service can't be
exercised live. The roles are written and syntax-valid; they just can't be
driven to completion here.

`tests/test_02_install.py::test_oracle_binary_linked_or_report_gap` and the
test_03 instance tests **detect this gap and skip with the precise reason**
rather than fake a pass.

## How to unblock (pick one)

1. **Reboot the host to cgroup v1** (`systemd.unified_cgroup_hierarchy=0`
   GRUB param, or boot an older kernel). Then OL7's systemd works in the
   container and 19.3 installs cleanly, certified, no applyRU. Switch
   `lab/Dockerfile.db` back to `oraclelinux:7-slim` (the OL7 variant with
   python3.9-from-source is in git history, commit `f7abeb9`~n). Gets tests
   01–04 fully passing.
2. **Pre-patched gold image.** Build the Oracle home ONCE on a transient
   cgroup-v1 container (just to produce linked binaries), export it as a
   tarball under `download/`, then have `oracle_db_install` extract that
   pre-linked home on OL8 instead of running `runInstaller`. Sidesteps both
   the systemd and the applyRU problems. Self-contained and reproducible.
3. **Network access for the lab.** If the lab container can reach Oracle
   Support / the update servers, the installer's `-applyRU` resolves its
   metadata and the OL8 path completes normally. Smallest code change.

## What's not started (out of scope until the install runs)

- Data Guard physical standby, broker config, READ ONLY WITH APPLY, manual
  switchover (`oracle_dataguard` — scaffolded).
- FSFO observer bring-up (`oracle_observer` — scaffolded).
- Patch apply (`oracle_patch` — detection is real; apply is scaffolded).
- Oracle Restart / Grid install (`oracle_gi_install` — scaffolded; the
  `oracle_restart_manage` registration role is implemented but can't be
  exercised until Grid is installed and a DB exists).

These are scaffolded with fixed interfaces and fail loudly only if explicitly
enabled, so they're ready to fill in once the install runs.

## Quick command reference

```bash
./scripts/bootstrap-venv.sh && source .venv/bin/activate
cd lab && ./scripts/build-images.sh && cd ..
export SOURCES_DIR="$HOME/sources/oracle"; ./lab/scripts/lab-up.sh
ansible-playbook -i inventory/hosts.yml playbooks/00-prep-os.yml
ORACLE_TEST_SSH_HOST=ansible-oracle-lab-superdb1-1 ./scripts/run-tests.sh
```

`02-install-dbhome.yml` and everything after it will report the OL8
certification gap described above until one of the unblock options is taken.
