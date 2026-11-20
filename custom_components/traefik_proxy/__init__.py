"""The Traefik integration: config entry migration, setup, unload and removal."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, Final
from urllib.parse import urlsplit

from homeassistant.const import CONF_PASSWORD, CONF_TOKEN, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback, split_entity_id
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir

from .api import AuthMode
from .cert_coordinator import CertCoordinator
from .const import (
    CONF_API_KEY,
    CONF_AUTH_TYPE,
    CONF_URL,
    CONF_VERIFY_SSL,
    DEFAULT_NAME,
    DOMAIN,
    PLATFORMS,
    UID_MIDDLEWARES_PROBLEM,
    UID_ROUTERS_PROBLEM,
    UID_SERVICES_PROBLEM,
)
from .coordinator import (
    TraefikProxyCoordinator,
    build_api_client,
    split_url_userinfo,
    url_host,
    url_unique_id,
)
from .data import TraefikProxyConfigEntry, TraefikRuntimeData
from .entity import (
    async_legacy_devices,
    async_remove_legacy_devices,
    async_setup_devices,
    async_track_sw_version,
)
from .entity_manager import (
    ROUTERS,
    SERVICES,
    TraefikEntityManager,
    async_remove_missing_store,
    per_item_entities_enabled,
)

_LOGGER = logging.getLogger(__name__)

# Repair issue raised once when the 1.2 migration removed replaced entities.
ISSUE_ENTITIES_MIGRATED: Final = "entities_migrated"
# Repair issue raised while a loaded entry sends credentials over plain HTTP.
ISSUE_INSECURE_CREDENTIALS: Final = "insecure_credentials"
# unique_id suffix of the 0.3.0 reload button, removed by the 1.2 migration.
_LEGACY_RELOAD_BUTTON_SUFFIX: Final = "diagnostics_reload"
# Maps the disabled_by of a removed 0.3.0 router binary sensor to the one its
# router sensor replacement is created with.
# - DEVICE becomes USER, but only while the old "HTTP Routers" device is
#   actually disabled: that device is removed after setup, and Home Assistant
#   clears a DEVICE disabler on the enabled Routers sub-device. A DEVICE
#   disabler on an enabled legacy device is stale and is not carried over.
# - INTEGRATION could only come from the entry's "disable new entities"
#   preference and is kept as it is.
# Enabled and CONFIG_ENTRY-disabled router binary sensors get no entry here:
# unless they are hidden, the platform creates their replacement as usual.
_ROUTER_REPLACEMENT_DISABLED_BY: Final[dict[er.RegistryEntryDisabler, er.RegistryEntryDisabler]] = {
    er.RegistryEntryDisabler.USER: er.RegistryEntryDisabler.USER,
    er.RegistryEntryDisabler.DEVICE: er.RegistryEntryDisabler.USER,
    er.RegistryEntryDisabler.INTEGRATION: er.RegistryEntryDisabler.INTEGRATION,
}


def _issue_id(entry_id: str) -> str:
    return f"{ISSUE_ENTITIES_MIGRATED}_{entry_id}"


@callback
def _async_raise_migrated_issue(hass: HomeAssistant, entry: TraefikProxyConfigEntry, removed_count: str) -> None:
    """Create or update the entry's persistent ``entities_migrated`` issue with its current title."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        _issue_id(entry.entry_id),
        config_entry_id=entry.entry_id,
        is_fixable=False,
        is_persistent=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_ENTITIES_MIGRATED,
        translation_placeholders={"entry_title": entry.title, "removed_count": removed_count},
    )


def _insecure_issue_id(entry_id: str) -> str:
    return f"{ISSUE_INSECURE_CREDENTIALS}_{entry_id}"


@callback
def _async_check_insecure_credentials(hass: HomeAssistant, entry: TraefikProxyConfigEntry) -> None:
    """Raise the insecure_credentials issue while the entry sends credentials over http, else delete it.

    The issue is bound to the entry (Home Assistant deletes it with the entry
    and hides it while the entry is disabled). :func:`async_unload_entry`
    deletes it, so every setup evaluates the current URL and auth type. It is
    not deleted through ``entry.async_on_unload``: Home Assistant runs those
    callbacks right after a failed setup, and the issue must stay while a
    retrying setup keeps sending the credentials.
    """
    issue_id = _insecure_issue_id(entry.entry_id)
    uses_http = urlsplit(str(entry.data.get(CONF_URL, ""))).scheme == "http"
    has_credentials = entry.data.get(CONF_AUTH_TYPE, AuthMode.none) != AuthMode.none
    if uses_http and has_credentials:
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            config_entry_id=entry.entry_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_INSECURE_CREDENTIALS,
            translation_placeholders={"entry_title": entry.title},
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id)


