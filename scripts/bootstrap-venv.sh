#!/usr/bin/env bash
# scripts/bootstrap-venv.sh
#
# Create the project's Python virtualenv at .venv using Python 3.12 or newer,
# and install requirements.txt into it.
#
# The "python 3.12 should be available" requirement is enforced here. The
# lab host may use a newer interpreter when available.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "${REPO_DIR}"

MIN_PY_MAJOR=3
MIN_PY_MINOR=12
CHECK_ONLY=0

usage() {
  cat <<'EOF'
Usage: scripts/bootstrap-venv.sh [--check]

Create .venv with Python 3.12 or newer and install requirements.txt.

Options:
  --check   Validate interpreter selection only; do not create .venv or install.
EOF
}

python_install_hint() {
  cat >&2 <<'EOF'
Install Python 3.12 or newer, then rerun this script.
On Fedora, install or update the system Python packages with dnf.
Alternatively set PYTHON=/path/to/python3.12+.
EOF
}

python_version() {
  local bin="$1"
  local quiet="${2:-0}"
  local output
  if ! output="$("${bin}" --version 2>&1)"; then
    if [ "${quiet}" != "1" ]; then
      echo "error: could not execute ${bin} --version" >&2
      if [ -n "${output}" ]; then
        printf '%s\n' "${output}" >&2
      fi
      python_install_hint
    fi
    return 1
  fi
  printf '%s\n' "${output}" | awk '{print $2}'
}

python_version_is_supported() {
  local version="$1"
  local major="${version%%.*}"
  local rest="${version#*.}"
  local minor="${rest%%.*}"

  [[ "${major}" =~ ^[0-9]+$ && "${minor}" =~ ^[0-9]+$ ]] || return 2
  if [ "${major}" -lt "${MIN_PY_MAJOR}" ] ||
     { [ "${major}" -eq "${MIN_PY_MAJOR}" ] && [ "${minor}" -lt "${MIN_PY_MINOR}" ]; }; then
    return 1
  fi
  return 0
}

require_supported_python() {
  local label="$1"
  local version="$2"
  local rc=0

  python_version_is_supported "${version}" || rc=$?
  if [ "${rc}" -ne 0 ]; then
    case "${rc}" in
      2)
        echo "error: could not parse Python version from ${label}: ${version}" >&2
        ;;
      *)
        echo "error: ${label} (${version}) is too old; Python ${MIN_PY_MAJOR}.${MIN_PY_MINOR}+ is required" >&2
        ;;
    esac
    python_install_hint
    exit 1
  fi
}

select_python() {
  local cand
  local version

  if [ -n "${PYTHON:-}" ]; then
    PYBIN="${PYTHON}"
    PYVER="$(python_version "${PYBIN}")"
    require_supported_python "${PYBIN}" "${PYVER}"
    return 0
  fi

  for cand in python3.14 python3.13 python3.12 python3; do
    if ! command -v "${cand}" >/dev/null 2>&1; then
      continue
    fi
    if ! version="$(python_version "${cand}" 1)"; then
      continue
    fi
    if python_version_is_supported "${version}"; then
      PYBIN="${cand}"
      PYVER="${version}"
      return 0
    fi
  done

  echo "error: no usable Python ${MIN_PY_MAJOR}.${MIN_PY_MINOR}+ found on PATH" >&2
  python_install_hint
  exit 1
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --check)
      CHECK_ONLY=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
  shift
done

PYBIN=""
PYVER=""
select_python

echo "[venv] Using ${PYBIN} (${PYVER})"
if [ -d ".venv" ]; then
  if [ ! -x ".venv/bin/python" ]; then
    if [ "${CHECK_ONLY}" -eq 1 ]; then
      echo "error: existing .venv has no executable bin/python" >&2
      exit 1
    fi
    echo "[venv] Existing .venv is incomplete; recreating"
    rm -rf .venv
  else
    VENV_PYVER="$(python_version .venv/bin/python)"
    if ! python_version_is_supported "${VENV_PYVER}"; then
      if [ "${CHECK_ONLY}" -eq 1 ]; then
        echo "error: existing .venv uses Python ${VENV_PYVER}; Python ${MIN_PY_MAJOR}.${MIN_PY_MINOR}+ is required" >&2
        python_install_hint
        exit 1
      fi
      echo "[venv] Existing .venv uses Python ${VENV_PYVER}; recreating with ${PYBIN}"
      rm -rf .venv
    fi
  fi
fi

if [ "${CHECK_ONLY}" -eq 1 ]; then
  echo "[venv] Interpreter check passed"
  exit 0
fi

if [ ! -d ".venv" ]; then
  echo "[venv] Creating .venv"
  "${PYBIN}" -m venv .venv
fi

# Keep pip/setuptools/wheel fresh.
echo "[venv] Upgrading pip tooling"
.venv/bin/python -m pip install --upgrade pip setuptools wheel >/dev/null

echo "[venv] Installing requirements.txt"
.venv/bin/python -m pip install -r requirements.txt

echo "[venv] Done. Activate with:  source .venv/bin/activate"
echo "[venv] Ansible version:"
.venv/bin/ansible --version 2>/dev/null | head -3 || echo "  (ansible not on PATH in venv yet)"

# Ensure inventory/hosts.yml exists so syntax checks/lint pass without the lab.
if [ ! -f "inventory/hosts.yml" ]; then
  echo "[venv] Seeding inventory/hosts.yml from hosts.example.yml"
  cp inventory/hosts.example.yml inventory/hosts.yml
fi
