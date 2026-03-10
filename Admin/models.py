"""
Database models for queue matchmaking.
Change slot structure here and in QueueFunctions.slot_template for different games.
"""
from sqlalchemy import Column, Integer, String, Boolean, TIMESTAMP, text, ForeignKey, BigInteger
from sqlalchemy.sql.expression import null
from sqlalchemy.sql.sqltypes import TIMESTAMP
from .Database import Base
from sqlalchemy.orm import relationship


class Queues(Base):
    """One queue instance. queue_code is human-readable (e.g. eu_01)."""
    __tablename__ = 'queues'
    queue_id = Column(Integer, primary_key=True, nullable=False, unique=True)
    queue_code = Column(String, nullable=False, unique=True)
    status = Column(String, nullable=False)
    region = Column(String, nullable=False)
    max_players = Column(Integer, nullable=False)
    players_in_queue = Column(Integer, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), default=text('now()'), nullable=False)
    countdown_ends_at = Column(TIMESTAMP(timezone=True), nullable=True)
    reserved_job_id = Column(String, nullable=True)


class QueueSlot(Base):
    """Individual seat in a queue. team + position define the role (e.g. A/GK, B/ST)."""
    __tablename__ = 'queue_slot'
    slot_id = Column(Integer, primary_key=True,nullable=False,unique=True)
    queue_id = Column(Integer, ForeignKey('queues.queue_id'), nullable=False)
    team = Column(String, nullable=False)
    position = Column(String, nullable=False)
    slot_number = Column(Integer, nullable=False)
    occupant_user_id = Column(BigInteger, nullable=True)
    status = Column(String, nullable=False)

class queue_players(Base):
    """Links a user to a queue and their assigned slot. party_id groups party members."""
    __tablename__ = 'queue_players'
    id = Column(Integer, primary_key=True,nullable=False,unique=True)
    user_id = Column(BigInteger, nullable=False)
    queue_id = Column(Integer, ForeignKey('queues.queue_id'), nullable=False)
    party_id = Column(String, nullable=True)
    assigned_slot_id = Column(Integer, ForeignKey('queue_slot.slot_id'), nullable=False)
    joined_at = Column(TIMESTAMP(timezone=True),default=text('now()'),nullable=False)

class matches(Base):
    """Future: reserved match/server after queue fills."""
    __tablename__ = 'matches'
    match_id = Column(Integer, primary_key=True,nullable=False,unique=True)
    queue_id = Column(Integer, ForeignKey('queues.queue_id'), nullable=False)
    match_code = Column(String, nullable=False,unique=True)
    status = Column(String, nullable=False)
    region = Column(String, nullable=False)
    place_id = Column(BigInteger, nullable=False)
    reserved_server_code = Column(String, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True),default=text('now()'),nullable=False)

class region_counters(Base):
    """Generates unique queue codes per region (eu_01, eu_02, ...)."""
    __tablename__ = 'region_counters'
    region = Column(String, primary_key=True,nullable=False,unique=True)
    next_number = Column(Integer, nullable=False)

