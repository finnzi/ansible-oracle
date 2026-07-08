#!/usr/bin/env bash
# lab/scripts/lib/common.sh — shared helpers for the KVM/libvirt lab tooling.
# Sourced by fetch-base-image.sh / lab-up.sh / lab-down.sh / update-hosts.sh.
# Not executable on purpose.

set -euo pipefail

# Resolve repo + lab dirs regardless of where the caller is.
# BASH_SOURCE here is lab/scripts/lib/common.sh, so the lab dir is two levels up.
LAB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REPO_DIR="$(cd "${LAB_DIR}/.." && pwd)"
DOWNLOAD_DIR="${REPO_DIR}/download"
INVENTORY_DIR="${REPO_DIR}/inventory"
SOURCES_DIR="${SOURCES_DIR:-${HOME}/sources/oracle}"

# KVM/libvirt lab state.
LAB_STATE_DIR="${LAB_STATE_DIR:-${LAB_DIR}/state}"
IMAGE_DIR="${LAB_STATE_DIR}/images"
VM_DIR="${LAB_STATE_DIR}/vms"
SEED_DIR="${LAB_STATE_DIR}/seed"
EMPTY_STAGE_DIR="${LAB_STATE_DIR}/empty-stage"

LAB_NAME="${LAB_NAME:-ansible-oracle-lab}"
LAB_NETWORK_NAME="${LAB_NETWORK_NAME:-ansible-oracle-lab}"
LAB_BRIDGE_NAME="${LAB_BRIDGE_NAME:-virbr-oracle}"
LAB_DOMAIN="${LAB_DOMAIN:-domain.is}"
LAB_OS_VERSION="${LAB_OS_VERSION:-9}"
LAB_ROOT_DISK_SIZE="${LAB_ROOT_DISK_SIZE:-120G}"
LAB_DB_MEMORY_MIB="${LAB_DB_MEMORY_MIB:-12288}"
LAB_OBSERVER_MEMORY_MIB="${LAB_OBSERVER_MEMORY_MIB:-4096}"
LAB_DB_VCPUS="${LAB_DB_VCPUS:-4}"
LAB_OBSERVER_VCPUS="${LAB_OBSERVER_VCPUS:-2}"
VIRSH_URI="${VIRSH_URI:-qemu:///system}"

BASE_IMAGE="${ORACLE_LINUX_BASE_IMAGE:-${IMAGE_DIR}/OracleLinux-${LAB_OS_VERSION}-x86_64-kvm.qcow2}"

# Lab network conventions (must match inventory/hosts.example.yml).
LAB_NET_PREFIX="${LAB_NET_PREFIX:-192.168.87}"
IP_SUPERDB1="${LAB_NET_PREFIX}.11"
IP_SUPERDB2="${LAB_NET_PREFIX}.12"
IP_OBSERVER="${LAB_NET_PREFIX}.13"

log()  { printf '\033[1;34m[lab]\033[0m %s\n' "$*" >&2; }
warn() { printf '\033[1;33m[lab warn]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[lab error]\033[0m %s\n' "$*" >&2; exit 1; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

check_cmd() {
  command -v "$1" >/dev/null 2>&1
}

group_list_has() {
  local wanted="$1" group
  shift
  for group in "$@"; do
    [ "${group}" = "${wanted}" ] && return 0
  done
  return 1
}

virsh_cmd() {
  virsh --connect "${VIRSH_URI}" "$@"
}

lab_prepare_state_dirs() {
  mkdir -p "${IMAGE_DIR}" "${VM_DIR}" "${SEED_DIR}" "${EMPTY_STAGE_DIR}" "${DOWNLOAD_DIR}"
  touch "${DOWNLOAD_DIR}/.gitkeep"
}

lab_pubkey() {
  cat "$(ssh_pubkey_file)"
}

lab_stage_mount_source() {
  if [ -d "${SOURCES_DIR}" ]; then
    printf '%s\n' "${SOURCES_DIR}"
  else
    printf '%s\n' "${EMPTY_STAGE_DIR}"
  fi
}

vm_name() {
  printf '%s-%s\n' "${LAB_NAME}" "$1"
}

vm_mac() {
  case "$1" in
    superdb1) echo "52:54:00:87:00:11" ;;
    superdb2) echo "52:54:00:87:00:12" ;;
    observer) echo "52:54:00:87:00:13" ;;
    *) die "Unknown VM: $1" ;;
  esac
}

