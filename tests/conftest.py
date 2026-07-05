"""
pytest configuration and fixtures for the ansible-oracle test suite.

The suite runs on the control host and reaches the lab containers over the
published listener port and the /etc/hosts entries written by
lab/scripts/update-hosts.sh. Connection details come from environment
variables with sensible lab defaults.

Tests 01-04 + the standby-first parser unit test are GREEN in the vertical
slice. Tests 05-07 are skipped cleanly until the corresponding roles land.
"""
from __future__ import annotations

import os
import socket
import sys

import pytest


# ── Configuration ──────────────────────────────────────────────────────
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


# Lab connection details. Override via env when running outside the lab.
PRIMARY_HOST = _env("ORACLE_TEST_HOST", "superdb.domain.is")
PRIMARY_PORT = int(_env("ORACLE_TEST_PORT", "1521"))
DB_SERVICE = _env("ORACLE_TEST_SERVICE", "super_svc")
DB_SID = _env("ORACLE_TEST_SID", "super")
SYS_USER = _env("ORACLE_TEST_USER", "system")
SYS_PASSWORD = _env("ORACLE_TEST_PASSWORD", "SysPassword1_")
SSH_USER = _env("ORACLE_TEST_SSH_USER", "root")
SSH_HOST = _env("ORACLE_TEST_SSH_HOST", "superdb1")  # docker exec name


def pytest_configure(config):
    """Register markers used by the suite and make library/ importable."""
    config.addinivalue_line("markers", "slice: part of the vertical slice (must pass)")
    config.addinivalue_line("markers", "scaffolded: depends on a role still being scaffolded")
    config.addinivalue_line("markers", "slow: test may take many minutes")
    # Make library/ importable at collection time so unit tests can import the
    # detectors directly (before any fixture runs).
    lib = os.path.join(REPO_ROOT, "library")
    if os.path.isdir(lib) and lib not in sys.path:
        sys.path.insert(0, lib)


# ── Connection fixtures ────────────────────────────────────────────────
@pytest.fixture(scope="session")
def oracledb():
    """Return the oracledb module, skipping if unavailable."""
    try:
        import oracledb  # noqa: F401
    except ImportError:
        pytest.skip("python-oracledb not installed; run ./scripts/bootstrap-venv.sh")
    return oracledb


@pytest.fixture(scope="session")
def db_conn_kwargs():
    """Connection kwargs for the client service. Tests use SYSDBA via system pwd."""
    return {
        "host": PRIMARY_HOST,
        "port": PRIMARY_PORT,
        "service": DB_SERVICE,
        "user": SYS_USER,
        "password": SYS_PASSWORD,
    }


@pytest.fixture(scope="session")
def db_connection(oracledb, db_conn_kwargs):
    """A live Oracle connection to the client service. Skips if unreachable."""
    if not _port_open(db_conn_kwargs["host"], db_conn_kwargs["port"]):
        pytest.skip(
            f"Listener not reachable at {db_conn_kwargs['host']}:{db_conn_kwargs['port']} "
            "— bring the lab up (lab/scripts/lab-up.sh) and run site.yml first."
        )
    dsn = oracledb.makedsn(
        db_conn_kwargs["host"], db_conn_kwargs["port"],
        service_name=db_conn_kwargs["service"],
    )
    try:
        conn = oracledb.connect(
            user=db_conn_kwargs["user"],
            password=db_conn_kwargs["password"],
            dsn=dsn,
            mode=oracledb.AUTH_MODE_SYSDBA,
        )
    except Exception as exc:
        pytest.skip(f"Could not connect to Oracle: {exc}")
    yield conn
    try:
        conn.close()
    except Exception:
        pass


# ── Docker exec helper ─────────────────────────────────────────────────
@pytest.fixture(scope="session")
def docker_exec():
    """Run a command inside the superdb1 container via docker exec."""
    import subprocess

    def _run(cmd: str, timeout: int = 60) -> subprocess.CompletedProcess:
        full = ["docker", "exec", SSH_HOST, "bash", "-lc", cmd]
        return subprocess.run(full, capture_output=True, text=True, timeout=timeout)

    # Skip the suite cleanly if the container isn't there.
    probe = _run("true")
    if probe.returncode != 0:
        pytest.skip(f"docker exec into {SSH_HOST} failed; is the lab up? {probe.stderr}")
    return _run


def _port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
