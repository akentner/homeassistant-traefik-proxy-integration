# Phase 8: Local Marketplace validation (D-24)

Both validators ran locally in throwaway Docker containers (`--rm`) against the
unpushed working tree of `feat/marketplace-polish`. Nothing was pushed: no fork,
no temporary repository, no ref (D-24).

## hassfest

| Field | Value |
|---|---|
| Date | 2026-11-15 |
| Plan | 08-08 Task 1 |
| Image | `ghcr.io/home-assistant/hassfest:latest` |
| Digest | `sha256:da6522993280166fe072704989a2b4c33e639e8ceb69c8ab6ad7ec5045c1a1e3` (created 2026-11-09T18:57:27Z) |
| Home Assistant in the image | 2026.11.1 (`homeassistant.const.__version__`) |
| Command | `make hassfest` = `docker run --rm --pull always -v "$(CURDIR)":/github/workspace ghcr.io/home-assistant/hassfest:latest` |
| Exit status | 0 |

The command is the only real step of `home-assistant/actions/hassfest` (research F1),
plus `--pull always` so the local image cannot be staler than CI's (P4).
Output was redirected to a log file and the `make` status checked directly (P11).

Result lines:

```
Integrations: 1
Invalid integrations: 0
```

No `[ERROR]` and no `[WARNING]` line (in particular no manifest key-order error and no
unknown-category warning). No hassfest container remained after the run
(`docker ps -a` before/after identical); `git status` showed no files written by the
container.

Manifest under test (D-01): `version` `1.0.0`, `categories` `["computers_network.monitoring"]`,
keys `domain`, `name`, then alphabetical. `hacs.json` unchanged (`"homeassistant": "2026.11.0"`).

Offline sanity check: `uv run python scripts/hassfest_checks.py all` -> `hassfest-style checks passed`, exit 0.

### Release identity (D-01, D-02)

| Command | Exit | Output |
|---|---|---|
| `python3 scripts/check_release_tag.py v1.0.0` | 0 | `tag v1.0.0 matches manifest.json version 1.0.0` |
| `python3 scripts/check_release_tag.py v1.0.1` | 1 | `::error::tag v1.0.1 (version 1.0.1) != manifest.json version 1.0.0` |
| `python3 scripts/check_release_tag.py vv1.0.0` | 1 | `::error::tag vv1.0.0 (version v1.0.0) != manifest.json version 1.0.0` |

`pyproject.toml` `version = "1.0.0"` agrees with the manifest.

## hacs/action

**Status: BLOCKED. The validator run has not happened yet; no result line exists.**

| Field | Value |
|---|---|
| Date | 2026-11-15 |
| Plan | 08-08 Task 2 |
| Image | `ghcr.io/hacs/action:main` |
| Digest | `sha256:187499a09c5d41f9f0d42ff80d203ed87b974c028290140913b61e005fb0aab2` (created 2026-10-20T07:47:16Z) |
| Command | `make hacs-action` (below) |
| Exit status | not run |

```make
INPUT_GITHUB_TOKEN="$$HACS_ACTION_TOKEN" docker run --rm \
  -e INPUT_GITHUB_TOKEN -e INPUT_CATEGORY=integration -e REPOSITORY_REF=local-tree \
  -e INPUT_REPOSITORY=$(REPO) -e REPOSITORY=$(REPO) -e GITHUB_REPOSITORY=$(REPO) \
  -v "$(CURDIR)":/repo:ro -v <harness>:/harness:ro \
  --entrypoint python3 $(HACS_IMG) /harness/hacs_action_local.py
```

**Token (changed by the 08 review fix CR-01):** the target no longer reads
`gh auth token`. It needs `HACS_ACTION_TOKEN`, a fine-grained token with
read-only access to public repositories, and exits 2 with a hint when the
variable is unset. `HACS_IMG` is pinned by digest
(`ghcr.io/hacs/action@sha256:187499a0…`, the `:main` digest listed above), so
the token only reaches that exact image. The token is passed only by variable
name (`-e INPUT_GITHUB_TOKEN`). It never appears in argv, in the recipe echo
(`@`), in a log or in this file. The harness directory is removed by an `EXIT`
trap, also when a step fails.

