"""add is_subscribed to users

Revision ID: a1b2c3d4e5f6
Revises: eb47cadd9123
Create Date: 2026-09-26 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = 'eb47cadd9123'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # False for every existing account — no one was subscribed before
    # this column existed, and new accounts default to False in the ORM
    # (see db/models.py's User.is_subscribed).
    op.add_column(
        'users',
        sa.Column('is_subscribed', sa.Boolean(), nullable=False, server_default='false'),
    )


def downgrade() -> None:
    op.drop_column('users', 'is_subscribed')
