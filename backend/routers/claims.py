"""
Claims router — claim submission and management.
Business logic lives in ClaimService.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.dependencies import get_current_agent, get_current_user
from backend.core.redis_client import get_redis
from backend.core.responses import err, ok
from backend.models.models import Claim
from backend.schemas.schemas import ClaimCreate, ClaimResponse
from backend.services.ai_service import AIService
from backend.services.claim_service import ClaimService
from backend.services.fabric_service import FabricService
from backend.services.payment_service import PaymentService

router = APIRouter(prefix="/claims", tags=["Claims"])


def _claim_service(
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
) -> ClaimService:
    ai = AIService(db=db, redis=redis)
    fabric = FabricService()
    payments = PaymentService()
    return ClaimService(db=db, ai_service=ai, fabric_service=fabric, payment_service=payments)


@router.post("/submit", response_model=dict)
async def submit_claim(
    body: ClaimCreate,
    agent: dict = Depends(get_current_agent),
    svc: ClaimService = Depends(_claim_service),
    db: AsyncSession = Depends(get_db),
):
    """Submit a claim. AI document verification runs synchronously."""
    try:
        claim = await svc.submit_claim(
            policy_id=body.policy_id,
            user_id=body.policy_id,  # resolved from policy inside service
            claim_type=body.claim_type,
            claim_amount=float(body.claim_amount),
            document_s3_keys=body.document_s3_keys,
        )
        return ok(ClaimResponse.model_validate(claim).model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{claim_id}/approve", response_model=dict)
async def approve_claim(
    claim_id: uuid.UUID,
    beneficiary_account: str | None = None,
    beneficiary_ifsc: str | None = None,
    agent: dict = Depends(get_current_agent),
    svc: ClaimService = Depends(_claim_service),
):
    """Approve a claim and optionally trigger payout (admin agent only)."""
    try:
        claim = await svc.approve_claim(
            claim_id=claim_id,
            beneficiary_account=beneficiary_account,
            beneficiary_ifsc=beneficiary_ifsc,
        )
        return ok(ClaimResponse.model_validate(claim).model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/policy/{policy_id}", response_model=dict)
async def get_claims_for_policy(
    policy_id: uuid.UUID,
    agent: dict = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Claim)
        .where(Claim.policy_id == policy_id)
        .order_by(Claim.submitted_at.desc())
    )
    claims = result.scalars().all()
    return ok([ClaimResponse.model_validate(c).model_dump() for c in claims])


@router.get("/{claim_id}", response_model=dict)
async def get_claim(
    claim_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """User portal: get own claim status."""
    result = await db.execute(select(Claim).where(Claim.id == claim_id))
    claim = result.scalar_one_or_none()
    if not claim:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")
    return ok(ClaimResponse.model_validate(claim).model_dump())
