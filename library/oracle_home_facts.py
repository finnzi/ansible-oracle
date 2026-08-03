#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# library/oracle_home_facts.py
#
# Ansible module: inspect an Oracle home and report the base product version,
# installed Database Release Update (when present), and OPatch one-off patch
# IDs. Used by upgrade prepare/cutover playbooks and tests to assert 19.31 vs
# 19.32 without hardcoding only patch IDs in every assertion.
#
# USAGE
#   - name: Read target home version
#     oracle_home_facts:
#       home_path: /fluff/app/oracle/dbhome_2
#     register: home
#   - debug: var=home.facts
#
# RETURNS (under `facts`):
#   home_path:           str
#   exists:              bool
#   oracle_home_version: str|None   # e.g. 19.0.0.0.0 from comps.xml
#   release_update:      str|None   # e.g. 19.32.0.0.260721
#   patch_ids:           list[str]
#   db_ru_patch_id:      str|None
#   db_ru_description:   str|None
#   opatch_version:      str|None
#   errors:              dict

from __future__ import annotations

import os
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    from ansible.module_utils.basic import AnsibleModule
except ImportError:  # pragma: no cover — unit tests import pure helpers
    AnsibleModule = None


__all__ = ["gather_home_facts", "parse_lspatches", "parse_opatch_version", "parse_comps_version"]


_RU_DESC_RE = re.compile(
    r"Database\s+Release\s+Update\s*(?::\s*)?"
    r"(?P<version>19\.\d+\.\d+\.\d+\.\d+)"
    r"(?:\s*\((?P<patch_id>\d+)\))?",
    re.I,
)
_RU_VERSION_ONLY_RE = re.compile(r"\b(19\.\d+\.\d+\.\d+\.\d+)\b")
_PATCH_ID_LINE_RE = re.compile(r"^(?P<patch_id>\d+)\s*;\s*(?P<description>.*)$")
_OPATCH_VERSION_RE = re.compile(r"OPatch\s+Version\s*:\s*(?P<version>\S+)", re.I)
_COMP_VERSION_RE = re.compile(r"\b(19\.\d+\.\d+\.\d+\.\d+)\b")


def parse_lspatches(stdout: str) -> tuple[list[str], str | None, str | None, str | None]:
    """
    Parse `opatch lspatches` output.

    Returns (patch_ids, db_ru_patch_id, db_ru_description, release_update).
    """
    patch_ids: list[str] = []
    db_ru_patch_id: str | None = None
    db_ru_description: str | None = None
    release_update: str | None = None

    for raw in (stdout or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("Oracle Interim Patch Installer") or line.startswith("---"):
            continue
        if "OPatch succeeded" in line or line.startswith("OPatch session"):
            continue
        m = _PATCH_ID_LINE_RE.match(line)
        if not m:
            # Some lspatches variants emit bare IDs; keep digits-only lines.
            if re.fullmatch(r"\d+", line):
                if line not in patch_ids:
                    patch_ids.append(line)
            continue
        patch_id = m.group("patch_id")
        description = m.group("description").strip()
        if patch_id not in patch_ids:
            patch_ids.append(patch_id)
        if "Database Release Update" in description and db_ru_patch_id is None:
            db_ru_patch_id = patch_id
            db_ru_description = description
            ru_match = _RU_DESC_RE.search(description)
            if ru_match:
                release_update = ru_match.group("version")
            else:
                ver_match = _RU_VERSION_ONLY_RE.search(description)
                if ver_match:
                    release_update = ver_match.group(1)
            if release_update is None:
                # Common form: "Database Release Update : 19.32.0.0.260721 (39472050)"
                # already handled; fallback keeps description for callers.
                pass

    return patch_ids, db_ru_patch_id, db_ru_description, release_update


def parse_opatch_version(stdout: str) -> str | None:
    m = _OPATCH_VERSION_RE.search(stdout or "")
    return m.group("version") if m else None


def parse_comps_version(comps_xml: str) -> str | None:
    """Extract the primary oracle.server / oracle.rdbms version from comps.xml."""
    if not comps_xml:
        return None
    try:
        root = ET.fromstring(comps_xml)
    except ET.ParseError:
        # Fall back to a simple version scan.
        m = _COMP_VERSION_RE.search(comps_xml)
        return m.group(1) if m else None

    preferred = (
        "oracle.server",
        "oracle.rdbms",
        "oracle.rdbms.rsf",
    )
    versions: dict[str, str] = {}
    for comp in root.iter():
        name = comp.attrib.get("NAME") or comp.attrib.get("name")
        version = comp.attrib.get("VER") or comp.attrib.get("ver") or comp.attrib.get("VERSION")
        if name and version and re.match(r"^\d+\.\d+", version):
            versions[name] = version
    for key in preferred:
        if key in versions:
            return versions[key]
    # Any 19.x version is better than nothing.
    for version in versions.values():
        if version.startswith("19."):
            return version
    return next(iter(versions.values()), None)


def _run(cmd: list[str], env: dict[str, str] | None = None) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, "", str(exc)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def gather_home_facts(home_path: str) -> dict:
    facts: dict = {
        "home_path": home_path,
        "exists": False,
        "oracle_home_version": None,
        "release_update": None,
        "patch_ids": [],
        "db_ru_patch_id": None,
        "db_ru_description": None,
        "opatch_version": None,
        "errors": {},
    }
    home = Path(home_path)
    if not home_path or not home.is_dir():
        facts["errors"]["home"] = f"ORACLE_HOME does not exist: {home_path}"
        return facts
    facts["exists"] = True

    comps = home / "inventory" / "ContentsXML" / "comps.xml"
    if comps.is_file():
        try:
            facts["oracle_home_version"] = parse_comps_version(comps.read_text(encoding="utf-8", errors="replace"))
        except OSError as exc:
            facts["errors"]["comps"] = str(exc)
    else:
        facts["errors"]["comps"] = f"missing {comps}"

    opatch = home / "OPatch" / "opatch"
    env = os.environ.copy()
    env["ORACLE_HOME"] = home_path
    if opatch.is_file() and os.access(opatch, os.X_OK):
        rc, out, err = _run([str(opatch), "version"], env=env)
        combined = out + "\n" + err
        if rc == 0:
            facts["opatch_version"] = parse_opatch_version(combined)
        else:
            facts["errors"]["opatch_version"] = err.strip() or out.strip() or f"rc={rc}"

        rc, out, err = _run([str(opatch), "lspatches"], env=env)
        if rc == 0 or "OPatch succeeded" in out:
            patch_ids, db_ru_id, db_ru_desc, release_update = parse_lspatches(out)
            facts["patch_ids"] = patch_ids
            facts["db_ru_patch_id"] = db_ru_id
            facts["db_ru_description"] = db_ru_desc
            facts["release_update"] = release_update
        else:
            facts["errors"]["lspatches"] = err.strip() or out.strip() or f"rc={rc}"
    else:
        facts["errors"]["opatch"] = f"OPatch binary missing or not executable: {opatch}"

    return facts


def main() -> None:
    if AnsibleModule is None:  # pragma: no cover
        raise SystemExit("AnsibleModule is required to run this as a module")

    module = AnsibleModule(
        argument_spec={
            "home_path": {"type": "str", "required": True},
        },
        supports_check_mode=True,
    )
    facts = gather_home_facts(module.params["home_path"])
    module.exit_json(changed=False, facts=facts)


if __name__ == "__main__":
    main()
