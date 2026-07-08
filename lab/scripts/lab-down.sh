#!/usr/bin/env bash
# lab/scripts/lab-down.sh — stop the KVM/libvirt lab VMs.
# VM disks are NOT removed by default; pass --purge to undefine VMs and delete
# lab/state/vms + lab/state/seed.

set -euo pipefail
source "$(dirname "$0")/lib/common.sh"

PURGE=false
case "${1:-}" in
  --purge) PURGE=true ;;
  "") ;;
  *) die "Unknown option: $1 (use --purge or no option)" ;;
esac

require_cmd virsh

for svc in superdb1 superdb2 observer; do
  name="$(vm_name "${svc}")"
  if virsh_cmd dominfo "${name}" >/dev/null 2>&1; then
    if virsh_cmd domstate "${name}" 2>/dev/null | grep -q running; then
      log "Shutting down ${name}"
      virsh_cmd shutdown "${name}" >/dev/null || true
    fi
    if [ "${PURGE}" = true ]; then
      log "Undefining ${name}"
      virsh_cmd destroy "${name}" >/dev/null 2>&1 || true
      virsh_cmd undefine "${name}" --nvram --remove-all-storage >/dev/null 2>&1 || \
        virsh_cmd undefine "${name}" --nvram >/dev/null 2>&1 || true
    fi
  fi
done

if [ "${PURGE}" = true ]; then
  log "Removing lab VM and seed state"
  rm -rf "${VM_DIR}" "${SEED_DIR}"
fi

if virsh_cmd net-info "${LAB_NETWORK_NAME}" >/dev/null 2>&1 && [ "${PURGE}" = true ]; then
  log "Removing libvirt network ${LAB_NETWORK_NAME}"
  virsh_cmd net-destroy "${LAB_NETWORK_NAME}" >/dev/null 2>&1 || true
  virsh_cmd net-undefine "${LAB_NETWORK_NAME}" >/dev/null 2>&1 || true
fi

# Best-effort: remove our /etc/hosts block (it will be re-added on next lab-up).
"$(dirname "$0")/update-hosts.sh" --clean || true

log "Lab down."