def _migrated_entry_data(data: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
    """Return entry data 1.3 for the data of an older entry, and whether URL credentials were dropped.

    The 0.3.0 bearer token (``api_key``) becomes auth type bearer when it is
    non-empty. Credentials in the URL (userinfo) are cut from it: without a
    token, a complete username and password become basic auth; next to a
    token, or when incomplete, they are dropped. Otherwise the auth type is
    none. Data that already names an auth type keeps its auth keys. Only
    known keys are carried over.
    """
    new_data: dict[str, Any] = {key: data[key] for key in (CONF_URL, CONF_VERIFY_SSL) if key in data}
    if CONF_AUTH_TYPE in data:
        # Deliberate defence: no older version wrote an auth type, so this only
        # keeps the auth keys of a hand-edited core.config_entries entry.
        new_data.update(
            {key: data[key] for key in (CONF_AUTH_TYPE, CONF_USERNAME, CONF_PASSWORD, CONF_TOKEN) if key in data}
        )
        return new_data, False
    username = password = None
    had_userinfo = False
    url = data.get(CONF_URL)
    if isinstance(url, str):
        try:
            new_url, username, password = split_url_userinfo(url)
        except ValueError:
            # Unparsable: kept as stored; setup reports the invalid URL.
            new_url = url
        had_userinfo = new_url != url
        new_data[CONF_URL] = new_url
    token = data.get(CONF_API_KEY)
    if isinstance(token, str) and token:
        new_data[CONF_AUTH_TYPE] = AuthMode.bearer.value
        new_data[CONF_TOKEN] = token
        return new_data, had_userinfo
    if username and password:
        new_data.update({CONF_AUTH_TYPE: AuthMode.basic.value, CONF_USERNAME: username, CONF_PASSWORD: password})
        return new_data, False
    new_data[CONF_AUTH_TYPE] = AuthMode.none.value
    return new_data, had_userinfo


def _migrated_unique_id(hass: HomeAssistant, entry: TraefikProxyConfigEntry, url: str) -> str | None:
    """Return the host:port unique_id for ``url``, or None to keep the entry's current one.

    The current one is kept when the URL has no usable host and port or when
    another entry of the domain already owns the new unique_id; a WARNING
    names the entries only.
    """
    try:
        unique_id = url_unique_id(url)
    except ValueError:
        _LOGGER.warning("Traefik entry %s: its URL has no usable host and port; kept its unique_id", entry.entry_id)
        return None
    owner = hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, unique_id)
    if owner is not None and owner.entry_id != entry.entry_id:
        _LOGGER.warning(
            "Traefik entry %s: entry %s already uses the same host and port; kept its unique_id",
            entry.entry_id,
            owner.entry_id,
        )
        return None
    return unique_id