### Why blocked

The action exits without a token: it reads one only from `INPUT_GITHUB_TOKEN`
(research F2). The executor's run of `make hacs-action` was **denied by the
Claude Code permission classifier ("Unauthorized Access")** because the target
reads the user's GitHub credential (`gh auth token`) and passes it into a
container. The executor did not work around the denial. It did not use a dummy
token, an unauthenticated client patch or another credential source. A dummy
token would have produced failed GitHub API calls, not a real result.

**To unblock:** the user exports `HACS_ACTION_TOKEN` (fine-grained, read-only,
public repositories) and runs `make hacs-action` once from the repository root. Expected output: the `LOCAL OVERLAY` lines,
then the result line for 10 checks with no failures and no categories warning.
A report of only 5 checks is a failure (P2). The negative control below has to
be repeated with the same token. 08-13 re-runs both validators before the push
in any case.

### What was verified without a token (same image digest, `--network none`)

The harness was built exactly like the Make recipe builds it
(`git ls-files -co --exclude-standard` -> `files.txt` + a copy of the script).
`/hacs/action.py` was stubbed out, so these runs prove only the overlay, not the
validators:

| Probe | Result |
|---|---|
| Overlay applies to this digest | `LOCAL OVERLAY: patched 4 methods; 327 files from /repo`, exit 0 |
| `get_tree` (patched) | `LOCAL OVERLAY: tree from /repo (327 files)`, 378 entries incl. `custom_components/traefik_proxy/brand/icon.png` |
| `async_get_hacs_json` (patched) | `{'name': 'Traefik Proxy', 'homeassistant': '2026.11.0', 'hacs': '2.0.5'}` from the working tree |
| `async_get_integration_manifest` (patched) | `1.0.0 ['computers_network.monitoring']` from the working tree |
| `async_download_file` (patched), raw URL of `brand/icon.png` | 17018 bytes, PNG magic, from the working tree |
| `async_download_file`, raw URL of an ignored file (`.venv/pyvenv.cfg`) | `None`. An ignored file cannot satisfy a check. |
| Fail-closed guard: `HacsIntegrationRepository.async_get_integration_manifest` deleted before the overlay loads | `LOCAL OVERLAY ERROR: HacsIntegrationRepository.async_get_integration_manifest is missing in this image; refusing to run as a no-op`, exit 1 |

All six brand files (`icon.png`, `icon@2x.png`, `logo.png`, `logo@2x.png`,
`dark_logo.png`, `dark_logo@2x.png`) are tracked and therefore in the overlay's file list.

### Negative control (unknown category)

**Not run.** It needs the same token as the positive run. Procedure for the
unblocked run: copy the tracked tree to a temporary directory, set the manifest
category to `computers_network.bogus`, write that copy's own `files.txt`, mount it
as `/repo` and run the same container. Expected: a failed `integration_categories`
check and a non-zero exit status. Then delete the copy.

### GitHub metadata checks against the public repository

The five `allow_fork=False` checks read only live repository metadata. That
metadata was fetched anonymously (no token,
`GET https://api.github.com/repos/akentner/homeassistant-traefik-proxy-integration`,
2026-11-15):

| Check | Requirement | Live value | Verdict |
|---|---|---|---|
| `archived` | not archived | `archived: false` | green |
| `description` | description set | "Home Assistant integration exposing Traefik reverse-proxy state (routers, services, TLS certs) as entities." | green |
| `issues` | issues enabled | `has_issues: true` | green |
| `license` | license present | `MIT` | green |
| `topics` | topics present | `hacs, hass, home-assistant, integration, traefik` | green |
| (precondition) | public repository | `private: false` | green |

## Checks the post-push CI run must confirm

The overlay emulates these, but only the CI run on the pushed ref can prove them (research F2):

1. `brands` and `information` against the **pushed tree** at the PR head ref.
2. `hacsjson`, `integration_manifest` and `integration_categories` read through the
   GitHub API and raw URLs at that ref (encoding, LFS or case issues would only show there).
3. The job runs with the CI `github.token` under the workflow's `permissions`
   (`permissions: {}` in `validate.yml`, 08-07).

