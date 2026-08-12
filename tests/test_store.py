"""Tests for HomeUpkeepStore CRUD, dispatcher notifications, and persistence."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from homeassistant.helpers.dispatcher import async_dispatcher_connect
from pytest_homeassistant_custom_component.common import flush_store

from custom_components.home_upkeep.const import SIGNAL_UPKEEP_CHANGED
from custom_components.home_upkeep.store import HomeUpkeepStore

# ruff (TC002) wants type-only imports under TYPE_CHECKING to avoid an
# unnecessary runtime import, since `from __future__ import annotations`
# means annotations are never evaluated at runtime anyway.
if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


async def test_create_and_get_list(hass: HomeAssistant) -> None:
    """Creating a list makes it retrievable and listed."""
    store = HomeUpkeepStore(hass)
    await store.async_load()

    lst = store.create_list("Cleaning")
    assert lst.id == 1
    assert lst.name == "Cleaning"
    assert store.get_list(1) is lst
    assert store.list_lists() == [lst]


async def test_rename_and_delete_list(hass: HomeAssistant) -> None:
    """Renaming and deleting a list behaves, including missing-id cases."""
    store = HomeUpkeepStore(hass)
    await store.async_load()

    lst = store.create_list("Cleaning")
    renamed = store.rename_list(lst.id, "Chores")
    assert renamed is not None
    assert renamed.name == "Chores"

    assert store.rename_list(999, "Nope") is None

    assert store.delete_list(lst.id) is True
    assert store.get_list(lst.id) is None
    assert store.delete_list(lst.id) is False


async def test_create_task_defaults(hass: HomeAssistant) -> None:
    """A freshly created task gets the documented defaults."""
    store = HomeUpkeepStore(hass)
    await store.async_load()

    lst = store.create_list("Cleaning")
    task = store.create_task(lst.id, "Mop floors", None)

    assert task.id == 1
    assert task.list_id == lst.id
    assert task.completed is False
    assert task.reschedule_base == "completed"
    assert task.prohibited_months == []
    assert task.constraints == []
    assert store.list_tasks(lst.id) == [task]


async def test_update_task_sets_completed_at(hass: HomeAssistant) -> None:
    """Toggling `completed` sets/clears `completed_at`; unknown id is a no-op."""
    store = HomeUpkeepStore(hass)
    await store.async_load()

    lst = store.create_list("Cleaning")
    task = store.create_task(lst.id, "Mop floors", None)

    updated = store.update_task(task.id, completed=True)
    assert updated is not None
    assert updated.completed is True
    assert updated.completed_at is not None

    reverted = store.update_task(task.id, completed=False)
    assert reverted is not None
    assert reverted.completed_at is None

    assert store.update_task(999, title="nope") is None


async def test_delete_task(hass: HomeAssistant) -> None:
    """Deleting a task removes it; deleting again reports not-found."""
    store = HomeUpkeepStore(hass)
    await store.async_load()

    lst = store.create_list("Cleaning")
    task = store.create_task(lst.id, "Mop floors", None)

    assert store.delete_task(task.id) is True
    assert store.get_task(task.id) is None
    assert store.delete_task(task.id) is False


async def test_delete_list_cascades_tasks(hass: HomeAssistant) -> None:
    """Deleting a list also removes all tasks that belonged to it."""
    store = HomeUpkeepStore(hass)
    await store.async_load()

    lst = store.create_list("Cleaning")
    store.create_task(lst.id, "Mop floors", None)
    store.create_task(lst.id, "Dust shelves", None)

    assert store.delete_list(lst.id) is True
    assert store.list_tasks(lst.id) == []


async def test_dispatcher_signal_fires_on_mutation(hass: HomeAssistant) -> None:
    """Every mutation notifies dispatcher subscribers with a typed event."""
    store = HomeUpkeepStore(hass)
    await store.async_load()

    events: list[dict] = []
    async_dispatcher_connect(
        hass, SIGNAL_UPKEEP_CHANGED, events.append
    )

    lst = store.create_list("Cleaning")
    await hass.async_block_till_done()
    assert events[-1]["type"] == "list_created"

    store.create_task(lst.id, "Mop floors", None)
    await hass.async_block_till_done()
    assert events[-1]["type"] == "task_created"


async def test_persistence_round_trip(hass: HomeAssistant) -> None:
    """Data saved by one store instance loads correctly in a fresh one."""
    store = HomeUpkeepStore(hass)
    await store.async_load()

    lst = store.create_list("Cleaning")
    store.create_task(
        lst.id,
        "Mop floors",
        "Kitchen and hallway",
        due_date=date(2026, 3, 1),
        reschedule_period="1m",
        prohibited_months=[7, 8],
    )

    await flush_store(store._store)  # noqa: SLF001

    reloaded = HomeUpkeepStore(hass)
    await reloaded.async_load()

    assert [lst.name for lst in reloaded.list_lists()] == ["Cleaning"]
    [task] = reloaded.list_tasks(lst.id)
    assert task.title == "Mop floors"
    assert task.due_date == date(2026, 3, 1)
    assert task.reschedule_period == "1m"
    assert task.prohibited_months == [7, 8]
