# Queue matchmaking logic: solo/party join, leave, status.
# Adapt slot_template in create_slots_for_queue_* for different game formats (5v5, 7v7).
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, Response, status, HTTPException, Depends, APIRouter
from sqlalchemy.orm import Session
from typing import Optional
from sqlalchemy import desc, select, Column
from sqlalchemy.util import deprecated
from sqlalchemy import func
from .Database import get_db
from . import schemas, models
from .config import settings
from .schemas import *

COUNTDOWN_SECONDS = 10

# ----------------------------------------------------------------------
# Queue code generation
# ----------------------------------------------------------------------

def generate_queue_code(db, region):
    counter_row = db.query(models.region_counters).filter(models.region_counters.region == region).first()

    if counter_row is None:
        counter_row = models.region_counters(region=region,next_number=2)
        db.add(counter_row)
        number_to_use = 1
    else:
        number_to_use = counter_row.next_number
        counter_row.next_number = counter_row.next_number + 1

    region_text = region.lower()
    number_text = str(number_to_use).zfill(2)
    queue_code = region_text + "_" + number_text

    return queue_code

# ----------------------------------------------------------------------
# Team / assignment helpers
# ----------------------------------------------------------------------

def build_queue_teams(db, queue_id):
    # Build team_a / team_b rosters from filled slots. Used in status and join responses.
    filled_slots = db.query(models.QueueSlot).filter(
        models.QueueSlot.queue_id == queue_id,
        models.QueueSlot.occupant_user_id.is_not(None)
    ).all()

    team_a = []
    team_b = []

    for slot in filled_slots:
        player_info = {
            "user_id": slot.occupant_user_id,
            "position": slot.position
        }

        if slot.team == "A":
            team_a.append(player_info)
        elif slot.team == "B":
            team_b.append(player_info)

    return {
        "team_a": team_a,
        "team_b": team_b
    }


def build_queue_assignment(db, player):
    # Returns solo or party assignment. Party includes all members' positions for UI.
    assigned_slot = db.query(models.QueueSlot).filter(
        models.QueueSlot.slot_id == player.assigned_slot_id
    ).first()

    if assigned_slot is None:
        raise HTTPException(status_code=404, detail="Assigned slot not found.")

    if player.party_id:
        party_players = db.query(models.queue_players).filter(
            models.queue_players.party_id == player.party_id,
            models.queue_players.queue_id == player.queue_id
        ).all()

        assigned_positions = []

        for party_player in party_players:
            party_slot = db.query(models.QueueSlot).filter(
                models.QueueSlot.slot_id == party_player.assigned_slot_id
            ).first()

            if party_slot is not None:
                assigned_positions.append({
                    "user_id": party_player.user_id,
                    "position": party_slot.position
                })

        return {
            "type": "party",
            "party_id": player.party_id,
            "assigned_positions": assigned_positions
        }

    return {
        "type": "solo",
        "assigned_position": assigned_slot.position
    }

# ----------------------------------------------------------------------
# Slot creation
# ----------------------------------------------------------------------

def create_slots_for_queue_5v5(db, queue_id):
    # Create slot rows per queue. Plan 5v5: GK, CB, LM, RM, ST per team (10 total).
    slot_template = [
        ("A", "GK", 1), ("A", "CB", 2), ("A", "LM", 3), ("A", "RM", 4), ("A", "ST", 5),
        ("B", "GK", 1), ("B", "CB", 2), ("B", "LM", 3), ("B", "RM", 4), ("B", "ST", 5),
    ]
    for team, position, slot_number in slot_template:
        db.add(models.QueueSlot(queue_id=queue_id, position=position, slot_number=slot_number, team=team, status=schemas.QueueStatus.OPEN.value))


def create_slots_for_queue_7v7(db, queue_id):
    # Create slot rows for 7v7. Plan: GK, RDF, LDF, CM, LM, RM, FW per team (14 total).
    slot_template = [
        ("A", "GK", 1), ("A", "RDF", 2), ("A", "LDF", 3), ("A", "CM", 4), ("A", "LM", 5), ("A", "RM", 6), ("A", "FW", 7),
        ("B", "GK", 1), ("B", "RDF", 2), ("B", "LDF", 3), ("B", "CM", 4), ("B", "LM", 5), ("B", "RM", 6), ("B", "FW", 7),
    ]
    for team, position, slot_number in slot_template:
        db.add(models.QueueSlot(queue_id=queue_id, position=position, slot_number=slot_number, team=team, status=schemas.QueueStatus.OPEN.value))

