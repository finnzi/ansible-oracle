"""Static contract for the full-lab post-boot startup proof."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_full_lab_power_cycles_before_read_only_autostart_verification():
    e2e = (REPO_ROOT / "scripts/run-e2e-full-lab.sh").read_text(encoding="utf-8")
    verifier_path = REPO_ROOT / "scripts/verify-lab-autostart.sh"
    verifier = verifier_path.read_text(encoding="utf-8")

    down = e2e.index("./lab/scripts/lab-down.sh")
    up = e2e.index("./lab/scripts/lab-up.sh", down)
    verify = e2e.index("./scripts/verify-lab-autostart.sh", up)
    tests = e2e.index("./scripts/run-tests.sh", verify)

    assert down < up < verify < tests
    assert verifier_path.stat().st_mode & 0o111
    assert "VERIFY_TIMEOUT_SECONDS" in verifier
    assert "discover_dg_members" in verifier
    assert "database_resource_profile" in verifier
    assert "USR_ORA_INST_NAME" in verifier
    assert "GEN_USR_ORA_INST_NAME" in verifier
    assert "ORACLE_HOME" in verifier
    assert "DG_UNIQUES" in verifier
    assert "PRIMARY_INDEX" in verifier
    assert "STANDBY_INDEX" in verifier
    assert "Exactly one PRIMARY" in verifier
    assert "Oracle home:" in verifier
    assert "Database role: ${role}" in verifier
    assert "PHYSICAL STANDBY|READ ONLY WITH APPLY" in verifier
    assert "PRIMARY|READ WRITE" in verifier
    assert "Listener LISTENER_SUPER is running" in verifier
    assert "check_service_resource" in verifier
    assert "super_svc" in verifier
    assert "super_stb" in verifier
    assert "duper_svc" in verifier
    assert "fluff_svc" in verifier
    assert "NullPointerException" in verifier
    assert "oracle-fsfo-observer.service" in verifier
    assert "SHOW FAST_START FAILOVER" in verifier
    assert "Fast-Start Failover: Enabled" in verifier
    assert "Protection Mode:    MaxAvailability" in verifier
    assert "Observer:[[:space:]]+\\(none\\)" in verifier
    assert "srvctl status ons" in verifier
    assert "crsctl config has" in verifier
    assert "crsctl check css" in verifier
    assert "srvctl status asm" in verifier
    assert "srvctl status diskgroup -diskgroup RESTART" in verifier
    assert "srvctl config database -db ${db_unique_name} -all" in verifier
    assert "srvctl config listener" in verifier
    assert 'endpoint_line="$(awk' in verifier
    assert '[ "${endpoint_line}" = "IPC:${listener}" ] || ready=1' in verifier
    assert 'End points: /IPC:${listener}' not in verifier
    assert 'ANSIBLE_ORACLE_SOCKET=' in verifier
    assert 'sed -n \'s/^ANSIBLE_ORACLE_SOCKET=//p\'' in verifier
    assert "srvctl config service" in verifier
    assert "Management policy: AUTOMATIC" in verifier
    assert "Database is enabled" in verifier
    assert "Listener is enabled" in verifier
    assert "Service is enabled" in verifier
    assert "env ORACLE_HOME=${oracle_home}" in verifier
    assert "crsctl status resource ora.${db_unique}.db -p" in verifier
    assert 'resource="ora.${db_unique}.${service}.svc"' in verifier
    assert "MANAGEMENT_POLICY=AUTOMATIC" in verifier
    assert "PHYSICAL_STANDBY" in verifier
    assert "USR_ORA_OPEN_MODE=${start_option}" in verifier
    assert "dbhome_1" not in verifier
    assert verifier.count("/grid/19c/gi_home1") == 1
    assert '${GI_HOME}/bin/crsctl check has' in verifier

    # The proof must observe the boot result, never repair it.
    assert "srvctl start" not in verifier
    assert "lsnrctl start" not in verifier
    assert "crsctl start" not in verifier
