"""
test_library_standbyfirst.py — unit tests for the patch_standbyfirst_info
library module.

This is the GREEN unit test for the standby-first patch eligibility detector,
the requirement the user explicitly called out ("preferably we automatically
read it from the release notes if this is supported or not").

The detector is exercised against:
  - synthetic README HTML for each of Oracle's documented phrasings
    (eligible, ineligible via "non-", ineligible via "not");
  - the real 19.31 combo patches when they are staged under download/
    (skipped gracefully if not staged, so CI on a fresh checkout is green).
"""
from __future__ import annotations

import os
import zipfile

import pytest

# The conftest autouse fixture adds library/ to sys.path.
import importlib

patch_sf = importlib.import_module("patch_standbyfirst_info")
analyze_readme_text = patch_sf.analyze_readme_text
analyze_zip = patch_sf.analyze_zip
scan_directory = patch_sf.scan_directory


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
DOWNLOAD_DIR = os.path.join(REPO_ROOT, "download")


# ── Synthetic-text tests (the core detection logic) ────────────────────
@pytest.mark.slice
class TestReadmePhraseDetection:
    def test_eligible_phrase_is_detected(self):
        text = "<p>This patch is Data Guard Standby First Installable.</p>"
        eligible, evidence = analyze_readme_text(text)
        assert eligible is True
        assert "ELIGIBLE" in evidence

    def test_eligible_with_hyphen_variant(self):
        text = "Accordingly, this patch is Data Guard Standby-First Installable."
        eligible, _ = analyze_readme_text(text)
        assert eligible is True

    def test_ineligible_via_non_prefix(self):
        # The OJVM README wording — this is the classic disqualifier.
        text = "<p>This patch is non-Data Guard Standby-First Installable.</p>"
        eligible, evidence = analyze_readme_text(text)
        assert eligible is False
        assert "INELIGIBLE" in evidence

    def test_ineligible_via_explicit_not(self):
        text = "This patch is not Data Guard Standby First Installable."
        eligible, _ = analyze_readme_text(text)
        assert eligible is False

    def test_no_statement_defaults_to_not_eligible(self):
        # Defensive default: never auto-enable standby-first on absence of evidence.
        eligible, evidence = analyze_readme_text("Nothing relevant here.")
        assert eligible is False
        assert "no Standby-First statement" in evidence

    def test_negative_phrase_wins_over_positive_substring(self):
        # "non-...Installable" contains the positive substring; the negative
        # form MUST take precedence.
        text = (
            "Some preamble. This patch is non-Data Guard Standby-First "
            "Installable. Trailing text."
        )
        eligible, _ = analyze_readme_text(text)
        assert eligible is False

    def test_empty_text(self):
        eligible, evidence = analyze_readme_text("")
        assert eligible is False
        assert "no README text" in evidence

    def test_html_entities_decoded(self):
        # Oracle READMEs use &nbsp; etc. Make sure entity decoding doesn't
        # break the match.
        text = "This&nbsp;patch&nbsp;is&nbsp;Data&nbsp;Guard&nbsp;Standby&nbsp;First&nbsp;Installable."
        eligible, _ = analyze_readme_text(text)
        assert eligible is True


# ── Zip-level tests ────────────────────────────────────────────────────
@pytest.mark.slice
class TestAnalyzeZip:
    def _build_zip(self, tmp_path, layout: dict[str, str]) -> str:
        """layout: {zip_path: contents}"""
        zp = tmp_path / "patch.zip"
        with zipfile.ZipFile(zp, "w") as zf:
            for member, content in layout.items():
                zf.writestr(member, content)
        return str(zp)

    def test_bundle_with_one_ineligible_component_is_overall_ineligible(self, tmp_path):
        # Mirrors the 19.31 combo: DB RU eligible, OJVM ineligible.
        z = self._build_zip(tmp_path, {
            "39062931/README.html":
                "<html>Combo patch overview.</html>",
            "39062931/39034528/README.html":
                "<p>This patch is Data Guard Standby First Installable.</p>",
            "39062931/38906621/README.html":
                "<p>This patch is non-Data Guard Standby-First Installable.</p>",
        })
        result = analyze_zip(z)
        assert result["eligible"] is False
        assert result["readme_files_examined"] >= 2
        descriptions = {c["patch_number"]: c["description"] for c in result["components"]}
        assert descriptions["39034528"] == ""
        assert result["patch_inventory"] == []
        # OJVM should be named in the reason.
        assert "38906621" in result["reason"] or "OJVM" in result["reason"].upper() \
            or "ineligible" in result["reason"].lower()

    def test_bundle_all_eligible_is_overall_eligible(self, tmp_path):
        z = self._build_zip(tmp_path, {
            "12345678/README.html":
                "<p>This patch is Data Guard Standby First Installable.</p>",
            "12345678/12340001/README.html":
                "<p>This patch is Data Guard Standby First Installable.</p>",
        })
        result = analyze_zip(z)
        assert result["eligible"] is True
        assert "all components" in result["reason"]

    def test_missing_zip_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            analyze_zip(str(tmp_path / "does-not-exist.zip"))


