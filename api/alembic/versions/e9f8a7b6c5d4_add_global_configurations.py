"""add global configurations

Revision ID: e9f8a7b6c5d4
Revises: bad4aefcfcf4
Create Date: 2026-07-01 14:15:00.000000

"""

from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e9f8a7b6c5d4"
down_revision: Union[str, None] = "bad4aefcfcf4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create global_configurations table
    global_configurations = op.create_table(
        "global_configurations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_global_configurations_id"),
        "global_configurations",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_global_configurations_key"),
        "global_configurations",
        ["key"],
        unique=True,
    )

    # Seed global_configurations
    default_models = {
        "llm_provider": "openrouter",
        "llm_model": "openai/gpt-4o",
        "stt_provider": "deepgram",
        "stt_model": "nova-2",
        "tts_provider": "elevenlabs",
        "tts_model": "default",
    }

    pricing_config = {
        "markup_multiplier": 1.5,
        "llm": {
            "openai": {
                "gpt-4o": {
                    "prompt_token_price": 0.0000025,
                    "completion_token_price": 0.000010,
                },
                "gpt-4o-mini": {
                    "prompt_token_price": 0.00000015,
                    "completion_token_price": 0.00000060,
                },
            }
        },
        "tts": {
            "elevenlabs": {
                "default": {
                    "character_price": 0.0000256,
                }
            }
        },
        "stt": {
            "deepgram": {
                "nova-2": {
                    "second_price": 0.000096,
                }
            }
        },
    }

    # Use SQL insert to seed the tables
    op.bulk_insert(
        global_configurations,
        [
            {
                "key": "default_models",
                "value": default_models,
            },
            {
                "key": "pricing_config",
                "value": pricing_config,
            },
        ],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_global_configurations_key"),
        table_name="global_configurations",
    )
    op.drop_index(
        op.f("ix_global_configurations_id"),
        table_name="global_configurations",
    )
    op.drop_table("global_configurations")
