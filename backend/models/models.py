"""
SQLAlchemy 2.0 ORM models — canonical schema reference.
NEVER add columns here without a corresponding Alembic migration.
Column names must match /CLAUDE.md schema exactly.
"""
import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    TIMESTAMP,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from backend.core.database import Base

# ── ENUM definitions ─────────────────────────────────────────

kyc_status_enum = Enum(
    "pending", "verified", "rejected",
    name="kyc_status",
    create_constraint=True,
)

policy_status_enum = Enum(
    "active", "lapsed", "claimed", "cancelled",
    name="policy_status",
    create_constraint=True,
)

ai_verification_status_enum = Enum(
    "pending", "passed", "failed",
    name="ai_verification_status",
    create_constraint=True,
)

claim_status_enum = Enum(
    "submitted", "under_review", "approved", "rejected", "paid",
    name="claim_status",
    create_constraint=True,
)

payment_method_enum = Enum(
    "upi", "cash",
    name="payment_method",
    create_constraint=True,
)

payment_status_enum = Enum(
    "pending", "success", "failed",
    name="payment_status",
    create_constraint=True,
)

ai_entity_type_enum = Enum(
    "policy", "claim",
    name="ai_entity_type",
    create_constraint=True,
)


# ── Models ────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    phone = Column(String(15), unique=True, nullable=False, index=True)
    name = Column(String)
    aadhaar_hash = Column(String)
    location_district = Column(String)
    location_state = Column(String)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    kyc_status = Column(kyc_status_enum, nullable=False, server_default="pending")


class Agent(Base):
    __tablename__ = "agents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    agent_code = Column(String, unique=True, nullable=False, index=True)
    commission_rate = Column(Numeric(5, 2), nullable=False)
    total_policies = Column(Integer, nullable=False, server_default="0")
    is_active = Column(Boolean, nullable=False, server_default="true")
    onboarded_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class Policy(Base):
    __tablename__ = "policies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="RESTRICT"), nullable=False, index=True)
    insurer_name = Column(String, nullable=False)
    product_code = Column(String, nullable=False)
    premium_monthly = Column(Numeric(10, 2), nullable=False)
    sum_insured = Column(Numeric(12, 2), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    status = Column(policy_status_enum, nullable=False, server_default="active")
    fabric_tx_id = Column(String)
    fabric_block_number = Column(BigInteger)
    ipfs_cid = Column(String)
    blockchain_tx_hash = Column(String)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class Claim(Base):
    __tablename__ = "claims"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    policy_id = Column(UUID(as_uuid=True), ForeignKey("policies.id", ondelete="RESTRICT"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    claim_type = Column(String, nullable=False)
    claim_amount = Column(Numeric(12, 2), nullable=False)
    documents = Column(JSONB, nullable=False, server_default="{}")
    ai_fraud_score = Column(Numeric(5, 4))
    ai_verification_status = Column(ai_verification_status_enum, nullable=False, server_default="pending")
    status = Column(claim_status_enum, nullable=False, server_default="submitted")
    payout_tx_hash = Column(String)
    fabric_payout_tx_id = Column(String)
    submitted_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    resolved_at = Column(TIMESTAMP(timezone=True))


class Payment(Base):
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    policy_id = Column(UUID(as_uuid=True), ForeignKey("policies.id", ondelete="RESTRICT"), nullable=False, index=True)
    amount = Column(Numeric(10, 2), nullable=False)
    payment_method = Column(payment_method_enum, nullable=False)
    razorpay_order_id = Column(String, index=True)
    razorpay_payment_id = Column(String, index=True)
    collected_by_agent = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"))
    status = Column(payment_status_enum, nullable=False, server_default="pending")
    paid_at = Column(TIMESTAMP(timezone=True))


class AILog(Base):
    __tablename__ = "ai_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    entity_type = Column(ai_entity_type_enum, nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    model_used = Column(String, nullable=False)
    input_summary = Column(Text)
    output_summary = Column(Text)
    score = Column(Numeric(5, 4))
    tokens_used = Column(Integer)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
