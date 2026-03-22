---
status: complete
priority: p2
issue_id: "017"
tags: [code-review, alembic, migrations, dx, tooling, agents]
dependencies: [016]
---

# Add `make migrate-check`, `make migrate-current`; update AGENTS.md

## Problem Statement

Two migration capabilities needed by developers and CI pipelines are completely missing from the Makefile: drift detection (`alembic check`) and version introspection (`alembic current`). Additionally, `AGENTS.md` — the authoritative reference for project operations — was not updated to document the new migration commands, making them invisible to any agent or new developer consulting it.

`alembic check` is especially important before Phase 4 lands five new models simultaneously — it's the automated gate that catches "model added, migration forgotten" before a PR merges.

## Findings

### 1. No `make migrate-check` target

`alembic check` exits non-zero when SQLAlchemy model metadata has drifted from the migration history. Without a Makefile target, neither a developer nor CI can run this check without manually constructing the Docker command. This gap will become critical during Phase 4 when `Usuario`, `Programa`, `Curso`, `Inscripcion`, and `EnlaceInvitacion` are all added in sequence — each new model needs a corresponding migration, and drift is easy to miss.

### 2. No `make migrate-current` target

`alembic current` shows which revision is applied to the live database. Without this, diagnosing migration state requires opening a psql shell or inspecting `alembic_version` directly.

### 3. `AGENTS.md` not updated

`AGENTS.md` is the system-prompt equivalent for this project — both human developers and agents consult it for authoritative command references. The "Common Commands" section was not updated with `make migrate`, `make migrate-down`, `make revision`, or the new targets above.

## Proposed Solutions

### Makefile additions

```makefile
migrate-check:
    docker compose run --rm -e PYTHONPATH=/app api alembic check

migrate-current:
    docker compose run --rm -e PYTHONPATH=/app api alembic current
```

Add both to `.PHONY`.

### AGENTS.md update

Add a "Migrations" section to the Common Commands table:

```markdown
| `make migrate`          | Apply all pending Alembic migrations |
| `make migrate-down`     | Roll back one migration step         |
| `make migrate-check`    | Fail if models have drifted from migrations |
| `make migrate-current`  | Show current migration version in DB |
| `make revision MSG="…"` | Generate a new autogenerate migration |
```

Also add a note: "Always run `make migrate-check` before opening a PR that adds or modifies SQLAlchemy models."

## Acceptance Criteria

- [ ] `make migrate-check` runs `alembic check` via Docker and exits non-zero on drift
- [ ] `make migrate-current` runs `alembic current` via Docker
- [ ] Both targets listed in `.PHONY`
- [ ] `AGENTS.md` Common Commands section documents all migration targets
- [ ] `make migrate-check` added to the `lint` workflow or a pre-PR checklist in `AGENTS.md`

## Work Log

- 2026-03-22: migrate-check flagged as P2 by agent-native-reviewer; migrate-current as P3; AGENTS.md as P3. Grouped here as P2 given importance of drift detection before Phase 4.
