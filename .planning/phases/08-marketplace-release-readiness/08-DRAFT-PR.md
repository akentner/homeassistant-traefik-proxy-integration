# Draft: Draft PR `feat/marketplace-polish` -> `main`

For the manager (M41). The manager pushes `feat/marketplace-polish` after phase
verification and opens this as a **Draft** PR against `main`. No agent has
pushed, tagged or opened a PR.

Suggested command for the manager (not run by the executor):

```bash
gh pr create --draft --base main --head feat/marketplace-polish \
  --title "Traefik Proxy 1.0.0: data layer, entity model, certificates, config flow, marketplace readiness" \
  --body-file <body extracted from the "PR body" section below>
```

## PR title

```
Traefik Proxy 1.0.0: data layer, entity model, certificates, config flow, marketplace readiness
```

## PR body

```markdown
## Summary

Milestone v1.0 of the Traefik Proxy integration: Phases 4–8, ending at
version **1.0.0** (manifest and `pyproject.toml`; CHANGELOG `## [1.0.0] - Unreleased`).
The branch also carries the earlier unpushed security commits from `main`'s
local history (M1).

- **Phase 4 – Data layer (correct + lean):** typed models, one `GET /api/rawdata`
  per cycle with a paginated fallback (rawdata retried hourly), version and
  entrypoints read only when needed, GET-only client, real anonymised fixtures
  from Traefik v2.11 and v3.x.
- **Phase 5 – Entity model + lifecycle:** router and service enum sensors
  (`enabled`/`warning`/`error`/`disabled`/`missing`), entity manager with a
  grace period for vanished items, main device "Traefik (`<host>`)" with
  router/service/certificate sub-devices, entity migration with a persistent
  repair notice, problem aggregates enabled by default.
- **Phase 6 – Certificates:** `/api/certificates` on Traefik 3.7+, otherwise an
  async TLS probe to the Traefik host with SNI; `verified` against HA's trust
  store; live days-until-expiry; "Certificate problems" sensor.
- **Phase 7 – Config flow, HA 2026.11 baseline, observability:** minimum HA
  2026.11.0, auth selection (none/basic/bearer) with config-entry migration,
  `host:port` unique IDs, reauth/reconfigure, options with grace period and the
  per-item entity switch, YAML setup removed, `insecure_credentials` repair,
  diagnostics, German translation.
- **Phase 8 – Marketplace + release readiness:** manifest `categories`
  (`computers_network.monitoring`), version 1.0.0, brand icon/logo/dark logo,
  diagnostics redaction of router-rule secrets, CI pinned and extended
  (minimum-HA job from a hashed lock, `permissions: {}`, schedule/dispatch,
  release tag check), coverage gate 99 %, README and CHANGELOG rewritten.

## Breaking changes (details in CHANGELOG.md, "Breaking changes and required actions")

- Home Assistant **2026.11.0** or later is required.
- YAML setup is removed; existing YAML-created entries stay and are managed in the UI.
- Router binary sensors are replaced by router enum sensors (new entity IDs for
  enabled, visible routers); service sensors are enum sensors (IDs kept).
- The reload button and the `traefik_proxy.reload_routers` action are removed;
  use the new **Refresh now** button.
- Authentication type selection; existing entries are migrated automatically.
- Entries are identified by `host:port`; titles are the host.
- Devices are restructured (main device + sub-devices); device areas must be re-assigned.
- Problem aggregates renamed and enabled; their attributes are `problems` / `problem_count`.
- Count, service and entrypoint sensor attributes reduced (see "Removed").
- Certificate entities renamed (entity IDs kept).

## Verification evidence (local, on the final tree of this branch)

