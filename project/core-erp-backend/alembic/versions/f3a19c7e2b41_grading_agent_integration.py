"""grading_agent integration: origen de la nota y revisión docente

Revision ID: f3a19c7e2b41
Revises: cc1706fd3ce3
Create Date: 2026-07-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a19c7e2b41'
down_revision: Union[str, None] = 'cc1706fd3ce3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    graded_by_enum = sa.Enum('teacher', 'ai_grading_agent', name='gradedby')
    graded_by_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        'grades',
        sa.Column('graded_by', graded_by_enum, nullable=False, server_default='teacher'),
    )
    op.add_column(
        'grades',
        sa.Column('feedback', sa.String(), nullable=True),
    )
    op.add_column(
        'grades',
        sa.Column('needs_teacher_review', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        'grades',
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('grades', 'reviewed_at')
    op.drop_column('grades', 'needs_teacher_review')
    op.drop_column('grades', 'feedback')
    op.drop_column('grades', 'graded_by')
    sa.Enum(name='gradedby').drop(op.get_bind(), checkfirst=True)
