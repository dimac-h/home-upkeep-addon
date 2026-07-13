# Home Upkeep: Add-on → Custom Panel Migration — Design

- **Date:** 2026-07-13
- **Status:** Approved design, pending spec review
- **Author:** Hugo (with Claude)

## 1. Context

Home Upkeep currently ships as a Home Assistant **add-on**: a Docker container
running a FastAPI backend + a static React/Vite/Tailwind frontend served through
nginx, exposed via HA ingress. Data is persisted as JSON files
(`list_<id>.json`) by a `FileStore` at `/data/storage`. Real-time updates use a
custom WebSocket `ConnectionManager` that broadcasts change events. A separate
companion integration (`home-upkeep-component`) exposes lists as `todo`
entities.

This project migrates the entire thing into a **single Home Assistant custom
integration** that runs in-process inside HA Core. There is no more container,
ingress, nginx, s6, or FastAPI. The frontend becomes a Lit custom panel served
and registered by the integration; the backend logic is ported to Python
running inside HA; data lives in HA's own storage; and the API is exposed over
HA's authenticated WebSocket connection.

## 2. Locked decisions

These were decided during brainstorming and are the premises of this design:

1. **Native HA integration.** Port the backend into a Python custom integration
   (`custom_components/home_upkeep/`). Storage via HA's `Store` helper; API via
   HA WebSocket commands; auth via `hass`. Fully self-contained.
2. **WebSocket commands transport.** The panel talks to the integration through
   `hass.connection` WebSocket commands plus a subscription for live push. No
   REST, no CORS, no tokens in the frontend.
3. **No iframe.** The panel is a real custom element mounted directly (shadow
   DOM), not an iframe embed.
4. **Frontend framework: Lit** (HA's own framework). Full UI rewrite from React.
5. **This repo becomes the single integration.** The `todo`-entity role of the
   separate `home-upkeep-component` repo folds in here (in a later milestone).
6. **Drop Tailwind.** Styles authored in Lit `css` templates.
7. **Styling: reproduce the current look exactly** — a pixel-for-pixel port of
   today's palette/spacing/typography into Lit `css` (fixed palette, not
   HA-theme-variable driven).
8. **Data migration: API import with JSON fallback.** Import existing add-on
   data over the add-on's REST API, with import-from-copied-`list_*.json` as a
   fallback. The add-on/FastAPI stays runnable until the importer is validated.
9. **Two implementation plans**, not one (see §16).

## 3. Target architecture

A single custom integration owns data, exposes a WebSocket API, serves and
registers the Lit panel, and (later) provides `todo` entities — all in-process
in HA Core.

```
custom_components/home_upkeep/
├─ manifest.json        # domain=home_upkeep; deps: http, websocket_api, frontend, panel_custom; config_flow: true
├─ config_flow.py       # single-instance "Add integration" flow + optional import step
├─ __init__.py          # async_setup_entry: init store → register WS cmds → register panel → forward todo (later)
├─ const.py             # DOMAIN, signals, storage key/version, panel constants
├─ models.py            # StoredTask / StoredList (ported from backend/app/storage/models.py)
├─ store.py             # data layer over homeassistant.helpers.storage.Store
├─ logic.py             # pure rescheduling/seasonal functions (ported from backend/app/main.py)
├─ websocket_api.py     # home_upkeep/* command handlers + subscription push
├─ migration.py         # importer: from add-on REST API or copied JSON files
├─ todo.py              # (later milestone) TodoListEntity per list
├─ panel.py             # serve built frontend (static path) + panel_custom.async_register_panel(embed_iframe=False)
├─ strings.json
├─ translations/en.json
└─ frontend/            # Lit + TS + Vite source; build output served by panel.py
```

## 4. Python component breakdown

- **`manifest.json`** — `domain: home_upkeep`, `dependencies: ["http",
  "websocket_api", "frontend", "panel_custom"]`, `config_flow: true`,
  `integration_type: service`, `iot_class: local_push`, version, codeowners.
- **`config_flow.py`** — Minimal single-instance config flow (only one entry
  allowed). Offers an optional data-import step (§12). No runtime options
  required.
