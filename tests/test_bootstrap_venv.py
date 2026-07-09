"""Tests for the project Python virtualenv bootstrap script."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def write_fake_python(bin_dir: Path, name: str, version: str) -> None:
    python = bin_dir / name
    python.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "if [ \"${1:-}\" = \"--version\" ]; then\n"
        f"  echo 'Python {version}'\n"
        "  exit 0\n"
        "fi\n"
        "echo 'fake python should only be used for --version' >&2\n"
        "exit 2\n",
        encoding="utf-8",
    )
    python.chmod(0o755)


def write_broken_python(bin_dir: Path, name: str) -> None:
    python = bin_dir / name
    python.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "echo 'broken python fixture' >&2\n"
        "exit 2\n",
        encoding="utf-8",
    )
    python.chmod(0o755)


def write_fake_bootstrap_python(bin_dir: Path, name: str, version: str) -> None:
    python = bin_dir / name
    python.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "if [ \"${1:-}\" = \"--version\" ]; then\n"
        f"  echo 'Python {version}'\n"
        "  exit 0\n"
        "fi\n"
        "if [ \"${1:-}\" = \"-m\" ] && [ \"${2:-}\" = \"venv\" ]; then\n"
        "  venv_dir=\"$3\"\n"
        "  mkdir -p \"${venv_dir}/bin\"\n"
        "  cat > \"${venv_dir}/bin/python\" <<'PY'\n"
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "if [ \"${1:-}\" = \"--version\" ]; then\n"
        f"  echo 'Python {version}'\n"
        "  exit 0\n"
        "fi\n"
        "if [ \"${1:-}\" = \"-m\" ] && [ \"${2:-}\" = \"pip\" ]; then\n"
        "  exit 0\n"
        "fi\n"
        "exit 2\n"
        "PY\n"
        "  chmod +x \"${venv_dir}/bin/python\"\n"
        "  printf '#!/usr/bin/env bash\\necho ansible fixture\\n' > \"${venv_dir}/bin/ansible\"\n"
        "  chmod +x \"${venv_dir}/bin/ansible\"\n"
        "  exit 0\n"
        "fi\n"
        "echo 'fake python only supports --version and -m venv' >&2\n"
        "exit 2\n",
        encoding="utf-8",
    )
    python.chmod(0o755)


def make_bootstrap_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    scripts_dir = repo / "scripts"
    inventory_dir = repo / "inventory"
    scripts_dir.mkdir(parents=True)
    inventory_dir.mkdir()
    bootstrap = scripts_dir / "bootstrap-venv.sh"
    bootstrap.write_text(
        (REPO_ROOT / "scripts/bootstrap-venv.sh").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    bootstrap.chmod(0o755)
    (repo / "requirements.txt").write_text("", encoding="utf-8")
    (inventory_dir / "hosts.example.yml").write_text("---\nall: {}\n", encoding="utf-8")
    return repo


def run_bootstrap(
    env: dict[str, str],
    *args: str,
    repo_root: Path = REPO_ROOT,
) -> subprocess.CompletedProcess:
    merged_env = os.environ.copy()
    merged_env.update(env)
    return subprocess.run(
        [str(repo_root / "scripts/bootstrap-venv.sh"), *args],
        cwd=repo_root,
        env=merged_env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_bootstrap_check_selects_python_312_or_newer(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_python(bin_dir, "python3.14", "3.14.0")
    write_fake_python(bin_dir, "python3.12", "3.12.1")
    write_fake_python(bin_dir, "python3", "3.11.9")

    result = run_bootstrap({"PATH": f"{bin_dir}:{os.environ['PATH']}"}, "--check")

    assert result.returncode == 0, result.stderr
    assert "[venv] Using python3.14 (3.14.0)" in result.stdout
    assert "[venv] Interpreter check passed" in result.stdout
    assert "Installing requirements.txt" not in result.stdout


def test_bootstrap_check_skips_unusable_auto_candidates(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_broken_python(bin_dir, "python3.14")
    write_fake_python(bin_dir, "python3.12", "3.12.1")

    result = run_bootstrap({"PATH": f"{bin_dir}:{os.environ['PATH']}"}, "--check")

    assert result.returncode == 0, result.stderr
    assert "[venv] Using python3.12 (3.12.1)" in result.stdout


def test_bootstrap_check_rejects_explicit_python_below_312(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_python(bin_dir, "python3.11", "3.11.9")

    result = run_bootstrap(
        {
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "PYTHON": str(bin_dir / "python3.11"),
        },
        "--check",
    )

    assert result.returncode == 1
    assert "Python 3.12+ is required" in result.stderr


def test_bootstrap_check_reports_unusable_explicit_python():
    result = run_bootstrap({"PYTHON": "/bin/false"}, "--check")

    assert result.returncode == 1
    assert "could not execute /bin/false --version" in result.stderr


def test_bootstrap_check_rejects_existing_venv_below_312(tmp_path: Path):
    repo = make_bootstrap_repo(tmp_path)
    venv_bin = repo / ".venv/bin"
    venv_bin.mkdir(parents=True)
    write_fake_python(venv_bin, "python", "3.11.9")

    result = run_bootstrap({}, "--check", repo_root=repo)

    assert result.returncode == 1
    assert "existing" in result.stderr
    assert "uses Python 3.11.9" in result.stderr


def test_bootstrap_recreates_existing_venv_below_312(tmp_path: Path):
    repo = make_bootstrap_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_bootstrap_python(bin_dir, "python3.14", "3.14.0")
    venv_dir = repo / ".venv"
    old_venv_bin = venv_dir / "bin"
    old_venv_bin.mkdir(parents=True)
    write_fake_python(old_venv_bin, "python", "3.11.9")

    result = run_bootstrap(
        {
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
        },
        repo_root=repo,
    )

    assert result.returncode == 0, result.stderr
    assert "Existing" in result.stdout
    assert "uses Python 3.11.9; recreating with python3.14" in result.stdout
    assert "Installing requirements.txt" in result.stdout
    assert subprocess.run(
        [str(venv_dir / "bin/python"), "--version"],
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip() == "Python 3.14.0"
