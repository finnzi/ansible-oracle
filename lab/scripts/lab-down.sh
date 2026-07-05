#!/usr/bin/env bash
# lab/scripts/lab-down.sh — stop and remove the lab containers.
# Data volumes are NOT removed by default; pass --purge to delete them too.

set -euo pipefail
source "$(dirname "$0")/lib/common.sh"

log "Stopping lab containers"
dc down "$@"

if [ "${1:-}" = "--purge" ] || [ "${2:-}" = "--purge" ]; then
  log "Removing lab volumes (data will be lost)"
  dc down -v
fi

# Best-effort: remove our /etc/hosts block (it will be re-added on next lab-up).
"$(dirname "$0")/update-hosts.sh" --clean || true

log "Lab down."