# ----------------------------------------------------------------------
# Slot lookup
# ----------------------------------------------------------------------

def find_matching_open_slot(db, queue_id, position):
    # Find the first open slot matching any preferred position. Returns slot or None.
    for position_name in position:
        slot = db.query(models.QueueSlot).filter(
                 models.QueueSlot.queue_id == queue_id,
                 models.QueueSlot.position == position_name.value,
                 models.QueueSlot.status == schemas.QueueStatus.OPEN.value,
                 models.QueueSlot.occupant_user_id.is_(None)
                ).first()
        if slot:
            return slot
    return None


def find_matching_open_slots_for_party(db, queue_id, members):
    # Check if the whole party can fit on the same team. Tries A first, then B. Returns the list of {user_id, slot} or None.
    available_slots = db.query(models.QueueSlot).filter(
        models.QueueSlot.queue_id == queue_id,
        models.QueueSlot.status == schemas.QueueStatus.OPEN.value,
        models.QueueSlot.occupant_user_id.is_(None)
    ).all()

    for team in ("A", "B"):
        team_slots = [s for s in available_slots if s.team == team]
        assigned_slots = []
        used_slot_ids = set()

        for member in members:
            matched_slot = None
            for preferred_position in member.positions:
                for slot in team_slots:
                    if slot.slot_id in used_slot_ids:
                        continue
                    if slot.position == preferred_position.value:
                        matched_slot = slot
                        break
                if matched_slot is not None:
                    break
            if matched_slot is None:
                break
            assigned_slots.append({"user_id": member.user_id, "slot": matched_slot})
            used_slot_ids.add(matched_slot.slot_id)

        if len(assigned_slots) == len(members):
            return assigned_slots

    return None


def remove_player_from_slot(db, user_id, queue_id):
    # Free slot and set status back to OPEN. Used when a player leaves the queue.
    slot = db.query(models.QueueSlot).filter(
        models.QueueSlot.occupant_user_id == user_id,
        models.QueueSlot.queue_id == queue_id).first()
    if not slot:
        return None
    slot.occupant_user_id = None
    slot.status = schemas.QueueStatus.OPEN.value
    return slot

# ----------------------------------------------------------------------
# Solo queue
# ----------------------------------------------------------------------