- **`const.py`** — `DOMAIN`, `SIGNAL_UPKEEP_CHANGED`, storage key
  (`home_upkeep`) and version, panel URL path / webcomponent name / static path.
- **`models.py`** — `StoredTask`, `StoredList`. Ported verbatim from the current
  storage models (pydantic or dataclasses). Field set is unchanged: task has
  `id, list_id, title, description, completed, due_date, reschedule_period,
  reschedule_base, completed_at, created_at, updated_at, prohibited_months,
  constraints`; list has `id, name, created_at, updated_at`.
- **`store.py`** — Data layer backed by `homeassistant.helpers.storage.Store`
  (async load on setup, debounced async save on mutation). Holds in-memory
  dicts of tasks/lists keyed by int id, plus `next_task_id` / `next_list_id`
  counters — mirroring today's `FileStore` semantics. Exposes the same CRUD
  surface as the existing `Store` ABC (`list_tasks, get_task, create_task,
  update_task, delete_task, list_lists, create_list, get_list, rename_list,
  delete_list`). Every mutation fires `async_dispatcher_send(hass,
  SIGNAL_UPKEEP_CHANGED, event)` and schedules a save. **Storage layout change:**
  the add-on's one-file-per-list layout is replaced by HA's single
  `.storage/home_upkeep` document (HA owns the file lifecycle). The importer
  bridges the old layout to the new one.
- **`logic.py`** — Pure functions ported from `main.py`:
  `calculate_next_due_date(base_date, reschedule_period, prohibited_months)` and
  `find_first_non_prohibited_month(start_date, prohibited_months)`. These are
  currently untested; they get unit tests here. The follow-up-task creation
  logic on completion (today in `update_task`) moves into the WS update handler
  (or a small service function) so it is testable and transport-independent.
- **`websocket_api.py`** — Command handlers + registration (§7).
- **`migration.py`** — Importer (§12).
- **`panel.py`** — Registers a static path serving `frontend/dist`
  (`hass.http.async_register_static_paths([StaticPathConfig(...)])`), then
  `await panel_custom.async_register_panel(hass, frontend_url_path="home-upkeep",
  webcomponent_name="home-upkeep-panel", module_url="<static>/entrypoint.js",
  embed_iframe=False, require_admin=False, sidebar_title="Home Upkeep",
  sidebar_icon="mdi:duck")`. `require_admin=False` matches today's
  `panel_admin: false`.
- **`todo.py`** — (later) `TodoListEntity` per list (§11).

## 5. Data flow & real-time updates

A single dispatcher-driven path replaces both the REST endpoints and the custom
`ConnectionManager` broadcast:

```
panel loads → HA sets `hass` on <home-upkeep-panel>
            → client subscribes home_upkeep/subscribe + fetches lists/tasks

mutation:   WS command → handler → store mutate
            → async_dispatcher_send(SIGNAL_UPKEEP_CHANGED, event)
                 ├─ subscription handler forwards event to all open panels
                 └─ todo entities (later) refresh
            → store schedules async save
```

Auth is implicit: only authenticated WS connections reach the command handlers.

## 6. WebSocket API surface

Command types mirror today's REST endpoints 1:1. Each is registered via
`websocket_api.async_register_command` with a voluptuous schema.

| Command | Payload | Result |
|---|---|---|
| `home_upkeep/lists/list` | — | `TaskList[]` |
| `home_upkeep/lists/create` | `{name}` | `TaskList` |
| `home_upkeep/lists/update` | `{list_id, name}` | `TaskList` |
| `home_upkeep/lists/delete` | `{list_id}` | `{success: true}` |
| `home_upkeep/tasks/list` | `{list_id}` | `Task[]` |
| `home_upkeep/tasks/get` | `{task_id}` | `Task` |
| `home_upkeep/tasks/create` | `{...task fields}` | `Task` |
| `home_upkeep/tasks/update` | `{task_id, ...fields, updated_at}` | `{task, created_task?}` |
| `home_upkeep/tasks/snooze` | `{task_id, period, updated_at}` | `Task` |
| `home_upkeep/tasks/delete` | `{task_id}` | `{success: true}` |
| `home_upkeep/subscribe` | — | stream of `{type, ...}` events |