vm_ip() {
  case "$1" in
    superdb1) echo "${IP_SUPERDB1}" ;;
    superdb2) echo "${IP_SUPERDB2}" ;;
    observer) echo "${IP_OBSERVER}" ;;
    *) die "Unknown VM: $1" ;;
  esac
}

vm_memory() {
  case "$1" in
    superdb1|superdb2) echo "${LAB_DB_MEMORY_MIB}" ;;
    observer) echo "${LAB_OBSERVER_MEMORY_MIB}" ;;
    *) die "Unknown VM: $1" ;;
  esac
}

vm_vcpus() {
  case "$1" in
    superdb1|superdb2) echo "${LAB_DB_VCPUS}" ;;
    observer) echo "${LAB_OBSERVER_VCPUS}" ;;
    *) die "Unknown VM: $1" ;;
  esac
}

ssh_key_file() {
  printf '%s\n' "${ORACLE_LAB_SSH_KEY:-${HOME}/.ssh/lab_oracle}"
}

ssh_pubkey_file() {
  printf '%s.pub\n' "$(ssh_key_file)"
}

ssh_opts() {
  printf '%s\n' \
    "-i" "$(ssh_key_file)" \
    "-o" "StrictHostKeyChecking=no" \
    "-o" "UserKnownHostsFile=/dev/null" \
    "-o" "ConnectTimeout=5" \
    "-o" "BatchMode=yes"
}

# Wait until SSH on a VM is accepting connections (used after lab-up).
wait_for_ssh() {
  local host_ip="$1" tries=0
  while ! ssh $(ssh_opts) "root@${host_ip}" true 2>/dev/null; do
    tries=$((tries+1))
    [ "${tries}" -ge 120 ] && { warn "SSH to ${host_ip} did not come up in 10m"; return 1; }
    sleep 5
  done
}

path_world_accessible_for_9p() {
  local real="$1" cur="" part mode other required
  real="$(readlink -f "${real}")" || return 1
  [ -n "${real}" ] || return 1

  IFS=/ read -r -a parts <<< "${real#/}"
  for part in "${parts[@]}"; do
    cur="${cur}/${part}"
    mode="$(stat -c '%a' "${cur}" 2>/dev/null)" || return 1
    other=$((mode % 10))
    required=1
    if [ "${cur}" = "${real}" ]; then
      required=5
    fi
    if (( (other & required) != required )); then
      return 1
    fi
  done
}

write_network_xml() {
  local net_xml="${LAB_STATE_DIR}/network.xml"
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
  printf '%s\n' "${net_xml}"
}

