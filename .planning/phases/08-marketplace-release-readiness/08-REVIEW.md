---
phase: 08-marketplace-release-readiness
reviewed: 2026-11-15T21:40:19Z
depth: standard
files_reviewed: 44
files_reviewed_list:
  - CHANGELOG.md
  - CLAUDE.md
  - custom_components/traefik_proxy/api.py
  - custom_components/traefik_proxy/cert_coordinator.py
  - custom_components/traefik_proxy/config_flow.py
  - custom_components/traefik_proxy/const.py
  - custom_components/traefik_proxy/coordinator.py
  - custom_components/traefik_proxy/diagnostics.py
  - custom_components/traefik_proxy/entity.py
  - custom_components/traefik_proxy/__init__.py
  - custom_components/traefik_proxy/manifest.json
  - custom_components/traefik_proxy/rules.py
  - custom_components/traefik_proxy/translations/de.json
  - custom_components/traefik_proxy/translations/en.json
  - docs/BRAND.md
  - .github/dependabot.yml
  - .github/requirements-min-ha.in
  - .github/workflows/release.yml
  - .github/workflows/validate.yml
  - .gitignore
  - hacs.json
  - Makefile
  - .pre-commit-config.yaml
  - pyproject.toml
  - README.md
  - scripts/check_release_tag.py
  - scripts/hacs_action_local.py
  - scripts/hassfest_checks.py
  - scripts/pre-commit
  - tests/conftest.py
  - tests/test_baseline_guards.py
  - tests/test_binary_sensor_tls_expiring.py
  - tests/test_brand.py
  - tests/test_cert_coordinator.py
  - tests/test_cert_entity_state.py
  - tests/test_coordinator.py
  - tests/test_diagnostics.py
  - tests/test_entity_manager.py
  - tests/test_migration.py
  - tests/test_release_tag_check.py
  - tests/test_rules.py
  - tests/test_sensor_tls.py
  - tests/test_tls.py
  - tests/traefik/capture.py
findings:
  critical: 1
  warning: 4
  info: 6
  total: 11
  necessity: 0
status: issues_found
---

# Phase 08: Code Review Report

**Reviewed:** 2026-11-15T21:40:19Z
**Depth:** standard
**Files Reviewed:** 44
**Status:** issues_found

## Narrative Findings (AI reviewer)

## Summary

I reviewed the phase 08 diff (`64afd52..HEAD`) of all 44 listed files. The integration code changes are small and mostly correct: the migration DEVICE→USER fix, the rawdata probe clock rename, the cert-entity host handling, and the `redact_rule` tokenizer. A runtime check confirmed that `redact_rule` handles v2 and v3 Header/Query forms, double-quoted escapes, and unparsable rules. The main problems are in the security-sensitive tooling and at the edges of the new features:

- `make hacs-action` gives the developer's full-scope `gh` OAuth token to a mutable `:main` container image. That image is pulled fresh on every run.
- Two of the four "SHA-pinned" CI actions still run mutable Docker images, because their `action.yml` uses `docker://…:main` or an untagged image. I checked this against the pinned SHAs through the GitHub API. The pin does not freeze the code that runs.
- Diagnostics redaction of router `errors` leaks the value of an invalid `HeaderRegexp`/`QueryRegexp`, because Traefik/Go quote it without a matcher call. I reproduced this with the shipped `rules.py`.
- Probe mode now connects only to the first `getaddrinfo` address. Before, `open_connection` tried every address, so this is a regression for IPv6-first names such as `localhost`.

The `necessity-review.md` and `cicd-review-patterns.md` references were read. No necessity findings: the "deliberate defence" guards in `config_flow.py` and `__init__.py` guard data that crosses a trust boundary (stored config entries), which is excluded by the rubric.

## Critical Issues

### CR-01: `make hacs-action` hands the developer's full `gh` token to a mutable third-party image

