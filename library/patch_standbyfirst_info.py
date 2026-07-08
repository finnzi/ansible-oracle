#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# library/patch_standbyfirst_info.py
#
# Ansible module: determine whether an Oracle patch (zip) is
# "Data Guard Standby-First Installable" by parsing its bundled README files.
#
# WHY THIS EXISTS
#   The patching playbook must, in a Data Guard setup, support standby-first
#   patching (patch standby, switchover, patch the new standby). Whether a
#   given patch is eligible is documented only in the patch README — Oracle
#   does not provide a machine-readable flag. This module automates that
#   detection so the playbook can gate the standby-first branch.
#
# DETECTION RULE (from Oracle's own README wording, verified against the
#   19.31 OJVM+RU combo patches):
#   - Eligible   phrase: "This patch is Data Guard Standby First Installable."
#   - Ineligible phrase: "non-Data Guard Standby-First Installable."
#                       or "not Data Guard Standby First Installable."
#   A bundle (combo patch, GI RU that contains a DB RU, etc.) is eligible only
#   if EVERY component README is eligible. The classic disqualifier is OJVM.
#
# USAGE
#   - name: Is the DB RU standby-first installable?
#     patch_standbyfirst_info:
#       zip: "{{ oracle_stage_dir }}/{{ oracle_patch_files.db_ru_zip }}"
#     register: sf
#   - debug: var=sf
#
# RETURNS
#   eligible:   bool                # overall verdict (AND of components)
#   components: list of {name, patch_number, standby_first, evidence}
#   reason:     str                 # human-readable summary
#   readme_files_examined: int

from __future__ import annotations

import os
import re
import subprocess
import zipfile
from html.parser import HTMLParser

# Defer the Ansible import so the parsing functions (analyze_zip,
# analyze_readme_text) remain importable without Ansible installed — this
# lets the test suite unit-test the detector in isolation.
try:
    from ansible.module_utils.basic import AnsibleModule
except ImportError:  # pragma: no cover — Ansible is present in the venv
    AnsibleModule = None


__all__ = ["analyze_zip", "analyze_readme_text"]


# ── Standby-first phrase detection ────────────────────────────────────
# We normalise whitespace and hyphenation before matching, because Oracle's
# own READMEs mix "Standby-First", "Standby First", and "StandbyFirst".
#
# Order matters: we test the NEGATIVE forms first, because the eligible
# phrase is a substring of "non-...Standby First Installable".
_NEGATIVE_PATTERNS = [
    re.compile(r"non\s*-?\s*Data\s+Guard\s+Standby[-\s]?First\s+Installable", re.I),
    re.compile(r"\bnot\s+Data\s+Guard\s+Standby[-\s]?First\s+Installable", re.I),
    re.compile(r"\bis\s+not\s+Data\s+Guard\s+Standby[-\s]?First\s+Installable", re.I),
]
_POSITIVE_PATTERNS = [
    re.compile(r"\bData\s+Guard\s+Standby[-\s]?First\s+Installable", re.I),
]


