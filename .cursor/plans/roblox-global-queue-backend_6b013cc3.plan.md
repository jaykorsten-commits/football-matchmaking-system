---
name: roblox-global-queue-backend
overview: Plan to refine the existing FastAPI queue backend for a Roblox football game, define clean API contracts for Lua, and prepare Heroku-ready deployment with security and cleanup.
todos: []
isProject: false
---

## Roblox Global Queue Backend — Implementation Plan

### 1. High-level architecture

- **Backend stack**: FastAPI app in `[Admin/main.py](Admin/main.py)`, routers in `[Admin/routers/queue_service.py](Admin/routers/queue_service.py)`, DB access in `[Admin/Database.py](Admin/Database.py)`, queue logic in `Admin/QueueFunctions.py`, Pydantic models in `Admin/schemas.py`, SQLAlchemy models in `Admin/models.py`.
- **Flow**: Roblox ServerScript (never LocalScript) → `ApiClient` HTTP requests → FastAPI queue routes → DB (PostgreSQL on Heroku) → JSON responses back to Roblox.
- **Goal**: Keep current architecture, but formalize queue types, team formats, regions, and cleanup, and publish a clear API contract document for Lua developers.

### 2. Backend systems to create or refine

- **Queue domain model** (SQLAlchemy):
  - Add or refine `Queue` table with fields like: `id`, `queue_code`, `region`, `queue_type`, `team_format`, `status`, `created_at`, `updated_at`, `last_activity_at`.
  - Add or refine `QueuePlayer`/`QueueMember` table: `id`, `queue_id`, `user_id`, `party_id` (nullable), `team` (`team_a` / `team_b`), `position`, `player_level`, `joined_at`.
- **Enums & constants (schemas + logic)**:
  - `QueueType`: `regular`, `pro`, `elite`.
  - `TeamFormat`: `5v5`, `7v7`.
  - `Region`: `EU`, `NA`, `ASIA`, plus room for more.
  - `Position5v5`: `GK`, `CB`, `LM`, `RM`, `CF`.
  - `Position7v7`: `GK`, `RDF`, `LDF`, `CM`, `LM`, `RM`, `FW`.
- **Queue templates and matching logic** (in `Admin/QueueFunctions.py`):
  - Define slot templates for each `team_format` that map positions to team/slot counts.
  - Implement a reusable function that, given `team_format`, `queue_type`, `region`, and desired positions, finds the first compatible open queue or creates a new one.
  - Implement solo join path (single user) and party join path (multiple members) that both use the same core matching logic.
- **Queue status & region stats**:
  - Ensure `get_queue_status` builds a response including: queue summary, player assignment, `teams` (team A/B lists), and `region_stats` (open queues, total players).
  - Ensure `get_region_status` returns aggregated queue counts and total players by region/queue type/team format.
- **Queue list & manual join (planned later)**:
  - Design but not necessarily implement in v1: functions to list open queues for a given region/queue_type/team_format and join a specific queue by `queue_id`.
- **Cleanup subsystem**:
  - Add functions to mark queues and members as stale and delete queues that meet cleanup rules (empty ≥ 5 minutes, or open and older than 15 minutes).
  - Implement **lazy cleanup**: run quick cleanup passes inside join/status/list flows so it works even without a scheduler.
  - Optionally expose an internal `/queue/cleanup/run` route for Heroku Scheduler or admin use later.
- **Security layer**:
  - Keep and extend `verify_api_key` in `[Admin/routers/queue_service.py](Admin/routers/queue_service.py)` so every queue route requires an `X-API-Key` header when `settings.api_key` is set.
  - Add Pydantic validation schemas with enums and stricter types to reject invalid payloads.

### 3. API router paths

#### 3.1 Already present (confirm and refine)

- **POST `/queue/join/solo`**
  - Request: `schemas.SoloJoinRequest`.
  - Response: queue summary, assignment, teams, region stats (see Section 4).
- **POST `/queue/leave/solo`**
  - Request: `schemas.LeaveRequest`.
  - Response: `{ "success": true }` and possibly updated region stats.
- **GET `/queue/status/{user_id}`**
  - Returns the queue (if any) that a user is currently in, with the same payload shape as join responses.
- **POST `/queue/region/status`**
  - Request: `schemas.RegionStatsRequest`.
  - Response: summary of open queues and total players for the requested pool.
- **POST `/queue/join/party`**
  - Request: `schemas.PartyJoinRequest`.
  - Response: same structure as solo join, with `assignment.type = "party"` and `assigned_positions` list.
- **POST `/queue/{queue_code}/reserve`**
  - For later reserved-server / teleport integration (keep, but not core for initial Lua work).
- **POST `/queue/{queue_code}/test-force-start`**
  - For internal testing only; keep behind API key.
- **GET `/health`**
  - From `[Admin/main.py](Admin/main.py)`, used by Heroku health checks.

#### 3.2 Planned additions (Phase 3+)

- **POST `/queue/list`**
  - Filters: `region`, `queue_type`, `team_format`.
  - Response: list of visible open queues; see example in Section 5.
