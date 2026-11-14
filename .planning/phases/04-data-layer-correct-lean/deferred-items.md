## Deferred Items

- Invalid escape sequence in a test docstring emits a SyntaxWarning on recompile
  status: open
  **What:** `tests/test_binary_sensor.py:35` contains ``r"@\w+"`` inside a non-raw docstring, so Python 3.14 emits `SyntaxWarning: invalid escape sequence '\w'` whenever the file is recompiled (seen as "1 warning" on the first pytest run after the file changes, in both the dev venv and the HA 2026.3 venv).
  **Found by:** 04-02 (pre-existing; not caused by the plan, so left untouched per the scope rule).
  **Fix:** make the docstring raw (`r"""..."""`) or escape the backslash. Fits the Phase 8 docstring sweep.
