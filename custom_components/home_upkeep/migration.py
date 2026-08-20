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
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .models import StoredList, StoredTask
from .store import ImportConflictError, async_get_store

# ruff (TC002) wants type-only imports under TYPE_CHECKING to avoid an
# unnecessary runtime import, since `from __future__ import annotations`
# means annotations are never evaluated at runtime anyway.
if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse

    from .store import HomeUpkeepStore

_LOGGER = logging.getLogger(__name__)

SERVICE_IMPORT_FROM_JSON = "import_from_json"
SERVICE_IMPORT_FROM_ADDON = "import_from_addon"

_IMPORT_FROM_JSON_SCHEMA = vol.Schema({vol.Required("path"): str})

_IMPORT_FROM_ADDON_SCHEMA = vol.Schema(
    {
        vol.Required("docs"): [dict],
        vol.Optional("overwrite_list_ids"): [int],
    }
)


def _parse_docs(
    docs: list[dict[str, Any]],
) -> tuple[list[StoredList], list[StoredTask]]:
    """Parse `{version, list, tasks}` docs into StoredList/StoredTask objects."""
    lists: list[StoredList] = []
    tasks: list[StoredTask] = []
    for doc in docs:
        lists.append(StoredList.from_storage(doc["list"]))
        tasks.extend(StoredTask.from_storage(t) for t in doc.get("tasks", []))
    return lists, tasks


def _read_json_files(directory: str) -> list[dict[str, Any]]:
    """
    Read add-on `list_<id>.json` files from a directory.

    Blocking (filesystem I/O) — call via `hass.async_add_executor_job`.
    """
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(Path(directory).glob("list_*.json"))
    ]


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
    docs = await hass.async_add_executor_job(_read_json_files, directory)
    lists, tasks = _parse_docs(docs)
    return await store.async_import(lists, tasks)


async def async_import_from_docs(
    store: HomeUpkeepStore,
    docs: list[dict[str, Any]],
    *,
    overwrite_list_ids: set[int] | None = None,
) -> tuple[int, int]:
    """
    Import lists/tasks from already-parsed `{version, list, tasks}` docs.

    Used by the panel's Import button: the browser reads the user's
    `list_<id>.json` files directly (via the File API) and sends their
    parsed content over the WS connection, so no `/config` filesystem
    access is needed at all.

    Args:
        store: The store to import into.
        docs: Parsed `{version, list, tasks}` docs, one per list.
        overwrite_list_ids: IDs of conflicting lists the user has confirmed
            overwriting (see `HomeUpkeepStore.async_import`).

    Returns:
        The number of (lists, tasks) imported.

    """
    lists, tasks = _parse_docs(docs)
    return await store.async_import(
        lists, tasks, overwrite_list_ids=overwrite_list_ids
    )


async def _async_handle_import_from_json(call: ServiceCall) -> None:
    """Handle the `import_from_json` service call."""
    store = async_get_store(call.hass)
    directory = call.data["path"]
    try:
        list_count, task_count = await async_import_from_json(
            call.hass, store, directory
        )
    except ImportConflictError as err:
        raise HomeAssistantError(str(err)) from err
    except OSError as err:
        msg = f"Could not read add-on export files at {directory}: {err}"
        raise HomeAssistantError(msg) from err
    except (KeyError, TypeError, ValueError) as err:
        # ValueError also covers json.JSONDecodeError from a corrupt file.
        msg = f"Malformed export data in {directory}: {err}"
        raise HomeAssistantError(msg) from err
    _LOGGER.info(
        "Imported %d lists and %d tasks from %s", list_count, task_count, directory
    )


async def _async_handle_import_from_addon(call: ServiceCall) -> ServiceResponse:
    """
    Handle the `import_from_addon` service call.

    Called by `home-upkeep-component` (a separate integration) once, the
    first time it starts up alongside an already-loaded panel — see
    `docs/superpowers/specs/2026-08-19-addon-to-panel-auto-migration-design.md`.
    A conflict is reported back as normal response data rather than raised,
    mirroring the `home_upkeep/import_json` WS command, since it's an
    expected outcome the caller branches on (whether to retry with
    `overwrite_list_ids`), not an exceptional one. The `migrated_from_addon`
    flag is set on both outcomes: a conflict is still a completed attempt,
    and retrying it automatically on every restart wouldn't resolve it.
    """
    store = async_get_store(call.hass)
    overwrite_list_ids = set(call.data.get("overwrite_list_ids", []))
    try:
        list_count, task_count = await async_import_from_docs(
            store, call.data["docs"], overwrite_list_ids=overwrite_list_ids
        )
    except ImportConflictError as err:
        await store.async_mark_migrated_from_addon()
        return {
            "imported": False,
            "conflicts": [
                {"id": lst.id, "name": lst.name} for lst in err.conflicting_lists
            ],
        }
    await store.async_mark_migrated_from_addon()
    return {
        "imported": True,
        "conflicts": [],
        "list_count": list_count,
        "task_count": task_count,
    }


def async_register_services(hass: HomeAssistant) -> None:
    """Register the `import_from_json` and `import_from_addon` services."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_IMPORT_FROM_JSON,
        _async_handle_import_from_json,
        schema=_IMPORT_FROM_JSON_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_IMPORT_FROM_ADDON,
        _async_handle_import_from_addon,
        schema=_IMPORT_FROM_ADDON_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )


def async_unregister_services(hass: HomeAssistant) -> None:
    """Unregister the `import_from_json` and `import_from_addon` services."""
    hass.services.async_remove(DOMAIN, SERVICE_IMPORT_FROM_JSON)
    hass.services.async_remove(DOMAIN, SERVICE_IMPORT_FROM_ADDON)