**File:** `Makefile:5`, `Makefile:53-62`
**Issue:** The recipe runs `INPUT_GITHUB_TOKEN="$$(gh auth token)" docker run --rm --pull always … $(HACS_IMG)` with `HACS_IMG ?= ghcr.io/hacs/action:main`.

- `gh auth token` returns the developer's interactive OAuth token. Its usual scopes are `repo`, `workflow`, `read:org` and `gist`, which means write access to every repository of the account. That includes the private `dotfiles` and SOPS `secrets` repositories named in the user's global CLAUDE.md.
- `--pull always` combined with a moving `:main` tag runs whatever image was pushed last, as root, with that token in its environment. `hacs_action_local.py` then `runpy`-executes `/hacs/action.py` from that image.
- A compromised or malicious upstream push therefore gets a broad, long-lived credential on every local run. In CI the same image only gets a `permissions: {}` `GITHUB_TOKEN`.
- The validation only needs public repository metadata (description, topics, issues, license, archived). That works with no token, or with a fine-grained, read-only, public-repos token.

**Fix:** Do not forward the interactive token. Pin the image by digest:
```make
HACS_IMG ?= ghcr.io/hacs/action@sha256:<digest>   # bump deliberately

hacs-action:
	@tmp=$$(mktemp -d) || exit 1; trap 'rm -rf "$$tmp"' EXIT; \
	git ls-files -co --exclude-standard > "$$tmp/files.txt" || exit 1; \
	cp scripts/hacs_action_local.py "$$tmp/"; \
	docker run --rm \
	  -e INPUT_GITHUB_TOKEN="$${HACS_ACTION_TOKEN:-}" \
	  ... $(HACS_IMG) /harness/hacs_action_local.py
```
`HACS_ACTION_TOKEN` should be an optional fine-grained token with read-only access to public repositories. Without it the run is anonymous, which is enough for metadata reads within the 60 requests per hour limit. Document the variable in the target's help text.

## Warnings

### WR-01: Diagnostics leak secret-bearing `HeaderRegexp`/`QueryRegexp` values through router `errors`

**File:** `custom_components/traefik_proxy/diagnostics.py:58-68` (with `rules.py:has_matcher_call`)
**Issue:** `_redact_error` replaces the verbatim rule and redacts the whole error only when a remaining segment still contains a matcher call. For an invalid regexp, both Traefik versions add the Go `regexp` error after the rule. That error quotes the raw value without any `Name(` prefix:
- v3: `compiling HeaderRegexp matcher: error parsing regexp: missing closing ): `…``
- v2: the same text through gorilla/mux

