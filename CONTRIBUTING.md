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

| Language | Formatter | Linter |
|----------|-----------|--------|
| TS/JS    | Prettier 3 | ESLint 10 |
| Python   | Ruff (format + lint) | mypy `--strict` |
| YAML     | Prettier (basic) | ansible-lint for `infra/ansible/` |
| Markdown | Prettier | none |

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
