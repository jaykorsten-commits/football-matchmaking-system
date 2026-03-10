"""add countdown and reserve columns to queues

Revision ID: add_countdown_reserve
Revises: 801ae74ce1f5
Create Date: 2026-03-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "add_countdown_reserve"
down_revision: Union[str, Sequence[str], None] = "801ae74ce1f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("queues", sa.Column("countdown_ends_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("queues", sa.Column("reserved_job_id", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("queues", "reserved_job_id")
    op.drop_column("queues", "countdown_ends_at")
