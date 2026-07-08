#!/usr/bin/env bash
# lab/scripts/lab-up.sh
#
# Bring the three-node KVM/libvirt lab up:
#   1. Ensure the libvirt network exists with fixed DHCP leases.
#   2. Ensure the OL cloud backing image exists.
#   3. Create/import the three VMs with cloud-init seed ISOs.
#   4. Wait for SSH.
#   5. Generate inventory/hosts.yml and update /etc/hosts on the host.

set -euo pipefail
source "$(dirname "$0")/lib/common.sh"

require_cmd virsh
require_cmd virt-install
require_cmd qemu-img
require_cmd cloud-localds

mkdir -p "${IMAGE_DIR}" "${VM_DIR}" "${SEED_DIR}" "${EMPTY_STAGE_DIR}" "${DOWNLOAD_DIR}"
touch "${DOWNLOAD_DIR}/.gitkeep"

if [ ! -f "$(ssh_pubkey_file)" ]; then
  die "SSH public key not found: $(ssh_pubkey_file). Run: ssh-keygen -t ed25519 -f $(ssh_key_file) -N ''"
fi
LAB_PUBKEY="$(cat "$(ssh_pubkey_file)")"

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
  if virsh_cmd net-info "${LAB_NETWORK_NAME}" >/dev/null 2>&1; then
    if ! virsh_cmd net-info "${LAB_NETWORK_NAME}" | grep -q "Active:.*yes"; then
      log "Starting libvirt network ${LAB_NETWORK_NAME}"
      virsh_cmd net-start "${LAB_NETWORK_NAME}" >/dev/null
    fi
    return
  fi

  local net_xml="${LAB_STATE_DIR}/network.xml"
  log "Defining libvirt network ${LAB_NETWORK_NAME} (${LAB_NET_PREFIX}.0/24)"
  cat > "${net_xml}" <<EOF
<network>
  <name>${LAB_NETWORK_NAME}</name>
  <bridge name='${LAB_BRIDGE_NAME}' stp='on' delay='0'/>
  <forward mode='nat'/>
  <domain name='${LAB_DOMAIN}' localOnly='yes'/>
  <ip address='${LAB_NET_PREFIX}.1' netmask='255.255.255.0'>
    <dhcp>
      <range start='${LAB_NET_PREFIX}.100' end='${LAB_NET_PREFIX}.254'/>
      <host mac='$(vm_mac superdb1)' name='superdb1' ip='${IP_SUPERDB1}'/>
      <host mac='$(vm_mac superdb2)' name='superdb2' ip='${IP_SUPERDB2}'/>
      <host mac='$(vm_mac observer)' name='observer' ip='${IP_OBSERVER}'/>
    </dhcp>
  </ip>
</network>
EOF
  virsh_cmd net-define "${net_xml}" >/dev/null
  virsh_cmd net-autostart "${LAB_NETWORK_NAME}" >/dev/null
  virsh_cmd net-start "${LAB_NETWORK_NAME}" >/dev/null
}

write_seed() {
  local short="$1" ip="$2" user_data="${SEED_DIR}/${short}-user-data" meta_data="${SEED_DIR}/${short}-meta-data"
  cat > "${user_data}" <<EOF
#cloud-config
preserve_hostname: false
hostname: ${short}
fqdn: ${short}.${LAB_DOMAIN}
manage_etc_hosts: true
disable_root: false
ssh_pwauth: false
users:
  - default
  - name: root
    ssh_authorized_keys:
      - ${LAB_PUBKEY}
write_files:
  - path: /etc/ssh/sshd_config.d/01-ansible-oracle-root-login.conf
    permissions: '0644'
    content: |
      PermitRootLogin prohibit-password
runcmd:
  - [ mkdir, -p, /u01/stage, /super/app/oracle, /super/d01, /super/a01, /super/f01, /super/r01, /grid ]
  - [ sh, -lc, "grep -q '^u01_stage ' /etc/fstab || echo 'u01_stage /u01/stage 9p trans=virtio,version=9p2000.L,ro,nofail,_netdev 0 0' >> /etc/fstab" ]
  - [ sh, -lc, "modprobe 9pnet_virtio || true" ]
  - [ sh, -lc, "mount /u01/stage || true" ]
  - [ systemctl, enable, --now, sshd ]
  - [ systemctl, restart, sshd ]
EOF
  cat > "${meta_data}" <<EOF
instance-id: ${LAB_NAME}-${short}
local-hostname: ${short}
EOF
  rm -f "${SEED_DIR}/${short}.iso"
  cloud-localds "${SEED_DIR}/${short}.iso" "${user_data}" "${meta_data}"
}

ensure_vm() {
  local short="$1" name disk seed ip
  name="$(vm_name "${short}")"
  disk="${VM_DIR}/${short}.qcow2"
  seed="${SEED_DIR}/${short}.iso"
  ip="$(vm_ip "${short}")"

  write_seed "${short}" "${ip}"

  if ! [ -f "${disk}" ]; then
    log "Creating ${short} root disk (${LAB_ROOT_DISK_SIZE})"
    qemu-img create -f qcow2 -F qcow2 -b "${BASE_IMAGE}" "${disk}" "${LAB_ROOT_DISK_SIZE}" >/dev/null
  fi

  if ! virsh_cmd dominfo "${name}" >/dev/null 2>&1; then
    log "Importing VM ${name}"
    virt_install_cmd \
      --name "${name}" \
      --memory "$(vm_memory "${short}")" \
      --vcpus "$(vm_vcpus "${short}")" \
      --import \
      --os-variant generic \
      --disk "path=${disk},format=qcow2,bus=virtio" \
      --disk "path=${seed},device=cdrom" \
      --filesystem "type=mount,source=${STAGE_MOUNT_SOURCE},target=u01_stage,accessmode=mapped" \
      --network "network=${LAB_NETWORK_NAME},mac=$(vm_mac "${short}"),model=virtio" \
      --graphics none \
      --console pty,target.type=serial \
      --noautoconsole \
      --boot hd \
      --events on_reboot=restart >/dev/null
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

log "Generating ${INVENTORY_DIR}/hosts.yml"
mkdir -p "${INVENTORY_DIR}"
cp "${INVENTORY_DIR}/hosts.example.yml" "${INVENTORY_DIR}/hosts.yml"

log "Updating /etc/hosts (standalone slice: superdb.domain.is -> ${IP_SUPERDB1})"
"$(dirname "$0")/update-hosts.sh"

log "Lab is up. Inventory: ${INVENTORY_DIR}/hosts.yml"
log "Next: ./scripts/bootstrap-venv.sh && source .venv/bin/activate"
log "Then:  ansible-playbook playbooks/site.yml"
