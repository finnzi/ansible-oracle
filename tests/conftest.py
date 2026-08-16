"""pytest configuration and fixtures for the ansible-oracle test suite."""
from __future__ import annotations

import os
import shlex
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
SYS_USER = _env("ORACLE_TEST_USER", "sys")
SYS_PASSWORD = _env("ORACLE_TEST_PASSWORD", "SysPassword1_")
SSH_USER = _env("ORACLE_TEST_SSH_USER", "root")
SSH_HOST = _env("ORACLE_TEST_SSH_HOST", "192.168.87.11")
STANDBY_SSH_HOST = _env("ORACLE_TEST_STANDBY_SSH_HOST", "192.168.87.12")
OBSERVER_SSH_HOST = _env("ORACLE_TEST_OBSERVER_SSH_HOST", "192.168.87.13")
SSH_KEY = _env("ORACLE_TEST_SSH_KEY", os.path.expanduser("~/.ssh/lab_oracle"))


def pytest_addoption(parser):
    """Opt-in: fail (do not skip) when the KVM lab is unreachable."""
    parser.addoption(
        "--require-lab",
        action="store_true",
        default=False,
        help="Fail instead of skip when the KVM lab is unreachable.",
    )


def pytest_configure(config):
    """Register markers used by the suite and make library/ importable."""
    config.addinivalue_line("markers", "slice: part of the vertical slice (must pass)")
    config.addinivalue_line("markers", "slow: test may take many minutes")
    # Make library/ importable at collection time so unit tests can import the
    # detectors directly (before any fixture runs).
    lib = os.path.join(REPO_ROOT, "library")
    if os.path.isdir(lib) and lib not in sys.path:
        sys.path.insert(0, lib)


def _lab_required(config=None) -> bool:
    """True when the acceptance suite must fail closed if the lab is down."""
    if config is not None and bool(config.getoption("--require-lab", default=False)):
        return True
    return os.environ.get("ORACLE_TEST_REQUIRE_LAB", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _skip_or_fail(message, request=None):
    """Skip when the lab is optional; fail when --require-lab / env demands it."""
    config = request.config if request is not None else None
    if _lab_required(config):
        pytest.fail(message)
    pytest.skip(message)


# ── Connection fixtures ────────────────────────────────────────────────
@pytest.fixture(scope="session")
def oracledb(request):
    """Return the oracledb module, failing closed in acceptance mode."""
    try:
        import oracledb  # noqa: F401
    except ImportError:
        _skip_or_fail(
            "python-oracledb not installed; run ./scripts/bootstrap-venv.sh",
            request,
        )
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


@pytest.fixture
def db_connection(oracledb, db_conn_kwargs, request):
    """A live Oracle connection to the client service. Skips if unreachable."""
    if not _port_open(db_conn_kwargs["host"], db_conn_kwargs["port"]):
        _skip_or_fail(
            f"Listener not reachable at {db_conn_kwargs['host']}:{db_conn_kwargs['port']} "
            "— bring the lab up (lab/scripts/lab-up.sh) and run site.yml first.",
            request,
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
        _skip_or_fail(f"Could not connect to Oracle: {exc}", request)
    yield conn
    try:
        conn.close()
    except Exception:
        pass


# ── Remote shell helper ────────────────────────────────────────────────
def _ssh_runner(host: str, user: str, key: str):
    """Build a shell-command runner for a lab VM over SSH."""
    import subprocess

    def _run(cmd: str, timeout: int = 60) -> subprocess.CompletedProcess:
        full = [
            "ssh",
            "-F", "/dev/null",
            "-i", SSH_KEY,
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ConnectTimeout=5",
            "-o", "BatchMode=yes",
            f"{user}@{host}",
            f"bash -lc {shlex.quote(cmd)}",
        ]
        return subprocess.run(full, capture_output=True, text=True, timeout=timeout)

    return _run


@pytest.fixture(scope="session")
def require_lab(request):
    """Skip live ansible-playbook tests when the KVM lab is not reachable."""
    _run = _ssh_runner(SSH_HOST, SSH_USER, SSH_KEY)
    probe = _run("true")
    if probe.returncode != 0:
        _skip_or_fail(
            f"KVM lab unreachable; skipping live playbook test. {probe.stderr}",
            request,
        )


@pytest.fixture(scope="session")
def lab_exec(request):
    """Run a shell command on the primary lab VM over SSH."""
    _run = _ssh_runner(SSH_HOST, SSH_USER, SSH_KEY)
    probe = _run("true")
    if probe.returncode != 0:
        _skip_or_fail(
            f"SSH to {SSH_USER}@{SSH_HOST} failed; is the KVM lab up? {probe.stderr}",
            request,
        )
    return _run


@pytest.fixture(scope="session")
def standby_exec(request):
    """Run a shell command on the standby-candidate lab VM over SSH."""
    _run = _ssh_runner(STANDBY_SSH_HOST, SSH_USER, SSH_KEY)
    probe = _run("true")
    if probe.returncode != 0:
        _skip_or_fail(
            f"SSH to {SSH_USER}@{STANDBY_SSH_HOST} failed; is the KVM lab up? "
            f"{probe.stderr}",
            request,
        )
    return _run


@pytest.fixture(scope="session")
def observer_exec(request):
    """Run a shell command on the observer lab VM over SSH."""
    _run = _ssh_runner(OBSERVER_SSH_HOST, SSH_USER, SSH_KEY)
    probe = _run("true")
    if probe.returncode != 0:
        _skip_or_fail(
            f"SSH to {SSH_USER}@{OBSERVER_SSH_HOST} failed; is the KVM lab up? "
            f"{probe.stderr}",
            request,
        )
    return _run


def _port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
