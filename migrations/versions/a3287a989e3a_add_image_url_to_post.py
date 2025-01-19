"""Add image_url to Post

Revision ID: a3287a989e3a
Revises: 22d6df9a3a44
Create Date: 2025-01-12 15:59:33.444358

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a3287a989e3a'
down_revision = '22d6df9a3a44'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('posts', sa.Column('video_url', sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column('posts', 'video_url')

    # ### end Alembic commands ###
