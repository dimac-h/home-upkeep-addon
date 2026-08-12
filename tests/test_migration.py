"""Tests for the add-on data importer (API + JSON fallback)."""

from __future__ import annotations

import json
from datetime import date
from typing import TYPE_CHECKING

import aiohttp
import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.home_upkeep import migration
from custom_components.home_upkeep.const import DOMAIN
from custom_components.home_upkeep.store import StoreNotEmptyError, async_get_store

if TYPE_CHECKING:
    from pathlib import Path

    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )

BASE_URL = "http://homeassistant.local:8125"

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


def _mock_addon_api(aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(f"{BASE_URL}/lists", json=[LIST_DOC])
    aioclient_mock.get(
        f"{BASE_URL}/tasks", params={"list_id": 1}, json=[TASK_DOC]
    )


async def test_import_from_api_preserves_ids(
    setup_integration: MockConfigEntry,
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Importing from the add-on API preserves the original int IDs."""
    _mock_addon_api(aioclient_mock)
    store = async_get_store(hass)

    list_count, task_count = await migration.async_import_from_api(
        hass, store, BASE_URL
    )

    assert (list_count, task_count) == (1, 1)
    assert [lst.id for lst in store.list_lists()] == [1]
    [task] = store.list_tasks(1)
    assert task.id == TASK_DOC["id"]
    assert task.title == "Mop floors"
    assert task.due_date == date(2026, 3, 1)
    assert task.prohibited_months == [7, 8]


async def test_import_from_api_refuses_non_empty_store(
    setup_integration: MockConfigEntry,
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Importing into a store that already has data is refused."""
    _mock_addon_api(aioclient_mock)
    store = async_get_store(hass)
    store.create_list("Existing")

    with pytest.raises(StoreNotEmptyError):
        await migration.async_import_from_api(hass, store, BASE_URL)


async def test_import_from_api_unreachable_raises(
    setup_integration: MockConfigEntry,
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """A connection failure propagates as an aiohttp.ClientError."""
    aioclient_mock.get(f"{BASE_URL}/lists", exc=aiohttp.ClientConnectionError)
    store = async_get_store(hass)

    with pytest.raises(aiohttp.ClientError):
        await migration.async_import_from_api(hass, store, BASE_URL)


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


async def test_import_from_json_refuses_non_empty_store(
    setup_integration: MockConfigEntry,
    hass: HomeAssistant,
    tmp_path: Path,
) -> None:
    """Importing into a store that already has data is refused."""
    await _write_export_file(tmp_path)
    store = async_get_store(hass)
    store.create_list("Existing")

    with pytest.raises(StoreNotEmptyError):
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


async def test_service_import_from_json_refuses_non_empty_store(
    setup_integration: MockConfigEntry,
    hass: HomeAssistant,
    tmp_path: Path,
) -> None:
    """The service surfaces the store-not-empty guard as a HomeAssistantError."""
    await _write_export_file(tmp_path)
    store = async_get_store(hass)
    store.create_list("Existing")

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            migration.SERVICE_IMPORT_FROM_JSON,
            {"path": str(tmp_path)},
            blocking=True,
        )


async def test_service_import_from_api_unreachable_raises_home_assistant_error(
    setup_integration: MockConfigEntry,
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """The service surfaces a connection failure as a HomeAssistantError."""
    aioclient_mock.get(f"{BASE_URL}/lists", exc=aiohttp.ClientConnectionError)

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            migration.SERVICE_IMPORT_FROM_API,
            {"base_url": BASE_URL},
            blocking=True,
        )
