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
#   ./update-hosts.sh --clean   # remove the block entirely
#
# Requires sudo to write /etc/hosts.

set -euo pipefail
source "$(dirname "$0")/lib/common.sh"

MODE="standalone"
case "${1:-}" in
  --dg)    MODE="dataguard" ;;
  --clean) MODE="clean" ;;
  "")      MODE="standalone" ;;
  *) die "Unknown option: $1 (use --dg, --clean, or none)" ;;
esac

# Build the block contents for the requested mode.
block() {
  echo "${HOSTS_MARKER_BEGIN}"
  case "$1" in
    standalone)
      # Vertical slice: a single DB, listener VIP superdb.domain.is
      echo "${IP_SUPERDB1}  superdb1.domain.is superdb1"
      echo "${IP_SUPERDB1}  superdb.domain.is superdb"
      # Short-name aliases the playbooks/tests also use.
      echo "${IP_SUPERDB1}  superdb1"
      echo "${IP_SUPERDB2}  superdb2.domain.is superdb2 superdb2"
      echo "${IP_OBSERVER}  observer.domain.is observer"
      ;;
    dataguard)
      # When DG lands: each node binds its own listener VIP.
      echo "${IP_SUPERDB1}  superdc1.domain.is superdc1 superdb1.domain.is superdb1"
      echo "${IP_SUPERDB2}  superdc2.domain.is superdc2 superdb2.domain.is superdb2"
      echo "${IP_OBSERVER}  observer.domain.is observer"
      ;;
  esac
  echo "${HOSTS_MARKER_END}"
}

# Strip any existing marked block from /etc/hosts on the host.
strip_block() {
  local tmp
  tmp="$(mktemp)"
  if sudo test -f /etc/hosts; then
    sudo awk -v b="${HOSTS_MARKER_BEGIN}" -v e="${HOSTS_MARKER_END}" '
      $0==b {ind=1; next}
      $0==e {ind=0; next}
      !ind {print}
    ' /etc/hosts > "${tmp}" || cp /etc/hosts "${tmp}"
    sudo cp "${tmp}" /etc/hosts
  fi
  rm -f "${tmp}"
}

if [ "${MODE}" = "clean" ]; then
  log "Removing ansible-oracle block from /etc/hosts"
  strip_block
  exit 0
fi

log "Updating /etc/hosts (mode=${MODE}) — may prompt for sudo"
strip_block
block "${MODE}" | sudo tee -a /etc/hosts >/dev/null
log "/etc/hosts updated:"
sudo sed -n "/${HOSTS_MARKER_BEGIN}/,/${HOSTS_MARKER_END}/p" /etc/hosts | sed 's/^/    /' >&2
