# Home Upkeep

Home Upkeep is a local to-do list for recurring and non-recurring household
tasks, such as cleaning, gardening, and maintenance chores.

It is not a replacement for a calendar and is not intended to alert you if a
task needs doing on a specific day or time (i.e. it is not a bin day
reminder!).

Instead, it is useful for tracking tasks that need doing _when you have
time_ — check what needs doing around the house and garden whenever you have
a free afternoon.

It runs entirely in-process inside Home Assistant Core as a custom
integration with a Lit-based sidebar panel — no separate container, no
add-on, nothing else to install.

## About

Home Upkeep is designed around how household tasks actually work in real
life. Unlike traditional to-do lists that rigidly schedule recurring tasks,
Home Upkeep adapts to your actual completion patterns.

### Recurring tasks

Most task management systems schedule recurring tasks with fixed intervals,
but Home Upkeep understands that life doesn't always follow a strict
schedule. When you complete a task, by default, the next occurrence is
scheduled from that completion date, not the original due date.

**Example:** A cleaning task scheduled every 4 weeks. If you complete it a
week late, the next task will be scheduled 4 weeks from when you actually
finished it, not from the original due date.

For tasks that must maintain a fixed schedule regardless of completion
timing, you can choose to reschedule from the due date instead.

### Seasonal tasks

Gardening and outdoor tasks often have seasonal constraints. Home Upkeep
allows you to specify which months tasks can or cannot be completed in.

**Example:** Pruning fruit trees is an annual task that must be completed
between December and February. Set it up as a yearly recurring task, and if
it slips into February, you'll see a warning telling you it must be done
before March.

Seasonal constraints also apply to recurring tasks. For instance, weed
spraying in the UK typically only happens between April and October. A
monthly spraying task will automatically skip the winter months and resume
in April.

### Constraints

Add custom constraints and notes to tasks to inform you of specific
conditions (e.g., "apply lawn feed only when rain is forecast"). These
constraints help you prioritize tasks and make informed decisions about when
to complete them.

You can snooze tasks if conditions aren't right, ensuring you see them again
when it's more appropriate to tackle them.

## Screenshot

<img src="assets/screenshot.png" width="500">

## Installation

Home Upkeep is a Home Assistant custom integration, installed via
[HACS](https://hacs.xyz/):

1. In HACS, add this repository
   ([`dimac-h/home-upkeep-addon`](https://github.com/dimac-h/home-upkeep-addon))
   as a custom repository of type "Integration".
2. Install "Home Upkeep" from HACS.
3. Restart Home Assistant.
4. Add the integration under **Settings → Devices & services → Add
   Integration → Home Upkeep**.

Once set up, a "Home Upkeep" panel appears in the sidebar, and your task
lists are also available as `todo` entities.

### Migrating from the old add-on

If you were using the previous Home Upkeep **add-on**, use the
`home_upkeep.import_from_json` service for a one-time data import:

1. Copy the add-on's `list_<id>.json` files (from its data folder — reachable
   via the Samba share, SSH & Terminal, or File editor add-on) to a folder
   Home Assistant Core can read, e.g. `/config/home_upkeep_import`.
2. Call `home_upkeep.import_from_json` once, with that folder's path. No
   conversion needed — it's the exact format the add-on already wrote.

There's also a `home_upkeep.import_from_api` service that imports directly
over the add-on's REST API, but most installs won't be reachable this way:
the add-on only exposes itself via Home Assistant's ingress proxy, which
isn't a plain HTTP endpoint a service call (or an external script) can use.
It only works if you've separately exposed the add-on's port to your
network. `import_from_json` is the path that works for everyone.
