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
require_cmd qemu-img
require_cmd genisoimage
require_cmd timeout

if ! timeout 8 virsh --connect "${VIRSH_URI}" list --all >/dev/null 2>&1; then
  die "Cannot access libvirt at ${VIRSH_URI}. For Fedora, install/start libvirt and run this from a user allowed to manage system VMs, for example: sudo dnf install -y libvirt-daemon-driver-qemu qemu-kvm genisoimage; sudo systemctl enable --now virtqemud.socket virtnetworkd.socket virtstoraged.socket; sudo usermod -aG libvirt,kvm \$USER; then log out/in. You can also set VIRSH_URI if you use a different libvirt connection."
fi

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
  if [ "${VIRSH_URI}" = "qemu:///system" ] \
      && [ "${LAB_SKIP_SOURCE_ACCESS_CHECK:-0}" != "1" ] \
      && ! path_world_accessible_for_9p "${SOURCES_DIR}"; then
    die "SOURCES_DIR=${SOURCES_DIR} is not traversable/readable by an unprivileged system QEMU process. Move or bind-mount the Oracle media to a libvirt-readable path such as /var/lib/libvirt/ansible-oracle-sources, set SOURCES_DIR to that path, or set LAB_SKIP_SOURCE_ACCESS_CHECK=1 if your libvirt QEMU process can read it through another mechanism."
  fi
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
  genisoimage \
    -quiet \
    -output "${SEED_DIR}/${short}.iso" \
    -volid cidata \
    -joliet \
    -rock \
    -graft-points \
    "user-data=${user_data}" \
    "meta-data=${meta_data}"
}

write_domain_xml() {
  local short="$1" name disk seed domain_xml
  name="$(vm_name "${short}")"
  disk="${VM_DIR}/${short}.qcow2"
  seed="${SEED_DIR}/${short}.iso"
  domain_xml="${VM_DIR}/${short}.xml"

  cat > "${domain_xml}" <<EOF
<domain type='kvm'>
  <name>${name}</name>
  <memory unit='MiB'>$(vm_memory "${short}")</memory>
  <currentMemory unit='MiB'>$(vm_memory "${short}")</currentMemory>
  <vcpu placement='static'>$(vm_vcpus "${short}")</vcpu>
  <os>
    <type arch='x86_64' machine='pc'>hvm</type>
    <boot dev='hd'/>
  </os>
  <features>
    <acpi/>
    <apic/>
  </features>
  <cpu mode='host-passthrough' check='none'/>
  <clock offset='utc'/>
  <on_poweroff>destroy</on_poweroff>
  <on_reboot>restart</on_reboot>
  <on_crash>restart</on_crash>
  <devices>
    <emulator>/usr/bin/qemu-system-x86_64</emulator>
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2'/>
      <source file='${disk}'/>
      <target dev='vda' bus='virtio'/>
    </disk>
    <disk type='file' device='cdrom'>
      <driver name='qemu' type='raw'/>
      <source file='${seed}'/>
      <target dev='sda' bus='sata'/>
      <readonly/>
    </disk>
    <interface type='network'>
      <mac address='$(vm_mac "${short}")'/>
      <source network='${LAB_NETWORK_NAME}'/>
      <model type='virtio'/>
    </interface>
    <filesystem type='mount' accessmode='mapped'>
      <source dir='${STAGE_MOUNT_SOURCE}'/>
      <target dir='u01_stage'/>
    </filesystem>
    <serial type='pty'>
      <target port='0'/>
    </serial>
    <console type='pty'>
      <target type='serial' port='0'/>
    </console>
    <graphics type='vnc' listen='127.0.0.1' autoport='yes'/>
    <rng model='virtio'>
      <backend model='random'>/dev/urandom</backend>
    </rng>
  </devices>
</domain>
EOF
  printf '%s\n' "${domain_xml}"
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

log "Generating ${INVENTORY_DIR}/hosts.yml"
mkdir -p "${INVENTORY_DIR}"
cp "${INVENTORY_DIR}/hosts.example.yml" "${INVENTORY_DIR}/hosts.yml"

log "Updating /etc/hosts (standalone slice: superdb.domain.is -> ${IP_SUPERDB1})"
"$(dirname "$0")/update-hosts.sh"

log "Lab is up. Inventory: ${INVENTORY_DIR}/hosts.yml"
log "Next: ./scripts/bootstrap-venv.sh && source .venv/bin/activate"
log "Then:  ansible-playbook playbooks/site.yml"
