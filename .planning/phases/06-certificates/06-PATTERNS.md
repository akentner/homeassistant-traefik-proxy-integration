# Phase 6: Certificates - Pattern Map

**Mapped:** 2026-11-15
**Files analyzed:** 16 (production 11, tests 5 groups)
**Analogs found:** 15 / 16

All paths are relative to `custom_components/traefik_proxy/` (prod) or the repo root (tests). All analogs are git-tracked.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `models.py` (+`TraefikCertificate`, `parse_certificates`) | model/parser | transform | `models.py` `parse_entrypoints` (362-374), `parse_version` (377-387) | exact |
| `api.py` (+`async_get_certificates`) | service (client) | request-response, paginated | `api.py` `_get_paginated` (217-241) + `async_get_entrypoints` (252-259) | exact |
| `rules.py` (NEW, `extract_hosts`) | utility (pure) | transform | `models.py` pure-module style (header 1-24); replaces `cert_coordinator.py:56` `_HOST_FROM_RULE` | role-match |
| `cert_coordinator.py` (rewrite) | coordinator | batch / event-driven | itself (`_async_update_data` 123-133, host collection 178-214) | exact (self) |
| `tls.py` (rewrite: async probe, DER, verify) | utility | streaming (socket) | itself: `_hostname_matches_san` (213), error set `CertError` (63); `api.py:_request` exception ordering (198-206) | partial |
| `entity.py` (`TraefikCertEntity`, new cert aggregate base) | component base | event-driven | `entity.py` `_TraefikEntityBase` (214-248), `TraefikEntity` (251-255), `TraefikCertEntity` (293-331) | exact |
| `binary_sensor.py` (+`certificates_problem`, reason semantics) | component | event-driven | `binary_sensor.py` `TraefikProblemBinarySensor` (92-115), `TraefikCertExpiringBinarySensor` (118-164) | exact |
| `sensor.py` (`TraefikCertExpirySensor` live days) | component | event-driven | same file, existing `TraefikCertExpirySensor` | exact (self) |
| `entity_manager.py` (cert kinds) | registry helper | event-driven | `CERT_EXPIRY` / `CERT_EXPIRING` KindSpecs (85-86), `async_add_kind` (203-249) | exact — likely unchanged except `keys=` source |
| `const.py` (+`MAX_CERT_HOSTS`, `CERT_FAILURES_FOR_PROBLEM`, `UID_CERTIFICATES_PROBLEM`) | config | — | `const.py` `MAX_PROBLEM_NAMES` / `UID_*_PROBLEM` block (38-46) | exact |
| `__init__.py` (D-23 first refresh) | setup | request-response | `__init__.py` 252-261 (current catch-all to remove) | exact (self) |
| `translations/en.json`, `de.json`, `strings.json`, `icons.json` | config | — | `routers_problem` entries; `icons.json` binary_sensor block (49-) | exact |
| `tests/test_models.py`, `tests/test_api*.py` | test | — | conftest `load_fixture` (57), `stub_traefik` (111-133), `stub_traefik_paginated` (136-158) | exact |
| `tests/test_rules.py` (NEW) | test | — | `tests/test_tls.py` parametrized `test_hostname_matches_san` (~150-175) | role-match |
| `tests/test_tls.py`, `tests/conftest.py` (cryptography-generated local TLS server) | test | streaming | `conftest.py` `mock_certificate_server` (250-) — openssl-based, must be replaced | partial |
| `tests/test_cert_coordinator.py`, `test_cert_entity_state.py`, `test_binary_sensor_tls_expiring.py`, `test_sensor_tls.py`, `test_translations.py` | test | — | same files + `mock_tls_probe` (conftest 211-221), `freezer` usage (`test_devices.py:200-218`) | exact (migrate) |

## Pattern Assignments

### `models.py` — `TraefikCertificate` + `parse_certificates`