def join_solo_queue(payload, db):
    # Place solo player in the queue. Uses existing open queue or creates a new one.
    run_queue_cleanup(db)
    user_id = payload.user_id
    region = payload.region
    positions = payload.positions

    existing_player = db.query(models.queue_players).filter(models.queue_players.user_id == user_id).first()
    if existing_player:
        raise HTTPException(status_code=400, detail="User is already in a queue.")

    queue_type_val = payload.queue_type.value
    ranked_tier_val = payload.ranked_tier.value if payload.ranked_tier else None
    team_format_val = payload.team_format
    max_players = 10 if team_format_val == "5v5" else 14

    pool_f_solo = [
        models.Queues.status == schemas.QueueStatus.OPEN.value,
        models.Queues.region == payload.region.value,
        models.Queues.queue_type == queue_type_val,
        models.Queues.team_format == team_format_val,
    ]
    if ranked_tier_val:
        pool_f_solo.append(models.Queues.ranked_tier == ranked_tier_val)
    else:
        pool_f_solo.append(models.Queues.ranked_tier.is_(None))
    Available_Queues = db.query(models.Queues).filter(*pool_f_solo).all()
    chosen_queue = None
    chosen_slot = None

    for queue in Available_Queues:
        slot = find_matching_open_slot(db, queue.queue_id, positions)
        if slot:
            chosen_queue = queue
            chosen_slot = slot
            break

    if chosen_queue is None:
        queue_code = generate_queue_code(db, region)
        chosen_queue = models.Queues(
            queue_code=queue_code,
            region=region.value,
            status=schemas.QueueStatus.OPEN.value,
            max_players=max_players,
            players_in_queue=0,
            queue_type=queue_type_val,
            ranked_tier=ranked_tier_val,
            team_format=team_format_val,
        )
        db.add(chosen_queue)
        db.flush()

        if team_format_val == "7v7":
            create_slots_for_queue_7v7(db, chosen_queue.queue_id)
        else:
            create_slots_for_queue_5v5(db, chosen_queue.queue_id)
        db.flush()


        chosen_slot = find_matching_open_slot(db,chosen_queue.queue_id,positions)

        if chosen_slot is None:
            print("queue created:", chosen_queue.queue_id, chosen_queue.queue_code)
            print("positions from payload:", positions)
            slots = db.query(models.QueueSlot).filter(models.QueueSlot.queue_id == chosen_queue.queue_id).all()
            print("slots created:", len(slots))
            for s in slots:
                print(s.position, s.status, s.occupant_user_id)
            raise HTTPException(status_code=500, detail="Queue created but no slots found.")

    chosen_slot.occupant_user_id = user_id
    chosen_slot.status = "filled"

    new_queue_player = models.queue_players(
            user_id=user_id,
            queue_id=chosen_queue.queue_id,
            assigned_slot_id=chosen_slot.slot_id,
            player_level=payload.player_level,
        )

    db.add(new_queue_player)

    chosen_queue.players_in_queue = chosen_queue.players_in_queue + 1

    if chosen_queue.players_in_queue >= chosen_queue.max_players:
        chosen_queue.status = schemas.QueueStatus.COUNTDOWN.value
        chosen_queue.countdown_ends_at = datetime.now(timezone.utc) + timedelta(seconds=COUNTDOWN_SECONDS)

    pool_f_out = _pool_filter(chosen_queue.region, chosen_queue.queue_type, chosen_queue.ranked_tier, chosen_queue.team_format)
    open_queues_count = db.query(models.Queues).filter(*pool_f_out).count()
    total_players_queued = db.query(
        func.coalesce(func.sum(models.Queues.players_in_queue), 0)
    ).filter(*pool_f_out).scalar()

    db.commit()
    db.refresh(chosen_queue)

    teams = build_queue_teams(db, chosen_queue.queue_id)

    queue_payload = {
        "queue_id": chosen_queue.queue_code,
        "region": chosen_queue.region,
        "queue_type": chosen_queue.queue_type,
        "ranked_tier": chosen_queue.ranked_tier,
        "team_format": chosen_queue.team_format,
        "status": chosen_queue.status,
        "players_in_queue": chosen_queue.players_in_queue,
        "max_players": chosen_queue.max_players,
        "players_needed": chosen_queue.max_players - chosen_queue.players_in_queue,
    }
    if chosen_queue.status == schemas.QueueStatus.COUNTDOWN.value and chosen_queue.countdown_ends_at:
        remaining = (chosen_queue.countdown_ends_at - datetime.now(timezone.utc)).total_seconds()
        queue_payload["countdown_seconds"] = max(0, int(remaining))

    return {
        "success": True,
        "queue": queue_payload,
        "assignment": {"type": "solo", "assigned_position": chosen_slot.position},
        "teams": teams,
        "region_stats": {
            "region": chosen_queue.region,
            "queue_type": chosen_queue.queue_type,
            "ranked_tier": chosen_queue.ranked_tier,
            "team_format": chosen_queue.team_format,
            "open_queues": open_queues_count,
            "total_players_queued": total_players_queued
        }
    }


def leave_solo_queue(payload, db):
    # Remove player from queue, free slot, decrement queue count.
    user_id = payload.user_id

    player = db.query(models.queue_players).filter(models.queue_players.user_id == user_id).first()
    if player is None:
        raise HTTPException(status_code=404, detail="User is not in a queue.")

    queue = db.query(models.Queues).filter(models.Queues.queue_id == player.queue_id).first()

    remove_player_from_slot(db, user_id, player.queue_id)
    db.delete(player)
    if queue is not None and queue.players_in_queue > 0:
        queue.players_in_queue = queue.players_in_queue - 1

    db.commit()

    return {"message": "User left the queue."}


