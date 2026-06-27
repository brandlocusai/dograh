"""add knowledge graph tables

Revision ID: 7a8e9d0c1b2f
Revises: 384be6596b36
Create Date: 2026-06-27 14:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "7a8e9d0c1b2f"
down_revision: Union[str, None] = "384be6596b36"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create knowledge_base_nodes table
    op.create_table(
        "knowledge_base_nodes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("type", sa.String(length=200), nullable=True),
        sa.Column("properties", sa.JSON(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["document_id"], ["knowledge_base_documents.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_kb_nodes_document_id",
        "knowledge_base_nodes",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        "ix_kb_nodes_organization_id",
        "knowledge_base_nodes",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_kb_nodes_name",
        "knowledge_base_nodes",
        ["name"],
        unique=False,
    )
    op.create_index(
        "ix_kb_nodes_embedding_ivfflat",
        "knowledge_base_nodes",
        ["embedding"],
        unique=False,
        postgresql_using="ivfflat",
        postgresql_with={"lists": 100},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    # Create knowledge_base_relationships table
    op.create_table(
        "knowledge_base_relationships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=500), nullable=False),
        sa.Column("target", sa.String(length=500), nullable=False),
        sa.Column("type", sa.String(length=200), nullable=False),
        sa.Column("properties", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["document_id"], ["knowledge_base_documents.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_kb_relationships_document_id",
        "knowledge_base_relationships",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        "ix_kb_relationships_organization_id",
        "knowledge_base_relationships",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_kb_relationships_source",
        "knowledge_base_relationships",
        ["source"],
        unique=False,
    )
    op.create_index(
        "ix_kb_relationships_target",
        "knowledge_base_relationships",
        ["target"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_kb_relationships_target", table_name="knowledge_base_relationships")
    op.drop_index("ix_kb_relationships_source", table_name="knowledge_base_relationships")
    op.drop_index("ix_kb_relationships_organization_id", table_name="knowledge_base_relationships")
    op.drop_index("ix_kb_relationships_document_id", table_name="knowledge_base_relationships")
    op.drop_table("knowledge_base_relationships")

    op.drop_index(
        "ix_kb_nodes_embedding_ivfflat",
        table_name="knowledge_base_nodes",
        postgresql_using="ivfflat",
        postgresql_with={"lists": 100},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.drop_index("ix_kb_nodes_name", table_name="knowledge_base_nodes")
    op.drop_index("ix_kb_nodes_organization_id", table_name="knowledge_base_nodes")
    op.drop_index("ix_kb_nodes_document_id", table_name="knowledge_base_nodes")
    op.drop_table("knowledge_base_nodes")