async def async_migrate_entry(hass: HomeAssistant, entry: TraefikProxyConfigEntry) -> bool:
    """Migrate a config entry to the current version.

    1.1 -> 1.2: remove this entry's router binary sensors (replaced by router
    sensors with new entity IDs) and the reload button, and enable the three
    problem aggregates where only the old disabled-by-default disabled them.
    A router binary sensor disabled by the user, through its device or by the
    entry's "disable new entities" preference is replaced by a disabled router
    sensor with the same unique_id and the old object id (user- and
    device-disabled ones as user-disabled). A hidden router binary sensor is
    replaced the same way, and its replacement keeps the hidden state. Every
    other entity of this entry that was disabled through one of its disabled
    0.3.0 devices becomes user-disabled; a DEVICE disabler on an enabled
    legacy device is stale and left to Home Assistant. User-disabled entities
    stay disabled; no surviving entity is renamed or re-IDed. A persistent
    repair issue explains the change when anything was removed; it is raised
    after the last step, so it names the entry's final title.

    1.2 -> 1.3: the entry data names its auth type (none, basic or bearer)
    and carries only the credentials of that type; the unique_id becomes
    ``host:port`` unless another entry owns it, and the default title becomes
    the host (a user-chosen title stays). An existing repair issue follows a
    title change. Entity and device unique_ids are entry_id-based and
    unchanged. The 1.1 -> 1.2 step runs first, so a 1.1
    entry reaches 1.3 in one setup. An entry from a newer major version fails
    (downgrade).
    """
    if entry.version > 1:
        _LOGGER.debug(
            "Cannot migrate Traefik entry %s from version %s.%s (downgrade)",
            entry.entry_id,
            entry.version,
            entry.minor_version,
        )
        return False

    removed = 0
    if entry.minor_version < 2:
        registry = er.async_get(hass)
        # A DEVICE disabler only means "disabled through a device" while that
        # device is disabled; on an enabled device it is stale.
        disabled_legacy_device_ids = {device.id for device in async_legacy_devices(hass, entry) if device.disabled}
        router_prefix = f"{entry.entry_id}_{ROUTERS.prefix}"
        reload_unique_id = f"{entry.entry_id}_{_LEGACY_RELOAD_BUTTON_SUFFIX}"
        aggregate_unique_ids = {
            f"{entry.entry_id}_{suffix}"
            for suffix in (UID_ROUTERS_PROBLEM, UID_SERVICES_PROBLEM, UID_MIDDLEWARES_PROBLEM)
        }
        # (unique_id, disabled_by, hidden_by, object_id) of each disabled or
        # hidden router to re-create
        replacements: list[tuple[str, er.RegistryEntryDisabler | None, er.RegistryEntryHider | None, str]] = []
        for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
            if reg_entry.domain == "binary_sensor" and reg_entry.unique_id.startswith(router_prefix):
                old_disabled_by = reg_entry.disabled_by
                if (
                    old_disabled_by is er.RegistryEntryDisabler.DEVICE
                    and reg_entry.device_id not in disabled_legacy_device_ids
                ):
                    old_disabled_by = None
                mapped = _ROUTER_REPLACEMENT_DISABLED_BY.get(old_disabled_by) if old_disabled_by is not None else None
                if mapped is not None or reg_entry.hidden_by is not None:
                    replacements.append(
                        (reg_entry.unique_id, mapped, reg_entry.hidden_by, split_entity_id(reg_entry.entity_id)[1])
                    )
                registry.async_remove(reg_entry.entity_id)
                removed += 1
            elif reg_entry.domain == "button" and reg_entry.unique_id == reload_unique_id:
                registry.async_remove(reg_entry.entity_id)
                removed += 1
            elif (
                reg_entry.domain == "binary_sensor"
                and reg_entry.unique_id in aggregate_unique_ids
                and reg_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
            ):
                registry.async_update_entity(reg_entry.entity_id, disabled_by=None)
        # An entity disabled through a disabled 0.3.0 device moves to an
        # enabled new device, and Home Assistant clears a DEVICE disabler
        # there, so it becomes user-disabled. A stale DEVICE disabler on an
        # enabled legacy device is left for Home Assistant to clear. Read
        # again so removed entries are skipped.
        for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
            if (
                reg_entry.disabled_by is er.RegistryEntryDisabler.DEVICE
                and reg_entry.device_id in disabled_legacy_device_ids
            ):
                registry.async_update_entity(reg_entry.entity_id, disabled_by=er.RegistryEntryDisabler.USER)
        # Only the disabled and hidden state and the object id carry over; the
        # platform attaches the replacement to its device when it adds the router.
        for unique_id, disabled_by, hidden_by, object_id in replacements:
            registry.async_get_or_create(
                ROUTERS.domain,
                DOMAIN,
                unique_id,
                config_entry=entry,
                disabled_by=disabled_by,
                hidden_by=hidden_by,
                suggested_object_id=object_id,
            )
        hass.config_entries.async_update_entry(entry, minor_version=2)
        _LOGGER.debug(
            "Migrated Traefik entry %s to 1.2: %d entities removed, %d disabled or hidden routers re-created",
            entry.entry_id,
            removed,
            len(replacements),
        )

    if entry.minor_version < 3:
        new_data, dropped_url_credentials = _migrated_entry_data(entry.data)
        if dropped_url_credentials:
            # Names the entry only, never a credential. A token next to URL
            # credentials was refused by aiohttp; incomplete URL credentials
            # (e.g. a username without a password, which aiohttp sent as
            # basic auth with an empty password) cannot be mapped to basic auth.
            _LOGGER.warning(
                "Traefik entry %s (%s): removed the credentials from its URL; "
                "if Traefik answers 401, re-authentication asks for them",
                entry.entry_id,
                entry.title,
            )
        url = str(new_data.get(CONF_URL, ""))
        new_unique_id = _migrated_unique_id(hass, entry, url) or entry.unique_id
        old_title = title = entry.title
        if title == DEFAULT_NAME:
            title = url_host(url) or title
        hass.config_entries.async_update_entry(
            entry, data=new_data, minor_version=3, unique_id=new_unique_id, title=title
        )
        if title != old_title and not removed:
            # An issue raised by an earlier 1.2 step still names the old title.
            issue = ir.async_get(hass).async_get_issue(DOMAIN, _issue_id(entry.entry_id))
            if issue is not None and issue.translation_placeholders:
                _async_raise_migrated_issue(hass, entry, issue.translation_placeholders.get("removed_count", "0"))
        _LOGGER.debug("Migrated Traefik entry %s to 1.3: auth type %s", entry.entry_id, new_data[CONF_AUTH_TYPE])

    if removed:
        _async_raise_migrated_issue(hass, entry, str(removed))
    return True


