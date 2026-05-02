# ADR-008: Accept Redis 8.x (apt repo serves 8, not 7)

- **Status**: Accepted
- **Date**: 2026-05-02
- **Decider**: Eliot (autonomy delegation)

## Context

`docs/ARCHITECTURE_FINALE.md` and AUDIT_V3 reference "Redis 7 (AOF
appendfsync everysec)". The Ansible `redis` role installs `redis` from the
official `packages.redis.io` apt repository.

Verified on Hetzner 2026-05-02 after `apt install redis`:

```
redis_version:8.6.2
```

The `packages.redis.io` repo serves Redis **8.x** as the current stable line.
Redis was renamed from 7.4 → 8.0 in mid-2024 alongside the license change
(BSD → RSALv2/AGPLv3 dual-license, "Redis Source Available License").

## Decision

Accept Redis 8.6.2. The Ichor codebase needs no change:

- **API compatibility**: Redis 8 is wire-compatible with Redis 7 for all
  commands we use (Streams, AOF, hashes, sorted sets, pub/sub).
- **AOF persistence** (our requirement, AUDIT_V3): unchanged in 8.x.
- **License risk for Ichor**: RSALv2 / AGPLv3 dual is **OK for self-host
  internal use** (which is our case — Redis runs on Hetzner, Ichor app
  consumes via wire protocol from same VM). License only restricts
  cloud-hosting Redis as a service to other customers, which we don't.

The plan's "Redis 7" reference is treated as informational, not normative.
Update `group_vars/all.yml`:

```yaml
# Was: redis_version: "7"
# Now: redis_version: "8"  (apt repo serves 8.x as current stable)
```

## Consequences

- **No code changes** in Ichor app (no Redis 8-specific feature used yet).
- **AGPLv3 contagion risk** : zero, because we only **link to Redis over
  TCP** (network protocol = no derivative work). If we ever fork Redis
  source, AGPLv3 obligations apply.
- **Migration path**: when/if upstream releases Redis 9, re-evaluate.

## Alternatives considered

- **Pin Redis 7.4 (last 7.x)** — rejected: would require pinning to a
  specific apt package version that's no longer maintained by Redis Labs;
  receiving security patches becomes manual.
- **Use Valkey (Redis fork by Linux Foundation, BSD-3)** — viable
  alternative if AGPLv3 ever becomes a problem. Valkey 8.0 is wire-compat.
  Documented for future ADR-XXX if we migrate.

## References

- [Redis 8.0 release notes](https://redis.io/blog/redis-8-0-released/)
- [Redis license FAQ](https://redis.io/legal/licenses/)
- [Valkey project](https://valkey.io/)
