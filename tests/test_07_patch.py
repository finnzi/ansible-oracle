"""
test_07_patch.py — patching assertions.

The standby-first DETECTION is exercised by test_library_standbyfirst.py.
This file asserts the APPLY outcome (opatch lsinventory shows the new patch)
once oracle_patch apply is implemented. SKIPPED in the slice.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.scaffolded


def test_patch_applied_to_db_home(docker_exec):
    pytest.skip(
        "Patch apply is scaffolded. Once implemented, this asserts "
        "`opatch lsinventory` reports the new RU on /super/app/oracle/db_homeN."
    )


def test_dual_home_switch(docker_exec):
    pytest.skip(
        "Dual-home patching is scaffolded. Once implemented, this asserts "
        "srvctl config database -d super points at the NEW home post-switch."
    )
