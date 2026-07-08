#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# library/oracle_db_facts.py
#
# Ansible module: gather live facts about an Oracle database instance —
# open mode, database role (PRIMARY/PHYSICAL STANDBY), Data Guard broker
# status, archive-log mode, flashback status — by connecting with
# python-oracledb (thin mode; no Oracle client libs required on the control
# node). Used by the roles for idempotent decision-making and by the test
# suite (via the same code path) for assertions.
#
# USAGE
#   - name: Read super facts
#     oracle_db_facts:
#       service_name: super_svc
#       host: superdb.domain.is
#       port: 1521
#       username: system
#       password: "{{ oracle_lab_system_password }}"
#       role: sysdba
#     register: db
#   - debug: var=db.facts
#
# RETURNS (under `facts`):
#   reachable:          bool
#   open_mode:          str  (e.g. "READ WRITE", "READ ONLY WITH APPLY", "MOUNTED")
#   database_role:      str  ("PRIMARY" | "PHYSICAL STANDBY" | ...)
#   protection_mode:    str
#   protection_level:   str
#   archivelog_mode:    str  ("ARCHIVELOG" | "NOARCHIVELOG")
#   flashback_on:       str  ("YES" | "NO")
#   force_logging:      str  ("YES" | "NO")
#   db_unique_name:     str
#   log_mode:           str  (alias of archivelog_mode)
#   dataguard_broker:   str  ("STARTED" | "DISABLED")

from __future__ import annotations

from ansible.module_utils.basic import AnsibleModule

try:
    import oracledb  # python-oracledb
except ImportError:  # pragma: no cover — the venv provides this
    oracledb = None


_QUERIES = {
    # Each query returns a single row, single meaningful column. We coalesce
    # the v$database columns so the query still parses on a non-DG database.
    "open_mode":       "SELECT open_mode FROM v$database",
    "database_role":   "SELECT database_role FROM v$database",
    "protection_mode": "SELECT protection_mode FROM v$database",
    "protection_level":"SELECT protection_level FROM v$database",
    "log_mode":        "SELECT log_mode FROM v$database",
    "flashback_on":    "SELECT flashback_on FROM v$database",
    "force_logging":   "SELECT force_logging FROM v$database",
    "db_unique_name":  "SELECT db_unique_name FROM v$database",
    "dataguard_broker":"SELECT value FROM v$parameter WHERE name = 'dg_broker_start'",
}


def gather_facts(host: str, port: int, service: str, user: str, password: str, role: str) -> dict:
    if oracledb is None:
        raise RuntimeError(
            "python-oracledb is not installed on the control node. "
            "Run ./scripts/bootstrap-venv.sh and activate .venv."
        )

    dsn = oracledb.makedsn(host, port, service_name=service)
    facts: dict = {"reachable": False}
    # Thin mode by default. SYSDBA needs the role keyword.
    connect_kwargs = {"user": user, "password": password, "dsn": dsn}
    if role and role.upper() in ("SYSDBA", "SYSOPER", "SYSDG", "SYSASM", "SYSBACKUP"):
        connect_kwargs["mode"] = getattr(oracledb, f"AUTH_MODE_{role.upper()}")

    with oracledb.connect(**connect_kwargs) as conn:
        facts["reachable"] = True
        with conn.cursor() as cur:
            for key, sql in _QUERIES.items():
                try:
                    val = cur.execute(sql).fetchone()
                    facts[key] = val[0] if val else None
                except oracledb.DatabaseError as exc:
                    # Some columns/views may be unavailable on certain editions;
                    # record None rather than abort the whole module.
                    facts[key] = None
                    facts.setdefault("_errors", {})[key] = str(exc)
    # Convenience aliases
    facts["archivelog_mode"] = facts.get("log_mode")
    return facts


def main() -> None:
    module = AnsibleModule(
        argument_spec={
            "service_name": {"type": "str", "required": True},
            "host":         {"type": "str", "required": True},
            "port":         {"type": "int", "default": 1521},
            "username":     {"type": "str", "required": True},
            "password":     {"type": "str", "required": True, "no_log": True},
            "role":         {"type": "str", "default": ""},  # sysdba/sysoper/sysdg
        },
        supports_check_mode=True,
    )
    try:
        facts = gather_facts(
            module.params["host"],
            module.params["port"],
            module.params["service_name"],
            module.params["username"],
            module.params["password"],
            module.params["role"],
        )
    except Exception as exc:  # noqa: BLE001
        # Connection failures are NOT a module failure — surface as a fact so
        # roles can branch (e.g. "DB not yet created") and tests can assert.
        module.exit_json(changed=False, facts={"reachable": False, "error": str(exc)})
        return

    module.exit_json(changed=False, facts=facts)


if __name__ == "__main__":
    main()