write_seed() {
  local short="$1" user_data meta_data
  user_data="${SEED_DIR}/${short}-user-data"
  meta_data="${SEED_DIR}/${short}-meta-data"
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
      - $(lab_pubkey)
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
  local short="$1" name disk seed domain_xml stage_mount_source
  name="$(vm_name "${short}")"
  disk="${VM_DIR}/${short}.qcow2"
  seed="${SEED_DIR}/${short}.iso"
  domain_xml="${VM_DIR}/${short}.xml"
  stage_mount_source="$(lab_stage_mount_source)"

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
      <source dir='${stage_mount_source}'/>
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

lab_render_config() {
  local svc
  lab_prepare_state_dirs
  write_network_xml >/dev/null
  for svc in superdb1 superdb2 observer; do
    write_seed "${svc}"
    write_domain_xml "${svc}" >/dev/null
  done
}

lab_required_commands() {
  printf '%s\n' virsh qemu-img genisoimage timeout ssh curl
}

lab_required_media_files() {
  printf '%s\n' \
    info.txt \
    V982063-01-Oracle.19c.Database.Enterprise.Edition.zip \
    V982064-01-Oracle.19c.Database.Client.zip \
    V982068-01-Oracle.19c.Grid.Infrastructure.zip \
    p6880880_190000_Linux-x86-64.zip \
    p39062931_190000_Linux-x86-64.zip \
    p39062956_190000_Linux-x86-64.zip
}

lab_preflight_commands() {
  local missing=0 cmd
  while read -r cmd; do
    if check_cmd "${cmd}"; then
      log "found command: ${cmd}"
    else
      warn "missing command: ${cmd}"
      missing=1
    fi
  done < <(lab_required_commands)
  return "${missing}"
}

lab_preflight_libvirt_groups() {
  local active_groups rc=0

  [ "${VIRSH_URI}" = "qemu:///system" ] || return 0
  [ "$(id -u)" -ne 0 ] || return 0

  read -r -a active_groups <<< "${LAB_ACTIVE_GROUPS:-$(id -nG 2>/dev/null || true)}"

  if group_list_has libvirt "${active_groups[@]}"; then
    log "active group present: libvirt"
  else
    warn "current shell is not in the active libvirt group."
    warn "Run: sudo usermod -aG libvirt,kvm \$USER"
    warn "Then log out and back in before running lab-up.sh."
    rc=1
  fi

  if group_list_has kvm "${active_groups[@]}"; then
    log "active group present: kvm"
  else
    warn "current shell is not in the active kvm group."
    warn "Add it with libvirt if direct KVM access is needed: sudo usermod -aG libvirt,kvm \$USER"
    rc=1
  fi

  if [ "${rc}" -ne 0 ]; then
    warn "Group membership is advisory; the libvirt connection check below is authoritative."
  fi
  return 0
}

lab_preflight_libvirt() {
  if timeout 8 virsh --connect "${VIRSH_URI}" list --all >/dev/null 2>&1; then
    log "libvirt reachable: ${VIRSH_URI}"
    return 0
  fi

  warn "cannot access libvirt at ${VIRSH_URI}"
  warn "Fedora setup usually needs:"
  warn "  sudo dnf install -y libvirt-daemon-driver-qemu qemu-kvm genisoimage"
  warn "  sudo systemctl enable --now virtqemud.socket virtnetworkd.socket virtstoraged.socket"
  warn "  sudo usermod -aG libvirt,kvm \$USER"
  warn "Then log out and back in so group membership applies."
  return 1
}

lab_preflight_session_network_note() {
  if [ "${VIRSH_URI}" = "qemu:///session" ]; then
    warn "VIRSH_URI=qemu:///session is not recommended for this lab."
    warn "The lab needs a NAT/bridge network with fixed DHCP leases; session libvirt often cannot create that network."
  fi
}

lab_preflight_ssh_key() {
  if [ -f "$(ssh_pubkey_file)" ]; then
    log "SSH public key present: $(ssh_pubkey_file)"
    return 0
  fi

  warn "SSH public key missing: $(ssh_pubkey_file)"
  warn "Create it with: ssh-keygen -t ed25519 -f $(ssh_key_file) -N ''"
  return 1
}

lab_preflight_sources() {
  local rc=0 file
  if [ ! -d "${SOURCES_DIR}" ]; then
    warn "SOURCES_DIR not found: ${SOURCES_DIR}"
    warn "Oracle installs will fail until the media from ~/sources/oracle is staged or SOURCES_DIR is overridden."
    if [ "${LAB_ALLOW_MISSING_MEDIA:-0}" = "1" ]; then
      warn "LAB_ALLOW_MISSING_MEDIA=1 is set; continuing for OS-only lab work."
      return 0
    fi
    return 1
  fi

  log "Oracle media directory present: ${SOURCES_DIR}"
  if [ "${VIRSH_URI}" = "qemu:///system" ] \
      && [ "${LAB_SKIP_SOURCE_ACCESS_CHECK:-0}" != "1" ] \
      && ! path_world_accessible_for_9p "${SOURCES_DIR}"; then
    warn "SOURCES_DIR is not traversable/readable by an unprivileged system QEMU process: ${SOURCES_DIR}"
    warn "Move or bind-mount the media to a libvirt-readable path, for example:"
    warn "  sudo mkdir -p /var/lib/libvirt/ansible-oracle-sources"
    warn "  sudo rsync -a --info=progress2 ${SOURCES_DIR}/ /var/lib/libvirt/ansible-oracle-sources/"
    warn "  sudo chmod -R a+rX /var/lib/libvirt/ansible-oracle-sources"
    warn "  SOURCES_DIR=/var/lib/libvirt/ansible-oracle-sources ./lab/scripts/lab-up.sh"
    warn "Set LAB_SKIP_SOURCE_ACCESS_CHECK=1 only if your libvirt setup grants QEMU access another way."
    rc=1
  fi

  while read -r file; do
    if [ -f "${SOURCES_DIR}/${file}" ]; then
      log "Oracle media present: ${file}"
    else
      warn "Oracle media missing: ${SOURCES_DIR}/${file}"
      rc=1
    fi
  done < <(lab_required_media_files)

  if [ -f "${SOURCES_DIR}/info.txt" ]; then
    while read -r file; do
      [ "${file}" = "info.txt" ] && continue
      if ! grep -Fq "${file}" "${SOURCES_DIR}/info.txt"; then
        warn "info.txt does not mention expected media file: ${file}"
      fi
    done < <(lab_required_media_files)
  fi

  if [ "${rc}" -ne 0 ] && [ "${LAB_ALLOW_MISSING_MEDIA:-0}" = "1" ]; then
    warn "LAB_ALLOW_MISSING_MEDIA=1 is set; continuing for OS-only lab work."
    return 0
  fi
  return "${rc}"
}

lab_preflight_all() {
  local rc=0
  lab_preflight_commands || rc=1
  lab_preflight_session_network_note
  lab_preflight_libvirt_groups
  lab_preflight_libvirt || rc=1
  lab_preflight_ssh_key || rc=1
  lab_preflight_sources || rc=1
  return "${rc}"
}

lab_require_preflight() {
  lab_preflight_all || die "KVM lab preflight failed. Run ./lab/scripts/preflight.sh for details."
}

discover_oracle_linux_image_url() {
  require_cmd curl
  local root="https://yum.oracle.com/templates/OracleLinux/OL${LAB_OS_VERSION}"
  local update page arch file
  page="$(curl -fsSL "${root}/" 2>/dev/null || true)"
  update="$(printf '%s\n' "${page}" | grep -Eo 'href="u[0-9]+/' | sed -E 's/^href="(u[0-9]+).*/\1/' | sort -V | tail -1)"
  [ -n "${update}" ] || die "Could not discover an OL${LAB_OS_VERSION} update directory at ${root}/. Set ORACLE_LINUX_IMAGE_URL explicitly."

  arch="${root}/${update}/x86_64"
  page="$(curl -fsSL "${arch}/" 2>/dev/null || true)"
  file="$(printf '%s\n' "${page}" | grep -Eo "OL${LAB_OS_VERSION}U[0-9]+_x86_64-kvm-b[0-9]+\\.qcow2" | sort -V | tail -1)"
  [ -n "${file}" ] || die "Could not discover a KVM qcow2 image at ${arch}/. Set ORACLE_LINUX_IMAGE_URL explicitly."

  printf '%s/%s\n' "${arch}" "${file}"
}

HOSTS_MARKER_BEGIN="# ansible-oracle lab begin"
HOSTS_MARKER_END="# ansible-oracle lab end"
