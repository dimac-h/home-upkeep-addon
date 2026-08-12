"""
One-time importer for existing add-on data.

Imports from copies of the add-on's `list_<id>.json` files
(`{version, list, tasks[]}`) — the only path that actually works for a real
install: the add-on only exposes itself via Home Assistant's ingress proxy,
so there's no plain HTTP endpoint this integration (or an external script)
could call instead. Since the storage models are the ones being ported, the
transform is essentially identity and original int IDs are preserved (see
`store.HomeUpkeepStore.async_import`).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .models import StoredList, StoredTask
from .store import StoreNotEmptyError, async_get_store

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, ServiceCall

    from .store import HomeUpkeepStore

_LOGGER = logging.getLogger(__name__)

SERVICE_IMPORT_FROM_JSON = "import_from_json"

_IMPORT_FROM_JSON_SCHEMA = vol.Schema({vol.Required("path"): str})


def _read_json_files(directory: str) -> tuple[list[StoredList], list[StoredTask]]:
    """
    Parse add-on `list_<id>.json` files from a directory.

    Blocking (filesystem I/O) — call via `hass.async_add_executor_job`.
    """
    lists: list[StoredList] = []
    tasks: list[StoredTask] = []
    for path in sorted(Path(directory).glob("list_*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        lists.append(StoredList.from_storage(doc["list"]))
        tasks.extend(StoredTask.from_storage(t) for t in doc.get("tasks", []))
    return lists, tasks


async def async_import_from_json(
    hass: HomeAssistant, store: HomeUpkeepStore, directory: str
) -> tuple[int, int]:
    """
    Import lists/tasks from copied add-on `list_<id>.json` files.

    Args:
        hass: The Home Assistant instance.
        store: The store to import into.
        directory: Path to a directory containing `list_<id>.json` files.

    Returns:
        The number of (lists, tasks) imported.

    """
    lists, tasks = await hass.async_add_executor_job(_read_json_files, directory)
    await store.async_import(lists, tasks)
    return len(lists), len(tasks)


async def _async_handle_import_from_json(call: ServiceCall) -> None:
    """Handle the `import_from_json` service call."""
    store = async_get_store(call.hass)
    directory = call.data["path"]
    try:
        list_count, task_count = await async_import_from_json(
            call.hass, store, directory
        )
    except StoreNotEmptyError as err:
        raise HomeAssistantError(str(err)) from err
    except OSError as err:
        msg = f"Could not read add-on export files at {directory}: {err}"
        raise HomeAssistantError(msg) from err
    _LOGGER.info(
        "Imported %d lists and %d tasks from %s", list_count, task_count, directory
    )


def async_register_services(hass: HomeAssistant) -> None:
    """Register the `import_from_json` service."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_IMPORT_FROM_JSON,
        _async_handle_import_from_json,
        schema=_IMPORT_FROM_JSON_SCHEMA,
    )


def async_unregister_services(hass: HomeAssistant) -> None:
    """Unregister the `import_from_json` service."""
    hass.services.async_remove(DOMAIN, SERVICE_IMPORT_FROM_JSON)
