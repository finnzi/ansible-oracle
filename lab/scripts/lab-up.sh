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
mkdir -p "${DOWNLOAD_DIR}"
if [ ! -d "${SOURCES_DIR}" ]; then
  warn "${SOURCES_DIR} not found — containers will start but installs will fail."
  warn "Place the Oracle 19c install zips there (see ~/sources/oracle/info.txt)."
else
  log "Staging installers from ${SOURCES_DIR} into ${DOWNLOAD_DIR}"
  for zip in "${SOURCES_DIR}"/*.zip; do
    [ -e "${zip}" ] || continue
    name="$(basename "${zip}")"
    target="${DOWNLOAD_DIR}/${name}"
    if [ -L "${target}" ]; then rm -f "${target}"; fi
    [ -e "${target}" ] || ln -s "${zip}" "${target}"
  done
fi
# Keep the .gitkeep so download/ is tracked when empty.
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
log "Waiting for systemd to settle in superdb1"
for svc in superdb1 superdb2 observer; do
  ip="IP_${svc^^}"; ip="${!ip}"
  # `docker exec` works once compose marks the container running; sshd comes a
  # few seconds later inside systemd.
  tries=0
  until docker exec "${svc}" systemctl is-system-running >/dev/null 2>&1 \
        || [ "${tries}" -ge 60 ]; do
    tries=$((tries+1)); sleep 1
  done
  if [ "${tries}" -ge 60 ]; then
    warn "systemd did not reach a stable state in ${svc} after 60s"
    docker exec "${svc}" systemctl status 2>&1 | tail -20 >&2 || true
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
