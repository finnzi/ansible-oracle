#!/usr/bin/env bash
# lab/scripts/lab-up.sh
#
# Bring the three-node lab up:
#   1. Stage installers from ~/sources/oracle into ./download (symlinks).
#   2. Build images if missing.
#   3. docker compose up -d.
#   4. Wait for systemd + sshd.
#   5. Generate inventory/hosts.yml from the example.
#   6. Update /etc/hosts on the host with the lab hostnames.

set -euo pipefail
source "$(dirname "$0")/lib/common.sh"

# ── 1. Stage installers ───────────────────────────────────────────────
# The containers bind-mount the host's sources dir directly as /u01/stage
# (read-only), so the multi-GB Oracle zips are never copied. We only need to
# export SOURCES_DIR for docker-compose to interpolate it.
if [ ! -d "${SOURCES_DIR}" ]; then
  warn "${SOURCES_DIR} not found — containers will start but installs will fail."
  warn "Place the Oracle 19c install zips there (see ~/sources/oracle/info.txt)."
  export SOURCES_DIR="/dev/null"
else
  export SOURCES_DIR="${SOURCES_DIR}"
  log "Installer sources: ${SOURCES_DIR} (bind-mounted read-only at /u01/stage)"
fi
# Keep download/.gitkeep so the dir is tracked in git even though it's unused now.
mkdir -p "${DOWNLOAD_DIR}"
touch "${DOWNLOAD_DIR}/.gitkeep"

# ── 2. Build images if missing ────────────────────────────────────────
if ! docker image inspect ansible-oracle/db:ol9 >/dev/null 2>&1; then
  log "DB image missing — building."
  "$(dirname "$0")/build-images.sh"
fi

# ── 3. compose up ─────────────────────────────────────────────────────
log "Starting containers"
dc up -d --no-build

# ── 4. Wait for systemd + sshd ─────────────────────────────────────────
log "Waiting for systemd to settle in the containers"
# Resolve the actual container names from compose (project-prefixed).
declare -A CNAMES
while read -r svc cname; do
  CNAMES["$svc"]="$cname"
done < <(dc ps --format '{{.Service}} {{.Name}}')

for svc in superdb1 superdb2 observer; do
  cname="${CNAMES[$svc]:-}"
  [ -n "$cname" ] || { warn "container for service $svc not found"; continue; }
  tries=0
  until docker exec "${cname}" systemctl is-system-running >/dev/null 2>&1 \
        || [ "${tries}" -ge 60 ]; do
    tries=$((tries+1)); sleep 1
  done
  if [ "${tries}" -ge 60 ]; then
    warn "systemd did not reach a stable state in ${svc} (${cname}) after 60s"
    docker exec "${cname}" systemctl status 2>&1 | tail -20 >&2 || true
  else
    log "${svc} systemd ready"
  fi
done

# ── 5. Generate inventory/hosts.yml ────────────────────────────────────
log "Generating ${INVENTORY_DIR}/hosts.yml"
mkdir -p "${INVENTORY_DIR}"
cp "${INVENTORY_DIR}/hosts.example.yml" "${INVENTORY_DIR}/hosts.yml"

# ── 6. Update /etc/hosts ───────────────────────────────────────────────
log "Updating /etc/hosts (standalone slice: superdb.domain.is -> ${IP_SUPERDB1})"
"$(dirname "$0")/update-hosts.sh"

log "Lab is up. Inventory: ${INVENTORY_DIR}/hosts.yml"
log "Next: ./scripts/bootstrap-venv.sh && source .venv/bin/activate"
log "Then:  ansible-playbook playbooks/site.yml"
