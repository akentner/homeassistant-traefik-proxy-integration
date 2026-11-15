.PHONY: install-hooks install-pre-commit pre-commit test test-min-ha min-ha-lock lint format typecheck hassfest-sanity hassfest hacs-action clean help

REPO         ?= akentner/homeassistant-traefik-proxy-integration
# Pinned by digest (ghcr.io/home-assistant/hassfest:latest as of 2026-11-09, HA 2026.11.1); bump deliberately.
# CI's home-assistant/actions/hassfest runs the moving :latest tag instead.
HASSFEST_IMG ?= ghcr.io/home-assistant/hassfest@sha256:da6522993280166fe072704989a2b4c33e639e8ceb69c8ab6ad7ec5045c1a1e3
# Pinned by digest (ghcr.io/hacs/action:main as of 2026-10-20); bump deliberately.
# CI's hacs/action runs the moving :main tag instead.
HACS_IMG     ?= ghcr.io/hacs/action@sha256:187499a09c5d41f9f0d42ff80d203ed87b974c028290140913b61e005fb0aab2

help:  ## Show this help.
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install-hooks:  ## Install the standalone pre-commit hook into .git/hooks/pre-commit.
	@cp scripts/pre-commit .git/hooks/pre-commit
	@chmod +x .git/hooks/pre-commit
	@echo "✓ Installed scripts/pre-commit → .git/hooks/pre-commit"
	@echo "  Now runs on every 'git commit'. Bypass with --no-verify if needed."
	@echo "  (Or use the pre-commit framework: make install-pre-commit)"

install-pre-commit:  ## Install pre-commit (the framework) and run pre-commit install.
	@uv tool install pre-commit
	@pre-commit install
	@echo "✓ pre-commit framework installed and hooks wired."

pre-commit:  ## Run all pre-commit hooks on all files (ephemeral pre-commit, nothing installed).
	uvx pre-commit run --all-files

test:  ## Run pytest with the coverage gate (fail_under in pyproject.toml).
	uv run pytest -q tests

min-ha-lock:  ## Regenerate the hashed minimum-HA test lock (.github/requirements-min-ha.txt).
	UV_HTTP_TIMEOUT=300 uv pip compile .github/requirements-min-ha.in --python-version 3.14.2 --python-platform x86_64-manylinux_2_28 --generate-hashes -o .github/requirements-min-ha.txt

test-min-ha:  ## Run the suite on the locked minimum HA (same commands as the CI test-min-ha job).
	uv venv --clear --python 3.14 .venv-min-ha
	uv pip sync --python .venv-min-ha/bin/python --require-hashes .github/requirements-min-ha.txt
	.venv-min-ha/bin/python -m pytest -q tests

lint:  ## Run ruff check + format check.
	uv run ruff check custom_components tests
	uv run ruff format --check custom_components tests

format:  ## Run ruff format (apply).
	uv run ruff format custom_components tests
	uv run ruff check --fix custom_components tests

typecheck:  ## Run mypy --strict.
	uv run mypy --strict custom_components/traefik_proxy

hassfest-sanity:  ## Run local hassfest-style sanity checks (no docker).
	uv run python scripts/hassfest_checks.py all

hassfest:  ## Run hassfest like home-assistant/actions/hassfest (digest-pinned image, read-only tree, throwaway container).
	docker run --rm -v "$(CURDIR)":/github/workspace:ro $(HASSFEST_IMG)

# The action refuses to run without a token. HACS_ACTION_TOKEN must be a
# fine-grained token with read-only access to public repositories (no scopes);
# it is passed to the container by variable name only. Never use the interactive
# `gh auth token` here: it can write to every repository of the account.
hacs-action:  ## Run the hacs/action validators on the LOCAL tree (needs HACS_ACTION_TOKEN: fine-grained, read-only, public repos).
	@if [ -z "$${HACS_ACTION_TOKEN:-}" ]; then \
	  echo "HACS_ACTION_TOKEN is not set: create a fine-grained token with read-only public repository access and export it." >&2; \
	  exit 2; \
	fi; \
	tmp=$$(mktemp -d) || exit 1; \
	trap 'rm -f "$$tmp/files.txt" "$$tmp/hacs_action_local.py"; rmdir "$$tmp"' EXIT; \
	git ls-files -co --exclude-standard > "$$tmp/files.txt" || exit 1; \
	cp scripts/hacs_action_local.py "$$tmp/" || exit 1; \
	INPUT_GITHUB_TOKEN="$$HACS_ACTION_TOKEN" docker run --rm \
	  -e INPUT_GITHUB_TOKEN -e INPUT_CATEGORY=integration -e REPOSITORY_REF=local-tree \
	  -e INPUT_REPOSITORY=$(REPO) -e REPOSITORY=$(REPO) -e GITHUB_REPOSITORY=$(REPO) \
	  -v "$(CURDIR)":/repo:ro -v "$$tmp":/harness:ro \
	  --entrypoint python3 $(HACS_IMG) /harness/hacs_action_local.py

clean:  ## Remove caches and build artefacts.
	@find . -name __pycache__ -prune -exec rm -rf {} +
	@find . -name '.mypy_cache' -prune -exec rm -rf {} +
	@find . -name '.ruff_cache' -prune -exec rm -rf {} +
	@find . -name '.pytest_cache' -prune -exec rm -rf {} +
