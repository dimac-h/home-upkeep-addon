"""The Home Upkeep integration."""

from __future__ import annotations

from homeassistant.components.frontend import async_remove_panel
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import panel
from .const import PANEL_URL_PATH


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Home Upkeep from a config entry."""
    await panel.async_register(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Home Upkeep config entry."""
    async_remove_panel(hass, PANEL_URL_PATH)
    return True
