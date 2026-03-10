"""
Queue matchmaking logic: solo/party join, leave, status.
Adapt slot_template in create_slots_for_queue() for different game formats (e.g. 3v3, 5v5).
"""
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


def build_queue_teams(db, queue_id):
    """Build team_a / team_b rosters from filled slots. Used in status and join responses."""
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
    """Returns solo or party assignment. Party includes all members' positions for UI."""
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


def create_slots_for_queue(db, queue_id):
    """Create slot rows per queue. Edit slot_template for different formats (3v3, 5v5, etc)."""
    slot_template = [
        ("A","GK",1),
        ("A","CB",1),
        ("A","CM",1),
        ("A","ST",1),
        ("B","GK",1),
        ("B","CB",1),
        ("B","CM",1),
        ("B","ST",1),
    ]
    for team,position,slot_number in slot_template:
        db.add(models.QueueSlot(queue_id=queue_id, position=position, slot_number=slot_number, team=team, status=schemas.QueueStatus.OPEN.value))


def find_matching_open_slot(db, queue_id, position):
    """Find first open slot matching any preferred position. Returns slot or None."""
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
    """Check if whole party can fit. Returns list of {user_id, slot} or None if impossible."""
    available_slots = db.query(models.QueueSlot).filter(
        models.QueueSlot.queue_id == queue_id,
        models.QueueSlot.status == schemas.QueueStatus.OPEN.value,
        models.QueueSlot.occupant_user_id.is_(None)
    ).all()

    assigned_slots = []
    used_slot_ids = set()

    for member in members:
        matched_slot = None

        for preferred_position in member.positions:
            for slot in available_slots:
                if slot.slot_id in used_slot_ids:
                    continue

                if slot.position == preferred_position.value:
                    matched_slot = slot
                    break

            if matched_slot is not None:
                break
        if matched_slot is None:
            return None

        assigned_slots.append({
            "user_id": member.user_id
            ,"slot": matched_slot
        })

        used_slot_ids.add(matched_slot.slot_id)

    return assigned_slots


def remove_player_from_slot(db, user_id, queue_id):
    """Free slot and set status back to OPEN. Used when player leaves queue."""
    slot = db.query(models.QueueSlot).filter(
        models.QueueSlot.occupant_user_id == user_id,
        models.QueueSlot.queue_id == queue_id).first()
    if not slot:
        return None
    slot.occupant_user_id = None
    slot.status = schemas.QueueStatus.OPEN.value
    return slot


def join_solo_queue(payload, db):
    """Place solo player in queue. Uses existing open queue or creates new one."""
    user_id = payload.user_id
    region = payload.region
    positions = payload.positions

    existing_player = db.query(models.queue_players).filter(models.queue_players.user_id == user_id).first()
    if existing_player:
        raise HTTPException(status_code=400, detail="User is already in a queue.")

    Available_Queues = db.query(models.Queues).filter(models.Queues.status == schemas.QueueStatus.OPEN.value,
                                                      models.Queues.region == payload.region.value).all()
    chosen_queue = None
    chosen_slot = None

    for queue in Available_Queues:
        slot = find_matching_open_slot(db, queue.queue_id, positions)
        if slot:
            chosen_queue = queue
            chosen_slot = slot
            break

    if chosen_queue is None:
        queue_code = generate_queue_code(db,region)

        chosen_queue = models.Queues(queue_code=queue_code,region=region.value,status=schemas.QueueStatus.OPEN.value,max_players=8,players_in_queue=0)
        db.add(chosen_queue)
        db.flush()

        create_slots_for_queue(db,chosen_queue.queue_id)
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
            assigned_slot_id=chosen_slot.slot_id
        )

    db.add(new_queue_player)


    chosen_queue.players_in_queue = chosen_queue.players_in_queue + 1

    if chosen_queue.players_in_queue >= chosen_queue.max_players:
        chosen_queue.status = schemas.QueueStatus.COUNTDOWN.value
        chosen_queue.countdown_ends_at = datetime.now(timezone.utc) + timedelta(seconds=COUNTDOWN_SECONDS)

    open_queues_count = db.query(models.Queues).filter(
        models.Queues.status == schemas.QueueStatus.OPEN.value,
        models.Queues.region == chosen_queue.region
    ).count()

    total_players_queued = db.query(
        func.coalesce(func.sum(models.Queues.players_in_queue), 0)
    ).filter(
        models.Queues.region == chosen_queue.region,
        models.Queues.status == schemas.QueueStatus.OPEN.value
    ).scalar()

    db.commit()
    db.refresh(chosen_queue)

    teams = build_queue_teams(db, chosen_queue.queue_id)

    queue_payload = {
        "queue_id": chosen_queue.queue_code,
        "region": chosen_queue.region,
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
            "open_queues": open_queues_count,
            "total_players_queued": total_players_queued
        }
    }


