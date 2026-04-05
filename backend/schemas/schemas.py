"""
Pydantic v2 request/response schemas.
Each table has: Create (input), Response (output), and an Update (partial) schema where needed.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ── Shared ────────────────────────────────────────────────────

class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


# ── Auth ──────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str = Field(..., description="Phone number or email registered in Cognito")
    password: str = Field(..., min_length=8)


class TokenResponse(BaseModel):
    access_token: str
    id_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "Bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


# ── Users ─────────────────────────────────────────────────────

class UserCreate(BaseModel):
    phone: str = Field(..., pattern=r"^\+91[0-9]{10}$", description="+91XXXXXXXXXX format")
    name: Optional[str] = None
    location_district: Optional[str] = None
    location_state: Optional[str] = None
    age: Optional[int] = Field(default=None, ge=1, le=120)
    occupation: Optional[str] = None
    pre_existing_conditions: list[str] = Field(default_factory=list)


class UserResponse(BaseModel):
    id: uuid.UUID
    phone: str
    name: Optional[str]
    location_district: Optional[str]
    location_state: Optional[str]
    kyc_status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Agents ────────────────────────────────────────────────────

class AgentResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    agent_code: str
    commission_rate: Decimal
    total_policies: int
    is_active: bool
    onboarded_at: datetime

    model_config = {"from_attributes": True}


# ── Policies ──────────────────────────────────────────────────

class PolicyCreate(BaseModel):
    user_id: uuid.UUID
    insurer_name: str
    product_code: str
    premium_monthly: Decimal = Field(..., gt=0)
    sum_insured: Decimal = Field(..., gt=0)
    start_date: date
    end_date: date
    razorpay_payment_id: str = Field(..., description="Must match a verified payment")

    @field_validator("end_date")
    @classmethod
    def end_after_start(cls, v: date, info) -> date:
        if "start_date" in info.data and v <= info.data["start_date"]:
            raise ValueError("end_date must be after start_date")
        return v


class PolicyResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    agent_id: uuid.UUID
    insurer_name: str
    product_code: str
    premium_monthly: Decimal
    sum_insured: Decimal
    start_date: date
    end_date: date
    status: str
    fabric_tx_id: Optional[str]
    fabric_block_number: Optional[int]
    ipfs_cid: Optional[str]
    blockchain_tx_hash: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class ProductItem(BaseModel):
    product_code: str
    insurer_name: str
    product_name: str
    description: str
    min_sum_insured: Decimal
    max_sum_insured: Decimal
    risk_tiers: list[str] = Field(description="Which risk tiers are eligible")


# ── Claims ────────────────────────────────────────────────────

class ClaimCreate(BaseModel):
    policy_id: uuid.UUID
    claim_type: str = Field(..., description="hospital_bill | discharge_summary | prescription | death_certificate")
    claim_amount: Decimal = Field(..., gt=0)
    document_s3_keys: list[str] = Field(..., min_length=1, description="S3 object keys of uploaded documents")


class ClaimResponse(BaseModel):
    id: uuid.UUID
    policy_id: uuid.UUID
    user_id: uuid.UUID
    claim_type: str
    claim_amount: Decimal
    documents: Any
    ai_fraud_score: Optional[Decimal]
    ai_verification_status: str
    status: str
    payout_tx_hash: Optional[str]
    fabric_payout_tx_id: Optional[str]
    submitted_at: datetime
    resolved_at: Optional[datetime]

    model_config = {"from_attributes": True}


# ── Payments ──────────────────────────────────────────────────

class CreateOrderRequest(BaseModel):
    policy_id: uuid.UUID
    amount: Decimal = Field(..., gt=0, description="Amount in INR")
    payment_method: str = Field(default="upi", pattern="^(upi|cash)$")


class CreateOrderResponse(BaseModel):
    order_id: str
    amount: int  # paise
    currency: str = "INR"
    key_id: str


class PaymentWebhookPayload(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


# ── AI ────────────────────────────────────────────────────────

class RiskScoreRequest(BaseModel):
    user_id: Optional[uuid.UUID] = None
    age: int = Field(..., ge=1, le=100)
    occupation: str
    district: str
    state: str
    pre_existing_conditions: list[str] = Field(default_factory=list)


class RiskScoreResponse(BaseModel):
    risk_tier: str  # low | medium | high
    score: float
    premium_min: Decimal
    premium_max: Decimal
    reasoning: str
    factors: list[str] = Field(default_factory=list)


class ChatRequest(BaseModel):
    user_id: str
    message: str = Field(..., min_length=1, max_length=2000)
    language: str = Field(default="hi", description="hi | en | hinglish")
    is_voice: bool = False


class ChatResponse(BaseModel):
    message: str
    suggested_action: Optional[str]
    hand_off_to_agent: bool
    agent_message: Optional[str] = None
    audio_url: Optional[str] = None


# ── Uploads ───────────────────────────────────────────────────

class PresignedUrlResponse(BaseModel):
    url: str
    key: str
    expires_in: int = 300