| Gate | Result |
|---|---|
| `uv run pytest -q` (coverage gate `fail_under = 99`) | 1152 passed; total coverage 99.29 % |
| `ruff check` / `ruff format --check` / `mypy --strict` | clean |
| Minimum HA 2026.11.0 (`make test-min-ha`, hashed lock) | see 08-LOCAL-VALIDATION.md "Final pre-push run" |
| `uvx pre-commit run --all-files` | see 08-LOCAL-VALIDATION.md "Final pre-push run" |
| hassfest (`make hassfest`, throwaway container, HA 2026.11.1 image) | `Integrations: 1`, `Invalid integrations: 0` |
| hacs/action (10 checks, category `integration`, no `ignore`) | **pending — proven by the first PR run of validate.yml (HACS job)**. Not run locally: it needs a GitHub token, and passing the user's credential to a container was declined (user decision). The overlay harness and the five repository-metadata checks (archived, description, issues, license, topics) were verified without a token. |
| Visual check (throwaway HA 2026.11.0 + Traefik v3.7.19, de/en) | passed: brand images served byte-identical, config flow, options, repairs, device tree, states and icons, 0.3.0 -> 1.0.0 migration (08-VISUAL-CHECK.md) |
| Visual-check findings | F-01 cosmetic (long certificate names truncated in the device card, full name in tooltip); F-02 upstream (HA core logs `Invalid domain <domain>.<platform>` translation warnings after a system-language change; affects core integrations equally, nothing visible) — recorded in `.planning/phases/08-marketplace-release-readiness/deferred-items.md` |

## Planning files

This PR includes `.planning/` (roadmap, requirements, phase plans, summaries,
validation records), like the earlier merges to `main`. The release drafts
(`08-RELEASE-NOTES-v1.0.0.md`, `08-HACS-DEFAULT-PR.md`, this file) live only in
`.planning/phases/08-marketplace-release-readiness/` and are not shipped in
`custom_components/`.

## Checks the first CI run must confirm

From `08-LOCAL-VALIDATION.md` ("Checks the post-push CI run must confirm") and
the manager's notes:

1. **All five `validate.yml` jobs are green:** `lint`, `test`,
   `test-min-ha` (installs the hashed lock `.github/requirements-min-ha.txt` —
   first run of the hashed install on CI), `hassfest`, `hacs`.
2. **`hacs` job (REL-07):** all 10 hacs/action checks pass with the CI
   `github.token` under the workflow's `permissions: {}`. If the action needs a
   read permission, grant the minimum on that job only (e.g. `contents: read`)
   and record it. In particular `brands` and `information` against the pushed
   tree at the PR head ref, and `hacsjson`, `integration_manifest` and
   `integration_categories` read through the GitHub API and raw URLs at that
   ref (encoding, LFS or case issues would only show there).
3. Already green on the public repository: `archived`, `description`,
   `issues`, `license`, `topics`.

Maintenance notes (no action needed for this PR):

- `home-assistant/actions/hassfest` is pinned to a `master` commit
  (`# master (2026-10-26)`); that action has no release tags, so Dependabot may
  not bump it. Bump the SHA manually from time to time.
- The hassfest and hacs actions pull moving container images
  (`ghcr.io/home-assistant/hassfest:latest`, `ghcr.io/hacs/action:main`); a
  failure that appears without a change in this repository may come from a new
  image.

## User actions after merge

1. Merge this PR (squash or merge commit, your choice).
2. On `main`, set the date in `CHANGELOG.md`: `## [1.0.0] - YYYY-MM-DD`.
3. Tag v1.0.0 on that commit (`v` prefix as before; the `Release check`
   workflow compares the tag without `v` with manifest version 1.0.0).
4. Publish the GitHub release "Traefik Proxy 1.0.0" with the body from
   `.planning/phases/08-marketplace-release-readiness/08-RELEASE-NOTES-v1.0.0.md`
   (update the CHANGELOG anchor in it to the dated heading).
5. When `Validate` is green on `main` and the release is published, open the
   `hacs/default` PR following `08-HACS-DEFAULT-PR.md` (personal account, no
   review requests).
6. Manual follow-up (optional, deferred): run the hacs/action negative control
   locally (manifest category `computers_network.bogus` in a temporary copy ->
   failing `integration_categories` check) with `make hacs-action` yourself;
   it needs your token and was not run by an agent.

## Decision for the user

**Logo trademark (open assumption A3/A8):** the shipped `logo.png` /
`dark_logo.png` are the horizontal "traefik proxy" lockup from the MIT-licensed
Traefik dashboard source (`traefik/traefik` @ v3.7.19). The MIT licence covers
the artwork's copyright, not the trademark; **Traefik Labs' trademark
guidelines have not been reviewed** and no permission is claimed (README
"Trademark", `docs/BRAND.md`).

- Keep the logo (current state), or
- Fallback: ship only the icon — delete the four logo PNGs from
  `custom_components/traefik_proxy/brand/` (HA then shows the icon where a logo
  would appear) and adjust `tests/test_brand.py` and `docs/BRAND.md`.

Decide before publishing the release and before the `hacs/default` PR.
```
