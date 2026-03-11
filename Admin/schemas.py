"""
Request/response validation. Add new schemas here when changing payload shapes.
"""
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional,Literal
from enum import Enum

class Region(str, Enum):
    """Add/remove regions here; update QueueFunctions if region logic changes."""
    EU = "EU"
    NA = "NA"
    ASIA = "ASIA"

class Position(str, Enum):
    """Game-specific roles. Must match QueueFunctions.slot_template in QueueFunctions."""
    GK = "GK"
    CB = "CB"
    CM = "CM"
    ST = "ST"

class QueueStatus(str, Enum):
    OPEN = "open"
    COUNTDOWN = "countdown"
    STARTING = "starting"
    TELEPORTING = "teleporting"
    LIVE = "live"
    CANCELLED = "cancelled"

class BaseSchema(BaseModel):
    """extra='forbid' blocks unknown fields. Remove if you need flexible payloads."""
    model_config = ConfigDict(
        extra="forbid"  # reject unknown fields
    )

class SoloJoinRequest(BaseSchema):
    user_id: int
    region: Region
    positions: list[Position] = Field(min_length=1, max_length=4) # So that the player can select preferences

class PartyMemberInput(BaseSchema):
    user_id: int
    positions: list[Position] = Field(min_length=1, max_length=4)

class PartyJoinRequest(BaseSchema):
    party_id: str = Field(min_length=1, max_length=64)
    region: Region
    members: list[PartyMemberInput] = Field(min_length=2, max_length=4)

class LeaveRequest(BaseSchema):
    user_id: int


class RegionStatsRequest(BaseSchema):
    region: Region


class ReserveRequest(BaseSchema):
    job_id: str = Field(min_length=1, max_length=128)


class TestForceStartRequest(BaseSchema):
    """Optional. If job_id provided, skips reserve and goes straight to teleporting."""
    job_id: Optional[str] = Field(default=None, max_length=128)

