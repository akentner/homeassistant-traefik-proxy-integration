# Phase 07 deferred items (out of scope, found during execution)

| Found in | Item | Why deferred | Owner |
|---|---|---|---|
| 07-03 | `.pre-commit-config.yaml` `files:` patterns (lines 47, 58, 65) still match `custom_components/traefik/...`, so the ruff/manifest/translations hooks never fire for `traefik_proxy` | Pre-existing; REL-04 ("pre-commit on Python 3.14 and `traefik_proxy` paths") owns it | Phase 8 (REL-04) |
| 07-03 | `scripts/hassfest_checks.py strings-shape` reports `top-level keys ['entity'] not allowed` for `translations/de.json` and `translations/en.json` (exit 1); `entity` is a valid hassfest key | Pre-existing false positive; plan 07-03 scope guard | Phase 8 (REL-04) |
| 07-03 | `tests/conftest.py` `tls_server` teardown: `await server.wait_closed()` sits after `pytest.fail(...)` inside `if fired.is_set():`, so it never runs | Dead code, no observed failure; changing teardown behaviour is outside 07-03 | Phase 8 (test hygiene, IN-11..IN-14 batch) |