`tasks/update` preserves the current behavior: when a task becomes completed and
has a `reschedule_period`, a rescheduled follow-up task is created and returned
as `created_task`. The **client-supplied `updated_at`** (local timezone, sent by
the frontend) remains the preferred base date for rescheduling, preserving the
timezone bugfix behavior. `reschedule_period`/`period` keep the `^[0-9]+[dwm]$`
validation. Subscription event types: `task_created`, `task_updated`,
`task_deleted`, `list_created`, `list_updated`, `list_deleted`.

## 7. Frontend (Lit) design

- **`entrypoint.ts`** — defines `<home-upkeep-panel>` (a `LitElement`) with
  reactive properties `hass`, `narrow`, `route`, `panel`. This is the panel root.
- **`ha-api.ts`** — thin typed wrapper over `hass.connection.sendMessagePromise`
  and `hass.connection.subscribeMessage`, one method per command in §6. Replaces
  both `frontend/src/api/client.ts` (fetch) and its `WebSocketManager`.
- **State** — a small Lit `ReactiveController` (or a store object) holds
  lists + the selected list's tasks, applies `home_upkeep/subscribe` events, and
  triggers re-render. Optimistic updates optional; live events are the source of
  truth.
- **Components (ported from the current React UI, ~8):** panel root/layout, list
  selector (`TaskLists`), `TaskItem`, `TaskForm`, and dialogs `CreateListDialog`,
  `EditListDialog`, `EditTaskDialog`, `SnoozeDialog`. HA's built-in elements
  (`ha-dialog`, `ha-textfield`, etc.) may be reused where convenient, but are not
  required.
- **Date handling** — keep the Luxon-based local-timezone logic (`dates.ts`,
  and sending `updated_at` in local ISO on update/snooze) so due-date behavior is
  unchanged.
- **Build** — Vite builds the Lit app to `custom_components/home_upkeep/frontend/dist`
  with `base` set to the integration's static path so chunk imports resolve.
  `entrypoint.js` is the module HA loads.

## 8. Styling

**Reproduce the current appearance exactly.** Today's Tailwind-produced styles
are ported into Lit `static styles = css\`…\`` with a fixed palette matching the
current design (colors, spacing, typography). This is authoring-mechanism change
only; the visual result is intended to be pixel-identical to the add-on UI.
Tailwind and its toolchain (`tailwind.config.js`, `postcss.config.js`,
`@tailwindcss/postcss`) are removed. Accepted tradeoff: the panel uses a fixed
palette and does not auto-adapt to the user's HA theme (may not match dark mode);
revisiting theme-variable adoption is explicitly out of scope for this migration.

## 9. `todo` entities (later milestone)

One `TodoListEntity` per list, mapping task ↔ `TodoItem`
(summary=title, status from `completed`, due=`due_date`, description), delegating
to `store` and refreshing on `SIGNAL_UPKEEP_CHANGED`. This absorbs the separate
`home-upkeep-component` repo's role. The mapping is intentionally lossy — the
reschedule/seasonal/constraints richness lives in the panel, not the todo entity.

## 10. Data migration

