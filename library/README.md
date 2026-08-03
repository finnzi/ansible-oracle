# Custom Ansible modules

Modules live here and are picked up automatically by `ansible.cfg`'s
`library = library` setting.

## oracle_home_facts

Inspect an Oracle home directory and report product/version facts without
connecting to a database:

```yaml
- name: Read dual-home target version
  oracle_home_facts:
    home_path: /fluff/app/oracle/dbhome_2
  register: home
- debug:
    msg: "{{ home.facts.release_update }} ({{ home.facts.db_ru_patch_id }})"
```

Returns under `facts`:

- `exists`, `home_path`
- `oracle_home_version` from `inventory/ContentsXML/comps.xml`
- `release_update`, `db_ru_patch_id`, `db_ru_description` from `opatch lspatches`
- `patch_ids`, `opatch_version`
- `errors` map for partial failures

Pure helpers (`parse_lspatches`, `parse_comps_version`, `gather_home_facts`) are
unit-tested offline so upgrade prepare/cutover can assert 19.31 vs 19.32.

## patch_standbyfirst_info

Inspect an Oracle patch zip and report whether it is **Data Guard Standby-First
Installable**, by parsing the README files bundled inside the zip.

```yaml
- name: Is the DB RU standby-first installable?
  patch_standbyfirst_info:
    zip: "/u01/stage/p39062931_190000_Linux-x86-64.zip"
  register: sf
- debug: var=sf.eligible
```

It can also scan every staged patch zip in a directory:

```yaml
- name: Find staged standby-first candidates
  patch_standbyfirst_info:
    directory: "/u01/stage"
    pattern: "*.zip"
  register: sf_media
- debug: var=sf_media.eligible_patches
```

Returns `eligible` (bool), `components` (per-component verdicts with patch
number, README-derived description, standby-first evidence snippet, and README
path), `patch_inventory` (OPatch `etc/config/inventory.xml` entries with patch
number, description, parent patch number, top-level patch number, and zip path),
`reason` (human-readable summary), and `readme_files_examined`.
Directory scans return `patches`, `eligible_patches`, `ineligible_patches`,
`errors`, and count fields for each category.

**Detection rule.** Oracle documents standby-first eligibility only as prose in
the README — there is no machine-readable flag. The module normalises the
wording ("Standby-First" / "Standby First") and matches:

- **Eligible**: `Data Guard Standby-First Installable`
- **Ineligible**: `non-Data Guard Standby-First Installable` or
  `not Data Guard Standby-First Installable`

A bundle is eligible only if **every** component README is eligible. The
classic disqualifier is OJVM (routinely marked non-standby-first). When the
19.31 OJVM+RU combo is in `download/`, the module will report the DB RU
component as eligible and the OJVM component as ineligible, giving an overall
verdict of **not eligible** with OJVM named as the reason — exactly what the
patching playbook needs to know to fall back to the special MOS procedure.

## oracle_db_facts

Connect to a database with python-oracledb (thin mode) and report open mode,
database role (PRIMARY / PHYSICAL STANDBY), protection mode/level, archive-log
mode, flashback status, force-logging status, db_unique_name, and broker
status. Used by the manage/restart roles for idempotent decisions and by the
test suite for assertions. Connection failure is reported as a fact
(`reachable: false`), not a module failure, so a play can branch on "DB not
created yet".

## oracle_session

Run a single SQL statement or script and return `columns` + `rows`. Read-only
by default; pass `commit: true` for DML. Use it for parameter *inspection*
(sga/pga); mutation should still go through sqlplus under the oracle user to
preserve audit semantics.
