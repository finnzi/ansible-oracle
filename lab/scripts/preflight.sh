#!/usr/bin/env bash
# lab/scripts/preflight.sh — check whether the host can run the KVM lab.

set -euo pipefail
source "$(dirname "$0")/lib/common.sh"

log "Checking KVM lab prerequisites"
if lab_preflight_all; then
  log "Preflight passed."
else
  die "Preflight failed. Fix the warnings above before running lab-up.sh."
fi
