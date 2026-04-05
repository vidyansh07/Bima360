"""
ClaimService — claim processing orchestration.
Coordinates: AI verification → DB update → Fabric approval → payout trigger.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.models import Claim, Payment, Policy
from backend.services.ai_service import AIService
from backend.services.fabric_service import FabricService
from backend.services.payment_service import PaymentService

logger = logging.getLogger(__name__)


class ClaimService:

    def __init__(
        self,
        db: AsyncSession,
        ai_service: AIService,
        fabric_service: FabricService,
        payment_service: PaymentService,
    ) -> None:
        self.db = db
        self.ai = ai_service
        self.fabric = fabric_service
        self.payments = payment_service

    async def submit_claim(
        self,
        policy_id: uuid.UUID,
        user_id: uuid.UUID,
        claim_type: str,
        claim_amount: float,
        document_s3_keys: list[str],
    ) -> Claim:
        """
        Create claim record, run AI document verification, submit to Fabric.
        AI verification failure does NOT block claim submission — flags for human review.
        """
        # Verify policy exists and is active
        policy_result = await self.db.execute(
            select(Policy).where(
                Policy.id == policy_id,
                Policy.user_id == user_id,
                Policy.status == "active",
            )
        )
        policy = policy_result.scalar_one_or_none()
        if not policy:
            raise ValueError("Active policy not found for this user")

        # Build initial documents structure
        documents: dict = {
            "s3_keys": document_s3_keys,
            "verification_results": [],
            "verification_flags": [],
        }

        # Run AI document verification for each uploaded document
        for s3_key in document_s3_keys:
            try:
                result = await self.ai.verify_claim_document(s3_key, claim_type)
                documents["verification_results"].append({
                    "s3_key": s3_key,
                    **result,
                })
                if result.get("flags"):
                    documents["verification_flags"].extend(result["flags"])
            except Exception as exc:
                logger.error("AI verification failed for %s: %s", s3_key, exc)
                documents["verification_results"].append({
                    "s3_key": s3_key,
                    "error": str(exc),
                    "needs_human_review": True,
                })

        # Compute aggregate fraud score
        results = documents["verification_results"]
        valid_scores = [
            r["confidence"]
            for r in results
            if isinstance(r.get("confidence"), (int, float))
        ]
        avg_confidence = sum(valid_scores) / len(valid_scores) if valid_scores else 0.5
        fraud_score = round(1.0 - avg_confidence, 4)  # Higher fraud score = lower confidence

        all_authentic = all(
            r.get("is_authentic", False) for r in results if "is_authentic" in r
        )
        ai_status = "passed" if all_authentic and fraud_score < 0.3 else (
            "failed" if fraud_score > 0.7 else "pending"
        )

        # Create claim in DB
        claim = Claim(
            policy_id=policy_id,
            user_id=user_id,
            claim_type=claim_type,
            claim_amount=claim_amount,
            documents=documents,
            ai_fraud_score=fraud_score,
            ai_verification_status=ai_status,
            status="submitted",
        )
        self.db.add(claim)
        await self.db.flush()  # Get claim.id

        # Submit to Fabric (non-blocking — failure doesn't prevent claim creation)
        fabric_result = await self.fabric.submit_claim_on_chain({
            "id": claim.id,
            "policy_id": policy_id,
            "user_id": user_id,
            "claim_type": claim_type,
            "claim_amount": claim_amount,
        })

        if fabric_result.get("tx_id"):
            claim.fabric_payout_tx_id = fabric_result["tx_id"]

        await self.db.commit()
        await self.db.refresh(claim)
        return claim

    async def approve_claim(
        self,
        claim_id: uuid.UUID,
        beneficiary_account: Optional[str] = None,
        beneficiary_ifsc: Optional[str] = None,
    ) -> Claim:
        """
        Approve claim and trigger payout via Cashfree.
        Updates Fabric, then triggers bank transfer, then updates DB.
        """
        claim_result = await self.db.execute(
            select(Claim).where(
                Claim.id == claim_id,
                Claim.status.in_(["submitted", "under_review"]),
            )
        )
        claim = claim_result.scalar_one_or_none()
        if not claim:
            raise ValueError("Claim not found or not in approvable state")

        # 1. Approve on Fabric
        fabric_result = await self.fabric.approve_claim_on_chain(
            str(claim_id),
            float(claim.ai_fraud_score or 0.0),
        )

        # 2. Trigger payout if bank details provided
        payout_tx_hash = None
        if beneficiary_account and beneficiary_ifsc:
            payout = await self.payments.trigger_cashfree_payout(
                claim_id=str(claim_id),
                beneficiary_account=beneficiary_account,
                beneficiary_ifsc=beneficiary_ifsc,
                amount_inr=claim.claim_amount,
            )
            payout_tx_hash = payout.get("reference_id")

            # Record on Fabric
            if payout_tx_hash:
                await self.fabric.trigger_payout_on_chain(str(claim_id), payout_tx_hash)

        # 3. Update DB
        new_status = "paid" if payout_tx_hash else "approved"
        await self.db.execute(
            update(Claim)
            .where(Claim.id == claim_id)
            .values(
                status=new_status,
                payout_tx_hash=payout_tx_hash,
                fabric_payout_tx_id=fabric_result.get("tx_id") or claim.fabric_payout_tx_id,
            )
        )
        await self.db.commit()
        await self.db.refresh(claim)
        return claim
