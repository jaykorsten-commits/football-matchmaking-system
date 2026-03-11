"""add queue_type, ranked_tier, team_format, player_level

Revision ID: add_queue_type_tf
Revises: add_countdown_reserve
Create Date: 2026-03-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "add_queue_type_tf"
down_revision: Union[str, Sequence[str], None] = "add_countdown_reserve"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("queues", sa.Column("queue_type", sa.String(), nullable=False, server_default="regular"))
    op.add_column("queues", sa.Column("ranked_tier", sa.String(), nullable=True))
    op.add_column("queues", sa.Column("team_format", sa.String(), nullable=False, server_default="5v5"))
    op.add_column("queue_players", sa.Column("player_level", sa.Integer(), nullable=True))
    op.alter_column("queues", "queue_type", server_default=None)
    op.alter_column("queues", "team_format", server_default=None)


def downgrade() -> None:
    op.drop_column("queue_players", "player_level")
    op.drop_column("queues", "team_format")
    op.drop_column("queues", "ranked_tier")
    op.drop_column("queues", "queue_type")
