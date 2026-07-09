#!/usr/bin/env bash
# lab/scripts/prepare-host-fedora.sh
#
# Prepare a Fedora workstation to run the ansible-oracle KVM lab.
# This script installs host packages, starts libvirt sockets, grants the
# selected user libvirt/kvm group membership, and copies Oracle media to a path
# system QEMU can read.

set -euo pipefail
source "$(dirname "$0")/lib/common.sh"

TARGET_USER="${TARGET_USER:-${SUDO_USER:-${USER}}}"
MEDIA_DEST="${MEDIA_DEST:-/var/lib/libvirt/ansible-oracle-sources}"
SKIP_PACKAGE_INSTALL="${SKIP_PACKAGE_INSTALL:-0}"
SKIP_MEDIA_STAGE="${SKIP_MEDIA_STAGE:-0}"

usage() {
  cat <<EOF
Usage: $0 [--user USER] [--media-dest PATH] [--skip-package-install] [--skip-media-stage]

Environment:
  SOURCES_DIR             Source Oracle media directory (default: ${HOME}/sources/oracle)
  TARGET_USER             User to add to libvirt,kvm groups (default: sudo caller/current user)
  MEDIA_DEST              Libvirt-readable media directory (default: /var/lib/libvirt/ansible-oracle-sources)
  SKIP_PACKAGE_INSTALL=1  Do not run dnf/systemctl/usermod
  SKIP_MEDIA_STAGE=1      Do not copy Oracle media
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --user)
      TARGET_USER="${2:?--user requires a value}"
      shift 2
      ;;
    --media-dest)
      MEDIA_DEST="${2:?--media-dest requires a value}"
      shift 2
      ;;
    --skip-package-install)
      SKIP_PACKAGE_INSTALL=1
      shift
      ;;
    --skip-media-stage)
      SKIP_MEDIA_STAGE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown option: $1"
      ;;
  esac
done

as_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

python_supports_bootstrap() {
  local bin="$1"
  command -v "${bin}" >/dev/null 2>&1 || return 1
  "${bin}" - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 12) else 1)
PY
}

has_supported_python() {
  local cand
  for cand in python3.14 python3.13 python3.12 python3; do
    python_supports_bootstrap "${cand}" && return 0
  done
  return 1
}

if [ "${SKIP_PACKAGE_INSTALL}" != "1" ]; then
  require_cmd sudo
  require_cmd dnf
  log "Installing Fedora KVM/libvirt lab packages"
  as_root dnf install -y \
    curl \
    genisoimage \
    libvirt-daemon-driver-qemu \
    openssh-clients \
    python3 \
    python3-pip \
    qemu-img \
    qemu-kvm \
    rsync

  if ! has_supported_python; then
    log "Installing Python 3.12 for the project venv bootstrap"
    if ! as_root dnf install -y python3.12 python3.12-pip; then
      as_root dnf install -y python3.12
    fi
  fi

  if ! has_supported_python; then
    die "Python 3.12 or newer is still unavailable after package installation"
  fi

  log "Starting libvirt sockets"
  as_root systemctl enable --now \
    virtlogd.socket \
    virtqemud.socket \
    virtnetworkd.socket \
    virtstoraged.socket

  log "Adding ${TARGET_USER} to libvirt,kvm groups"
  as_root usermod -aG libvirt,kvm "${TARGET_USER}"
fi

if [ "${SKIP_MEDIA_STAGE}" != "1" ]; then
  require_cmd rsync
  if [ ! -d "${SOURCES_DIR}" ]; then
    die "SOURCES_DIR does not exist: ${SOURCES_DIR}"
  fi

  log "Staging Oracle media from ${SOURCES_DIR} to ${MEDIA_DEST}"
  as_root mkdir -p "${MEDIA_DEST}"
  as_root rsync -a --info=progress2 "${SOURCES_DIR}/" "${MEDIA_DEST}/"
  as_root chmod -R a+rX "${MEDIA_DEST}"
  if command -v restorecon >/dev/null 2>&1; then
    as_root restorecon -R "${MEDIA_DEST}" || true
  fi
fi

cat >&2 <<EOF

Host preparation complete.

If group membership changed, log out and back in before starting the lab.
Then run:

  SOURCES_DIR=${MEDIA_DEST} ./lab/scripts/preflight.sh
  SOURCES_DIR=${MEDIA_DEST} ./lab/scripts/lab-up.sh

EOF
