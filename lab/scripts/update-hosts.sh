#!/usr/bin/env bash
# lab/scripts/update-hosts.sh
#
# Maintain a marked block in the host's /etc/hosts containing the lab
# hostnames. This is what satisfies the "no dedicated DNS for the lab"
# requirement: clients on the host resolve superdb.domain.is,
# superdc1.domain.is, superdc2.domain.is straight from /etc/hosts.
#
#   ./update-hosts.sh           # (re)write the block (standalone slice)
#   ./update-hosts.sh --dg      # switch to Data Guard hostnames
#   ./update-hosts.sh --print   # print the standalone block without writing
#   ./update-hosts.sh --dg --print
#   ./update-hosts.sh --clean   # remove the block entirely
#
# Requires direct write access or passwordless sudo to write /etc/hosts.

set -euo pipefail
source "$(dirname "$0")/lib/common.sh"

MODE="standalone"
PRINT_ONLY=false
for arg in "$@"; do
  case "${arg}" in
    --dg)    MODE="dataguard" ;;
    --clean) MODE="clean" ;;
    --print) PRINT_ONLY=true ;;
    *) die "Unknown option: ${arg} (use --dg, --print, --clean, or none)" ;;
  esac
done

# Build the block contents for the requested mode.
block() {
  echo "${HOSTS_MARKER_BEGIN}"
  case "$1" in
    standalone)
      # Vertical slice: a single DB, listener VIP superdb.domain.is
      echo "${IP_SUPERDB1}  superdb1.domain.is superdb1"
      echo "${IP_SUPERDB}  superdb.domain.is superdb"
      # Short-name aliases the playbooks/tests also use.
      echo "${IP_SUPERDB1}  superdb1"
      echo "${IP_SUPERDB2}  superdb2.domain.is superdb2"
      echo "${IP_OBSERVER}  observer.domain.is observer"
      ;;
    dataguard)
      # When DG lands: each node binds its own listener VIP.
      echo "${IP_SUPERDB1}  superdb1.domain.is superdb1"
      echo "${IP_SUPERDC1}  superdc1.domain.is superdc1"
      echo "${IP_SUPERDB2}  superdb2.domain.is superdb2"
      echo "${IP_SUPERDC2}  superdc2.domain.is superdc2"
      echo "${IP_OBSERVER}  observer.domain.is observer"
      ;;
  esac
  echo "${HOSTS_MARKER_END}"
}

# Strip any existing marked block from /etc/hosts on the host.
# Uses sudo only if /etc/hosts isn't writable directly.
strip_block() {
  local tmp; tmp="$(mktemp)"
  if [ -w /etc/hosts ]; then
    SUDO=""
  elif sudo -n true 2>/dev/null; then
    SUDO="sudo"
  else
    cp /etc/hosts "${tmp}" 2>/dev/null || true
    rm -f "${tmp}"
    return 1
  fi
  if $SUDO test -f /etc/hosts; then
    $SUDO awk -v b="${HOSTS_MARKER_BEGIN}" -v e="${HOSTS_MARKER_END}" '
      $0==b {ind=1; next}
      $0==e {ind=0; next}
      !ind {print}
    ' /etc/hosts > "${tmp}" 2>/dev/null || cp /etc/hosts "${tmp}" 2>/dev/null || true
    $SUDO cp "${tmp}" /etc/hosts 2>/dev/null || true
  fi
  rm -f "${tmp}"
}

if [ "${MODE}" = "clean" ]; then
  log "Removing ansible-oracle block from /etc/hosts"
  strip_block
  exit 0
fi

if $PRINT_ONLY; then
  block "${MODE}"
  exit 0
fi

log "Updating /etc/hosts (mode=${MODE})"
# Detect whether we have a working sudo (passwordless) or direct write access.
if [ -w /etc/hosts ]; then
  SUDO=""
elif sudo -n true 2>/dev/null; then
  SUDO="sudo"
else
  warn "Cannot write /etc/hosts (need root or passwordless sudo). Add this block manually:"
  block "${MODE}" | sed 's/^/    /' >&2
  exit 0
fi
strip_block
block "${MODE}" | $SUDO tee -a /etc/hosts >/dev/null
log "/etc/hosts updated:"
$SUDO sed -n "/${HOSTS_MARKER_BEGIN}/,/${HOSTS_MARKER_END}/p" /etc/hosts 2>/dev/null | sed 's/^/    /' >&2
