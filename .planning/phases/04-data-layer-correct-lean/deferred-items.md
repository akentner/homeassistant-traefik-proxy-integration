## Deferred Items

- Invalid escape sequence in a test docstring emits a SyntaxWarning on recompile
  status: resolved
  **Resolution (08-13):** the docstring line with ``r"@\w+"`` was removed from `tests/test_binary_sensor.py` by `f4bf7d7` (04-04, `git log -S'@\w' -- tests/test_binary_sensor.py`); the file has no `@\w` today. Regression guards: `2fdedc3` (08-03, `tests/test_baseline_guards.py::test_no_syntax_warning_on_compile` compiles `custom_components/`, `tests/` and `scripts/` with SyntaxWarning as an error) and `b6116e5` (08-06, pytest `filterwarnings = error::SyntaxWarning`).
  **What:** `tests/test_binary_sensor.py:35` contains ``r"@\w+"`` inside a non-raw docstring, so Python 3.14 emits `SyntaxWarning: invalid escape sequence '\w'` whenever the file is recompiled (seen as "1 warning" on the first pytest run after the file changes, in both the dev venv and the HA 2026.3 venv).
  **Found by:** 04-02 (pre-existing; not caused by the plan, so left untouched per the scope rule).
  **Fix:** make the docstring raw (`r"""..."""`) or escape the backslash. Fits the Phase 8 docstring sweep.

- invalid_url error text does not mention credentials in the URL
  status: resolved
  **Resolution (08-13):** `6f1ab67` (07-08) added the dedicated error key `url_has_credentials` ("The address contains a user name or password. Remove them from the address and enter them in the authentication fields instead.", en + de) for URLs with embedded credentials, together with the basic-auth selector. `invalid_url` keeps its scheme/host meaning; no further hint needed (D-23).
  **What:** Since 04-08 the user and reconfigure steps answer a URL with embedded credentials (`user:pass@host`) with `invalid_url`, whose text in `translations/en.json` / `strings.json` reads "The URL is malformed. Use the http or https scheme and a non-empty host." A user who pasted a userinfo URL gets no hint that the credentials are the problem.
  **Found by:** 04-08 (translation files are outside the plan's files_modified; error keys must not change).
  **Fix:** extend the `invalid_url` text (en + de) with "and no credentials in the URL; use the token field", or add a dedicated `url_has_credentials` key together with the Phase 7 basic-auth selector.
