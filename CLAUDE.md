# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Home Upkeep is a local to-do app for recurring/non-recurring household tasks (cleaning, gardening, maintenance). Its distinguishing domain logic: recurring tasks are rescheduled from the actual completion date by default (not the original due date), and tasks support **seasonal constraints** (`prohibited_months`) that push a due date forward to the next allowed month.

It currently ships as a **Home Assistant add-on**: a Docker container running a FastAPI backend + a static React frontend served through nginx, exposed via HA ingress. The companion HA integration (separate repo `home-upkeep-component`) surfaces lists as `todo` entities.

> **Direction (decided):** this is being rewritten from an add-on into a **Home Assistant custom integration + Lit custom panel** — everything runs in-process inside HA Core (no container, ingress, nginx, s6, or FastAPI). Data moves to HA's `Store` helper, the API moves to authenticated HA WebSocket commands, and the React/Tailwind UI is rewritten in Lit. Treat the add-on packaging (Dockerfile, s6 services, nginx template, `config.yaml`, `build.yaml`) as legacy scaffolding on its way out: don't invest in extending it, and prefer changes that move toward the panel model. The core value — the storage layer, schemas, and the rescheduling/seasonal-constraint domain logic — is what carries over.
>
> The full plan (locked decisions, target `custom_components/home_upkeep/` layout, milestones M1–M4) is in **`docs/superpowers/specs/2026-07-13-home-upkeep-panel-migration-design.md`** — read it before doing migration work. Migration branches: `panel-migration-design`, `custom-panel`.

## Layout

Everything lives under `home-upkeep/` (the add-on slug directory):
- `backend/` — FastAPI app (Python ≥3.14, managed with `uv`)
- `frontend/` — React 18 + Vite + TypeScript + Tailwind v4
- `rootfs/` — container runtime: s6-overlay service definitions + nginx ingress template
- `Dockerfile`, `config.yaml`, `build.yaml` — HA add-on packaging

## Commands

Backend (from `home-upkeep/backend/`):
```bash
uv sync                                        # install deps (uses uv.lock)
uv run uvicorn app.main:app --reload           # dev server on :8000
uv run ruff check .                            # lint (ruff config = ALL, see pyproject.toml)
uv run ruff format .                           # format
```

Frontend (from `home-upkeep/frontend/`):
```bash
npm install
npm run dev          # Vite dev server on :5173, proxies /api -> 127.0.0.1:8000
npm run build        # tsc -b && vite build -> dist/
npm run typecheck    # tsc -b
npm run lint         # eslint
```

There is **no test suite** in the repo yet.

Local panel development (`dev/`) runs a disposable HA instance that serves the built frontend:
```bash
docker compose -f dev/docker-compose.yml up -d      # HA at http://localhost:8123
docker compose -f dev/docker-compose.yml logs -f
docker compose -f dev/docker-compose.yml down
rm -rf dev/config                                   # full reset
```
It bind-mounts `custom_components/` → `/config/custom_components`, so HA loads the `home_upkeep` integration straight from the working tree (build the panel frontend first — see `custom_components/home_upkeep/frontend/`). `dev/config/` is a live HA config dir — don't commit its runtime artifacts (`.storage/`, logs, DB).

The add-on image is built in CI via `home-assistant/builder` (`.github/workflows/build.yaml`) for `aarch64` and `amd64`. There is no meaningful local `docker build` shortcut because the final stage depends on `${BUILD_FROM}` supplied by the HA builder.

## Architecture

**Request path (production):** browser → nginx (`:8099`, restricted to HA ingress IP `172.30.32.2`) serves static `dist/` and reverse-proxies `/api/*` → uvicorn backend. In dev, Vite's proxy plays nginx's role, rewriting `/api` → backend root. The frontend therefore always calls a relative `./api` base (`frontend/src/api/client.ts`) — never hardcode absolute API URLs, or ingress path-prefixing breaks.

**Two s6 services** (`rootfs/etc/s6-overlay/s6-rc.d/`): `backend` runs uvicorn, `webui` renders the nginx template (via `envsubst`) and runs nginx. Both read the user-configured port from `/data/options.json` with `jq`.

**Storage** (`backend/app/storage/`): a `Store` ABC with two implementations — `FileStore` (JSON at `UPKEEP_STORAGE_PATH`, set to `/data/storage` in the container) and `MemoryStore` (used when no path is set, e.g. local dev). `main.py` picks one at import time based on the `UPKEEP_STORAGE_PATH` env var.

**Real-time updates:** the backend holds a `ConnectionManager` of WebSocket clients (`/ws`, proxied as `/api/ws`). Every mutating REST endpoint broadcasts a typed message (`task_created`, `task_updated`, `task_deleted`, `list_*`). The frontend's `wsManager` (singleton in `client.ts`) auto-reconnects and pushes updates into React state, filtered by the currently selected `list_id`.

**Rescheduling logic** lives in `backend/app/main.py` (`_calculate_next_due_date`, `_find_first_non_prohibited_month`). Key rules:
- `reschedule_period` is a string matching `^[0-9]+[dwm]$` (days/weeks/months).
- On completing a task with a `reschedule_period`, `update_task` creates a *follow-up* task. Base date is `due_date` when `reschedule_base == "due"`, otherwise the completion date.
- **Timezone handling is deliberate:** the client sends `updated_at` in its local timezone (Luxon `DateTime.now().toISO()`), and the backend prefers it over server time so due dates land on the correct local day. Preserve this when touching date logic — regressions here were the subject of prior bug fixes (dates showing a day early in negative-UTC zones).
- `prohibited_months` (1–12) roll a computed due date forward to the first day of the next allowed month.

**Schemas** (`backend/app/schemas.py`) are the API contract; the TS types in `frontend/src/api/client.ts` mirror them by hand. Change both together.

## Conventions

- Backend lint is Ruff with `select = ["ALL"]` — expect full docstrings (Google style), type annotations, and `from __future__ import annotations`. Match the existing style; use `# noqa: <code>` sparingly as the codebase already does (e.g. `PLR0913` on wide signatures).
- Bump `version` in **both** `home-upkeep/config.yaml` and `home-upkeep/backend/pyproject.toml` together when releasing (both currently `0.1.1`).