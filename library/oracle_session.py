#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# library/oracle_session.py
#
# Ansible module: run an arbitrary SQL statement or script against an Oracle
# database via python-oracledb (thin mode), returning rows. Use this for
# parameter/setting *inspection* (e.g. checking sga_target, pga_aggregate_target)
# so the manage role can decide idempotently whether to apply a change.
#
# Mutating SQL should go through sqlplus under the oracle user (so that
# audit trails and trigger semantics match the command-line tools). This
# module is intentionally read-only-leaning; it commits only if `commit: true`.
#
# USAGE
#   - name: What is sga_target right now?
#     oracle_session:
#       service_name: super_svc
#       host: superdb.domain.is
#       username: system
#       password: "{{ oracle_lab_system_password }}"
#       sql: "SELECT name, value FROM v$parameter WHERE name IN ('sga_target','pga_aggregate_target')"
#     register: params
#   - debug: var=params.rows
#
# RETURNS
#   rows:    list[list]    # raw rows
#   columns: list[str]     # column names

from __future__ import annotations

from ansible.module_utils.basic import AnsibleModule

try:
    import oracledb
except ImportError:  # pragma: no cover
    oracledb = None


def run_sql(host, port, service, user, password, role, sql, script, commit):
    if oracledb is None:
        raise RuntimeError("python-oracledb is not installed on the control node.")
    if not sql and not script:
        raise ValueError("one of `sql` or `script` is required")

    dsn = oracledb.makedsn(host, port, service_name=service)
    connect_kwargs = {"user": user, "password": password, "dsn": dsn}
    if role and role.upper() in ("SYSDBA", "SYSOPER", "SYSDG", "SYSASM", "SYSBACKUP"):
        connect_kwargs["mode"] = getattr(oracledb, f"AUTH_MODE_{role.upper()}")

    rows_out: list[list] = []
    columns: list[str] = []
    with oracledb.connect(**connect_kwargs) as conn:
        cur = conn.cursor()
        if script:
            with open(script, "r", encoding="utf-8") as fh:
                sql_text = fh.read()
        else:
            sql_text = sql
        cur.execute(sql_text)
        if cur.description:
            columns = [d[0] for d in cur.description]
            rows_out = [list(r) for r in cur.fetchall()]
        if commit:
            conn.commit()
    return columns, rows_out


def main() -> None:
    module = AnsibleModule(
        argument_spec={
            "service_name": {"type": "str", "required": True},
            "host":         {"type": "str", "required": True},
            "port":         {"type": "int", "default": 1521},
            "username":     {"type": "str", "required": True},
            "password":     {"type": "str", "required": True, "no_log": True},
            "role":         {"type": "str", "default": ""},
            "sql":          {"type": "str", "default": ""},
            "script":       {"type": "str", "default": ""},
            "commit":       {"type": "bool", "default": False},
        },
        supports_check_mode=True,
        mutually_exclusive=[("sql", "script")],
    )
    try:
        columns, rows = run_sql(
            module.params["host"],
            module.params["port"],
            module.params["service_name"],
            module.params["username"],
            module.params["password"],
            module.params["role"],
            module.params["sql"],
            module.params["script"],
            module.params["commit"],
        )
    except Exception as exc:  # noqa: BLE001
        module.fail_json(msg=str(exc))
        return

    module.exit_json(changed=False, columns=columns, rows=rows)


if __name__ == "__main__":
    main()
