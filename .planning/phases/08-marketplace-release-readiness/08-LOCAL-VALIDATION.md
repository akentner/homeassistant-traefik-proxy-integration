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
INPUT_GITHUB_TOKEN="$(gh auth token)" docker run --rm --pull always \
  -e INPUT_GITHUB_TOKEN -e INPUT_CATEGORY=integration -e REPOSITORY_REF=local-tree \
  -e INPUT_REPOSITORY=$(REPO) -e REPOSITORY=$(REPO) -e GITHUB_REPOSITORY=$(REPO) \
  -v "$(CURDIR)":/repo:ro -v <harness>:/harness:ro \
  --entrypoint python3 ghcr.io/hacs/action:main /harness/hacs_action_local.py
```

The token is passed only by variable name (`-e INPUT_GITHUB_TOKEN`). It never
appears in argv, in the recipe echo (`@`), in a log or in this file.

### Why blocked

The action exits without a token: it reads one only from `INPUT_GITHUB_TOKEN`
(research F2). The executor's run of `make hacs-action` was **denied by the
Claude Code permission classifier ("Unauthorized Access")** because the target
reads the user's GitHub credential (`gh auth token`) and passes it into a
container. The executor did not work around the denial. It did not use a dummy
token, an unauthenticated client patch or another credential source. A dummy
token would have produced failed GitHub API calls, not a real result.

**To unblock:** the user runs `make hacs-action` once from the repository root,
or allows this command for the agent. Expected output: the `LOCAL OVERLAY` lines,
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