async def async_setup_entry(hass: HomeAssistant, entry: TraefikProxyConfigEntry) -> None:
    """Set up Traefik from a config entry; a failure raises, success returns None.

    Order matters:

    1. Build the API client, then raise the ``insecure_credentials`` repair
       issue when the URL uses plain HTTP and the entry has credentials
       (otherwise delete it). It depends on the entry data only, so it also
       shows while a failing setup retries. Unload deletes it, so a reload
       re-evaluates it (and resets a user's ignore). Then build both
       coordinators and assign ``entry.runtime_data`` before any refresh:
       the main coordinator reads its client from the runtime data, and the
       cert coordinator reads the main coordinator's data through it.
    2. Await the main coordinator's first refresh. It raises
       ``ConfigEntryNotReady`` on transient failure (HA retries) or
       ``ConfigEntryAuthFailed`` on 401/403 (reauth flow).
    3. Load the entity manager: stored missing-since times, the entry's
       registry entries and the deadline timer. With the per-item option
       off, purge the router and service registry entries right away.
    4. Register the main device and the Certificates sub-device, plus the
       Routers / Services sub-devices when per-item entities are on.
    5. Forward platforms (sensor, binary_sensor, button). The cert
       coordinator has no data yet, so its entities start unavailable and
       registry-restored hosts are not marked missing.
    6. Start the cert coordinator's first cycle as a background task: a
       probe cycle can take minutes and must not block the setup, and a
       certificate failure never fails it. A failed cycle stays failed, so
       the cert entities stay unavailable and the cycle is retried after
       ``CERT_RETRY_INTERVAL``. Unload cancels the task.
    7. Remove the entry's 0.3.0 per-category devices that no entity
       references any more, and keep the main device's ``sw_version``
       following the Traefik version.
    """
    client = build_api_client(hass, entry)
    _async_check_insecure_credentials(hass, entry)
    coordinator = TraefikProxyCoordinator(hass, entry)
    cert_coordinator = CertCoordinator(hass, entry)
    entry.runtime_data = TraefikRuntimeData(
        client=client,
        coordinator=coordinator,
        cert_coordinator=cert_coordinator,
        entity_manager=TraefikEntityManager(hass, entry),
    )

    await coordinator.async_config_entry_first_refresh()

    _LOGGER.debug(
        "cert coordinator initialised: update_interval=%ds threshold=%d",
        int(cert_coordinator.update_interval.total_seconds()) if cert_coordinator.update_interval else 0,
        cert_coordinator.threshold_days,
    )

    entity_manager = entry.runtime_data.entity_manager
    await entity_manager.async_load()
    # Read once per setup; a changed option applies on the next reload.
    per_item = per_item_entities_enabled(entry)
    if not per_item:
        entity_manager.async_purge(ROUTERS)
        entity_manager.async_purge(SERVICES)

    # Every device exists, named and linked, before the first entity attaches.
    main = async_setup_devices(hass, entry, per_item=per_item)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_create_background_task(hass, cert_coordinator.async_refresh(), "traefik_proxy first cert cycle")

    # Safe order: the platforms have re-pointed every entity they add to the
    # new devices, so only legacy devices nothing references are removed.
    async_remove_legacy_devices(hass, entry)
    entry.async_on_unload(async_track_sw_version(hass, entry, main.id))

    _LOGGER.debug(
        "Traefik integration ready: entry_id=%s, scan_interval=%ss",
        entry.entry_id,
        coordinator.update_interval.total_seconds() if coordinator.update_interval else 0.0,
    )


async def async_unload_entry(hass: HomeAssistant, entry: TraefikProxyConfigEntry) -> None:
    """Unload a Traefik config entry.

    Unloads the platforms; a platform that fails to unload raises Home
    Assistant's translated unload error. Then deletes the
    ``insecure_credentials`` issue, so the next setup re-evaluates it. Home
    Assistant then runs every callback the setup registered through
    ``entry.async_on_unload`` (timers and coordinator listeners).
    """
    await hass.config_entries.async_unload_platforms_or_raise(entry, PLATFORMS)
    ir.async_delete_issue(hass, DOMAIN, _insecure_issue_id(entry.entry_id))


async def async_remove_entry(hass: HomeAssistant, entry: TraefikProxyConfigEntry) -> None:
    """Delete the data the entry keeps outside the registries: its missing-since Store.

    Both repair issues are bound to the entry, so Home Assistant deletes them
    when the entry is removed (unload keeps the migration issue).
    """
    await async_remove_missing_store(hass, entry.entry_id)
