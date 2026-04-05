"""
Policies router — policy CRUD and creation flow.
Business logic → PolicyService / FabricService (not here).
"""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.dependencies import get_current_agent, get_current_user
from backend.core.redis_client import get_redis
from backend.core.responses import err, ok
from backend.models.models import Agent, Payment, Policy, User
from backend.schemas.schemas import PolicyCreate, PolicyResponse, ProductItem
from backend.services.ai_service import AIService
from backend.services.fabric_service import FabricService, PinataService
from backend.services.payment_service import PaymentService

router = APIRouter(prefix="/policies", tags=["Policies"])

# Hard-coded products catalogue (replace with DB table in v2)
_PRODUCTS = [
    ProductItem(
        product_code="BIMA_HEALTH_BASIC",
        insurer_name="Star Health Insurance",
        product_name="Bima Swasthya Basic",
        description="Cashless hospitalisation up to Rs 1 lakh. Covers accident, illness, surgery.",
        min_sum_insured=50_000,
        max_sum_insured=1_00_000,
        risk_tiers=["low", "medium", "high"],
    ),
    ProductItem(
        product_code="BIMA_CROP_KHARIF",
        insurer_name="Agriculture Insurance Company",
        product_name="Bima Crop Kharif",
        description="Pradhan Mantri Fasal Bima Yojana compliant crop insurance for kharif season.",
        min_sum_insured=25_000,
        max_sum_insured=5_00_000,
        risk_tiers=["low", "medium"],
    ),
    ProductItem(
        product_code="BIMA_ACCIDENT_PLUS",
        insurer_name="New India Assurance",
        product_name="Bima Suraksha Accident",
        description="Personal accident cover. Death or permanent disability. Valid 24x7.",
        min_sum_insured=1_00_000,
        max_sum_insured=5_00_000,
        risk_tiers=["low", "medium", "high"],
    ),
]


@router.get("/products", response_model=dict)
async def get_products(
    risk_tier: str | None = None,
    agent: dict = Depends(get_current_agent),
):
    """Return available insurance products. Filter by risk_tier if provided."""
    products = _PRODUCTS
    if risk_tier:
        products = [p for p in products if risk_tier in p.risk_tiers]
    return ok([p.model_dump() for p in products])


@router.post("/create", response_model=dict)
async def create_policy(
    body: PolicyCreate,
    agent: dict = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """
    Create a new policy after successful Razorpay payment.
    Flow: verify payment → create policy record → invoke Fabric (non-blocking) → pin IPFS.
    """
    # 1. Verify agent exists and is active
    agent_result = await db.execute(
        select(Agent).where(Agent.user_id == uuid.UUID(agent["sub"]), Agent.is_active.is_(True))
    )
    agent_record = agent_result.scalar_one_or_none()
    if not agent_record:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Active agent record not found")

    # 2. Verify user exists
    user_result = await db.execute(select(User).where(User.id == body.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # 3. Verify Razorpay payment is captured
    payment_service = PaymentService()
    rp_payment = await payment_service.fetch_razorpay_payment(body.razorpay_payment_id)
    if rp_payment.get("status") != "captured":
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Payment not yet captured",
        )

    # 4. Create policy record in DB
    policy = Policy(
        user_id=body.user_id,
        agent_id=agent_record.id,
        insurer_name=body.insurer_name,
        product_code=body.product_code,
        premium_monthly=body.premium_monthly,
        sum_insured=body.sum_insured,
        start_date=body.start_date,
        end_date=body.end_date,
        status="active",
    )
    db.add(policy)
    await db.flush()  # Get policy.id

    # 5. Create payment record
    payment = Payment(
        policy_id=policy.id,
        amount=body.premium_monthly,
        payment_method="upi",
        razorpay_payment_id=body.razorpay_payment_id,
        collected_by_agent=agent_record.id,
        status="success",
    )
    db.add(payment)

    await db.commit()
    await db.refresh(policy)

    # 6. Invoke Fabric (non-blocking background task)
    fabric_service = FabricService()
    pinata_service = PinataService()

    fabric_result = await fabric_service.create_policy_on_chain({
        "id": policy.id,
        "user_id": policy.user_id,
        "agent_id": policy.agent_id,
        "insurer_name": policy.insurer_name,
        "product_code": policy.product_code,
        "premium_monthly": float(policy.premium_monthly),
        "sum_insured": float(policy.sum_insured),
        "start_date": str(policy.start_date),
        "end_date": str(policy.end_date),
    })

    # 7. Pin to IPFS
    ipfs_cid = await pinata_service.pin_json(
        data={
            "policy_id": str(policy.id),
            "product_code": policy.product_code,
            "sum_insured": str(policy.sum_insured),
            "premium_monthly": str(policy.premium_monthly),
            "start_date": str(policy.start_date),
            "end_date": str(policy.end_date),
            "fabric_tx_id": fabric_result.get("tx_id"),
        },
        name=f"policy_{policy.id}",
    )

    # 8. Update policy with Fabric TX ID and IPFS CID
    await db.execute(
        update(Policy)
        .where(Policy.id == policy.id)
        .values(
            fabric_tx_id=fabric_result.get("tx_id"),
            fabric_block_number=fabric_result.get("block_number"),
            ipfs_cid=ipfs_cid,
        )
    )

    # 9. Increment agent's total_policies counter
    await db.execute(
        update(Agent)
        .where(Agent.id == agent_record.id)
        .values(total_policies=Agent.total_policies + 1)
    )

    await db.commit()
    await db.refresh(policy)

    return ok(PolicyResponse.model_validate(policy).model_dump())


@router.get("/my-clients", response_model=dict)
async def list_agent_policies(
    page: int = 1,
    page_size: int = 20,
    agent: dict = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """List all policies sold by the current agent."""
    agent_result = await db.execute(
        select(Agent).where(Agent.user_id == uuid.UUID(agent["sub"]))
    )
    agent_record = agent_result.scalar_one_or_none()
    if not agent_record:
        return ok({"items": [], "total": 0})

    offset = (page - 1) * page_size
    result = await db.execute(
        select(Policy)
        .where(Policy.agent_id == agent_record.id)
        .offset(offset)
        .limit(page_size)
        .order_by(Policy.created_at.desc())
    )
    policies = result.scalars().all()
    return ok({
        "items": [PolicyResponse.model_validate(p).model_dump() for p in policies],
        "page": page,
        "page_size": page_size,
    })


@router.get("/user/{user_id}", response_model=dict)
async def get_user_policies(
    user_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """User portal: list own policies (authenticated user only — sub must match)."""
    if str(user_id) != current_user.get("sub"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Policy).where(Policy.user_id == user_id).order_by(Policy.created_at.desc())
    )
    policies = result.scalars().all()
    return ok([PolicyResponse.model_validate(p).model_dump() for p in policies])


@router.get("/{policy_id}", response_model=dict)
async def get_policy(
    policy_id: uuid.UUID,
    agent: dict = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Policy).where(Policy.id == policy_id))
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    return ok(PolicyResponse.model_validate(policy).model_dump())