def get_queue_status(user_id, db):
    # Returns queue info, assignment (solo/party), teams, region_stats. Or {in_queue: false}.
    run_queue_cleanup(db)
    player = db.query(models.queue_players).filter(
        models.queue_players.user_id == user_id
    ).first()

    if player is None:
        return {"in_queue": False}

    chosen_queue = db.query(models.Queues).filter(
        models.Queues.queue_id == player.queue_id
    ).first()

    if chosen_queue is None:
        raise HTTPException(status_code=404, detail="Queue not found.")

    now_utc = datetime.now(timezone.utc)

    if chosen_queue.status == schemas.QueueStatus.COUNTDOWN.value and chosen_queue.countdown_ends_at:
        remaining = (chosen_queue.countdown_ends_at - now_utc).total_seconds()
        if remaining <= 0:
            chosen_queue.status = schemas.QueueStatus.STARTING.value
            chosen_queue.countdown_ends_at = None
            db.commit()
            db.refresh(chosen_queue)
        else:
            pass

    # Region stats for the same pool (region + queue_type + ranked_tier + team_format)
    pool_filter = [
        models.Queues.status == schemas.QueueStatus.OPEN.value,
        models.Queues.region == chosen_queue.region,
        models.Queues.queue_type == chosen_queue.queue_type,
        models.Queues.team_format == chosen_queue.team_format,
    ]
    if chosen_queue.ranked_tier:
        pool_filter.append(models.Queues.ranked_tier == chosen_queue.ranked_tier)
    else:
        pool_filter.append(models.Queues.ranked_tier.is_(None))

    open_queues_count = db.query(models.Queues).filter(*pool_filter).count()

    total_players_queued = db.query(func.count(models.queue_players.user_id)).join(
        models.Queues,
        models.queue_players.queue_id == models.Queues.queue_id
    ).filter(*pool_filter).scalar()

    assignment = build_queue_assignment(db, player)
    teams = build_queue_teams(db, chosen_queue.queue_id)

    queue_payload = {
        "queue_id": chosen_queue.queue_code,
        "region": chosen_queue.region,
        "queue_type": chosen_queue.queue_type,
        "ranked_tier": chosen_queue.ranked_tier,
        "team_format": chosen_queue.team_format,
        "status": chosen_queue.status,
        "players_in_queue": chosen_queue.players_in_queue,
        "max_players": chosen_queue.max_players,
        "players_needed": chosen_queue.max_players - chosen_queue.players_in_queue,
    }

    if chosen_queue.status == schemas.QueueStatus.COUNTDOWN.value and chosen_queue.countdown_ends_at:
        remaining = (chosen_queue.countdown_ends_at - now_utc).total_seconds()
        queue_payload["countdown_seconds"] = max(0, int(remaining))

    if chosen_queue.status in (schemas.QueueStatus.STARTING.value, schemas.QueueStatus.TELEPORTING.value):
        queue_payload["place_id"] = settings.match_place_id
        if chosen_queue.reserved_job_id:
            queue_payload["job_id"] = chosen_queue.reserved_job_id

    region_stats = {
        "region": chosen_queue.region,
        "queue_type": chosen_queue.queue_type,
        "ranked_tier": chosen_queue.ranked_tier,
        "team_format": chosen_queue.team_format,
        "open_queues": open_queues_count,
        "total_players_queued": total_players_queued
    }

    return {
        "success": True,
        "queue": queue_payload,
        "assignment": assignment,
        "teams": teams,
        "region_stats": region_stats
    }

# ----------------------------------------------------------------------
# Reserve / test force start
# ----------------------------------------------------------------------

def test_force_start_queue(queue_code: str, db, job_id: Optional[str] = None):
    # TEMP: For Postman/testing. Force the queue to start (skip countdown) or straight to teleporting.
    # No job_id: status=starting. Roblox will ReserveServer and POST /reserve.
    # With job_id: status=teleporting, store job_id. Clients get place_id+job_id.
    queue = db.query(models.Queues).filter(models.Queues.queue_code == queue_code).first()
    if queue is None:
        raise HTTPException(status_code=404, detail="Queue not found.")
    if queue.players_in_queue == 0:
        raise HTTPException(status_code=400, detail="Queue is empty.")

    if job_id:
        queue.status = schemas.QueueStatus.TELEPORTING.value
        queue.reserved_job_id = job_id
        queue.countdown_ends_at = None
        db.commit()
        return {"success": True, "status": "teleporting", "job_id": job_id}
    else:
        queue.status = schemas.QueueStatus.STARTING.value
        queue.countdown_ends_at = None
        db.commit()
        return {"success": True, "status": "starting", "message": "Queue ready for Roblox to reserve."}


