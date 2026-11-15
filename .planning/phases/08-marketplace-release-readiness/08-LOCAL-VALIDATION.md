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
