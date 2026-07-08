#!/usr/bin/env bash
# lab/scripts/fetch-base-image.sh
#
# Download the Oracle Linux qcow2 cloud image used as the backing image for
# the KVM lab VMs. You can either set ORACLE_LINUX_IMAGE_URL explicitly, pass a
# URL as the first argument, or let the script try to discover the latest image
# from yum.oracle.com for LAB_OS_VERSION.

set -euo pipefail
source "$(dirname "$0")/lib/common.sh"

IMAGE_URL="${1:-${ORACLE_LINUX_IMAGE_URL:-}}"

if [ -z "${IMAGE_URL}" ]; then
  log "No ORACLE_LINUX_IMAGE_URL set; trying to discover latest OL${LAB_OS_VERSION} KVM image"
  IMAGE_URL="$(discover_oracle_linux_image_url)"
fi

mkdir -p "${IMAGE_DIR}"
target="${BASE_IMAGE}"
tmp="${target}.tmp"

log "Downloading ${IMAGE_URL}"
require_cmd curl
curl -fL --progress-bar "${IMAGE_URL}" -o "${tmp}"
mv "${tmp}" "${target}"

log "Base image written to ${target}"
