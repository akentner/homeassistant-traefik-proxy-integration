# Phase 5 deferred items

Out-of-scope discoveries logged by executors; not fixed in the plan that found them.

| Found in | File | Item | Suggested owner | Status |
|---|---|---|---|---|
| 05-06 | README.md:14 | Feature list still names the "reload service", removed in 05-06 | Phase 8 (docs / CHANGELOG) | resolved: `33e6d4f` (08-10 README rewrite; no reload service in the feature list, FAQ states there is no reload action) |
| 05-06 | CLAUDE.md:99 | Stack table still lists `POST /api/http/routers/refresh` as "DIAG-03 reload service"; the integration is GET-only since 05-06 | Regenerate the project CLAUDE.md stack section (Phase 8 or next `generate-claude` run) | resolved: `52f41b2` (08-11 CLAUDE.md regeneration; no `routers/refresh` / DIAG-03 row, GET-only endpoint table) |
