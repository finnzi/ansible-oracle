#!/usr/bin/env bash
# scripts/bootstrap-venv.sh
#
# Create the project's Python virtualenv at .venv using the system Python
# (3.14 on the lab host), and install requirements.txt into it.
#
# Per the agreed design: use the host's already-installed Python 3.14.
# The "python 3.12 should be available" requirement is satisfied because
# 3.14 > 3.12, and Ansible + python-oracledb both support it.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "${REPO_DIR}"

PYBIN="${PYTHON:-}"
if [ -z "${PYBIN}" ]; then
  for cand in python3.14 python3.13 python3.12 python3; do
    if command -v "${cand}" >/dev/null 2>&1; then
      PYBIN="${cand}"
      break
    fi
  done
fi

if [ -z "${PYBIN}" ]; then
  echo "error: no python3 found on PATH" >&2
  exit 1
fi

PYVER="$("${PYBIN}" --version 2>&1 | awk '{print $2}')"
echo "[venv] Using ${PYBIN} (${PYVER})"

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
