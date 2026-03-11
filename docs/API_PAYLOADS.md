# Queue API — Payload Reference

Dict-style request/response examples for all routes. Use for Roblox Lua integration and Postman testing.

**Base URL**: `http://localhost:8000` (local) or your Heroku URL  
**Headers**: `Content-Type: application/json` — All queue routes require `X-API-Key: <your_key>` when configured.

---

## Enums (valid values)

```python
Region = ["EU", "NA", "ASIA"]
Position = ["GK", "CB", "CM", "ST", "RDF", "LDF", "FW", "LM", "RM"]
QueueType = ["regular", "ranked"]
RankedTier = ["beginner", "pro", "elite"]  # only when queue_type == "ranked"
TeamFormat = ["5v5", "7v7"]
```

---

## Routes

### GET /health
No auth. No body.

**Response**:
```python
{"status": "ok"}
```

---

### POST /queue/join/solo
Auto-queue: join first available queue in pool.

**Request**:
```python
{
    "user_id": 123456789,
    "region": "EU",
    "positions": ["CB", "GK"],
    "team_format": "5v5",
    "queue_type": "regular",
    "ranked_tier": None,
    "player_level": 42
}
```
- `ranked_tier`: required when `queue_type` == `"ranked"`
- `player_level`: required when `queue_type` == `"ranked"`, 1–99
- `positions`: 1–4 items from Position enum

**Response**:
```python
{
    "success": True,
    "queue": {
        "queue_id": "eu_01",
        "region": "EU",
        "queue_type": "regular",
        "ranked_tier": None,
        "team_format": "5v5",
        "status": "open",
        "players_in_queue": 3,
        "max_players": 10,
        "players_needed": 7,
        "countdown_seconds": 0
    },
    "assignment": {"type": "solo", "assigned_position": "CB"},
    "teams": {
        "team_a": [{"user_id": 111, "position": "GK"}],
        "team_b": [{"user_id": 222, "position": "CB"}]
    },
    "region_stats": {
        "region": "EU",
        "queue_type": "regular",
        "ranked_tier": None,
        "team_format": "5v5",
        "open_queues": 2,
        "total_players_queued": 8
    }
}
```

---

### POST /queue/leave/solo

**Request**:
```python
{"user_id": 123456789}
```

**Response**:
```python
{"message": "User left the queue."}
```

---

### GET /queue/status/{user_id}
Path param: `user_id` (int). No body.

**Response (in queue)**:
```python
{
    "success": True,
    "queue": {
        "queue_id": "eu_01",
        "region": "EU",
        "queue_type": "regular",
        "ranked_tier": None,
        "team_format": "5v5",
        "status": "open",
        "players_in_queue": 3,
        "max_players": 10,
        "players_needed": 7,
        "place_id": 123456,
        "job_id": "abc-xyz"
    },
    "assignment": {"type": "solo", "assigned_position": "CB"},
    "teams": {"team_a": [], "team_b": []},
    "region_stats": {"region": "EU", "queue_type": "regular", "ranked_tier": None, "team_format": "5v5", "open_queues": 1, "total_players_queued": 3}
}
```

**Response (not in queue)**:
```python
{"in_queue": False}
```

---

### POST /queue/region/status

**Request**:
```python
{
    "region": "EU",
    "queue_type": "regular",
    "ranked_tier": None,
    "team_format": "5v5"
}
```

**Response**:
```python
{
    "success": True,
    "region_stats": {
        "region": "EU",
        "queue_type": "regular",
        "ranked_tier": None,
        "team_format": "5v5",
        "open_queues": 2,
        "total_players_queued": 8
    }
}
```

---

### POST /queue/list
Manual queue mode: paginated server list.

**Request**:
```python
{
    "region": "EU",
    "queue_type": "regular",
    "ranked_tier": None,
    "team_format": "5v5",
    "page": 1,
    "page_size": 10
}
```
- `page`: 1-based, default 1
- `page_size`: 1–50, default 10

**Response**:
```python
{
    "success": True,
    "queues": [
        {
            "queue_code": "eu_01",
            "region": "EU",
            "queue_type": "regular",
            "ranked_tier": None,
            "team_format": "5v5",
            "status": "open",
            "players_in_queue": 2,
            "max_players": 10,
            "players_needed": 8,
            "level_range": None
        }
    ],
    "pagination": {"page": 1, "page_size": 10, "total_count": 1, "total_pages": 1},
    "region_stats": {"region": "EU", "queue_type": "regular", "ranked_tier": None, "team_format": "5v5", "open_queues": 1, "total_players_queued": 2}
}
```
- `level_range`: `{"min": 30, "max": 60}` for ranked pro; `None` for regular

---

### POST /queue/join/manual
Join a specific queue from server list.

**Request**:
```python
{
    "user_id": 123456789,
    "queue_code": "eu_01",
    "positions": ["GK", "CB"],
    "team_format": "5v5",
    "queue_type": "regular",
    "ranked_tier": None,
    "player_level": 32
}
```
- `queue_code`: from `/queue/list` response

**Response**: same shape as `POST /queue/join/solo`

---

### POST /queue/join/party

**Request**:
```python
{
    "party_id": "party_001",
    "region": "EU",
    "members": [
        {"user_id": 111, "positions": ["CM", "LM"], "player_level": 45},
        {"user_id": 222, "positions": ["FW"], "player_level": 48}
    ],
    "team_format": "7v7",
    "queue_type": "ranked",
    "ranked_tier": "pro"
}
```
- `members`: 2–4 items
- `player_level` per member when ranked

**Response**: same structure as solo join, with `assignment.type` == `"party"` and `assigned_positions` list

---

### POST /queue/{queue_code}/reserve
Roblox server calls after ReserveServer to claim teleport.

**Path**: `queue_code` (e.g. `eu_01`)

**Request**:
```python
{"job_id": "abc-xyz-reserved-server-id"}
```

**Response**:
```python
{"success": True, "job_id": "abc-xyz-reserved-server-id"}
```
- If already reserved: `{"success": True, "already_reserved": True}`

---

### GET /queue/{queue_code}/teleport-info
Roblox server calls after reserve to get players + place_id + job_id for teleport.

**Path**: `queue_code` (e.g. `eu_01`). No body.

**Response**:
```python
{
    "success": True,
    "place_id": 123456789,
    "job_id": "abc-xyz-...",
    "user_ids": [111, 222, 333]
}
```
- Only when queue status is `teleporting`

---

### POST /queue/cleanup/run
Runs lazy cleanup (empty 5min, teleported 10min). No body.

**Response**:
```python
{"deleted_empty": 0, "deleted_teleported": 1}
```

---

### POST /queue/{queue_code}/test-force-start
DEV: Force queue to starting or teleporting.

**Path**: `queue_code`

**Request** (optional body):
```python
{"job_id": "test-job-123"}
```
- No `job_id`: sets status `starting`
- With `job_id`: sets status `teleporting`, stores job_id

**Response**:
```python
{"success": True, "status": "teleporting", "job_id": "test-job-123"}
```

---

## Error envelope

```python
{
    "detail": [
        {"loc": ["body", "region"], "msg": "value is not a valid enumeration member", "type": "enum"}
    ]
}
```
- 422: validation error  
- 400: business logic (e.g. already in queue, queue full)  
- 404: queue/player not found  
- 401: missing or invalid X-API-Key
