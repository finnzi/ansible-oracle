#!/usr/bin/env bash
# lab/scripts/lab-down.sh — stop the KVM/libvirt lab VMs.
# VM disks are NOT removed by default; pass --purge to undefine VMs and delete
# ${LAB_STATE_DIR}/vms + ${LAB_STATE_DIR}/seed.

set -euo pipefail
source "$(dirname "$0")/lib/common.sh"

PURGE=false
FORCE=false

usage() {
  cat <<EOF
Usage: $0 [--purge] [--force]

Options:
  --purge  Undefine VMs and remove lab VM/seed state after shutdown.
  --force  Immediately destroy active VMs instead of graceful shutdown.

Environment:
  LAB_SHUTDOWN_TIMEOUT_SECONDS  Global graceful-shutdown timeout in seconds (default: ${LAB_SHUTDOWN_TIMEOUT_SECONDS}).
EOF
}

for arg in "$@"; do
  case "${arg}" in
    --purge) PURGE=true ;;
    --force) FORCE=true ;;
    -h|--help)
      usage
      exit 0
      ;;
    "") ;;
    *) die "Unknown option: ${arg} (use --purge, --force, or no option)" ;;
  esac
done

require_cmd virsh

if ! lab_is_positive_integer "${LAB_SHUTDOWN_TIMEOUT_SECONDS}"; then
  die "LAB_SHUTDOWN_TIMEOUT_SECONDS must be a positive integer (got: ${LAB_SHUTDOWN_TIMEOUT_SECONDS})"
fi

shutdown_deadline=""
if [ "${FORCE}" = false ]; then
  shutdown_deadline="$(lab_shutdown_deadline_after "${LAB_SHUTDOWN_TIMEOUT_SECONDS}")" || \
    die "Unable to establish shutdown deadline"
fi

domains=()
pending=()
dominfo_failed=false
shutdown_failed=false
for svc in superdb1 superdb2 observer; do
  name="$(vm_name "${svc}")"
  if [ "${FORCE}" = false ]; then
    if lab_shutdown_deadline_expired "${shutdown_deadline}"; then
      die "Lab shutdown deadline exhausted during domain discovery"
    else
      deadline_status=$?
      [ "${deadline_status}" -eq 2 ] && die "Unable to read shutdown deadline"
    fi
  fi
  dominfo_output=""
  if dominfo_output="$(virsh_cmd dominfo "${name}" 2>&1)"; then
    domains+=("${name}")
  else
    list_output=""
    if ! list_output="$(virsh_cmd list --all --name 2>&1)"; then
      warn "Unable to inspect ${name}: ${dominfo_output}"
      warn "Unable to list libvirt domains while checking ${name}: ${list_output}"
      dominfo_failed=true
    elif printf '%s\n' "${list_output}" | grep -Fqx "${name}"; then
      warn "Unable to inspect ${name}: ${dominfo_output}"
      warn "Libvirt lists ${name} despite the failed dominfo query"
      dominfo_failed=true
    fi
  fi
  if [ "${FORCE}" = false ]; then
    if lab_shutdown_deadline_expired "${shutdown_deadline}"; then
      die "Lab shutdown deadline exhausted during domain discovery"
    else
      deadline_status=$?
      [ "${deadline_status}" -eq 2 ] && die "Unable to read shutdown deadline"
    fi
  fi
done

if [ "${dominfo_failed}" = true ]; then
  die "Lab shutdown aborted: unable to inspect one or more lab domains"
fi

if [ "${FORCE}" = true ]; then
  force_failed=false
  force_pending=()
  force_destroyed=()

  for name in "${domains[@]}"; do
    if ! state="$(virsh_cmd domstate "${name}")"; then
      warn "Unable to read state for ${name}"
      force_failed=true
      continue
    fi
    state="$(printf '%s' "${state}" | tr -d '\r')"
    if [ -z "${state}" ]; then
      warn "Unable to read state for ${name}: empty state"
      force_failed=true
    elif [ "${state}" != "shut off" ]; then
      force_pending+=("${name}")
    fi
  done

  if [ "${force_failed}" = true ]; then
    die "Lab force shutdown aborted: unable to establish the state of one or more lab domains"
  fi

  for name in "${force_pending[@]}"; do
    log "Destroying ${name}"
    if virsh_cmd destroy "${name}" >/dev/null; then
      force_destroyed+=("${name}")
    else
      warn "Failed to destroy ${name}"
      force_failed=true
    fi
  done

  for name in "${force_destroyed[@]}"; do
    if ! state="$(virsh_cmd domstate "${name}")"; then
      warn "Unable to verify shutdown state for ${name} after destroy"
      force_failed=true
      continue
    fi
    state="$(printf '%s' "${state}" | tr -d '\r')"
    if [ "${state}" != "shut off" ]; then
      warn "${name} did not shut off after destroy (state: ${state:-unknown})"
      force_failed=true
    fi
  done

  if [ "${force_failed}" = true ]; then
    die "Lab force shutdown incomplete; resolve the reported VM state"
  fi
else
  for name in "${domains[@]}"; do
    if ! state="$(virsh_cmd domstate "${name}")"; then
      warn "Unable to read state for ${name}"
      shutdown_failed=true
      continue
    fi
    state="$(printf '%s' "${state}" | tr -d '\r')"
    case "${state}" in
      running)
        if lab_shutdown_deadline_expired "${shutdown_deadline}"; then
          warn "Shutdown deadline exhausted before requesting shutdown for ${name}"
          shutdown_failed=true
          continue
        else
          deadline_status=$?
          if [ "${deadline_status}" -eq 2 ]; then
            warn "Unable to read shutdown deadline before requesting shutdown for ${name}"
            shutdown_failed=true
            continue
          fi
        fi
        log "Shutting down ${name}"
        if virsh_cmd shutdown "${name}" >/dev/null; then
          pending+=("${name}")
        else
          warn "Failed to request shutdown for ${name}"
          shutdown_failed=true
        fi
        ;;
      "in shutdown"|dying)
        log "Waiting for ${name} to finish shutting down"
        pending+=("${name}")
        ;;
      "shut off")
        ;;
      *)
        warn "Cannot gracefully stop ${name} from state: ${state:-unknown}"
        shutdown_failed=true
        ;;
    esac
  done

  if [ "${#pending[@]}" -gt 0 ] && ! wait_for_domains_shutoff \
      "${shutdown_deadline}" "${LAB_SHUTDOWN_TIMEOUT_SECONDS}" "${pending[@]}"; then
    shutdown_failed=true
  fi

  if [ "${shutdown_failed}" = true ]; then
    die "Lab shutdown incomplete; resolve the reported VM state or use --force"
  fi
fi

if [ "${PURGE}" = true ]; then
  purge_failed=false
  for name in "${domains[@]}"; do
    log "Undefining ${name}"
    storage_error=""
    if storage_error="$(virsh_cmd undefine "${name}" --nvram --remove-all-storage \
        2>&1 > /dev/null)"; then
      continue
    fi

    fallback_error=""
    if fallback_error="$(virsh_cmd undefine "${name}" --nvram \
        2>&1 > /dev/null)"; then
      continue
    fi

    warn "Failed to undefine ${name} with storage removal: ${storage_error:-unknown error}"
    warn "Failed to undefine ${name}: ${fallback_error:-unknown error}"
    purge_failed=true
  done

  if [ "${purge_failed}" = true ]; then
    die "Lab purge incomplete; local VM and seed state were preserved"
  fi
fi

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
