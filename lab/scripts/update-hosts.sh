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
# Uses sudo only if /etc/hosts isn't writable directly.
strip_block() {
  local tmp; tmp="$(mktemp)"
  if [ -w /etc/hosts ]; then
    SUDO=""
  else
    SUDO="sudo"
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

log "Updating /etc/hosts (mode=${MODE})"
# Detect whether we have a working sudo (passwordless) or direct write access.
if [ -w /etc/hosts ]; then
  SUDO=""
elif sudo -n true 2>/dev/null; then
  SUDO="sudo"
else
  # No passwordless sudo and no direct write. Fall back to a transient
  # privileged container to edit the host's /etc/hosts (a standard lab
  # bootstrap trick when the control node lacks passwordless sudo).
  if command -v docker >/dev/null 2>&1; then
    log "No passwordless sudo — using a transient privileged container to edit /etc/hosts"
    block_text="$(block "${MODE}")"
    docker run --rm --privileged -v /etc/hosts:/etc/hosts:rw alpine sh -c "
      awk '/${HOSTS_MARKER_BEGIN}/{f=1;next} /${HOSTS_MARKER_END}/{f=0;next} !f' /etc/hosts > /tmp/h
      cat /tmp/h > /etc/hosts
      printf '%s\n' '$(printf "%s\n" "${block_text}" | sed "s/'/'\\\\''/g")' >> /etc/hosts
    " || warn "docker fallback failed; add this block to /etc/hosts manually:" \
              && block "${MODE}" | sed 's/^/    /' >&2
    exit 0
  fi
  warn "Cannot write /etc/hosts (need root or docker). Add this block manually:"
  block "${MODE}" | sed 's/^/    /' >&2
  exit 0
fi
strip_block
block "${MODE}" | $SUDO tee -a /etc/hosts >/dev/null
log "/etc/hosts updated:"
$SUDO sed -n "/${HOSTS_MARKER_BEGIN}/,/${HOSTS_MARKER_END}/p" /etc/hosts 2>/dev/null | sed 's/^/    /' >&2