def reserve_queue(queue_code: str, job_id: str, db):
    # First Roblox server to call with valid job_id claims teleport. Stores job_id, sets status=TELEPORTING.
    queue = db.query(models.Queues).filter(models.Queues.queue_code == queue_code).first()
    if queue is None:
        raise HTTPException(status_code=404, detail="Queue not found.")
    if queue.status != schemas.QueueStatus.STARTING.value:
        raise HTTPException(
            status_code=400,
            detail=f"Queue not ready for reserve. Status: {queue.status}."
        )
    if queue.reserved_job_id:
        return {"success": True, "already_reserved": True}

    queue.reserved_job_id = job_id
    queue.status = schemas.QueueStatus.TELEPORTING.value
    db.commit()
    return {"success": True, "job_id": job_id}


def get_queue_teleport_info(queue_code: str, db):
    # Roblox server calls this after reserve to get place_id, job_id, user_ids for teleporting all players.
    queue = db.query(models.Queues).filter(models.Queues.queue_code == queue_code).first()
    if queue is None:
        raise HTTPException(status_code=404, detail="Queue not found.")
    if queue.status != schemas.QueueStatus.TELEPORTING.value:
        raise HTTPException(
            status_code=400,
            detail=f"Queue not ready for teleport. Status: {queue.status}."
        )
    if not queue.reserved_job_id:
        raise HTTPException(status_code=400, detail="Queue has no reserved job_id.")

    players = db.query(models.queue_players.user_id).filter(
        models.queue_players.queue_id == queue.queue_id
    ).all()
    user_ids = [p.user_id for p in players]

    return {
        "success": True,
        "place_id": settings.match_place_id,
        "job_id": queue.reserved_job_id,
        "user_ids": user_ids,
    }


def run_queue_cleanup(db):
    # Delete stale empty queues (5 min) and teleported queues (10 min). Returns counts for logging.
    now = datetime.now(timezone.utc)
    empty_cutoff = now - timedelta(minutes=5)
    teleport_cutoff = now - timedelta(minutes=10)

    empty_queues = db.query(models.Queues.queue_id).filter(
        models.Queues.status == schemas.QueueStatus.OPEN.value,
        models.Queues.players_in_queue == 0,
        models.Queues.created_at < empty_cutoff,
    ).all()
    empty_ids = [q.queue_id for q in empty_queues]

    teleport_queues = db.query(models.Queues.queue_id).filter(
        models.Queues.status == schemas.QueueStatus.TELEPORTING.value,
        models.Queues.created_at < teleport_cutoff,
    ).all()
    teleport_ids = [q.queue_id for q in teleport_queues]

    to_delete = list(set(empty_ids + teleport_ids))
    deleted_empty = len(empty_ids)
    deleted_teleported = len(teleport_ids)

    if not to_delete:
        return {"deleted_empty": 0, "deleted_teleported": 0}

    db.query(models.queue_players).filter(
        models.queue_players.queue_id.in_(to_delete)
    ).delete(synchronize_session=False)
    db.query(models.QueueSlot).filter(
        models.QueueSlot.queue_id.in_(to_delete)
    ).delete(synchronize_session=False)
    db.query(models.Queues).filter(models.Queues.queue_id.in_(to_delete)).delete(
        synchronize_session=False
    )
    db.commit()

    return {"deleted_empty": deleted_empty, "deleted_teleported": deleted_teleported}

# ----------------------------------------------------------------------
# Region stats
# ----------------------------------------------------------------------

def get_region_status(payload, db):
    # Stats for a specific pool: region + queue_type + ranked_tier + team_format.
    run_queue_cleanup(db)
    pool_filter = [
        models.Queues.region == payload.region.value,
        models.Queues.status == schemas.QueueStatus.OPEN.value,
        models.Queues.queue_type == payload.queue_type.value,
        models.Queues.team_format == payload.team_format,
    ]
    if payload.ranked_tier:
        pool_filter.append(models.Queues.ranked_tier == payload.ranked_tier.value)
    else:
        pool_filter.append(models.Queues.ranked_tier.is_(None))

    open_queues_count = db.query(models.Queues).filter(*pool_filter).count()

    total_players_queued = db.query(
        func.coalesce(func.sum(models.Queues.players_in_queue), 0)
    ).filter(*pool_filter).scalar()

    return {
        "success": True,
        "region_stats": {
            "region": payload.region.value,
            "queue_type": payload.queue_type.value,
            "ranked_tier": payload.ranked_tier.value if payload.ranked_tier else None,
            "team_format": payload.team_format,
            "open_queues": open_queues_count,
            "total_players_queued": int(total_players_queued)
        }
    }

