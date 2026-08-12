"""The Home Upkeep integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.frontend import async_remove_panel
from homeassistant.config_entries import ConfigEntry

from . import migration, panel, websocket_api
from .const import PANEL_URL_PATH
from .store import HomeUpkeepStore

# ruff (TC002) wants type-only imports under TYPE_CHECKING to avoid an
# unnecessary runtime import, since `from __future__ import annotations`
# means annotations are never evaluated at runtime anyway.
if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

type HomeUpkeepConfigEntry = ConfigEntry[HomeUpkeepStore]


async def async_setup_entry(
    hass: HomeAssistant, entry: HomeUpkeepConfigEntry
) -> bool:
    """Set up Home Upkeep from a config entry."""
    store = HomeUpkeepStore(hass)
    await store.async_load()
    entry.runtime_data = store

    websocket_api.async_register(hass)
    migration.async_register_services(hass)
    await panel.async_register(hass)
    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: HomeUpkeepConfigEntry,  # noqa: ARG001
) -> bool:
    """Unload a Home Upkeep config entry."""
    migration.async_unregister_services(hass)
    async_remove_panel(hass, PANEL_URL_PATH)
    return True
