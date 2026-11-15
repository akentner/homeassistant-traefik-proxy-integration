"""Consistency of translations, icons and PARALLEL_UPDATES with the entity code (D-12, ENT-08).

Translation keys are collected from the entity classes and descriptions, so a
renamed key, a missing German text, a missing icon or a drifting placeholder
fails here.
"""

from __future__ import annotations

import json
import string
from pathlib import Path
from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from custom_components.traefik_proxy import binary_sensor, button, sensor
from custom_components.traefik_proxy.binary_sensor import PROBLEM_SENSORS, TraefikCertExpiringBinarySensor
from custom_components.traefik_proxy.button import TraefikRefreshButton
from custom_components.traefik_proxy.cert_coordinator import CertProblem
from custom_components.traefik_proxy.const import ITEM_STATE_OPTIONS
from custom_components.traefik_proxy.entity import TraefikDevice, device_identifier
from custom_components.traefik_proxy.sensor import (
    SNAPSHOT_SENSORS,
    TraefikCertExpirySensor,
    TraefikEntrypointSensor,
    TraefikRouterSensor,
    TraefikServiceSensor,
)
from tests.conftest import make_traefik_entry, setup_traefik_entry

PACKAGE = Path(__file__).parent.parent / "custom_components" / "traefik_proxy"
EN = PACKAGE / "translations" / "en.json"
DE = PACKAGE / "translations" / "de.json"
STRINGS = PACKAGE / "strings.json"
ICONS = PACKAGE / "icons.json"

# Sections this phase owns; config/options stay English until Phase 7.
PHASE_SECTIONS = ("device", "entity", "issues")
# Translation keys whose entities show an ENUM state.
STATE_KEYS = {("sensor", "router"), ("sensor", "service")}
# Translation keys with on/off state icons.
ON_OFF_KEYS = {
    ("binary_sensor", "routers_problem"),
    ("binary_sensor", "services_problem"),
    ("binary_sensor", "middlewares_problem"),
    ("binary_sensor", "certificate_expiring"),
    ("binary_sensor", "certificates_problem"),
}
# Translation keys whose entity name comes from the item key (no translated name).
UNNAMED_KEYS = {("sensor", "router"), ("sensor", "service"), ("sensor", "entrypoint")}


def _load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _flatten(node: Any, prefix: str = "") -> dict[str, str]:
    """Return {dotted.path: string} for every string leaf below ``node``."""
    if isinstance(node, str):
        return {prefix: node}
    assert isinstance(node, dict), f"{prefix}: unexpected {type(node).__name__}"
    flat: dict[str, str] = {}
    for key, value in node.items():
        flat.update(_flatten(value, f"{prefix}.{key}" if prefix else key))
    return flat


def _phase_strings(path: Path) -> dict[str, str]:
    data = _load(path)
    return {key: value for section in PHASE_SECTIONS for key, value in _flatten(data.get(section, {}), section).items()}


def _placeholders(text: str) -> set[str]:
    return {field for _, field, _, _ in string.Formatter().parse(text) if field is not None}


def _class_key(cls: type) -> str:
    # HA's CachedProperties metaclass keeps the class attribute under a mangled name.
    key = vars(cls).get("__attr_translation_key")
    assert key is not None, f"{cls.__name__} has no class-level _attr_translation_key"
    return str(key)


def _code_keys() -> set[tuple[str, str]]:
    """Return every (platform, translation_key) used by the entity code."""
    keys: set[tuple[str, str]] = set()
    for description in SNAPSHOT_SENSORS:
        assert description.translation_key is not None
        keys.add(("sensor", description.translation_key))
    for problem in PROBLEM_SENSORS:
        assert problem.translation_key is not None
        keys.add(("binary_sensor", problem.translation_key))
    for cls in (TraefikRouterSensor, TraefikServiceSensor, TraefikEntrypointSensor, TraefikCertExpirySensor):
        keys.add(("sensor", _class_key(cls)))
    keys.add(("binary_sensor", _class_key(TraefikCertExpiringBinarySensor)))
    # Not a PROBLEM_SENSORS description: it reads the cert coordinator, not the snapshot.
    keys.add(("binary_sensor", _class_key(binary_sensor.TraefikCertificatesProblemBinarySensor)))
    keys.add(("button", _class_key(TraefikRefreshButton)))
    return keys


def test_strings_json_equals_en_json() -> None:
    """strings.json is byte-identical to translations/en.json until Phase 7 deletes it."""
    assert STRINGS.read_bytes() == EN.read_bytes()


def test_english_texts_have_one_source() -> None:
    """translations/en.json is the only English source; the package root holds no text file (D-28)."""
    assert sorted(path.name for path in PACKAGE.glob("*.json")) == ["icons.json", "manifest.json"]