- **POST `/queue/join/manual`**
  - Request: `user_id`, `queue_id`, desired `positions`, optional `player_level`.
  - Response: same as solo join.
- **POST `/queue/cleanup/run`** (optional admin/scheduler-only)
  - No body or simple auth token.
  - Triggers a cleanup pass and returns counts of deleted queues/members.
- **GET `/version`** (optional)
  - Returns app version / git commit for debugging.

### 4. Request payload contracts ("send payloads")

Documented as JSON; actual FastAPI models will be Pydantic classes under `Admin/schemas.py`.

- **Solo join** (`POST /queue/join/solo`):

```json
{
  "user_id": 123456789,
  "region": "EU",           // enum: EU, NA, ASIA, ...
  "queue_type": "regular",  // enum: regular, pro, elite
  "team_format": "5v5",     // enum: 5v5, 7v7
  "positions": ["CB", "GK"],
  "player_level": 42         // optional but recommended
}
```

- **Party join** (`POST /queue/join/party`):

```json
{
  "party_id": "party_001",
  "region": "EU",
  "queue_type": "pro",
  "team_format": "7v7",
  "members": [
    {
      "user_id": 111,
      "player_level": 45,
      "positions": ["CM", "LM"]
    },
    {
      "user_id": 222,
      "player_level": 48,
      "positions": ["FW"]
    }
  ]
}
```

- **Leave queue** (`POST /queue/leave/solo`):

```json
{
  "user_id": 123456789
}
```

- **Region status** (`POST /queue/region/status`):

```json
{
  "region": "EU",
  "queue_type": "regular",
  "team_format": "5v5"
}
```

- **Queue list** (`POST /queue/list`, later phase):

```json
{
  "region": "EU",
  "queue_type": "regular",
  "team_format": "5v5"
}
```

- **Manual join selected queue** (`POST /queue/join/manual`, later phase):

```json
{
  "user_id": 123456789,
  "queue_id": "eu_regular_5v5_01",
  "positions": ["GK", "CB"],
  "player_level": 32
}
```

### 5. Response payload contracts

- **Solo or party join & queue status responses** (`POST /queue/join/solo`, `/queue/join/party`, `GET /queue/status/{user_id}`):

```json
{
  "success": true,
  "error_code": null,  // e.g. "LEVEL_TOO_LOW", "QUEUE_FULL" when not null
  "message": null,     // human readable explanation when needed
  "queue": {
    "queue_id": "eu_regular_5v5_01",
    "region": "EU",
    "queue_type": "regular",
    "team_format": "5v5",
    "status": "open",       // open, starting, teleporting, closed, etc.
    "players_in_queue": 3,
    "max_players": 10,
    "players_needed": 7
  },
  "assignment": {
    "type": "solo",          // solo or party
    "party_id": null,         // set when type == "party"
    "assigned_position": "CB",  // for solo
    "assigned_positions": null    // for party: list of {user_id, position}
  },
  "teams": {
    "team_a": [
      { "user_id": 123456789, "position": "CB", "player_level": 42 }
    ],
    "team_b": [
      { "user_id": 444, "position": "GK", "player_level": 40 }
    ]
  },
  "region_stats": {
    "region": "EU",
    "queue_type": "regular",
    "team_format": "5v5",
    "open_queues": 2,
    "total_players_queued": 8
  }
}
```

- **Region stats response** (`POST /queue/region/status`):

```json
{
  "success": true,
  "region": "EU",
  "queue_type": "regular",
  "team_format": "5v5",
  "open_queues": 2,
  "total_players_queued": 8
}
```

- **Queue list response** (`POST /queue/list`, later phase):

```json
{
  "success": true,
  "queues": [
    {
      "queue_id": "eu_regular_5v5_01",
      "region": "EU",
      "queue_type": "regular",
      "team_format": "5v5",
      "status": "open",
      "players_in_queue": 6,
      "max_players": 10,
      "players_needed": 4,
      "level_range": null
    },
    {
      "queue_id": "eu_pro_5v5_01",
      "region": "EU",
      "queue_type": "pro",
      "team_format": "5v5",
      "status": "open",
      "players_in_queue": 4,
      "max_players": 10,
      "players_needed": 6,
      "level_range": {
        "min": 30,
        "max": 60
      }
    }
  ]
}
```

- **Standard error envelope** (suggested for all endpoints):

```json
{
  "success": false,
  "error_code": "LEVEL_TOO_LOW",
  "message": "Player level 12 is below required min level 30 for pro queues."
}
```

### 6. Queue lifecycle & cleanup rules

- **Empty queue timeout**: if a queue has `status = "open"` and `players_in_queue = 0` and `last_activity_at` is more than 5 minutes ago → delete queue.
- **Stale open queue timeout**: if a queue has `status = "open"` and `players_in_queue > 0` and `created_at` is more than 15 minutes ago → close or delete queue (decide per game design; default: hard delete until you need history).
- **Lazy cleanup strategy**:
  - On every `join`, `status`, `region/status`, and later `list` request, run a quick cleanup query that removes stale queues and orphaned members.
  - Optionally, add `/queue/cleanup/run` and have Heroku Scheduler hit it every N minutes as traffic grows.

