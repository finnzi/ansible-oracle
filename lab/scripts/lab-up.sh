#!/usr/bin/env bash
# lab/scripts/lab-up.sh
#
# Bring the three-node KVM/libvirt lab up:
#   1. Ensure the libvirt network exists with fixed DHCP leases.
#   2. Ensure the OL cloud backing image exists.
#   3. Create/import the three VMs with cloud-init seed ISOs.
#   4. Wait for SSH and cloud-init completion.
#   5. Generate inventory/hosts.yml and update /etc/hosts on the host.

set -euo pipefail
source "$(dirname "$0")/lib/common.sh"

lab_require_preflight
lab_prepare_state_dirs

if [ ! -f "$(ssh_pubkey_file)" ]; then
  die "SSH public key not found: $(ssh_pubkey_file). Run: ssh-keygen -t ed25519 -f $(ssh_key_file) -N ''"
fi

if [ ! -d "${SOURCES_DIR}" ]; then
  warn "${SOURCES_DIR} not found — VMs will start but Oracle installs will fail until sources are staged."
  warn "Place the Oracle 19c install zips there (see ~/sources/oracle/info.txt), or set SOURCES_DIR."
  STAGE_MOUNT_SOURCE="${EMPTY_STAGE_DIR}"
else
  STAGE_MOUNT_SOURCE="${SOURCES_DIR}"
  log "Installer sources: ${SOURCES_DIR} (mounted read-only at /u01/stage)"
fi

if [ ! -f "${BASE_IMAGE}" ]; then
  "$(dirname "$0")/fetch-base-image.sh"
fi

ensure_network() {
  local net_info
  if virsh_cmd net-info "${LAB_NETWORK_NAME}" >/dev/null 2>&1; then
    net_info="$(virsh_cmd net-info "${LAB_NETWORK_NAME}")"
    if ! grep -q "Active:.*yes" <<< "${net_info}"; then
      log "Starting libvirt network ${LAB_NETWORK_NAME}"
      virsh_cmd net-start "${LAB_NETWORK_NAME}" >/dev/null
    fi
    return
  fi

  local net_xml
  log "Defining libvirt network ${LAB_NETWORK_NAME} (${LAB_NET_PREFIX}.0/24)"
  net_xml="$(write_network_xml)"
  virsh_cmd net-define "${net_xml}" >/dev/null
  virsh_cmd net-autostart "${LAB_NETWORK_NAME}" >/dev/null
  virsh_cmd net-start "${LAB_NETWORK_NAME}" >/dev/null
}

ensure_vm() {
  local short="$1" name disk grid_disk seed
  name="$(vm_name "${short}")"
  disk="${VM_DIR}/${short}.qcow2"
  grid_disk="${VM_DIR}/${short}-grid.qcow2"
  seed="${SEED_DIR}/${short}.iso"

  write_seed "${short}"

  if ! [ -f "${disk}" ]; then
    log "Creating ${short} root disk (${LAB_ROOT_DISK_SIZE})"
    qemu-img create -f qcow2 -F qcow2 -b "${BASE_IMAGE}" "${disk}" "${LAB_ROOT_DISK_SIZE}" >/dev/null
  fi

  if vm_has_grid_disk "${short}" && ! [ -f "${grid_disk}" ]; then
    log "Creating ${short} Grid ASM disk (${LAB_GRID_DISK_SIZE})"
    qemu-img create -f qcow2 "${grid_disk}" "${LAB_GRID_DISK_SIZE}" >/dev/null
  fi

  if ! virsh_cmd dominfo "${name}" >/dev/null 2>&1; then
    log "Importing VM ${name}"
    virsh_cmd define "$(write_domain_xml "${short}")" >/dev/null
    virsh_cmd start "${name}" >/dev/null
  elif ! virsh_cmd domstate "${name}" | grep -q running; then
    log "Starting VM ${name}"
    virsh_cmd start "${name}" >/dev/null
  else
    log "VM ${name} already running"
  fi
}

ensure_network

for svc in superdb1 superdb2 observer; do
  ensure_vm "${svc}"
done

log "Waiting for SSH on the lab VMs"
for svc in superdb1 superdb2 observer; do
  wait_for_ssh "$(vm_ip "${svc}")"
  log "${svc} SSH ready"
done

log "Waiting for cloud-init on the lab VMs"
for svc in superdb1 superdb2 observer; do
  wait_for_cloud_init "$(vm_ip "${svc}")"
  log "${svc} cloud-init complete"
done

log "Generating ${INVENTORY_DIR}/hosts.yml"
mkdir -p "${INVENTORY_DIR}"
cp "${INVENTORY_DIR}/hosts.example.yml" "${INVENTORY_DIR}/hosts.yml"

log "Updating /etc/hosts (standalone listener VIP: superdb.domain.is -> ${IP_SUPERDB})"
"$(dirname "$0")/update-hosts.sh"

log "Lab is up. Inventory: ${INVENTORY_DIR}/hosts.yml"
log "Next: ./scripts/bootstrap-venv.sh && source .venv/bin/activate"
log "Then:  ansible-playbook playbooks/site.yml -e oracle_gi_install_enabled=true"
