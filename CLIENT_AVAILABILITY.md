# Native Oracle Client Availability Across Data Guard Switchovers

## Decision

For applications whose only shared integration point is `tnsnames.ora`, use:

- an Oracle Restart service named `<instance>_pri` with role `PRIMARY`;
- an Oracle Restart service named `<instance>_stb` with role
  `PHYSICAL_STANDBY` for licensed Active Data Guard reads;
- both site listener addresses in each client alias;
- OCI Transparent Application Failover on the primary alias with
  `TYPE=SELECT`, `METHOD=BASIC`, bounded retries, and delay.

This is the most transparent option available from native Oracle Net
configuration alone. `SESSION` reconnects but does not preserve an open fetch.
`SELECT` reconnects and can resume a replayable open cursor. In-flight
transactions still roll back. Session state, LOB/XML use, non-replayable SQL,
and other driver-specific behavior must be tested per application.

Oracle documents the role-based service pattern and automatic service movement
after broker switchovers in [Switchover and Failover Operations](https://docs.oracle.com/en/database/oracle/oracle-database/19/dgbkr/using-data-guard-broker-to-manage-switchovers-failovers.html).
The `SELECT` versus `SESSION` behavior and transaction rollback boundary are in
[Transparent Application Failover](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/transparent-application-failover.html)
and the Oracle Net [local naming parameter reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/netrf/local-naming-parameters-in-tns-ora-file.html).

## Lab Names

The lab declares these services on both Restart databases:

| Service | Data Guard role | Purpose |
| --- | --- | --- |
| `super_pri` | `PRIMARY` | Writable client endpoint with TAF `SELECT/BASIC` |
| `super_stb` | `PHYSICAL_STANDBY` | Active Data Guard read-only endpoint |
| `super_svc` | `PRIMARY` | Backward-compatible existing lab endpoint |

The observer VM also acts as the native Oracle Client test machine. Its
`super_primary` and `super_standby` aliases both list
`superdc1.domain.is:1521` and `superdc2.domain.is:1521`. Only the service whose
role matches the local database is registered at each site.

The generated primary alias is equivalent to:

```text
super_primary =
  (DESCRIPTION =
    (CONNECT_TIMEOUT = 5)
    (TRANSPORT_CONNECT_TIMEOUT = 3)
    (RETRY_COUNT = 30)
    (RETRY_DELAY = 1)
    (ADDRESS_LIST =
      (LOAD_BALANCE = OFF)
      (FAILOVER = ON)
      (ADDRESS = (PROTOCOL = TCP)(HOST = superdc1.domain.is)(PORT = 1521))
      (ADDRESS = (PROTOCOL = TCP)(HOST = superdc2.domain.is)(PORT = 1521)))
    (CONNECT_DATA =
      (SERVER = DEDICATED)
      (SERVICE_NAME = super_pri)
      (FAILOVER_MODE =
        (TYPE = SELECT)
        (METHOD = BASIC)
        (RETRIES = 30)
        (DELAY = 1))))
```

Keep `LOAD_BALANCE=OFF` for this two-site, single-primary address list so a new
connection tries the preferred site first. `FAILOVER=ON` is connect-time
address failover; `FAILOVER_MODE` is TAF after a session has connected.

## Repeatable Proof

Safe service/client reconciliation and prerequisite check:

```bash
scripts/run-client-switchover-test.sh
```

Destructive switchover proof:

```bash
scripts/run-client-switchover-test.sh \
  --execute \
  --confirm CLIENT_SWITCHOVER
```

The proof creates a disposable account, starts a 5,000-row OCI fetch through
`super_primary`, switches the broker primary while that cursor is open,
verifies every sequence exactly once with no Oracle error, runs a post-fetch
statement on the new primary in the same SQL*Plus session, drops the account,
and restores the starting primary. Cleanup and restoration are retried after a
failure because FSFO may need time to initialize its new target.

The live KVM proof on 2026-07-11 fetched all 5,000 rows and continued the same
client session on `super` after switching from `super_sby`; it then restored
`super_sby` as primary. An intentionally non-replayable cursor containing a
site-dependent expression correctly produced `ORA-25401`, which is why the
test and this guidance do not claim arbitrary SQL is transparent.

## Retrofit

For each existing Data Guard member, add both services using that member's
`DB_UNIQUE_NAME`:

```bash
srvctl add service -db <db_unique_name> -service <instance>_pri \
  -role PRIMARY -policy AUTOMATIC -notification TRUE \
  -failovertype SELECT -failovermethod BASIC \
  -failoverretry 30 -failoverdelay 1

srvctl add service -db <db_unique_name> -service <instance>_stb \
  -role PHYSICAL_STANDBY -policy AUTOMATIC -notification TRUE \
  -failovertype NONE -failovermethod NONE

srvctl enable service -db <db_unique_name> -service <instance>_pri
srvctl enable service -db <db_unique_name> -service <instance>_stb
```

Run the commands on every member, start the role-matching service initially,
and prime the standby-role service once on the current primary as Oracle's
broker example requires:

```bash
srvctl start service -db <current_primary_db_unique_name> -service <instance>_stb
srvctl stop service -db <current_primary_db_unique_name> -service <instance>_stb
srvctl start service -db <current_standby_db_unique_name> -service <instance>_stb
```

The Ansible role records this one-time priming step under
`/var/lib/ansible-oracle/services`. Verify `lsnrctl services` before moving
clients. Use application accounts,
not SYS, for acceptance tests. Measure connection pools independently: a pool
may validate, cache, or discard connections differently even when its OCI
connection supports TAF.

## Application Continuity

Application Continuity is the next option to assess for applications using a
supported Oracle driver or connection pool. Oracle explicitly supports it for
physical-standby switchovers and Maximum Availability FSFO, and permits it when
the primary and standby are licensed for RAC or Active Data Guard. The current
environment has Active Data Guard, so licensing does not block that later
application-specific work. It is not a `tnsnames.ora`-only retrofit.

See Oracle's [Data Guard introduction](https://docs.oracle.com/en/database/oracle/oracle-database/19/sbydb/introduction-to-oracle-data-guard-concepts.html)
and [Database Licensing Information](https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/Licensing-Information.html).
