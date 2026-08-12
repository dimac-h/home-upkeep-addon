# Home Upkeep

Home Upkeep is a local to-do list for recurring and non-recurring household
tasks, such as cleaning, gardening, and maintenance chores.

It is not a replacement for a calendar and is not intended to alert you if a
task needs doing on a specific day or time (i.e. it is not a bin day
reminder!).

Instead, it is useful for tracking tasks that need doing _when you have
time_. Check what needs doing around the house and garden whenever you have
a free afternoon.

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

If you were using the previous Home Upkeep **add-on**, migrate your data in
two steps: get it out of the add-on (which needs a browser, not the
filesystem — see why below), then import it.

**1. Export it from the add-on, via your browser**

The add-on is only reachable through Home Assistant's ingress proxy — there
is no directly-dialable port, and its data folder
(`/addon_configs/<slug>/data`) is isolated from `/config`, so a typical
File editor/Samba-type add-on can't see it either. But the browser tab
you're already using to view the add-on's UI *is* authenticated through
that same ingress proxy — so a script run from that tab can reach the
add-on's own API the same way its UI already does.

With the add-on's own page open and focused, open your browser's DevTools
console (F12, or Cmd+Opt+I on macOS) and paste in:

```js
(async () => {
  const res = await fetch("./api/lists");
  if (!res.ok) {
    console.error(
      `Could not fetch lists (HTTP ${res.status}). Make sure this console ` +
        "is open on the Home Upkeep add-on's own tab, not the panel's.",
    );
    return;
  }
  const lists = await res.json();
  console.log(`Found ${lists.length} list(s).`);

  for (const list of lists) {
    const tasks = await (await fetch(`./api/tasks?list_id=${list.id}`)).json();
    const doc = { version: 1, list, tasks };
    const blob = new Blob([JSON.stringify(doc, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `list_${list.id}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    console.log(`  list ${list.id} ("${list.name}"): ${tasks.length} task(s) -> list_${list.id}.json`);
  }

  console.log(
    "\nDone. If your browser blocked multiple downloads, allow them and re-run this.",
  );
})();
```

This downloads one `list_<id>.json` file per list straight to your
computer — the exact format the add-on itself writes to disk, so nothing
needs converting. (Your browser may ask permission after the first
download to allow the rest — allow it and re-run the script if some are
missing.)

**2. Import it into the new integration**

1. Upload the downloaded `list_<id>.json` files somewhere Home Assistant
   Core can read them, e.g. `/config/home_upkeep_import` — using whichever
   `/config`-capable add-on you already have (File editor, Samba, Studio
   Code Server, etc.; this step only ever needs `/config`, which those all
   cover).
2. Call the `home_upkeep.import_from_json` service once, with that folder's
   path.
