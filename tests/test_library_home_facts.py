"""Unit tests for library/oracle_home_facts.py."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "library" / "oracle_home_facts.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("oracle_home_facts", MODULE_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


home_facts = _load_module()


def test_parse_lspatches_extracts_db_ru_version():
    stdout = """
Oracle Interim Patch Installer version 12.2.0.1.46
Copyright (c) 2026, Oracle Corporation.  All rights reserved.

39034528;Database Release Update : 19.31.0.0.260421 (39034528)
38906621;OJVM RELEASE UPDATE: 19.31.0.0.260421 (38906621)

OPatch succeeded.
"""
    patch_ids, db_ru_id, desc, release_update = home_facts.parse_lspatches(stdout)
    assert patch_ids == ["39034528", "38906621"]
    assert db_ru_id == "39034528"
    assert "Database Release Update" in desc
    assert release_update == "19.31.0.0.260421"


def test_parse_lspatches_19_32():
    stdout = """
39472050;Database Release Update : 19.32.0.0.260721 (39472050)
39222882;OJVM RELEASE UPDATE: 19.32.0.0.260721 (39222882)
OPatch succeeded.
"""
    patch_ids, db_ru_id, desc, release_update = home_facts.parse_lspatches(stdout)
    assert "39472050" in patch_ids
    assert db_ru_id == "39472050"
    assert release_update == "19.32.0.0.260721"
    assert "39472050" in desc


def test_parse_lspatches_empty():
    patch_ids, db_ru_id, desc, release_update = home_facts.parse_lspatches("")
    assert patch_ids == []
    assert db_ru_id is None
    assert desc is None
    assert release_update is None


def test_parse_opatch_version():
    assert (
        home_facts.parse_opatch_version("OPatch Version: 12.2.0.1.46\nOPatch succeeded.")
        == "12.2.0.1.46"
    )
    assert home_facts.parse_opatch_version("no version here") is None


def test_parse_comps_version_from_xml():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <PRD_LIST>
      <COMP NAME="oracle.server" VER="19.0.0.0.0"/>
      <COMP NAME="oracle.rdbms" VER="19.0.0.0.0"/>
    </PRD_LIST>
    """
    assert home_facts.parse_comps_version(xml) == "19.0.0.0.0"


def test_parse_comps_version_malformed_falls_back():
    assert home_facts.parse_comps_version("oracle.server 19.0.0.0.0 junk") == "19.0.0.0.0"
    assert home_facts.parse_comps_version("") is None


def test_gather_home_facts_missing_home(tmp_path: Path):
    facts = home_facts.gather_home_facts(str(tmp_path / "missing"))
    assert facts["exists"] is False
    assert "home" in facts["errors"]


def test_gather_home_facts_with_fixtures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    home = tmp_path / "dbhome_1"
    comps_dir = home / "inventory" / "ContentsXML"
    comps_dir.mkdir(parents=True)
    (comps_dir / "comps.xml").write_text(
        '<?xml version="1.0"?><PRD_LIST><COMP NAME="oracle.server" VER="19.0.0.0.0"/></PRD_LIST>',
        encoding="utf-8",
    )
    opatch_dir = home / "OPatch"
    opatch_dir.mkdir()
    opatch_bin = opatch_dir / "opatch"
    opatch_bin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    opatch_bin.chmod(0o755)

    def fake_run(cmd, env=None):
        if cmd[-1] == "version":
            return 0, "OPatch Version: 12.2.0.1.46\n", ""
        if cmd[-1] == "lspatches":
            return (
                0,
                "39472050;Database Release Update : 19.32.0.0.260721 (39472050)\n"
                "OPatch succeeded.\n",
                "",
            )
        return 1, "", "unknown"

    monkeypatch.setattr(home_facts, "_run", fake_run)

    facts = home_facts.gather_home_facts(str(home))
    assert facts["exists"] is True
    assert facts["oracle_home_version"] == "19.0.0.0.0"
    assert facts["opatch_version"] == "12.2.0.1.46"
    assert facts["db_ru_patch_id"] == "39472050"
    assert facts["release_update"] == "19.32.0.0.260721"
    assert "39472050" in facts["patch_ids"]