### 7. Polling and performance guidance for Lua devs

- **Status polling**:
  - Poll `/queue/status/{user_id}` every 3–5 seconds **only while** the player is queued or is on the matchmaking screen.
  - Stop polling when the player leaves the queue or navigates away.
- **Region stats**:
  - Call `/queue/region/status` every ~5–10 seconds while the main queue UI is open to update "players in queue" and "open queues".
- **Queue list** (later phase):
  - Only request `/queue/list` when the player opens the manual queue list or explicitly refreshes.
- **General rule**: no polling from LocalScripts; all HTTP goes through a single, rate-aware ServerScript module.

### 8. API security design

- **Transport**:
  - Use HTTPS only (Heroku provides TLS termination by default).
- **Auth**:
  - Every request must include `X-API-Key: <secret>` header; the key is stored in Roblox as a server-side `Secret`/ModuleScript and in Heroku config vars (e.g. `QUEUE_API_KEY`).
  - `verify_api_key` in `[Admin/routers/queue_service.py](Admin/routers/queue_service.py)` checks the header when `settings.api_key` is non-empty.
- **Validation**:
  - Use strict Pydantic models (`schemas`) with enums for `region`, `queue_type`, `team_format`, `position`.
  - Validate `player_level` vs queue type on the backend (e.g. pro: 30–60, elite: 60–99); reject mismatches with clear `error_code`s.
- **Roblox constraints**:
  - Only Roblox server scripts call the API; never expose base URL or API key in LocalScripts.
- **Optional hardening**:
  - Add request logging (method, path, user_id, IP, outcome) for debugging and abuse detection.
  - Later consider HMAC signatures or timestamps if needed.

### 9. Heroku deployment & config

- **App entrypoint**:
  - Use `[Admin/main.py](Admin/main.py)` with `app = FastAPI()` as the ASGI application.
- **Procfile** (to be created in repo root):
  - `web: uvicorn Admin.main:app --host 0.0.0.0 --port ${PORT:-8000}`
- **Dependencies**:
  - Ensure `fastapi`, `uvicorn[standard]`, `sqlalchemy`, `psycopg2-binary` (or `psycopg2`), `python-dotenv` (if used), and any other libs are in `requirements.txt`.
- **Environment variables**:
  - `DATABASE_URL` (Heroku Postgres provides this automatically).
  - `QUEUE_API_KEY` or similar used in `Admin.config.settings`.
  - Any additional config (allowed origins, debug flags, etc.).
- **Database**:
  - Use Heroku Postgres add-on or an external Postgres instance.
  - Run migrations or `models.Base.metadata.create_all(bind=engine)` once (under a management script) to create tables.
- **Health & monitoring**:
  - Use `/health` for Heroku health checks.
  - Log validation errors via `validation_exception_handler` already in `[Admin/main.py](Admin/main.py)`.
- **Cleanup scheduling option**:
  - Optional: use Heroku Scheduler to `curl https://<app>.herokuapp.com/queue/cleanup/run` every 5 minutes.

### 10. What to communicate to the Roblox/Lua team

- **Client responsibilities**:
  - Provide UI for: region selection, queue type selection (regular/pro/elite), team format selection (5v5/7v7), position selection, solo vs party join, and leave queue.
  - Manage party creation and membership fully on Roblox side and send `party_id` + members list to backend.
  - Implement a single API client module on the server that knows how to call the documented endpoints with the correct payloads and `X-API-Key`.
- **Data they must send**:
  - For solo join: `user_id`, `region`, `queue_type`, `team_format`, preferred `positions`, `player_level`.
  - For party join: `party_id`, `region`, `queue_type`, `team_format`, and array of `{user_id, player_level, positions}`.
  - For leave: `user_id`.
  - For region stats + (later) list: `region`, `queue_type`, `team_format`.
- **Data they will receive and must handle**:
  - `queue` object (queue id, region, type, format, status, counts) to show basic info.
  - `assignment` block to know which position (and team) each player is assigned.
  - `teams` block (team A/B lists) to render pitch slots and lineups.
  - `region_stats` for counts like total players queued and open queues.
  - Standard error envelope (`success`, `error_code`, `message`) to show UI errors.
- **Polling rules**:
  - Poll status only when relevant; no constant background polling for all players.

### 11. Suggested Cursor prompt for future work

You can start future Cursor sessions with something like:

```text
You are working on the Roblox Global Queue backend in this repo. The main FastAPI app is in Admin/main.py, routes in Admin/routers/queue_service.py, core queue logic in Admin/QueueFunctions.py, schemas in Admin/schemas.py, and models in Admin/models.py.

Follow the API contract and requirements defined in the "Roblox Global Queue Backend — Implementation Plan" document. Implement or refine:
- queue_type (regular, pro, elite) with level ranges,
- team_format (5v5, 7v7) with position templates,
- solo and party join logic with queue matching and assignment,
- queue status and region stats responses using the documented payload shapes,
- lazy cleanup (5-minute empty queues, 15-minute stale queues),
- and API key security with X-API-Key header.

Do not change Lua/Roblox code; only update the FastAPI backend and documentation.
```

This keeps future