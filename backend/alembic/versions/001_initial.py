"""Initial schema — all six tables.

Revision ID: 001
Revises:
Create Date: 2026-04-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Create PostgreSQL ENUM types ─────────────────────────
    op.execute("CREATE TYPE kyc_status AS ENUM ('pending', 'verified', 'rejected')")
    op.execute("CREATE TYPE policy_status AS ENUM ('active', 'lapsed', 'claimed', 'cancelled')")
    op.execute("CREATE TYPE ai_verification_status AS ENUM ('pending', 'passed', 'failed')")
    op.execute("CREATE TYPE claim_status AS ENUM ('submitted', 'under_review', 'approved', 'rejected', 'paid')")
    op.execute("CREATE TYPE payment_method AS ENUM ('upi', 'cash')")
    op.execute("CREATE TYPE payment_status AS ENUM ('pending', 'success', 'failed')")
    op.execute("CREATE TYPE ai_entity_type AS ENUM ('policy', 'claim')")

    # ── users ─────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("phone", sa.String(15), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("aadhaar_hash", sa.String(), nullable=True),
        sa.Column("location_district", sa.String(), nullable=True),
        sa.Column("location_state", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "kyc_status",
            postgresql.ENUM("pending", "verified", "rejected", name="kyc_status", create_type=False),
            server_default="pending",
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("phone"),
    )
    op.create_index("ix_users_phone", "users", ["phone"])

    # ── agents ────────────────────────────────────────────────
    op.create_table(
        "agents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_code", sa.String(), nullable=False),
        sa.Column("commission_rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("total_policies", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "onboarded_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_code"),
    )
    op.create_index("ix_agents_agent_code", "agents", ["agent_code"])

    # ── policies ──────────────────────────────────────────────
    op.create_table(
        "policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("insurer_name", sa.String(), nullable=False),
        sa.Column("product_code", sa.String(), nullable=False),
        sa.Column("premium_monthly", sa.Numeric(10, 2), nullable=False),
        sa.Column("sum_insured", sa.Numeric(12, 2), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM("active", "lapsed", "claimed", "cancelled", name="policy_status", create_type=False),
            server_default="active",
            nullable=False,
        ),
        sa.Column("fabric_tx_id", sa.String(), nullable=True),
        sa.Column("fabric_block_number", sa.BigInteger(), nullable=True),
        sa.Column("ipfs_cid", sa.String(), nullable=True),
        sa.Column("blockchain_tx_hash", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_policies_user_id", "policies", ["user_id"])
    op.create_index("ix_policies_agent_id", "policies", ["agent_id"])

    # ── claims ────────────────────────────────────────────────
    op.create_table(
        "claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_type", sa.String(), nullable=False),
        sa.Column("claim_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("documents", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("ai_fraud_score", sa.Numeric(5, 4), nullable=True),
        sa.Column(
            "ai_verification_status",
            postgresql.ENUM("pending", "passed", "failed", name="ai_verification_status", create_type=False),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "submitted", "under_review", "approved", "rejected", "paid",
                name="claim_status",
                create_type=False,
            ),
            server_default="submitted",
            nullable=False,
        ),
        sa.Column("payout_tx_hash", sa.String(), nullable=True),
        sa.Column("fabric_payout_tx_id", sa.String(), nullable=True),
        sa.Column(
            "submitted_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["policy_id"], ["policies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_claims_policy_id", "claims", ["policy_id"])
    op.create_index("ix_claims_user_id", "claims", ["user_id"])

    # ── payments ──────────────────────────────────────────────
    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column(
            "payment_method",
            postgresql.ENUM("upi", "cash", name="payment_method", create_type=False),
            nullable=False,
        ),
        sa.Column("razorpay_order_id", sa.String(), nullable=True),
        sa.Column("razorpay_payment_id", sa.String(), nullable=True),
        sa.Column("collected_by_agent", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM("pending", "success", "failed", name="payment_status", create_type=False),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("paid_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["collected_by_agent"], ["agents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["policy_id"], ["policies.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payments_policy_id", "payments", ["policy_id"])
    op.create_index("ix_payments_razorpay_order_id", "payments", ["razorpay_order_id"])

    # ── ai_logs ───────────────────────────────────────────────
    op.create_table(
        "ai_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "entity_type",
            postgresql.ENUM("policy", "claim", name="ai_entity_type", create_type=False),
            nullable=False,
        ),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_used", sa.String(), nullable=False),
        sa.Column("input_summary", sa.Text(), nullable=True),
        sa.Column("output_summary", sa.Text(), nullable=True),
        sa.Column("score", sa.Numeric(5, 4), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_logs_entity_id", "ai_logs", ["entity_id"])


def downgrade() -> None:
    op.drop_table("ai_logs")
    op.drop_table("payments")
    op.drop_table("claims")
    op.drop_table("policies")
    op.drop_table("agents")
    op.drop_table("users")

    op.execute("DROP TYPE ai_entity_type")
    op.execute("DROP TYPE payment_status")
    op.execute("DROP TYPE payment_method")
    op.execute("DROP TYPE claim_status")
    op.execute("DROP TYPE ai_verification_status")
    op.execute("DROP TYPE policy_status")
    op.execute("DROP TYPE kyc_status")
