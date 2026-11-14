## Deferred Items

- Invalid escape sequence in a test docstring emits a SyntaxWarning on recompile
  status: open
  **What:** `tests/test_binary_sensor.py:35` contains ``r"@\w+"`` inside a non-raw docstring, so Python 3.14 emits `SyntaxWarning: invalid escape sequence '\w'` whenever the file is recompiled (seen as "1 warning" on the first pytest run after the file changes, in both the dev venv and the HA 2026.3 venv).
  **Found by:** 04-02 (pre-existing; not caused by the plan, so left untouched per the scope rule).
  **Fix:** make the docstring raw (`r"""..."""`) or escape the backslash. Fits the Phase 8 docstring sweep.

- invalid_url error text does not mention credentials in the URL
  status: open
  **What:** Since 04-08 the user and reconfigure steps answer a URL with embedded credentials (`user:pass@host`) with `invalid_url`, whose text in `translations/en.json` / `strings.json` reads "The URL is malformed. Use the http or https scheme and a non-empty host." A user who pasted a userinfo URL gets no hint that the credentials are the problem.
  **Found by:** 04-08 (translation files are outside the plan's files_modified; error keys must not change).
  **Fix:** extend the `invalid_url` text (en + de) with "and no credentials in the URL; use the token field", or add a dedicated `url_has_credentials` key together with the Phase 7 basic-auth selector.