Module is pure (stdlib only, no HA imports, header lines 1-13). Shape errors raise `TypeError`/`KeyError`/`ValueError`; the client wraps them. Dataclass style (`models.py:109-125`):
```python
@dataclass(frozen=True, slots=True)
class Entrypoint:
    """An entrypoint; ``protocol`` is ``udp`` or ``tcp``."""
    name: str
    address: str
    protocol: str
```
List-parser template (`models.py:362-374`) and aware-datetime handling (`377-387`):
```python
def parse_entrypoints(payload: object) -> dict[str, Entrypoint]:
    if not isinstance(payload, list):
        raise TypeError(f"expected a list, got {type(payload).__name__}")
    for item in payload:
        if not isinstance(item, Mapping):
            raise TypeError(f"entrypoint must be an object, got {type(item).__name__}")
        name = _required_str(item, "name")
...
    start_date = datetime.fromisoformat(_required_str(payload, key))
    if start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=UTC)
```
Deviation per RESEARCH R-2: a **naive** `notAfter` must be rejected (raise `ValueError`), not coerced. Reuse helpers `_str` (255), `_required_str` (260), `_str_tuple` (267, for `sans`). `issuerCN` is `omitempty` → `_str(...) or None`. Return `tuple[TraefikCertificate, ...]` (no dedupe on `name` — fingerprints are zeroed in the fixture).

### `api.py` — `async_get_certificates`

Combine `_get_paginated` (217-241, reuse unchanged) with the getter wrapper (252-259):
```python
async def async_get_entrypoints(self) -> dict[str, Entrypoint]:
    path = "/api/entrypoints"
    payload, _ = await self._request(path)
    try:
        return parse_entrypoints(payload)
    except (ValueError, TypeError, KeyError) as err:
        raise TraefikProxyPayloadError(path, "unexpected payload shape") from err
```
→ `items = await self._get_paginated("/api/certificates")`, then `parse_certificates(items)` in the same try/except. 404 surfaces as `TraefikProxyNotFoundError` via `_status_error` (136-143) — no special handling in the client; the coordinator branches on it (D-02). Pagination tests: copy `tests/test_api_pagination.py` (`X-Next-Page` headers through `aioclient_mock`).

### `rules.py` (NEW) — `extract_hosts`