# ----------------------------------------------------------------------
# Server list (manual queue mode)
# ----------------------------------------------------------------------

def _pool_filter(region_val, queue_type_val, ranked_tier_val, team_format_val):
    # Build filter for region + queue_type + ranked_tier + team_format.
    f = [
        models.Queues.region == region_val,
        models.Queues.status == schemas.QueueStatus.OPEN.value,
        models.Queues.queue_type == queue_type_val,
        models.Queues.team_format == team_format_val,
    ]
    if ranked_tier_val:
        f.append(models.Queues.ranked_tier == ranked_tier_val)
    else:
        f.append(models.Queues.ranked_tier.is_(None))
    return f


def list_queues(payload, db):
    # Paginated list of open queues for manual queue mode. Same pool as region/status.
    run_queue_cleanup(db)
    region_val = payload.region.value
    queue_type_val = payload.queue_type.value
    ranked_tier_val = payload.ranked_tier.value if payload.ranked_tier else None
    team_format_val = payload.team_format
    page = payload.page
    page_size = payload.page_size

    pool_f = _pool_filter(region_val, queue_type_val, ranked_tier_val, team_format_val)

    total_count = db.query(models.Queues).filter(*pool_f).count()

    offset = (page - 1) * page_size
    queues = db.query(models.Queues).filter(*pool_f).order_by(
        models.Queues.created_at.desc()
    ).offset(offset).limit(page_size).all()

    total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 0

    queue_items = []
    for q in queues:
        level_range = None
        if q.queue_type == schemas.QueueType.RANKED.value and q.ranked_tier:
            # Level ranges: pro 30-60, elite 60-99
            ranges = {"pro": (30, 60), "elite": (60, 99)}
            mn, mx = ranges.get(q.ranked_tier, (1, 99))
            level_range = {"min": mn, "max": mx}
        queue_items.append({
            "queue_code": q.queue_code,
            "region": q.region,
            "queue_type": q.queue_type,
            "ranked_tier": q.ranked_tier,
            "team_format": q.team_format,
            "status": q.status,
            "players_in_queue": q.players_in_queue,
            "max_players": q.max_players,
            "players_needed": q.max_players - q.players_in_queue,
            "level_range": level_range,
        })

    return {
        "success": True,
        "queues": queue_items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_count": total_count,
            "total_pages": total_pages,
        },
        "region_stats": {
            "region": region_val,
            "queue_type": queue_type_val,
            "ranked_tier": ranked_tier_val,
            "team_format": team_format_val,
            "open_queues": total_count,
            "total_players_queued": int(db.query(func.coalesce(func.sum(models.Queues.players_in_queue), 0)).filter(*pool_f).scalar() or 0),
        }
    }


