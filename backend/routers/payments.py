"""
Payments router — Razorpay order creation and webhook.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.database import get_db
from backend.core.dependencies import get_current_agent
from backend.core.responses import err, ok
from backend.models.models import Payment
from backend.schemas.schemas import CreateOrderRequest, CreateOrderResponse, PaymentWebhookPayload
from backend.services.payment_service import PaymentService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post("/create-order", response_model=dict)
async def create_order(
    body: CreateOrderRequest,
    agent: dict = Depends(get_current_agent),
):
    """Create a Razorpay order for premium payment. Returns order_id for frontend checkout."""
    svc = PaymentService()
    order = await svc.create_razorpay_order(
        policy_id=str(body.policy_id),
        amount_inr=body.amount,
    )
    return ok(order)


@router.post("/verify", response_model=dict)
async def verify_payment(
    body: PaymentWebhookPayload,
    agent: dict = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """
    Verify Razorpay payment signature after frontend checkout success.
    Called by frontend BEFORE creating policy — confirms payment is genuine.
    """
    svc = PaymentService()
    valid = svc.verify_razorpay_signature(
        order_id=body.razorpay_order_id,
        payment_id=body.razorpay_payment_id,
        signature=body.razorpay_signature,
    )
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment signature verification failed",
        )

    # Update payment record if it exists
    await db.execute(
        update(Payment)
        .where(Payment.razorpay_order_id == body.razorpay_order_id)
        .values(
            razorpay_payment_id=body.razorpay_payment_id,
            status="success",
        )
    )
    await db.commit()
    return ok({"verified": True, "payment_id": body.razorpay_payment_id})


@router.post("/webhook/razorpay")
async def razorpay_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Razorpay webhook handler — handles async payment events.
    Signature verified using Razorpay webhook secret.
    """
    import hashlib
    import hmac

    payload_bytes = await request.body()
    received_sig = request.headers.get("x-razorpay-signature", "")

    webhook_secret = settings.RAZORPAY_KEY_SECRET  # Use dedicated webhook secret in prod
    expected_sig = hmac.new(
        webhook_secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_sig, received_sig):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature")

    import json
    event = json.loads(payload_bytes)
    if event.get("event") == "payment.captured":
        payment_entity = event["payload"]["payment"]["entity"]
        order_id = payment_entity.get("order_id")
        payment_id = payment_entity.get("id")

        await db.execute(
            update(Payment)
            .where(Payment.razorpay_order_id == order_id)
            .values(razorpay_payment_id=payment_id, status="success")
        )
        await db.commit()
        logger.info("Webhook: payment captured — order %s, payment %s", order_id, payment_id)

    return {"status": "ok"}
