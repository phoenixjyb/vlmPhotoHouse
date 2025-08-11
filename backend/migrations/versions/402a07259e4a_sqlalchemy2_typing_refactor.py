#!/usr/bin/env python
"""sqlalchemy2_typing_refactor

Revision ID: 402a07259e4a
Revises: 0001_initial
Create Date: 2025-08-11 17:57:30.766260

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '402a07259e4a'
down_revision = '0001_initial'
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != 'sqlite':
        op.alter_column('assets', 'status',
                    existing_type=sa.VARCHAR(length=16),
                    nullable=False)
    # SQLite: skip (column already has default; enforcing NOT NULL requires table rebuild)

def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != 'sqlite':
        op.alter_column('assets', 'status',
                    existing_type=sa.VARCHAR(length=16),
                    nullable=True)
