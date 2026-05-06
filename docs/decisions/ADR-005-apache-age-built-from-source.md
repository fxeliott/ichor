# ADR-005: Apache AGE built from source against Postgres 16

- **Status**: Accepted
- **Date**: 2026-05-02
- **Decider**: Eliot (autonomy delegation)

## Context

`docs/AUDIT_V3.md` §1 mandated Apache AGE (Apache 2.0 license) as the
knowledge graph extension for Postgres, replacing Kuzu (archived) and Neo4j
Community (GPLv3, contaminates if commercialised Phase 7).

Verified 2026-05-02:

- **No official Ubuntu 24.04 apt package** for Apache AGE.
- **No official PGDG apt package** for AGE either (PGDG ships TimescaleDB,
  pgvector, postgis, etc. but not AGE).
- AGE upstream provides **source releases tagged per Postgres version**:
  e.g. `release/PG16/1.5.0` builds against PG16.

## Decision

Build Apache AGE from source in the Ansible `postgres` role:

```yaml
- name: Clone Apache AGE repo
  ansible.builtin.git:
    repo: https://github.com/apache/age.git
    version: "release/PG{{ postgres_version }}/{{ apache_age_version }}"

- name: Build & install
  ansible.builtin.command: make PG_CONFIG=/usr/bin/pg_config install
```

Pinned version: **AGE 1.5.0** for **PG16** (`release/PG16/1.5.0` tag).

Build deps already installed by `base` role: `build-essential`, `pkg-config`,
`libssl-dev`, plus `bison`, `flex`, `libreadline-dev`, `postgresql-server-dev-16`
added explicitly to the postgres role.

Idempotency check: `stat /usr/lib/postgresql/16/lib/age.so` → skip build if
present.

Failure mode: if the AGE release tag for PG16/1.5.0 doesn't exist (could
happen post-AGE-2.0 release), Ansible `rescue` block fails the playbook with
clear error → Eliot manually inspects available tags at
[github.com/apache/age/releases](https://github.com/apache/age/releases) and
updates `apache_age_version` in `group_vars/all.yml`.

## Consequences

- **+5-10 min** to first Ansible run (compile time on Hetzner CX32, 8 vCPU).
- **Subsequent runs**: skipped via `creates:` check, ~zero overhead.
- **Upgrades**: bump `apache_age_version` var, run with `--tags postgres,age`,
  Ansible re-clones + rebuilds.
- **Risk**: AGE upstream depends on PG ABI; on Postgres point releases (16.1
  → 16.2) `age.so` should remain compatible, but on major (16 → 17) we must
  rebuild against new `pg_config`.

## Alternatives considered

- **Use Neo4j Community 5.26 LTS** — rejected: GPLv3 contaminates if Ichor
  is ever commercialised (AUDIT_V3 §2).
- **Use FalkorDB** — rejected: SSPLv1 (not OSI-approved, MongoDB-style
  proprietary tail).
- **Wait for upstream apt package** — rejected: no roadmap, indefinite delay.
- **Run AGE in a Docker container (separate from Postgres)** — rejected:
  AGE is a Postgres _extension_, must run in the same process as PG to
  manipulate the same data. Containerizing PG separately would lose
  TimescaleDB integration and complicate wal-g backup.

## References

- [`docs/AUDIT_V3.md`](../AUDIT_V3.md) §1, §2 (KG decision rationale)
- [Apache AGE GitHub](https://github.com/apache/age)
- [AGE 1.5.0 release](https://github.com/apache/age/releases/tag/PG16%2Fv1.5.0)