class _TextExtractor(HTMLParser):
    """Tiny HTML-to-text converter. Avoids a BeautifulSoup dependency."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip = False  # True inside <script>/<style>

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            self._chunks.append(data)

    def get_text(self) -> str:
        # Collapse whitespace; preserve sentence boundaries.
        text = " ".join(self._chunks)
        text = re.sub(r"\s+", " ", text).strip()
        return text


def _html_to_text(html: str) -> str:
    """Convert HTML (or HTML-fragment) to plain text, decoding entities."""
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        # Malformed HTML shouldn't blow up the module; fall back to tag strip.
        text = re.sub(r"<[^>]+>", " ", html)
    else:
        text = " ".join(parser._chunks)
    # Normalise non-breaking spaces and other unicode whitespace to ASCII
    # space, then collapse runs of whitespace.
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def analyze_readme_text(text: str) -> tuple[bool, str]:
    """
    Inspect README text and return (standby_first_eligible, evidence_snippet).

    Detection precedence:
      1. Any negative match -> not eligible, even if a positive phrase appears.
      2. Otherwise a positive match -> eligible.
      3. Otherwise -> undetermined; treated as not eligible (defensive default
         — never auto-enable standby-first on the basis of absence of evidence).
    """
    if not text:
        return False, "no README text"

    # Always run through _html_to_text: it decodes entities (e.g. &nbsp; ->
    # "\xa0" -> " ") and normalises whitespace, which matters even for inputs
    # that contain no tags at all.
    normalised = _html_to_text(text)

    for pat in _NEGATIVE_PATTERNS:
        m = pat.search(normalised)
        if m:
            # Pull a ~120-char window around the match for evidence.
            start = max(0, m.start() - 40)
            end = min(len(normalised), m.end() + 80)
            return False, f"INELIGIBLE: ...{normalised[start:end].strip()}..."

    for pat in _POSITIVE_PATTERNS:
        m = pat.search(normalised)
        if m:
            start = max(0, m.start() - 40)
            end = min(len(normalised), m.end() + 80)
            return True, f"ELIGIBLE: ...{normalised[start:end].strip()}..."

    return False, "no Standby-First statement found (defaulting to not eligible)"


# ── Zip inspection ────────────────────────────────────────────────────
# A patch zip layout (verified for the 19.31 combo patches):
#   <bugnum>/README.html              # combo overview (often silent on SF)
#   <bugnum>/<component>/README.html  # per-component READMEs (authoritative)
#   <bugnum>/<component>/README.txt   # tiny stub; we still examine it
# We collect every README.{html,txt} under the top-level <bugnum>/ directory
# and treat each as a component. The top-level README is included as the
# "combo" component.

README_RE = re.compile(r"([0-9]+)/README\.(html|txt)$")


def _list_readmes_in_zip(zf: zipfile.ZipFile) -> list[tuple[str, str, str]]:
    """
    Return [(component_name, patch_number, zip_path), ...] for every README
    inside the top-level patch directory.

    The patch_number is the README's immediate parent directory (e.g. for
    `39062931/39036936/39039430/README.html` it's `39039430`), so each distinct
    sub-patch is its own component even when nested inside a bundle. The
    top-level `<bugnum>/README.html` is reported with component="combo".
    """
    out: list[tuple[str, str, str]] = []
    # Find the top-level patch directory (the bug number), e.g. "39062931/".
    top_dirs: set[str] = set()
    for name in zf.namelist():
        top = name.split("/", 1)[0]
        if top.isdigit():
            top_dirs.add(top)

    for name in zf.namelist():
        m = README_RE.search(name)
        if not m:
            continue
        # Skip READMEs that aren't under one of our top-level patch dirs.
        if not any(name.startswith(f"{d}/") for d in top_dirs):
            continue
        patch_num = m.group(1)
        parts = name.split("/")
        component = "combo" if len(parts) == 2 else patch_num
        out.append((component, patch_num, name))
    return out


def _read_zip_member(zf: zipfile.ZipFile, member: str) -> str:
    with zf.open(member) as fh:
        return fh.read().decode("utf-8", errors="replace")


def analyze_zip(zip_path: str) -> dict:
    """
    Open an Oracle patch zip and return the standby-first analysis.

    Returns a dict with keys: eligible, components, reason,
    readme_files_examined. Raises FileNotFoundError / ValueError on bad input.
    """
    if not os.path.isfile(zip_path):
        raise FileNotFoundError(zip_path)

    components: list[dict] = []
    with zipfile.ZipFile(zip_path) as zf:
        readmes = _list_readmes_in_zip(zf)
        # De-duplicate by patch_number, preferring .html over .txt for each.
        seen: dict[str, tuple[str, str, str]] = {}  # patch_num -> (component, path, ext)
        for component, patch_num, path in readmes:
            ext = path.rsplit(".", 1)[-1]
            prev = seen.get(patch_num)
            if prev is None or (prev[2] == "txt" and ext == "html"):
                seen[patch_num] = (component, path, ext)

        for patch_num, (component, path, _ext) in sorted(seen.items()):
            text = _read_zip_member(zf, path)
            eligible, evidence = analyze_readme_text(text)
            components.append(
                {
                    "name": component,
                    "patch_number": patch_num,
                    "standby_first": eligible,
                    "evidence": evidence,
                    "readme": path,
                }
            )

    overall = bool(components) and all(c["standby_first"] for c in components)
    if not components:
        reason = "no README files found in patch zip; cannot determine standby-first eligibility"
    elif overall:
        reason = "all components are Data Guard Standby-First Installable"
    else:
        bad = [c["name"] for c in components if not c["standby_first"]]
        reason = (
            "NOT standby-first installable: component(s) "
            + ", ".join(bad)
            + " are ineligible or silent (OJVM is the classic disqualifier)"
        )

    return {
        "eligible": overall,
        "components": components,
        "reason": reason,
        "readme_files_examined": len(components),
    }


# ── Ansible module entry point ────────────────────────────────────────
def main() -> None:
    if AnsibleModule is None:
        raise SystemExit("ansible.module_utils.basic is required to run as a module")
    module = AnsibleModule(
        argument_spec={
            "zip": {"type": "str", "required": True},
        },
        supports_check_mode=True,
    )
    zip_path = module.params["zip"]

    try:
        result = analyze_zip(zip_path)
    except FileNotFoundError as exc:
        module.fail_json(msg=f"patch zip not found: {exc}")
    except (zipfile.BadZipFile, OSError) as exc:
        module.fail_json(msg=f"could not read patch zip {zip_path}: {exc}")
    except Exception as exc:  # noqa: BLE001 — surface any unexpected error to the user
        module.fail_json(msg=f"unexpected error analysing {zip_path}: {exc}")

    module.exit_json(changed=False, **result)


if __name__ == "__main__":
    main()
