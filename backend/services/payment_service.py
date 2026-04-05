"""
PaymentService — Razorpay (collect) + Cashfree (payout).
All payment operations go through this service.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
from decimal import Decimal

import razorpay
from fastapi import HTTPException, status

from backend.core.config import settings

logger = logging.getLogger(__name__)


def _razorpay_client() -> razorpay.Client:
    return razorpay.Client(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    )


class PaymentService:

    # ── Razorpay order creation ──────────────────────────────

    async def create_razorpay_order(
        self,
        policy_id: str,
        amount_inr: Decimal,
    ) -> dict:
        """
        Create a Razorpay order for premium collection.
        Returns: { order_id, amount_paise, currency, key_id }
        """
        amount_paise = int(amount_inr * 100)  # Razorpay expects paise

        def _create():
            client = _razorpay_client()
            return client.order.create({
                "amount": amount_paise,
                "currency": "INR",
                "receipt": f"policy_{policy_id[:8]}",
                "notes": {"policy_id": str(policy_id)},
                "payment_capture": True,
            })

        try:
            order = await asyncio.to_thread(_create)
        except Exception as exc:
            logger.error("Razorpay order creation failed: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Payment gateway error. Please try again.",
            ) from exc

        return {
            "order_id": order["id"],
            "amount": amount_paise,
            "currency": "INR",
            "key_id": settings.RAZORPAY_KEY_ID,
        }

    # ── Razorpay signature verification ─────────────────────

    def verify_razorpay_signature(
        self,
        order_id: str,
        payment_id: str,
        signature: str,
    ) -> bool:
        """
        Verify Razorpay payment signature.
        Must be called before marking payment as successful.
        """
        message = f"{order_id}|{payment_id}"
        expected = hmac.new(
            settings.RAZORPAY_KEY_SECRET.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def fetch_razorpay_payment(self, payment_id: str) -> dict:
        """Fetch payment details from Razorpay to confirm status."""
        def _fetch():
            client = _razorpay_client()
            return client.payment.fetch(payment_id)

        try:
            return await asyncio.to_thread(_fetch)
        except Exception as exc:
            logger.error("Razorpay payment fetch failed: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not verify payment status.",
            ) from exc

    # ── Cashfree payout ──────────────────────────────────────

    async def trigger_cashfree_payout(
        self,
        claim_id: str,
        beneficiary_account: str,
        beneficiary_ifsc: str,
        amount_inr: Decimal,
        remarks: str = "",
    ) -> dict:
        """
        Trigger claim payout via Cashfree Payouts API.
        Returns: { reference_id, status }
        """
        import httpx

        transfer_id = f"claim_{claim_id[:12]}"
        payload = {
            "beneDetails": {
                "bankAccount": beneficiary_account,
                "ifsc": beneficiary_ifsc,
                "name": "Bima360 Claim Payout",
            },
            "amount": str(amount_inr),
            "transferId": transfer_id,
            "transferMode": "NEFT",
            "remarks": remarks or f"Claim payout for {claim_id}",
        }

        # Cashfree uses app ID + secret key for auth
        headers = {
            "X-Client-Id": settings.CASHFREE_APP_ID,
            "X-Client-Secret": settings.CASHFREE_SECRET_KEY,
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    "https://payout-api.cashfree.com/payout/v1/requestTransfer",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                return {
                    "reference_id": data.get("data", {}).get("referenceId", transfer_id),
                    "status": data.get("status", "pending"),
                }
        except Exception as exc:
            logger.error("Cashfree payout failed for claim %s: %s", claim_id, exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Payout gateway error. Finance team has been notified.",
            ) from exc