@pytest.mark.slice
class TestScanDirectory:
    def _build_zip(self, tmp_path, name: str, layout: dict[str, str]) -> str:
        zp = tmp_path / name
        with zipfile.ZipFile(zp, "w") as zf:
            for member, content in layout.items():
                zf.writestr(member, content)
        return str(zp)

    def test_scan_directory_summarizes_eligible_and_ineligible_zips(self, tmp_path):
        self._build_zip(
            tmp_path,
            "eligible.zip",
            {
                "12345678/README.html": (
                    "<p>This patch is Data Guard Standby First Installable.</p>"
                ),
            },
        )
        self._build_zip(
            tmp_path,
            "ineligible.zip",
            {
                "87654321/README.html": (
                    "<p>This patch is non-Data Guard Standby-First Installable.</p>"
                ),
            },
        )

        result = scan_directory(str(tmp_path))

        assert result["zip_files_examined"] == 2
        assert result["eligible_count"] == 1
        assert result["ineligible_count"] == 1
        assert result["error_count"] == 0
        assert [p["basename"] for p in result["eligible_patches"]] == ["eligible.zip"]
        assert [p["basename"] for p in result["ineligible_patches"]] == [
            "ineligible.zip"
        ]

    def test_scan_directory_reports_bad_zip_without_failing_scan(self, tmp_path):
        (tmp_path / "bad.zip").write_text("not a zip", encoding="utf-8")

        result = scan_directory(str(tmp_path))

        assert result["zip_files_examined"] == 1
        assert result["eligible_count"] == 0
        assert result["ineligible_count"] == 0
        assert result["error_count"] == 1
        assert result["errors"][0]["basename"] == "bad.zip"
        assert "could not read patch zip" in result["errors"][0]["reason"]

    def test_scan_directory_missing_directory_raises(self, tmp_path):
        with pytest.raises(NotADirectoryError):
            scan_directory(str(tmp_path / "missing"))


# ── Real-patch tests (skipped if installers aren't staged) ─────────────
def _real_zip(name: str):
    p = os.path.join(DOWNLOAD_DIR, name)
    return p if os.path.isfile(p) else None


@pytest.mark.slice
def test_real_db_ru_19_31_standbyfirst_verdict():
    """The 19.31 OJVM+DB RU combo: must report NOT eligible (OJVM)."""
    z = _real_zip("p39062931_190000_Linux-x86-64.zip")
    if not z:
        pytest.skip("p39062931 not staged under download/; skipping real-patch test.")
    result = analyze_zip(z)
    # The DB RU component is standby-first installable; OJVM is not. The bundle
    # verdict therefore is NOT eligible.
    assert result["eligible"] is False, (
        f"Expected the OJVM+RU combo to be NOT standby-first (OJVM disqualifies). "
        f"Got: {result}"
    )
    components = {c["name"]: c["standby_first"] for c in result["components"]}
    descriptions = {c["patch_number"]: c["description"] for c in result["components"]}
    # The DB RU sub-component (39034528) should itself be eligible.
    assert components.get("39034528") is True, (
        f"DB RU component should be standby-first installable. Components: {components}"
    )
    assert descriptions["39034528"].startswith("Database Release Update")


@pytest.mark.slice
def test_real_gi_ru_19_31_returns_a_verdict():
    """The 19.31 GI RU: just assert the module produces a verdict either way."""
    z = _real_zip("p39062956_190000_Linux-x86-64.zip")
    if not z:
        pytest.skip("p39062956 not staged under download/; skipping real-patch test.")
    result = analyze_zip(z)
    assert "eligible" in result
    assert isinstance(result["components"], list)
    assert result["readme_files_examined"] >= 1
    inventory = {p["patch_number"]: p for p in result["patch_inventory"]}
    assert {"39034528", "39039430", "39055473", "39107825", "39107855"}.issubset(
        inventory
    )
    assert inventory["39107855"]["description"].startswith("TOMCAT RELEASE UPDATE")
    assert inventory["39107855"]["parent_patch_number"] == "39036936"