def leave_solo_queue(payload, db):
    """Remove player from queue, free slot, decrement queue count."""
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
    """Returns queue info, assignment (solo/party), teams, region_stats. Or {in_queue: false}."""
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

    open_queues_count = db.query(models.Queues).filter(
        models.Queues.status == schemas.QueueStatus.OPEN.value,
        models.Queues.region == chosen_queue.region
    ).count()

    total_players_queued = db.query(func.count(models.queue_players.user_id)).join(
        models.Queues,
        models.queue_players.queue_id == models.Queues.queue_id
    ).filter(
        models.Queues.region == chosen_queue.region,
        models.Queues.status == schemas.QueueStatus.OPEN.value
    ).scalar()

    assignment = build_queue_assignment(db, player)
    teams = build_queue_teams(db, chosen_queue.queue_id)

    queue_payload = {
        "queue_id": chosen_queue.queue_code,
        "region": chosen_queue.region,
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

    return {
        "success": True,
        "queue": queue_payload,
        "assignment": assignment,
        "teams": teams,
        "region_stats": {
            "region": chosen_queue.region,
            "open_queues": open_queues_count,
            "total_players_queued": total_players_queued
        }
    }


def test_force_start_queue(queue_code: str, db, job_id: Optional[str] = None):
    """
    TEMP: For Postman/testing. Force queue to starting (skip countdown) or straight to teleporting.
    - No job_id: set status=starting. Roblox will ReserveServer and POST /reserve.
    - With job_id: set status=teleporting, store job_id. Clients get place_id+job_id immediately.
    """
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
    """
    First Roblox server to call this with a valid job_id claims the teleport.
    Stores job_id, sets status to TELEPORTING.
    """
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


def get_region_status(payload, db):
    """Region-wide stats: open queues count, total players queued."""
    open_queues_count = db.query(models.Queues).filter(
        models.Queues.region == payload.region.value,
        models.Queues.status == "open"
    ).count()

    total_players_queued = db.query(
        func.coalesce(func.sum(models.Queues.players_in_queue), 0)
    ).filter(
        models.Queues.region == payload.region.value,
        models.Queues.status == schemas.QueueStatus.OPEN.value
    ).scalar()

    return {
        "region_stats": {
            "region": payload.region.value,
            "open_queues": open_queues_count,
            "total_players_queued": total_players_queued
        }
    }



def join_party_queue(payload, db):
    """Place entire party into one queue. Party exists in request only (no persistent party table)."""
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

    Available_Queues = db.query(models.Queues).filter(
        models.Queues.status == schemas.QueueStatus.OPEN.value,
        models.Queues.region == payload.region.value
    ).all()

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
            max_players=8,
            players_in_queue=0
        )
        db.add(chosen_queue)
        db.flush()

        create_slots_for_queue(db, chosen_queue.queue_id)
        db.flush()

        party_assignments = find_matching_open_slots_for_party(db, chosen_queue.queue_id, members)

    if party_assignments is None:
        raise HTTPException(status_code=500, detail="Queue created but no slots found.")

    for assignment in party_assignments:
        member_user_id = assignment["user_id"]
        assigned_slot = assignment["slot"]

        assigned_slot.occupant_user_id = member_user_id
        assigned_slot.status = "filled"

        new_queue_player = models.queue_players(
            user_id=member_user_id,
            queue_id=chosen_queue.queue_id,
            assigned_slot_id=assigned_slot.slot_id,
            party_id=party_id
        )
        db.add(new_queue_player)

    chosen_queue.players_in_queue = chosen_queue.players_in_queue + len(members)

    if chosen_queue.players_in_queue >= chosen_queue.max_players:
        chosen_queue.status = schemas.QueueStatus.COUNTDOWN.value
        chosen_queue.countdown_ends_at = datetime.now(timezone.utc) + timedelta(seconds=COUNTDOWN_SECONDS)

    db.commit()
    db.refresh(chosen_queue)

    open_queues_count = db.query(models.Queues).filter(
        models.Queues.status == schemas.QueueStatus.OPEN.value,
        models.Queues.region == chosen_queue.region
    ).count()

    total_players_queued = db.query(
        func.coalesce(func.sum(models.Queues.players_in_queue), 0)
    ).filter(
        models.Queues.region == chosen_queue.region,
        models.Queues.status == schemas.QueueStatus.OPEN.value
    ).scalar()

    teams = build_queue_teams(db, chosen_queue.queue_id)

    queue_payload = {
        "queue_id": chosen_queue.queue_code,
        "region": chosen_queue.region,
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
            "open_queues": open_queues_count,
            "total_players_queued": total_players_queued
        }
    }