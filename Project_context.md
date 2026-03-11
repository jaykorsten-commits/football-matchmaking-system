# Project context — Roblox Global Queue Backend

This repo is the **FastAPI backend** for a Roblox game’s global matchmaking/queue system. The game team builds UI and game logic in Roblox (Lua); this service handles queue creation, matching, and status.

## What lives here

- **Backend only**: FastAPI app, queue logic, PostgreSQL (e.g. Heroku Postgres). No Roblox/Lua code in this repo.
- **API contract**: Request/response shapes and router paths are defined in the implementation plan so the Lua team can integrate.

## Where to look

| Purpose | Location |
|--------|----------|
| Implementation plan (API contracts, security, cleanup, Heroku) | [`.cursor/plans/roblox-global-queue-backend_6b013cc3.plan.md`](.cursor/plans/roblox-global-queue-backend_6b013cc3.plan.md) |
| FastAPI app entry | `Admin/main.py` |
| Queue routes | `Admin/routers/queue_service.py` |
| Queue logic (join, leave, status, matching) | `Admin/QueueFunctions.py` |
| Pydantic request/response schemas | `Admin/schemas.py` |
| SQLAlchemy models | `Admin/models.py` |
| Config (DB URL, API key) | `Admin/config.py` |

## For Cursor / AI planning

When working on this backend, use the plan as the source of truth:

- **Router paths**: Section 3 of the plan.
- **Request/response payloads**: Sections 4 and 5.
- **Queue types, team formats, regions**: Enums and behaviour in the plan and in `Admin/schemas.py` / `Admin/QueueFunctions.py`.
- **Cleanup**: Lazy cleanup (5 min empty, 15 min stale); optional `/queue/cleanup/run`.
- **Security**: `X-API-Key` header; key from env (e.g. `QUEUE_API_KEY`).

Do not change or assume Roblox/Lua behaviour; only update the FastAPI backend and this documentation.
