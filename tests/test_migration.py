"""Tests for the add-on data importer (JSON export)."""

from __future__ import annotations

import json
from datetime import date
from typing import TYPE_CHECKING

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.home_upkeep import migration
from custom_components.home_upkeep.const import DOMAIN
from custom_components.home_upkeep.store import ImportConflictError, async_get_store

if TYPE_CHECKING:
    from pathlib import Path

    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry

LIST_DOC = {
    "id": 1,
    "name": "Cleaning",
    "created_at": "2026-01-01T00:00:00+00:00",
    "updated_at": "2026-01-01T00:00:00+00:00",
}
TASK_DOC = {
    "id": 5,
    "list_id": 1,
    "title": "Mop floors",
    "description": "Kitchen and hallway",
    "completed": False,
    "due_date": "2026-03-01",
    "reschedule_period": "1m",
    "reschedule_base": "completed",
    "completed_at": None,
    "created_at": "2026-01-01T00:00:00+00:00",
    "updated_at": "2026-01-01T00:00:00+00:00",
    "prohibited_months": [7, 8],
    "constraints": [],
}


async def _write_export_file(directory: Path) -> None:
    doc = {"version": 1, "list": LIST_DOC, "tasks": [TASK_DOC]}
    (directory / "list_1.json").write_text(json.dumps(doc), encoding="utf-8")


async def test_import_from_json_preserves_ids(
    setup_integration: MockConfigEntry,
    hass: HomeAssistant,
    tmp_path: Path,
) -> None:
    """Importing from copied list_<id>.json files preserves the original IDs."""
    await _write_export_file(tmp_path)
    store = async_get_store(hass)

    list_count, task_count = await migration.async_import_from_json(
        hass, store, str(tmp_path)
    )

    assert (list_count, task_count) == (1, 1)
    assert [lst.id for lst in store.list_lists()] == [1]
    [task] = store.list_tasks(1)
    assert task.id == TASK_DOC["id"]
    assert task.due_date == date(2026, 3, 1)


async def test_import_from_json_refuses_conflicting_list_id(
    setup_integration: MockConfigEntry,
    hass: HomeAssistant,
    tmp_path: Path,
) -> None:
    """Importing a list ID that already exists is refused."""
    await _write_export_file(tmp_path)
    store = async_get_store(hass)
    store.create_list("Existing")  # takes list ID 1, matching LIST_DOC's ID

    with pytest.raises(ImportConflictError):
        await migration.async_import_from_json(hass, store, str(tmp_path))


async def test_import_from_json_empty_directory(
    setup_integration: MockConfigEntry,
    hass: HomeAssistant,
    tmp_path: Path,
) -> None:
    """An empty (or nonexistent) directory imports zero records, not an error."""
    store = async_get_store(hass)

    list_count, task_count = await migration.async_import_from_json(
        hass, store, str(tmp_path / "does-not-exist")
    )

    assert (list_count, task_count) == (0, 0)


async def test_service_import_from_json_success(
    setup_integration: MockConfigEntry,
    hass: HomeAssistant,
    tmp_path: Path,
) -> None:
    """The import_from_json service performs a real import."""
    await _write_export_file(tmp_path)

    await hass.services.async_call(
        DOMAIN,
        migration.SERVICE_IMPORT_FROM_JSON,
        {"path": str(tmp_path)},
        blocking=True,
    )

    store = async_get_store(hass)
    assert [lst.id for lst in store.list_lists()] == [1]


async def test_service_import_from_json_refuses_conflicting_list_id(
    setup_integration: MockConfigEntry,
    hass: HomeAssistant,
    tmp_path: Path,
) -> None:
    """The service surfaces the list-conflict guard as a HomeAssistantError."""
    await _write_export_file(tmp_path)
    store = async_get_store(hass)
    store.create_list("Existing")  # takes list ID 1, matching LIST_DOC's ID

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            migration.SERVICE_IMPORT_FROM_JSON,
            {"path": str(tmp_path)},
            blocking=True,
        )


async def test_service_import_from_json_reports_malformed_file(
    setup_integration: MockConfigEntry,
    hass: HomeAssistant,
    tmp_path: Path,
) -> None:
    """
    A malformed export file surfaces as a HomeAssistantError, not a crash.

    Regression test: the service handler used to only catch
    `ImportConflictError`/`OSError`, so a corrupt file (bad JSON) or a doc
    missing the required `list` key propagated as a raw, uncaught
    `JSONDecodeError`/`KeyError` instead of the friendly error used
    everywhere else in this module.
    """
    (tmp_path / "list_1.json").write_text("{not valid json", encoding="utf-8")

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            migration.SERVICE_IMPORT_FROM_JSON,
            {"path": str(tmp_path)},
            blocking=True,
        )
