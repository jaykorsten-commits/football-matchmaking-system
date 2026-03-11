# Queue API routes. Payloads validated via schemas; logic in QueueFunctions.
from fastapi import FastAPI, Request, Response, status, HTTPException, Depends, APIRouter, Body
from sqlalchemy.orm import Session
from typing import Optional
from sqlalchemy import desc,select,Column
from sqlalchemy.util import deprecated
from sqlalchemy import func
from Admin.Database import get_db
from Admin import schemas, models
from Admin.config import settings
from Admin.QueueFunctions import (
    join_solo_queue,
    leave_solo_queue,
    get_queue_status,
    get_region_status,
    list_queues,
    join_manual_queue,
    join_party_queue,
    reserve_queue,
    test_force_start_queue,
    get_queue_teleport_info,
    run_queue_cleanup,
)

# ----------------------------------------------------------------------
# API key verification
# ----------------------------------------------------------------------

def verify_api_key(request: Request):
    # Require X-API-Key header when QUEUE_API_KEY or API_KEY is set in config.
    if not settings.api_key:
        return
    key = request.headers.get("X-API-Key")
    if key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

router = APIRouter(tags=['Queue Service'], dependencies=[Depends(verify_api_key)])

# ----------------------------------------------------------------------
# Queue routes
# ----------------------------------------------------------------------

@router.post("/queue/join/solo")
def join_solo_queue_route(payload: schemas.SoloJoinRequest, db: Session = Depends(get_db)):
    result = join_solo_queue(payload=payload,db=db)
    return result


@router.post("/queue/leave/solo")
def leave_solo_queue_route(payload: schemas.LeaveRequest, db: Session = Depends(get_db)):
    result = leave_solo_queue(payload=payload,db=db)
    return result


@router.get("/queue/status/{user_id}")
def get_queue_status_route(user_id: int, db: Session = Depends(get_db)):
    result = get_queue_status(user_id=user_id,db=db)
    return result

@router.post("/queue/region/status")
def get_region_status_route(payload: schemas.RegionStatsRequest, db: Session = Depends(get_db)):
    result = get_region_status(payload=payload, db=db)
    return result


@router.post("/queue/list")
def list_queues_route(payload: schemas.QueueListRequest, db: Session = Depends(get_db)):
    result = list_queues(payload=payload, db=db)
    return result


@router.post("/queue/join/manual")
def join_manual_queue_route(payload: schemas.ManualJoinRequest, db: Session = Depends(get_db)):
    result = join_manual_queue(payload=payload, db=db)
    return result


@router.post("/queue/join/party")
def join_party_queue_route(payload: schemas.PartyJoinRequest, db: Session = Depends(get_db)):
    result = join_party_queue(payload=payload, db=db)
    return result


@router.post("/queue/{queue_code}/reserve")
def reserve_queue_route(queue_code: str, payload: schemas.ReserveRequest, db: Session = Depends(get_db)):
    result = reserve_queue(queue_code=queue_code, job_id=payload.job_id, db=db)
    return result


@router.get("/queue/{queue_code}/teleport-info")
def get_teleport_info_route(queue_code: str, db: Session = Depends(get_db)):
    result = get_queue_teleport_info(queue_code=queue_code, db=db)
    return result


@router.post("/queue/cleanup/run")
def cleanup_run_route(db: Session = Depends(get_db)):
    result = run_queue_cleanup(db=db)
    return result


@router.post("/queue/{queue_code}/test-force-start")
def test_force_start_route(queue_code: str, payload: Optional[schemas.TestForceStartRequest] = Body(None), db: Session = Depends(get_db)):
    # TEMP: For Postman testing. Force queue to starting/teleporting without waiting for full players or countdown.
    job_id = payload.job_id if payload and payload.job_id else None
    result = test_force_start_queue(queue_code=queue_code, db=db, job_id=job_id)
    return result


