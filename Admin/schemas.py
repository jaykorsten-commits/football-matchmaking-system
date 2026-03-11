# Request/response validation. Add new schemas here when changing payload shapes.
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional, Literal
from enum import Enum

# ----------------------------------------------------------------------
# Enums
# ----------------------------------------------------------------------

class Region(str, Enum):
    # Add/remove regions here; update QueueFunctions if region logic changes.
    EU = "EU"
    NA = "NA"
    ASIA = "ASIA"

class Position(str, Enum):
    # Game-specific roles. Must match QueueFunctions slot_template.
    GK = "GK"
    CB = "CB"
    CM = "CM"
    ST = "ST"
    RDF = "RDF"
    LDF = "LDF"
    FW = "FW"
    LM = "LM"
    RM = "RM"

class QueueStatus(str, Enum):
    OPEN = "open"
    COUNTDOWN = "countdown"
    STARTING = "starting"
    TELEPORTING = "teleporting"
    LIVE = "live"
    CANCELLED = "cancelled"


class QueueType(str, Enum):
    # regular = open level; ranked = tiered with level ranges.
    REGULAR = "regular"
    RANKED = "ranked"


class RankedTier(str, Enum):
    # Tier when queue_type=ranked. Level ranges: beginner 1-29, pro 30-60, elite 60-99.
    BEGINNER = "beginner"
    PRO = "pro"
    ELITE = "elite"

# ----------------------------------------------------------------------
# Request schemas
# ----------------------------------------------------------------------

class BaseSchema(BaseModel):
    # extra='forbid' blocks unknown fields. Remove if you need flexible payloads.
    model_config = ConfigDict(
        extra="forbid"  # reject unknown fields in requests
    )

class SoloJoinRequest(BaseSchema):
    user_id: int
    region: Region
    positions: list[Position] = Field(min_length=1, max_length=4)
    team_format: Literal["5v5", "7v7"]
    queue_type: QueueType
    ranked_tier: Optional[RankedTier] = None  # required when queue_type=ranked
    player_level: Optional[int] = Field(default=None, ge=1, le=99)  # required when queue_type=ranked

class PartyMemberInput(BaseSchema):
    user_id: int
    positions: list[Position] = Field(min_length=1, max_length=4)
    player_level: Optional[int] = Field(default=None, ge=1, le=99)  # required when queue_type=ranked

class PartyJoinRequest(BaseSchema):
    party_id: str = Field(min_length=1, max_length=64)
    region: Region
    members: list[PartyMemberInput] = Field(min_length=2, max_length=4)
    team_format: Literal["5v5", "7v7"]
    queue_type: QueueType
    ranked_tier: Optional[RankedTier] = None  # required when queue_type=ranked

class LeaveRequest(BaseSchema):
    user_id: int


class RegionStatsRequest(BaseSchema):
    region: Region
    queue_type: QueueType
    ranked_tier: Optional[RankedTier] = None  # required when queue_type=ranked
    team_format: Literal["5v5", "7v7"]


class QueueListRequest(BaseSchema):
    # Manual queue mode: list open queues with pagination.
    region: Region
    queue_type: QueueType
    ranked_tier: Optional[RankedTier] = None
    team_format: Literal["5v5", "7v7"]
    page: int = Field(default=1, ge=1, description="Page number (1-based)")
    page_size: int = Field(default=10, ge=1, le=50, description="Queues per page")


class ManualJoinRequest(BaseSchema):
    # Join a specific queue from the server list (manual queue mode).
    user_id: int
    queue_code: str = Field(min_length=1, max_length=64)  # e.g. eu_01
    positions: list[Position] = Field(min_length=1, max_length=4)
    team_format: Literal["5v5", "7v7"]
    queue_type: QueueType
    ranked_tier: Optional[RankedTier] = None
    player_level: Optional[int] = Field(default=None, ge=1, le=99)


class ReserveRequest(BaseSchema):
    job_id: str = Field(min_length=1, max_length=128)

class TestForceStartRequest(BaseSchema):
    # Optional. If job_id provided, skips reserve and goes straight to teleporting.
    job_id: Optional[str] = Field(default=None, max_length=128)