Existing add-on data is imported once; nothing is read live across the
container boundary (HA Core cannot access the add-on's `/data`).

- **Primary — API import.** While the add-on is still installed and running, an
  import step (in the config flow, or a re-runnable service) fetches
  `GET /lists`, then `GET /tasks?list_id=` per list, from the add-on at its
  configured port (`8125`) or ingress URL. Because the models are the ones being
  ported, the transform is essentially identity and int IDs are preserved.
  Results are written into the new `Store`.
- **Fallback — JSON files.** Import from a copy of the add-on's `list_<id>.json`
  files (`{version, list, tasks[]}`) placed at a path the import step reads.
- **Sequencing.** The add-on/FastAPI backend stays runnable through the
  transition; decommissioning (M7) happens only after the importer is validated
  against a live add-on. In the throwaway dev container (no add-on present), the
  importer is tested against sample JSON files and/or a temporarily-run backend.
- **Safety.** Import into a non-empty store is guarded (fresh-install adopts IDs
  directly; otherwise the import is refused or namespaced to avoid ID
  collisions).

## 11. Dev workflow

Using the disposable HA Container instance under `dev/`:

- Update `dev/docker-compose.yml`: replace the `/config/www` mount with
  `../custom_components:/config/custom_components` so HA loads the integration.
- Add the integration once via **Settings → Devices & Services → Add
  Integration → Home Upkeep**.
- Frontend iteration: `vite build --watch` → integration serves fresh
  `frontend/dist` → reload the panel. (No Vite dev-server/HMR through HA
  initially; build-watch is the pragmatic loop.)
- Backend iteration: edit Python → `docker compose -f dev/docker-compose.yml
  restart` (or reload the config entry).

## 12. Testing

- **Python** — adopt `pytest-homeassistant-custom-component`. Unit-test
  `logic.py` (rescheduling + seasonal `prohibited_months` — currently untested),
  `store.py` CRUD + persistence, the follow-up-on-completion logic, and the WS
  command handlers via `hass_ws_client`. Test the importer transform against
  sample add-on JSON.
- **Frontend** — typecheck + lint first; manual verification in the dev
  instance. Lit component tests (`@open-wc/testing`) are optional/later.

## 13. Packaging & decommission (final milestone)

Once the panel + integration are validated and migration works, remove the
add-on scaffolding: `home-upkeep/Dockerfile`, `home-upkeep/rootfs/` (s6 +
nginx), `home-upkeep/config.yaml`, `home-upkeep/build.yaml`, the FastAPI
`home-upkeep/backend/`, and the `.github` add-on build workflows. Add HACS
integration packaging (`hacs.json`, updated `repository.json`/README), move the
frontend source under the integration, and update `CLAUDE.md` to describe the
integration architecture. The separate `home-upkeep-component` repo is
retired/redirected.

## 14. Phasing / milestones

Split across **two implementation plans**:

**Plan 1 — Backend, skeleton, migration (M1–M4)**
- **M1** Integration skeleton: `manifest.json`, `config_flow.py`, `__init__.py`,
  `panel.py` registering a minimal Lit `<home-upkeep-panel>` ("hello, N
  entities") served from `frontend/dist`. Update `dev/docker-compose.yml`.
  **Exit:** panel appears in the sidebar of the dev instance, no iframe, with
  `hass.connection` available.
- **M2** Port `models.py`, `store.py` (HA `Store`), `logic.py` + unit tests.
- **M3** WS command surface + subscription + tests (`hass_ws_client`).
- **M4** Data migration importer (API + JSON) + tests. Placed here (right after
  the store and WS API exist) so the store can be populated with real add-on
  data early — enabling dogfooding via the WS API before the Lit UI is built.

**Plan 2 — Frontend, todo entities, cleanup (M5–M7)**
- **M5** Lit frontend rewrite: `ha-api.ts` client, state controller, all
  components + dialogs, exact-styling port; full CRUD + live updates working
  against M3.
- **M6** `todo` entities folded in + tests.
- **M7** Decommission add-on scaffolding; HACS packaging; docs/`CLAUDE.md`
  update; retire `home-upkeep-component`.

## 15. Risks & open questions

- **Lit styling parity.** Reproducing Tailwind output exactly in hand-written
  `css` requires care; accept minor pixel drift.
- **Panel module loading.** `panel_custom.async_register_panel` +
  `embed_iframe=False` + integration-served ES module must resolve chunk imports
  (Vite `base`); validated in M1 before committing to the full frontend.
- **Migration reachability.** API import requires the add-on to be running and
  reachable from HA Core at migration time; JSON fallback covers the rest.
- **`todo` entity fidelity.** Lossy mapping is accepted.

## 16. Out of scope (YAGNI)

- HA theme-variable theming / dark-mode adaptation.
- Vite HMR through HA during development.
- Multi-instance support (single config entry only).
- Any new task features beyond parity with the current add-on.
