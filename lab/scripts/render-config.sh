#!/usr/bin/env bash
# lab/scripts/render-config.sh — render KVM lab XML and cloud-init seed ISOs
# without defining libvirt networks or VMs.

set -euo pipefail
source "$(dirname "$0")/lib/common.sh"

VALIDATE=false

case "${1:-}" in
  --validate) VALIDATE=true ;;
  "") ;;
  -h|--help)
    cat <<EOF
Usage: $0 [--validate]

Renders:
  ${LAB_STATE_DIR}/network.xml
  ${VM_DIR}/{superdb1,superdb2,observer}.xml
  ${SEED_DIR}/{superdb1,superdb2,observer}.iso

--validate also runs virt-xml-validate when available.
EOF
    exit 0
    ;;
  *) die "Unknown option: $1" ;;
esac

require_cmd genisoimage
lab_os_support_note
if [ ! -f "$(ssh_pubkey_file)" ]; then
  die "SSH public key not found: $(ssh_pubkey_file). Run: ssh-keygen -t ed25519 -f $(ssh_key_file) -N ''"
fi

lab_render_config
log "Rendered libvirt/cloud-init artifacts under ${LAB_STATE_DIR}"

if [ "${VALIDATE}" = true ]; then
  if ! command -v virt-xml-validate >/dev/null 2>&1; then
    warn "virt-xml-validate not found; skipping XML validation."
    exit 0
  fi
  virt-xml-validate "${LAB_STATE_DIR}/network.xml" network
  for svc in superdb1 superdb2 observer; do
    virt-xml-validate "${VM_DIR}/${svc}.xml" domain
  done
  log "libvirt XML validation passed."
fi