I reproduced it with the shipped module:
```
rule  = Host(`a.example.com`) && HeaderRegexp(`X-Api-Key`, `^s3cr3t-(`)
error = error while adding rule <rule>: compiling HeaderRegexp matcher: error parsing regexp: missing closing ): `^s3cr3t-(`
diagnostics errors[0] -> "error while adding rule Host(`a.example.com`) && HeaderRegexp(`X-Api-Key`, `**REDACTED**`): compiling HeaderRegexp matcher: error parsing regexp: missing closing ): `^s3cr3t-(`"
```
The secret `^s3cr3t-(` reaches the download, although README.md:335-337 promises that matcher values are replaced. A typo in a header regex is a common way to create exactly this kind of erroring router.

**Fix:** Fail closed for every error that contains rule-derived text. Check whether any literal argument value of the rule's header or query matchers appears in the remaining segments; if one does, redact the error. Simpler and safer: redact the whole error when the router rule contains any header or query matcher at all.
```python
def _redact_error(error: str, rule: str, redacted_rule: str, secret_values: frozenset[str]) -> str:
    segments = error.split(rule) if rule.strip() else [error]
    if any(has_matcher_call(s) or any(v and v in s for v in secret_values) for s in segments):
        return REDACTED
    return redacted_rule.join(segments)
```
Expose `secret_values` (the unquoted contents of the redacted literals) from `rules.py`. Add a test that uses the regexp error text above.

### WR-02: Probe mode connects only to the first resolved address (regression for IPv6-first or multi-address hosts)

**File:** `custom_components/traefik_proxy/cert_coordinator.py:376-401`, `:448`
**Issue:** `_async_resolve_connect_host` calls `getaddrinfo(host, None, type=SOCK_STREAM)` with `AF_UNSPEC` and returns `infos[0][4][0]`. Every probe of the cycle then connects only there. Before phase 08, `asyncio.open_connection(<name>, port)` tried every resolved address in turn.

RFC 6724 ordering usually puts AAAA first. Examples that now break:
- A Traefik API URL like `https://localhost:8443`, which resolves to `::1` first.
- A name with an AAAA record where Traefik listens only on IPv4.

In both cases every certificate probe now fails with `refused` or `timeout`. The API coordinator keeps working, because aiohttp tries all addresses. The tests cannot catch this: `traefik_test_dns` in `tests/conftest.py` returns a single AF_INET tuple.
**Fix:** Keep the "resolve once per cycle" goal but keep the fallback. Either pass all resolved addresses on and let `async_probe_certificate` try them in order until one connects, or prefer the family that the API session already reaches. The minimal form is to return the de-duplicated address list and loop over it in `_async_probe_host`, using the first address that does not fail with `REFUSED`, `TIMEOUT` or `OSERROR`. Add a test where the first address is unreachable.

### WR-03: SHA pins of `hacs/action` and `home-assistant/actions/hassfest` do not pin the executed code

**File:** `.github/workflows/validate.yml:3-6`, `:90`, `:100`; `Makefile:4`, `:50-51`
**Issue:** The workflow header says "Actions are pinned to commit SHAs", and Dependabot is meant to manage the pins. The pinned definitions run mutable images (checked through the GitHub API at the pinned SHAs):
- `hacs/action@d556e736…/action.yml`: `runs: using: docker, image: "docker://ghcr.io/hacs/action:main"`.
- `home-assistant/actions/hassfest@86d45647…/action.yml`: `docker run --rm -v …://github/workspace ghcr.io/home-assistant/hassfest` (implicit `:latest`).

So two of the four "pinned" actions run different code on every run, and Dependabot never sees the change. Locally, `make hassfest` mounts the working tree read-write into `hassfest:latest` with `--pull always`, running as root. In a normal (non-worktree) checkout, a bad image can write `.git/hooks/*` and so execute code on the host on the next commit.
**Fix:**
- Correct the comment, for example: "hassfest and hacs/action run upstream images by tag; their action SHA pins only freeze the wrapper."
- For the local targets, pin by digest (`HASSFEST_IMG ?= ghcr.io/home-assistant/hassfest@sha256:…`) and mount read-only (`-v "$(CURDIR)":/github/workspace:ro`, if hassfest needs no writes).
- In CI, the jobs already run with `permissions: {}`. If full pinning matters, replace the action with a `docker run` of a digest-pinned image.

### WR-04: CI lint and test jobs install dev dependencies without a lock (`uv.lock` is git-ignored)

**File:** `.github/workflows/validate.yml:32`, `:56`; `.gitignore:23`
**Issue:** `uv sync` runs with no `uv.lock` in the repository, so every CI run resolves `ruff`, `mypy`, `pytest-homeassistant-custom-component` and the rest freshly. The header comment says "a developer runs exactly what CI runs". In practice the developer's local `uv.lock`, which is ignored, and CI diverge as soon as anything is released. A new ruff or mypy release can turn `main` red without any code change. With the new nightly `schedule:` this is guaranteed to happen eventually. This is the "non-idempotent install" pattern. Only the min-HA job is locked.
**Fix:** Commit `uv.lock`, remove it from `.gitignore`, and use `uv sync --locked` in CI and in `Makefile`. If tracking the latest HA nightly is intended, keep that in a separate scheduled job with `uv sync --upgrade`, so PR and push runs stay reproducible.

## Info

### IN-01: README promises redacted rule values, but router sensor attributes expose them verbatim

**File:** `README.md:27`, `README.md:333-337`, `README.md:176` (and `custom_components/traefik_proxy/sensor.py:213`, `:219`)
**Issue:** Decision D-29 keeps the `rule` and `errors` state attributes unredacted. These values reach the recorder database and history, and any Home Assistant user, including non-admins, can see them. The README presents redaction as a diagnostics feature without saying that the same values are stored as entity attributes. A user who reads "sensitive rule values redacted" may assume the secrets are not stored.
**Fix:** Add one sentence to the Diagnostics section, for example: "Router sensors keep the full rule and errors as attributes; exclude `sensor.traefik_*router*` from the recorder if your rules contain secrets."

### IN-02: The migration repair issue now depends on the 1.3 step completing

**File:** `custom_components/traefik_proxy/__init__.py:291`, `:320-328`
**Issue:** `minor_version=2` is persisted at line 291, but the `entities_migrated` issue is only raised at line 327, after the 1.2→1.3 step. If anything in between raises, the issue is lost for good, because the next setup sees `minor_version == 2` and `removed == 0`. Examples: an HA-side `async_update_entry` failure, or an unexpected `KeyError`. Before phase 08 the issue was raised immediately after persisting. The current helpers make this unlikely, since they catch `ValueError`.
**Fix:** Raise the issue right after line 291, as before. Keep the existing title re-raise after the 1.3 step; it already handles the title change.

### IN-03: `UnicodeError` from `getaddrinfo` escapes the probe cycle

**File:** `custom_components/traefik_proxy/cert_coordinator.py:390-399`
**Issue:** `socket.getaddrinfo` raises `UnicodeError` for a host label longer than 63 characters or for invalid IDNA. That is not an `OSError`, so it propagates as an "unexpected error" from `_async_update_data` instead of becoming a `ProbeFailure(ProbeError.DNS, …)`. Before phase 08 the same input was classified inside `async_probe_certificate`, which catches `Exception`.
**Fix:** Add `except UnicodeError as err: return ProbeFailure(ProbeError.DNS, f"{type(err).__name__}: {err}")`.

### IN-04: The release check runs after publication and fires twice

**File:** `.github/workflows/release.yml:3-7`
**Issue:** `release: published` runs after the release is already visible to HACS, so a mismatched tag cannot be blocked, only reported. Creating a release from the UI with a new tag also triggers `push: tags`, so the job runs twice.
**Fix:** Keep `push: tags` as the gate and drop the `release` trigger, or document that it is a post-hoc report. Before publishing, run `python3 scripts/check_release_tag.py vX.Y.Z` as part of the release checklist.

### IN-05: `_download` URL parsing in the local HACS overlay is fragile

**File:** `scripts/hacs_action_local.py:111-120`
**Issue:**
- `url[len(RAW_PREFIX):].split("/", 1)[1]` raises `IndexError` for a URL without a path after the ref.
- `refs/heads/<branch>/<path>` is not unwrapped (only `tags/` is), so such a lookup returns `None`. HACS treats that as a missing file, which gives a false failure rather than a false pass.

**Fix:** Guard the split and strip `refs/heads/<x>/` and `refs/tags/<x>/` symmetrically. Return `None` with a `LOCAL OVERLAY` warning for unknown shapes.

### IN-06: Coverage gate and x86-only lock make partial and non-x86 local runs fail

**File:** `pyproject.toml:24`, `:31`; `Makefile` `min-ha-lock`/`test-min-ha`
**Issue:**
- `--cov` in `addopts` together with `fail_under = 99` makes every partial run fail on coverage, for example `uv run pytest tests/test_rules.py`.
- The min-HA lock is compiled for `x86_64-manylinux_2_28` only, so `make test-min-ha` with `--require-hashes` fails on aarch64 machines.

**Fix:** Document `--no-cov` (or `-p no:cov`) for focused runs. Optionally compile the lock with `--universal`, or note in the help text that the target supports x86_64 only.

---

_Reviewed: 2026-11-15T21:40:19Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
