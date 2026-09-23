"""academic memory and approved board publication audit

Revision ID: f1a9c2d4e6b8
Revises: cc1706fd3ce3
"""
from alembic import op
import sqlalchemy as sa

revision = "f1a9c2d4e6b8"
down_revision = "cc1706fd3ce3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("academic_contents",
        sa.Column("id", sa.String(), primary_key=True), sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("classroom_id", sa.String(), nullable=True), sa.Column("created_by_user_id", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False), sa.Column("grade", sa.String(), nullable=True), sa.Column("topic", sa.String(), nullable=False), sa.Column("subtopic", sa.String(), nullable=True),
        sa.Column("content_type", sa.Enum("EXPLANATION", "DEFINITION", "FORMULA", "EXAMPLE", "EXERCISE", "SOLVED_EXERCISE", "QUIZ", "LESSON", "SUMMARY", "STUDY_GUIDE", "DIAGRAM", "THREE_D_OBJECT_DESCRIPTION", name="academiccontenttype"), nullable=False),
        sa.Column("title", sa.String(), nullable=False), sa.Column("content", sa.Text(), nullable=False), sa.Column("steps", sa.JSON(), nullable=False), sa.Column("answer", sa.Text(), nullable=True), sa.Column("difficulty", sa.String(), nullable=True), sa.Column("keywords", sa.JSON(), nullable=False), sa.Column("language", sa.String(), nullable=False), sa.Column("content_hash", sa.String(64), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]), sa.ForeignKeyConstraint(["classroom_id"], ["classrooms.id"]), sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]), sa.UniqueConstraint("organization_id", "content_hash", name="uq_academic_content_org_hash"))
    op.create_index("ix_academic_content_org_search", "academic_contents", ["organization_id", "subject", "grade", "topic"])
    op.create_table("board_publication_audit", sa.Column("id", sa.String(), primary_key=True), sa.Column("organization_id", sa.String(), nullable=False), sa.Column("classroom_id", sa.String(), nullable=False), sa.Column("actor_user_id", sa.String(), nullable=False), sa.Column("component_type", sa.String(), nullable=False), sa.Column("component_payload", sa.JSON(), nullable=False), sa.Column("status", sa.String(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=True), sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]), sa.ForeignKeyConstraint(["classroom_id"], ["classrooms.id"]), sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]))


def downgrade():
    op.drop_table("board_publication_audit")
    op.drop_index("ix_academic_content_org_search", table_name="academic_contents")
    op.drop_table("academic_contents")