Copy the pure-module header convention from `models.py:1-24` (docstring stating "stdlib only, no HA imports", `from __future__ import annotations`). Replaces `cert_coordinator.py:56` and its use at 211-213:
```python
_HOST_FROM_RULE = re.compile(r"Host\(`([^`]+)`\)")
...
for match in _HOST_FROM_RULE.findall(router.rule):
```
New regex must anchor on a non-identifier boundary before `Host(` (exclude `HostRegexp`, `HostSNI`, `HostHeader` unless discretion chooses to include it) and handle multi-arg ``Host(`a`, `b`)``. Return lowercase, de-duped, first-seen order tuple.

### `cert_coordinator.py` (rewrite)

Keep: constructor shape (87-121: `config_entry=entry`, `update_interval=timedelta(seconds=DEFAULT_TLS_CERT_COOLDOWN)`, `self._sem = asyncio.Semaphore(sem)`, `threshold_days`), `async_set_threshold` (164-176, mutate + `async_update_listeners()`), router iteration over `self.config_entry.runtime_data.coordinator.data.routers.values()` with `if not router.tls: continue` (198-214).
Change: data type `dict[str, CertInfo | CertError]` (line 59) → per-host state dataclass (D-14); host collection → `rules.extract_hosts` + sort + `MAX_CERT_HOSTS` cap; cycle = `await client.async_get_certificates()` with `except TraefikProxyNotFoundError` → probe mode, other `TraefikProxyApiError` → `raise UpdateFailed(...) from err`; gather pattern (130-133) stays for probes. Port resolution from `snapshot.entrypoints[name].address` (`models.Entrypoint`, `Router.entry_points`). Connect host = `entity.entry_host(entry)` (`entity.py:53`). Day-boundary timer: use `homeassistant.helpers.event.async_track_point_in_utc_time`, cancel on reschedule and register unsub via `entry.async_on_unload` (same lifecycle style as `entity_manager.py:225` `self._entry.async_on_unload(...)`).

### `tls.py` (rewrite)

Keep `_hostname_matches_san` (213) but fix to single-label wildcard (D-12). Error classification order — copy the "specific before generic" style of `api.py:198-206`:
```python
except aiohttp.InvalidUrlClientError as err: ...
except (aiohttp.ClientError, TimeoutError, OSError) as err: ...
```
Required order: `TimeoutError` → `timeout` (P1), `ssl.SSLError` → `ssl`, `ConnectionRefusedError` → `refused`, `socket.gaierror` → `dns`, `OSError` → `oserror`, else `unknown`. Delete `parse_not_after`, `NOTAFTER_FORMATS`, `CertDict`, `_open_tls_connection`, `_fetch_cert_raw`, `fetch_cert_info*`, `_log_parse_failure_once`. Probe/verify code: RESEARCH.md "Pattern: threadless probe + offline verification" (lines 392-445) — no codebase analog.

### `entity.py` — cert entity + aggregate base

Base to reuse (`entity.py:214-255`): `_TraefikEntityBase[CoordinatorT]` provides device + write-on-change via `_state_token()`. Aggregate on main device bound to cert coordinator = subclass `_TraefikEntityBase[CertCoordinator]` with default `_traefik_device = TraefikDevice.MAIN`, mirroring:
```python
class TraefikEntity(_TraefikEntityBase[TraefikProxyCoordinator]):
    def __init__(self, entry: TraefikProxyConfigEntry, unique_id: str) -> None:
        super().__init__(entry.runtime_data.coordinator, entry, unique_id)
```
→ e.g. `TraefikCertAggregateEntity` passing `entry.runtime_data.cert_coordinator`.
`TraefikCertEntity` (293-331): change `available` (327-328) to `super().available and host in host set` (D-15); `_row()` returns per-host state; `cert_hosts()` (288-290) reads the new state keys. `_state_token` must include live-day-derived values (days/reason), not only the row, so timer notifications write on change.

### `binary_sensor.py` — `certificates_problem` + reason

Aggregate template (`binary_sensor.py:92-115`):
```python
def __init__(self, entry, description) -> None:
    super().__init__(entry, f"{entry.entry_id}_{description.unique_id_suffix}")
...
@property
def extra_state_attributes(self) -> dict[str, Any]:
    problems = self._problems()
    return {"problems": list(problems[:MAX_PROBLEM_NAMES]), "problem_count": len(problems)}
```
Add `reasons: {host: reason}` for listed hosts. Description fields: `translation_key="certificates_problem"`, `device_class=BinarySensorDeviceClass.PROBLEM` (keep the `try/except ImportError` import at 17-19). Add it in `async_setup_entry` (78) next to `PROBLEM_SENSORS`. Not in `PROBLEM_SENSORS` tuple (that is bound to `TraefikSnapshot`), so `test_translations._code_keys` (87-101) must add its class key explicitly. Per-host sensor (118-164): `is_on` becomes the D-15 precedence; attributes add `reason`, `verified`, `source`; `_state_token` keeps `threshold_days`.

### `entity_manager.py`

Cert kinds stay (`entity_manager.py:85-86`, unique_ids unchanged, W34):
```python
CERT_EXPIRY = KindSpec("certificate_expiry", "sensor", "tls_cert_")
CERT_EXPIRING = KindSpec("certificate_expiring", "binary_sensor", "tls_expiring_")
```
Registration call site (`binary_sensor.py:81-88`, same in `sensor.py`): `keys=lambda: cert_hosts(cert_coordinator)`. D-23: with a failed first cycle `coordinator.data` is `None` → `cert_hosts` returns empty → restored hosts would be marked missing; guard in `_async_kind_updated` / keys (skip when `not coordinator.last_update_success`).

### `const.py`

Append next to `MAX_PROBLEM_NAMES` / `UID_*_PROBLEM` (38-46):
```python
UID_MIDDLEWARES_PROBLEM: Final = "diagnostics_any_middleware_failing"
```
→ `UID_CERTIFICATES_PROBLEM: Final = "certificates_problem"`; `MAX_CERT_HOSTS: Final = 200`; `CERT_FAILURES_FOR_PROBLEM: Final = 2` near the TLS knobs (62-64).

### `__init__.py`

Remove lines 252-261 fake success:
```python
try:
    await cert_coordinator.async_config_entry_first_refresh()
except Exception as err:  # final-resort catch-all; ...
    ...
    cert_coordinator.async_set_updated_data({})
```
Use `await cert_coordinator.async_refresh()` (never raises `ConfigEntryNotReady`, leaves `last_update_success=False`).

### Translations / icons

- `icons.json` binary_sensor block (49-) — copy `routers_problem` node with `default` + `state.on/off` (required by `ON_OFF_KEYS` in `tests/test_translations.py:43-48`; add `("binary_sensor","certificates_problem")`).
- `en.json` (127-138): `"certificates_problem": {"name": "Certificate problems", "state_attributes": {"reasons"/"reason": ...}}`; `de.json` same keys and placeholders (`test_de_matches_en_keys_and_placeholders`); `strings.json` must stay byte-identical to `en.json` (`test_strings_json_equals_en_json`, 103-105). Icon test also fails on unused icon keys (166-170).

## Shared Patterns

### Payload-error wrapping
**Source:** `api.py:252-259` — parsers raise plain `TypeError/KeyError/ValueError`, client wraps into `TraefikProxyPayloadError(path, "unexpected payload shape")`. Messages never contain URL/credentials (`api.py:102-113`).

### Write-on-change
**Source:** `entity.py:231-248` — override `_state_token()` only; `_handle_coordinator_update` compares `(available, token)`. Apply to all cert entities and the aggregate.

### Test harness
- Fixtures: `load_fixture("v3.7", "certificates.json")` (`conftest.py:57`); register `aioclient_mock.get(f"{MOCK_URL}/api/certificates", json=...)` / `status=404` in `stub_traefik` (`conftest.py:111-133`) — v2.11 → 404. Note the paginated GET carries `per_page`/`page` params; check how `stub_traefik_paginated` (136-158) registers params.
- `mock_tls_probe` (`conftest.py:211-221`) patches `cert_coordinator.fetch_cert_info_async` — must be repointed at the new probe function name and return the new error shape.
- Time: `freezer` fixture as in `tests/test_devices.py:200-218` (`freezer.tick(...)` + fire time changed); every test depending on `notAfter 2027-02-12T00:17:40Z` freezes time (D-20). Not for the hanging-server timeout test (P3).
- Real sockets: `socket_enabled` fixture (`tests/test_tls.py:217-226`); `gaierror` via `monkeypatch.setattr(socket, "getaddrinfo", ...)` (`test_tls.py:233-250`) — note the async probe goes through the loop's `getaddrinfo`, verify the patch still applies.
- Local TLS server: `conftest.py:250-` `mock_certificate_server` uses `asyncio.start_server` + openssl subprocess + `load_verify_locations` monkeypatch. Replace cert generation with in-process `cryptography` (CA, intermediate, leaf with SAN/AKI, expired, self-signed, wildcard) and an SNI callback; inject trust via the `trust_store` seam instead of patching `SSLContext`.

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `tls.py` async probe + `x509.verification` verifier | utility | streaming | No native-async socket or cryptography code exists; use RESEARCH.md lines 392-460 (probe, verify, day-boundary math) |

## Metadata

**Analog search scope:** `custom_components/traefik_proxy/`, `tests/`
**Files scanned:** ~20
**Pattern extraction date:** 2026-11-15
