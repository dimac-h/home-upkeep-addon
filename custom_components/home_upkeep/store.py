"""
Storage layer for the Home Upkeep integration, backed by HA's Store helper.

Ported from the add-on backend's `Store` ABC / `FileStore` / `MemoryStore`
(`backend/app/storage/`). CRUD surface is unchanged; persistence moves from
one-JSON-file-per-list to a single HA `Store` document, and every mutation
notifies listeners (websocket subscribers, later `todo` entities) via the
dispatcher instead of a custom WebSocket `ConnectionManager`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store

from .const import DOMAIN, SIGNAL_UPKEEP_CHANGED, STORAGE_KEY, STORAGE_VERSION
from .models import StoredList, StoredTask

SAVE_DELAY = 10


class StoreNotEmptyError(Exception):
    """Raised when a bulk import is attempted into a store that has data."""


def async_get_store(hass: HomeAssistant) -> HomeUpkeepStore:
    """Get the single Home Upkeep store instance (single-instance integration)."""
    entries = hass.config_entries.async_entries(DOMAIN)
    return entries[0].runtime_data


class HomeUpkeepStore:
    """In-memory task/list store, persisted via HA's Store helper."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the store."""
        self._hass = hass
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, STORAGE_KEY
        )
        self._tasks: dict[int, StoredTask] = {}
        self._lists: dict[int, StoredList] = {}
        self._next_task_id = 1
        self._next_list_id = 1

    async def async_load(self) -> None:
        """Load tasks and lists from storage."""
        data = await self._store.async_load()
        if data is None:
            return
        self._lists = {
            item["id"]: StoredList.from_storage(item)
            for item in data.get("lists", [])
        }
        self._tasks = {
            item["id"]: StoredTask.from_storage(item)
            for item in data.get("tasks", [])
        }
        if self._lists:
            self._next_list_id = max(self._lists) + 1
        if self._tasks:
            self._next_task_id = max(self._tasks) + 1

    @callback
    def _data_to_save(self) -> dict[str, Any]:
        return {
            "lists": [lst.to_storage() for lst in self._lists.values()],
            "tasks": [task.to_storage() for task in self._tasks.values()],
        }

    @callback
    def _async_notify(self, event: dict[str, Any]) -> None:
        self._store.async_delay_save(self._data_to_save, SAVE_DELAY)
        async_dispatcher_send(self._hass, SIGNAL_UPKEEP_CHANGED, event)

    async def async_import(
        self, lists: list[StoredList], tasks: list[StoredTask]
    ) -> None:
        """
        Bulk-load previously-exported lists/tasks, preserving their IDs.

        Refuses to import into a store that already has data, since adopting
        foreign IDs into a populated store risks ID collisions.
        """
        if self._lists or self._tasks:
            msg = "Cannot import into a store that already has data"
            raise StoreNotEmptyError(msg)

        self._lists = {lst.id: lst for lst in lists}
        self._tasks = {task.id: task for task in tasks}
        if self._lists:
            self._next_list_id = max(self._lists) + 1
        if self._tasks:
            self._next_task_id = max(self._tasks) + 1

        await self._store.async_save(self._data_to_save())
        async_dispatcher_send(
            self._hass,
            SIGNAL_UPKEEP_CHANGED,
            {
                "type": "data_imported",
                "list_count": len(lists),
                "task_count": len(tasks),
            },
        )

    # -------- Tasks --------

    def list_tasks(self, list_id: int) -> list[StoredTask]:
        """Get all tasks for a specific list."""
        return [t for t in self._tasks.values() if t.list_id == list_id]

    def get_task(self, task_id: int) -> StoredTask | None:
        """Get a task by its ID."""
        return self._tasks.get(task_id)

    def create_task(  # noqa: PLR0913
        self,
        list_id: int,
        title: str,
        description: str | None,
        *,
        completed: bool = False,
        due_date: date | None = None,
        reschedule_period: str | None = None,
        reschedule_base: str | None = "completed",
        prohibited_months: list[int] | None = None,
        constraints: list[str] | None = None,
    ) -> StoredTask:
        """Create a new task."""
        now = datetime.now(UTC)
        task_id = self._next_task_id
        self._next_task_id += 1
        task = StoredTask(
            id=task_id,
            list_id=list_id,
            title=title,
            description=description,
            completed=completed,
            due_date=due_date,
            reschedule_period=reschedule_period,
            reschedule_base=reschedule_base,
            completed_at=None,
            created_at=now,
            updated_at=now,
            prohibited_months=prohibited_months or [],
            constraints=constraints or [],
        )
        self._tasks[task_id] = task
        self._async_notify(
            {"type": "task_created", "list_id": list_id, "task": task}
        )
        return task

    def update_task(  # noqa: PLR0913
        self,
        task_id: int,
        *,
        list_id: int | None = None,
        title: str | None = None,
        description: str | None = None,
        completed: bool | None = None,
        due_date: date | None = None,
        reschedule_period: str | None = None,
        reschedule_base: str | None = None,
        completed_at: datetime | None = None,
        prohibited_months: list[int] | None = None,
        constraints: list[str] | None = None,
    ) -> StoredTask | None:
        """Update an existing task."""
        task = self._tasks.get(task_id)
        if task is None:
            return None
        now = datetime.now(UTC)
        if list_id is not None:
            task.list_id = list_id
        if title is not None:
            task.title = title
        if description is not None:
            task.description = description
        if completed is not None:
            task.completed = completed
            task.completed_at = now if completed else None
        if due_date is not None:
            task.due_date = due_date
        if reschedule_period is not None:
            task.reschedule_period = reschedule_period
        if reschedule_base is not None:
            task.reschedule_base = reschedule_base
        if completed_at is not None:
            task.completed_at = completed_at
        if prohibited_months is not None:
            task.prohibited_months = prohibited_months
        if constraints is not None:
            task.constraints = constraints
        task.updated_at = now
        self._async_notify(
            {"type": "task_updated", "list_id": task.list_id, "task": task}
        )
        return task

    def delete_task(self, task_id: int) -> bool:
        """Delete a task by its ID."""
        task = self._tasks.pop(task_id, None)
        if task is None:
            return False
        self._async_notify(
            {"type": "task_deleted", "list_id": task.list_id, "task_id": task_id}
        )
        return True

    # -------- Lists --------

    def list_lists(self) -> list[StoredList]:
        """Get all task lists."""
        return list(self._lists.values())

    def create_list(self, name: str) -> StoredList:
        """Create a new task list."""
        now = datetime.now(UTC)
        list_id = self._next_list_id
        self._next_list_id += 1
        lst = StoredList(id=list_id, name=name, created_at=now, updated_at=now)
        self._lists[list_id] = lst
        self._async_notify({"type": "list_created", "list": lst})
        return lst

    def get_list(self, list_id: int) -> StoredList | None:
        """Get a list by its ID."""
        return self._lists.get(list_id)

    def rename_list(self, list_id: int, name: str) -> StoredList | None:
        """Rename a task list."""
        lst = self._lists.get(list_id)
        if lst is None:
            return None
        lst.name = name
        lst.updated_at = datetime.now(UTC)
        self._async_notify({"type": "list_updated", "list": lst})
        return lst

    def delete_list(self, list_id: int) -> bool:
        """Delete a task list and all its tasks."""
        if list_id not in self._lists:
            return False
        self._tasks = {
            tid: t for tid, t in self._tasks.items() if t.list_id != list_id
        }
        del self._lists[list_id]
        self._async_notify({"type": "list_deleted", "list_id": list_id})
        return True
