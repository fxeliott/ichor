# Contributing to Ichor

Currently a solo project (Eliot + Claude Code). This document captures
conventions so any future contributor (or future-Eliot) can pick up
without surprise.

## Branching

- `main` — protected, only merged via PR
- Feature branches: `feat/<short-slug>` (`feat/wal-g-r2-bucket`)
- Bugfix branches: `fix/<short-slug>`
- Chore branches: `chore/<short-slug>`
- Docs-only: `docs/<short-slug>`

## Commits

[Conventional Commits](https://www.conventionalcommits.org/), in **English**.

```
<type>(<scope>): <subject in imperative mood>

<optional body>

<optional footers>
```

Types: `feat`, `fix`, `chore`, `docs`, `refactor`, `perf`, `test`, `build`,
`ci`, `revert`.

Scopes: `api`, `web`, `claude-runner`, `agents`, `ml`, `ui`, `infra`,
`docs`, `ci`, `security`.

Examples:

```
feat(api): expose /briefings/{id}/audio endpoint
fix(infra): pin AGE clone to release/PG16/v1.5.0 (default branch was unstable)
chore(deps): bump motion 12.38.0 -> 12.39.0
docs(adr): ADR-008 — switch from R2 to B2 (cost analysis)
```

## Pull requests

- One logical change per PR (don't bundle a refactor with a feat unless
  small + entangled)
- All checks must be green before merge: lint, typecheck, build, audit
- Squash-and-merge into main (keeps `git log` linear)
- ADR required for any architecture-level change (anything in `infra/`,
  any new external dep, any breaking API change, any schema migration)

## Code style

| Language | Formatter            | Linter                            |
| -------- | -------------------- | --------------------------------- |
| TS/JS    | Prettier 3           | ESLint 10                         |
| Python   | Ruff (format + lint) | mypy `--strict`                   |
| YAML     | Prettier (basic)     | ansible-lint for `infra/ansible/` |
| Markdown | Prettier             | none                              |

Run locally:

```bash
pnpm format        # write
pnpm format:check  # CI mode
pnpm lint
pnpm typecheck
```

Python (in respective package dirs):

```bash
uv run ruff check --fix .
uv run ruff format .
uv run mypy .
uv run pytest
```

## ADR (Architecture Decision Record)

Mandatory for:

- Adding/removing a service in `infra/ansible/`
- Adding an external dependency that is **paid** or **changes licensing**
- Choosing between two non-trivial architecture alternatives
- Any decision that future-Eliot might second-guess

See `docs/decisions/README.md` for the template.

## Secrets

**Never commit a secret.** All sensitive material lives in `infra/secrets/`,
SOPS-encrypted with age. See `infra/secrets/README.md` for setup.

The `.gitignore` blocks `.env*`, `*.pem`, `*.key`, `secrets/*.dec.*`. CI
runs `trivy fs` (`audit.yml` workflow) — but defense-in-depth: review your
diff before committing.

## Claude Code conventions

- Use `/clear` between unrelated tasks
- For tasks touching > 2 files or with architecture choices: invoke
  `/spec` or planner first
- Always announce destructive commands and ask for confirmation
- Verify with `/verify-no-hallucinate` after non-trivial implementations

## Adding a new model

1. Implement under `packages/ml/src/ichor_ml/<family>/<model>.py`.
2. Register in [`packages/ml/model_registry.yaml`](packages/ml/model_registry.yaml)
   with status `scaffolded`.
3. Write a [model card](packages/ml/model_cards/) (Mitchell 2019 format —
   see [`packages/ml/model_cards/README.md`](packages/ml/model_cards/README.md)).
4. Promote to `live` only after :
   - Cross-validated Brier score on hold-out beats baseline.
   - Calibration plot looks reasonable (95% of bins within ±0.05 of empirical).
   - 30 days of out-of-sample shadow predictions in `predictions_audit`.
5. Update aggregator weights in
   `packages/ml/src/ichor_ml/bias_aggregator.py`.
6. Trigger [RUNBOOK-007](docs/runbooks/RUNBOOK-007-brier-degradation.md) cadence
   for the new model.

## Adding a new collector

1. Implement under `apps/api/src/ichor_api/collectors/<source>.py`.
2. Pure-parse tests in `apps/api/tests/test_<source>_parser.py`.
3. Add a persistence helper in
   `apps/api/src/ichor_api/collectors/persistence.py`.
4. Wire into the CLI
   `apps/api/src/ichor_api/cli/run_collectors.py`.
5. If a new table is needed, add an Alembic migration under
   `apps/api/migrations/versions/000N_<slug>.py`.
6. Register a systemd timer in
   `scripts/hetzner/register-cron-collectors.sh` and run it on Hetzner.

## Voie D — non-negotiable

[ADR-009](docs/decisions/ADR-009-voie-d-no-api-consumption.md) :
**no Anthropic API consumption, ever.** All Claude work goes through the
Max 20x subscription via `apps/claude-runner` + Cloudflare Tunnel. No PR may
introduce `anthropic` SDK code paths or ANTHROPIC_API_KEY environment access
without amending ADR-009 first.

## Legal floors (also non-negotiable)

- **AMF DOC-2008-23** : briefings are research / not personalized advice.
  See [`docs/legal/amf-mapping.md`](docs/legal/amf-mapping.md) for the 5
  design constraints.
- **EU AI Act Article 50** : every screen and every export carries the
  AI-generated disclosure. The `<DisclaimerBanner>` component is
  non-dismissible.
- **Anthropic Usage Policy** : no high-risk decisions taken on behalf of
  the user — every output is "research material to inform a human decision".
