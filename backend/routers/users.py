"""
Users router — user creation and KYC.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.dependencies import get_current_agent
from backend.core.responses import err, ok
from backend.models.models import User
from backend.schemas.schemas import UserCreate, UserResponse

router = APIRouter(prefix="/users", tags=["Users"])


@router.post("/create", response_model=dict)
async def create_user(
    body: UserCreate,
    agent: dict = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Create a new user record. Called during policy creation wizard step 1."""
    existing = await db.execute(select(User).where(User.phone == body.phone))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this phone number already exists",
        )

    user = User(
        phone=body.phone,
        name=body.name,
        location_district=body.location_district,
        location_state=body.location_state,
        kyc_status="pending",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return ok(UserResponse.model_validate(user).model_dump())


@router.get("/{user_id}", response_model=dict)
async def get_user(
    user_id: uuid.UUID,
    agent: dict = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return ok(UserResponse.model_validate(user).model_dump())