def join_manual_queue(payload, db):
    # Join a specific queue by queue_code (from a server list). Same validation as solo join.
    user_id = payload.user_id
    queue_code = payload.queue_code
    positions = payload.positions
    queue_type_val = payload.queue_type.value
    ranked_tier_val = payload.ranked_tier.value if payload.ranked_tier else None
    team_format_val = payload.team_format

    existing_player = db.query(models.queue_players).filter(models.queue_players.user_id == user_id).first()
    if existing_player:
        raise HTTPException(status_code=400, detail="User is already in a queue.")

    chosen_queue = db.query(models.Queues).filter(
        models.Queues.queue_code == queue_code,
        models.Queues.status == schemas.QueueStatus.OPEN.value,
    ).first()

    if chosen_queue is None:
        raise HTTPException(status_code=404, detail="Queue not found or no longer open.")

    if chosen_queue.queue_type != queue_type_val or chosen_queue.team_format != team_format_val:
        raise HTTPException(status_code=400, detail="Queue type or team format mismatch.")

    if (chosen_queue.ranked_tier or ranked_tier_val) and chosen_queue.ranked_tier != ranked_tier_val:
        raise HTTPException(status_code=400, detail="Ranked tier mismatch.")

    if chosen_queue.players_in_queue >= chosen_queue.max_players:
        raise HTTPException(status_code=400, detail="Queue is full.")

    chosen_slot = find_matching_open_slot(db, chosen_queue.queue_id, positions)
    if chosen_slot is None:
        raise HTTPException(status_code=400, detail="No open slot for your positions in this queue.")

    chosen_slot.occupant_user_id = user_id
    chosen_slot.status = "filled"

    new_queue_player = models.queue_players(
        user_id=user_id,
        queue_id=chosen_queue.queue_id,
        assigned_slot_id=chosen_slot.slot_id,
        player_level=payload.player_level,
    )
    db.add(new_queue_player)

    chosen_queue.players_in_queue = chosen_queue.players_in_queue + 1

    if chosen_queue.players_in_queue >= chosen_queue.max_players:
        chosen_queue.status = schemas.QueueStatus.COUNTDOWN.value
        chosen_queue.countdown_ends_at = datetime.now(timezone.utc) + timedelta(seconds=COUNTDOWN_SECONDS)

    pool_f = _pool_filter(chosen_queue.region, chosen_queue.queue_type, chosen_queue.ranked_tier, chosen_queue.team_format)
    open_queues_count = db.query(models.Queues).filter(*pool_f).count()
    total_players_queued = db.query(func.count(models.queue_players.user_id)).join(
        models.Queues, models.queue_players.queue_id == models.Queues.queue_id
    ).filter(*pool_f).scalar()

    db.commit()
    db.refresh(chosen_queue)

    teams = build_queue_teams(db, chosen_queue.queue_id)

    queue_payload = {
        "queue_id": chosen_queue.queue_code,
        "region": chosen_queue.region,
        "queue_type": chosen_queue.queue_type,
        "ranked_tier": chosen_queue.ranked_tier,
        "team_format": chosen_queue.team_format,
        "status": chosen_queue.status,
        "players_in_queue": chosen_queue.players_in_queue,
        "max_players": chosen_queue.max_players,
        "players_needed": chosen_queue.max_players - chosen_queue.players_in_queue,
    }
    if chosen_queue.status == schemas.QueueStatus.COUNTDOWN.value and chosen_queue.countdown_ends_at:
        remaining = (chosen_queue.countdown_ends_at - datetime.now(timezone.utc)).total_seconds()
        queue_payload["countdown_seconds"] = max(0, int(remaining))

    return {
        "success": True,
        "queue": queue_payload,
        "assignment": {"type": "solo", "assigned_position": chosen_slot.position},
        "teams": teams,
        "region_stats": {
            "region": chosen_queue.region,
            "queue_type": chosen_queue.queue_type,
            "ranked_tier": chosen_queue.ranked_tier,
            "team_format": chosen_queue.team_format,
            "open_queues": open_queues_count,
            "total_players_queued": total_players_queued
        }
    }

# ----------------------------------------------------------------------
# Party queue
# ----------------------------------------------------------------------

