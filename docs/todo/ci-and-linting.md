# CI, Linting & Code Quality Setup

## Linting

### Python (api/, pipeline/)
- [ ] Add root `pyproject.toml` with shared `[tool.ruff]` config
- [ ] Per-service overrides in `api/pyproject.toml` and `pipeline/pyproject.toml` if needed
- [ ] ruff for linting + formatting (replaces black, isort, flake8)
- [ ] mypy or pyright for type checking — per-service config

### JavaScript/TypeScript (app/)
- [ ] ESLint + Prettier config for Expo (React Native) and web app
- [ ] Shared ESLint config if mobile and web are in the same `app/` folder, or separate configs if split

### Terraform (infra/)
- [ ] `terraform fmt` for formatting
- [ ] `tflint` for linting

## Pre-commit Hooks

- [ ] Single `.pre-commit-config.yaml` at repo root
- [ ] ruff + ruff-format scoped to `^(api|pipeline)/`
- [ ] ESLint scoped to `^app/`
- [ ] terraform_fmt scoped to `^infra/`

## CI (GitHub Actions)

- [ ] `.github/workflows/api.yml` — triggered by `api/**` changes; runs ruff, mypy, pytest
- [ ] `.github/workflows/pipeline.yml` — triggered by `pipeline/**` changes; runs ruff, pytest
- [ ] `.github/workflows/app.yml` — triggered by `app/**` changes; runs ESLint, tests
- [ ] `.github/workflows/infra.yml` — triggered by `infra/**` changes; runs terraform fmt/validate
- [ ] Path filters so each workflow only runs when its folder changes
- [ ] Cross-cutting triggers for root config changes (`*.toml`, `*.yml`)

## Open Questions

- Shared Python dependencies between `api/` and `pipeline/` — do they share a virtualenv or separate?
- App structure within `app/` — single Expo project serving mobile + web, or separate projects?