def test_de_matches_en_keys_and_placeholders() -> None:
    """de.json parses as UTF-8 JSON and mirrors en.json's device/entity/issues keys and placeholders."""
    en = _phase_strings(EN)
    de = _phase_strings(DE)
    assert set(de) == set(en)
    for key, text in en.items():
        assert _placeholders(de[key]) == _placeholders(text), key


def test_no_empty_strings() -> None:
    """No string in en.json, de.json or icons.json is empty."""
    for path in (EN, DE, ICONS):
        for key, value in _flatten(_load(path)).items():
            assert value.strip(), f"{path.name}: {key} is empty"


def test_item_state_keys_equal_options() -> None:
    """Router and service state keys equal ITEM_STATE_OPTIONS in en and de."""
    for path in (EN, DE):
        sensors = _load(path)["entity"]["sensor"]
        for key in ("router", "service"):
            assert set(sensors[key]["state"]) == set(ITEM_STATE_OPTIONS), f"{path.name}: {key}"


def test_reason_state_keys_equal_cert_problems() -> None:
    """The reason attribute of certificate_expiring has a name and one text per CertProblem in en and de."""
    for path in (EN, DE):
        expiring = _load(path)["entity"]["binary_sensor"]["certificate_expiring"]
        reason = expiring.get("state_attributes", {}).get("reason")
        assert reason is not None, f"{path.name}: certificate_expiring.state_attributes.reason missing"
        assert reason["name"].strip(), path.name
        assert set(reason["state"]) == {member.value for member in CertProblem}, path.name
        assert all(text.strip() for text in reason["state"].values()), path.name


def test_every_code_key_has_texts() -> None:
    """Every translation key used in code has an en and de name (or state texts for ENUM sensors)."""
    keys = _code_keys()
    for path in (EN, DE):
        entity = _load(path)["entity"]
        for platform, key in keys:
            if (platform, key) in UNNAMED_KEYS and (platform, key) not in STATE_KEYS:
                continue  # name from the item key, no states: nothing to translate
            node = entity.get(platform, {}).get(key)
            assert node is not None, f"{path.name}: entity.{platform}.{key} missing"
            if (platform, key) not in UNNAMED_KEYS:
                assert node.get("name"), f"{path.name}: entity.{platform}.{key}.name missing"
            if (platform, key) in STATE_KEYS:
                assert set(node["state"]) == set(ITEM_STATE_OPTIONS)
    # The {host} placeholder of the cert names is filled from the entity.
    for path in (EN, DE):
        entity = _load(path)["entity"]
        assert _placeholders(entity["sensor"]["certificate_expiry"]["name"]) == {"host"}
        assert _placeholders(entity["binary_sensor"]["certificate_expiring"]["name"]) == {"host"}


def test_every_code_key_has_icons() -> None:
    """Every translation key has a default icon; ENUM sensors and problem sensors have state icons."""
    icons = _load(ICONS)["entity"]
    for platform, key in _code_keys():
        node = icons.get(platform, {}).get(key)
        assert node is not None, f"icons.json: entity.{platform}.{key} missing"
        assert node["default"].startswith("mdi:"), f"{platform}.{key}"
        if (platform, key) in STATE_KEYS:
            assert set(node["state"]) == set(ITEM_STATE_OPTIONS), f"{platform}.{key}"
        if (platform, key) in ON_OFF_KEYS:
            assert set(node["state"]) == {"on", "off"}, f"{platform}.{key}"
        for icon in node.get("state", {}).values():
            assert icon.startswith("mdi:")
    # No icon for a key the code does not use.
    used = _code_keys()
    for platform, entries in icons.items():
        for key in entries:
            assert (platform, key) in used, f"icons.json: unused entity.{platform}.{key}"


def test_parallel_updates() -> None:
    """sensor and binary_sensor read the snapshot (0); button presses are serialized (1)."""
    assert sensor.PARALLEL_UPDATES == 0
    assert binary_sensor.PARALLEL_UPDATES == 0
    assert button.PARALLEL_UPDATES == 1


@pytest.mark.usefixtures("mock_tls_probe")
async def test_german_device_names(hass: HomeAssistant, aioclient_mock: Any) -> None:
    """With the HA language set to German the sub-devices get the German names."""
    hass.config.language = "de"
    entry = await setup_traefik_entry(hass, aioclient_mock, make_traefik_entry())
    names = {
        identifier: device.name
        for device in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
        for identifier in device.identifiers
    }
    host = "traefik.example.com"
    assert names[device_identifier(entry.entry_id, TraefikDevice.ROUTERS)] == f"Traefik-Router ({host})"
    assert names[device_identifier(entry.entry_id, TraefikDevice.SERVICES)] == f"Traefik-Dienste ({host})"
    assert names[device_identifier(entry.entry_id, TraefikDevice.CERTIFICATES)] == f"Traefik-Zertifikate ({host})"
    assert names[device_identifier(entry.entry_id, TraefikDevice.MAIN)] == f"Traefik ({host})"