def join_party_queue(payload, db):
    # Place the entire party into one queue. Party exists in request only (no persistent party table).
    run_queue_cleanup(db)
    party_id = payload.party_id
    region = payload.region
    members = payload.members

    if len(members) > 4:
        raise HTTPException(status_code=400, detail="Party is to large for one queue")

    seen_user_ids = set()

    for member in members:
        if member.user_id in seen_user_ids:
            raise HTTPException(status_code=400, detail=f"Duplicate user_id {member.user_id} in party members.")
        seen_user_ids.add(member.user_id)

    for member in members:
        existing_player = db.query(models.queue_players).filter(
            models.queue_players.user_id == member.user_id
        ).first()
        if existing_player:
            raise HTTPException(status_code=400, detail=f"User {member.user_id} is already in a queue.")

    queue_type_val = payload.queue_type.value
    ranked_tier_val = payload.ranked_tier.value if payload.ranked_tier else None
    team_format_val = payload.team_format
    max_players = 10 if team_format_val == "5v5" else 14

    pool_f_party = [
        models.Queues.status == schemas.QueueStatus.OPEN.value,
        models.Queues.region == payload.region.value,
        models.Queues.queue_type == queue_type_val,
        models.Queues.team_format == team_format_val,
    ]
    if ranked_tier_val:
        pool_f_party.append(models.Queues.ranked_tier == ranked_tier_val)
    else:
        pool_f_party.append(models.Queues.ranked_tier.is_(None))
    Available_Queues = db.query(models.Queues).filter(*pool_f_party).all()

    chosen_queue = None
    party_assignments = None

    for queue in Available_Queues:
        possible_assignments = find_matching_open_slots_for_party(db, queue.queue_id, members)
        if possible_assignments is not None:
            chosen_queue = queue
            party_assignments = possible_assignments
            break

    if chosen_queue is None:
        queue_code = generate_queue_code(db, region)
        chosen_queue = models.Queues(
            queue_code=queue_code,
            region=region.value,
            status=schemas.QueueStatus.OPEN.value,
            max_players=max_players,
            players_in_queue=0,
            queue_type=queue_type_val,
            ranked_tier=ranked_tier_val,
            team_format=team_format_val,
        )
        db.add(chosen_queue)
        db.flush()

        if team_format_val == "7v7":
            create_slots_for_queue_7v7(db, chosen_queue.queue_id)
        else:
            create_slots_for_queue_5v5(db, chosen_queue.queue_id)
        db.flush()

        party_assignments = find_matching_open_slots_for_party(db, chosen_queue.queue_id, members)

    if party_assignments is None:
        raise HTTPException(status_code=500, detail="Queue created but no slots found.")

    member_by_id = {m.user_id: m for m in members}
    for assignment in party_assignments:
        member_user_id = assignment["user_id"]
        assigned_slot = assignment["slot"]
        member = member_by_id.get(member_user_id)

        assigned_slot.occupant_user_id = member_user_id
        assigned_slot.status = "filled"

        new_queue_player = models.queue_players(
            user_id=member_user_id,
            queue_id=chosen_queue.queue_id,
            assigned_slot_id=assigned_slot.slot_id,
            party_id=party_id,
            player_level=member.player_level if member else None,
        )
        db.add(new_queue_player)

    chosen_queue.players_in_queue = chosen_queue.players_in_queue + len(members)

    if chosen_queue.players_in_queue >= chosen_queue.max_players:
        chosen_queue.status = schemas.QueueStatus.COUNTDOWN.value
        chosen_queue.countdown_ends_at = datetime.now(timezone.utc) + timedelta(seconds=COUNTDOWN_SECONDS)

    db.commit()
    db.refresh(chosen_queue)

    pool_f_out = _pool_filter(chosen_queue.region, chosen_queue.queue_type, chosen_queue.ranked_tier, chosen_queue.team_format)
    open_queues_count = db.query(models.Queues).filter(*pool_f_out).count()
    total_players_queued = db.query(
        func.coalesce(func.sum(models.Queues.players_in_queue), 0)
    ).filter(*pool_f_out).scalar()

    teams = build_queue_teams(db, chosen_queue.queue_id)

    queue_payload = {
        "queue_id": chosen_queue.queue_code,
        "region": chosen_queue.region,
        "queue_type": chosen_queue.queue_type,
        "ranked_tier": chosen_queue.ranked_tier,
        "team_format": chosen_queue.team_format,
        "status": chosen_queue.status,
        "players_in_queue": chosen_queue.players_in_queue,
        "max_players": chosen_queue.max_players,
        "players_needed": chosen_queue.max_players - chosen_queue.players_in_queue,
    }
    if chosen_queue.status == schemas.QueueStatus.COUNTDOWN.value and chosen_queue.countdown_ends_at:
        remaining = (chosen_queue.countdown_ends_at - datetime.now(timezone.utc)).total_seconds()
        queue_payload["countdown_seconds"] = max(0, int(remaining))

    return {
        "success": True,
        "queue": queue_payload,
        "assignment": {
            "type": "party",
            "party_id": party_id,
            "assigned_positions": [
                {
                    "user_id": assignment["user_id"],
                    "position": assignment["slot"].position
                }
                for assignment in party_assignments
            ]
        },
        "teams": teams,
        "region_stats": {
            "region": chosen_queue.region,
            "queue_type": chosen_queue.queue_type,
            "ranked_tier": chosen_queue.ranked_tier,
            "team_format": chosen_queue.team_format,
            "open_queues": open_queues_count,
            "total_players_queued": total_players_queued
        }
    }