Already green on the public repository (see the table above): `archived`,
`description`, `issues`, `license`, `topics`.

Until the local run is unblocked, the post-push CI run is the **only** completed
execution of all 10 hacs/action validators on this tree.

A **GitHub release for 1.0.0** is a catalog requirement checked by humans, not by
the action. It is created by the user (M8, I4/I5: tag `v1.0.0`).

## Final pre-push run (08-13, D-27)

Run on 2026-11-15 by the 08-13 executor on the final code tree (HEAD `435751b`;
the later 08-13 commits change only `.planning/` documents). Commands ran in this
order; each output was redirected to a log and the exit status checked directly.

| # | Command | Exit | Key result line |
|---|---|---|---|
| 1 | `uv run pytest -q` | 0 | `1152 passed, 5 warnings`; `Required test coverage of 99.0% reached. Total coverage: 99.29%`; no `Lingering` |
| 2a | `uv run ruff check custom_components tests` | 0 | `All checks passed!` |
| 2b | `uv run ruff format --check custom_components tests` | 0 | `50 files already formatted` |
| 2c | `uv run mypy --strict custom_components/traefik_proxy` | 0 | `Success: no issues found in 16 source files` |
| 3 | `make test-min-ha` (hashed lock, `homeassistant==2026.11.0`, `pytest-homeassistant==2026.11.0`) | 0 | `1152 passed, 5 warnings`; coverage gate reached (99.29 %) |
| 4 | `~/.cache/traefik-proxy-integration/ha2611-venv/bin/python -m pytest -q -o addopts="-p no:respx" tests` (HA 2026.11.0) | 0 | `1152 passed, 5 warnings` |
| 5 | `uvx pre-commit run --all-files` | 0 | all 13 hooks `Passed` (incl. ruff, mypy --strict, hassfest key order, translations shape) |
| 6 | `make hassfest` (`ghcr.io/home-assistant/hassfest@sha256:da6522993280166fe072704989a2b4c33e639e8ceb69c8ab6ad7ec5045c1a1e3`, same digest as 08-08) | 0 | `Integrations: 1` / `Invalid integrations: 0`; no `[ERROR]`, no `[WARNING]` |
| 7 | `make hacs-action` | **not run** | **REL-07 pending — proven by the first PR run of validate.yml (HACS job).** User decision 2026-11-15: the target needs a user credential (at that time `gh auth token`; since review fix CR-01 `HACS_ACTION_TOKEN`); agents never read or pass any credential. No result line exists locally. |
| 8 | README consistency check (08-10 Task 1 verify: entity keys/names, states, option keys; private-host grep; reload/YAML grep) | 0 / 0 / 0 | `missing: []` |
| 9 | Planning-reference grep over `custom_components/` (`*.py`, `*.json`; 08-03 Task 3) + `pytest tests/test_baseline_guards.py -k "planning_references or doc_links or syntax_warning or multi_second_sleep" --no-cov` | 0 / 0 | no match; `4 passed` |

Docker cleanup after step 6: `docker ps -a`, `docker network ls` and
`docker volume ls` were identical before and after the hassfest run and match
`docker-baseline-phase8.txt` (7 pre-existing containers, networks `bridge`,
`host`, `none`, `winboat_default`, 6 volumes). No container, network or volume
of this phase remains. `git status` showed no file written by the container.

Still open after this run (not satisfiable locally by decision):

- **hacs/action (10 checks, REL-07):** pending the first PR run of
  `validate.yml` (HACS job). The statement in the hacs/action section above that
  "08-13 re-runs both validators before the push" is superseded by the user
  decision of 2026-11-15 (deferred to CI).
- **Negative control (unknown category):** not run; manual follow-up for the
  user (`make hacs-action` on a temporary copy with
  `computers_network.bogus`, expected failing `integration_categories`).

Checks the first CI run must confirm (in addition to the list in "Checks the
post-push CI run must confirm" above): all five `validate.yml` jobs green
(`lint`, `test`, `test-min-ha` with the hashed install, `hassfest`, `hacs`
with `permissions: {}`). The hassfest action is pinned to a `master` commit
(`# master (2026-10-26)`) that Dependabot may not bump; the hassfest and hacs
actions pull moving images.
