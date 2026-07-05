#!/usr/bin/env bash
# lab/scripts/build-images.sh
#
# Build the two lab images (ansible-oracle/db:ol9 and observer:ol9).
# Reads the lab public key from ~/.ssh/lab_oracle.pub if present and injects
# it at build time so Ansible can SSH in as root without a password.

set -euo pipefail
source "$(dirname "$0")/lib/common.sh"

cd "${LAB_DIR}"

PUBKEY=""
if [ -f "${HOME}/.ssh/lab_oracle.pub" ]; then
  PUBKEY="$(cat "${HOME}/.ssh/lab_oracle.pub")"
  log "Injecting lab pubkey from ~/.ssh/lab_oracle.pub"
else
  warn "~/.ssh/lab_oracle.pub not found; containers will be built without a pre-seeded key."
  warn "Run ssh-keygen -t ed25519 -f ~/.ssh/lab_oracle -N '' first, or pass nothing to use password SSH."
fi

log "Building ansible-oracle/db:ol9 (Oracle Linux 9 + systemd + preinstall)"
docker build \
  --build-arg "LAB_PUBKEY=${PUBKEY}" \
  -t ansible-oracle/db:ol9 \
  -f Dockerfile.db .

log "Building ansible-oracle/observer:ol9"
docker build \
  --build-arg "LAB_PUBKEY=${PUBKEY}" \
  -t ansible-oracle/observer:ol9 \
  -f Dockerfile.observer .

log "Images built."
