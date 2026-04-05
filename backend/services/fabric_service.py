"""
FabricService — all Hyperledger Fabric interactions go through this class.
Never call fabric-sdk-py or peer CLI directly from routers or other services.

Key rules:
- All calls wrapped in try/except — Fabric errors NEVER crash the main API
- If Fabric unreachable → returns pending state, logs failure
- fabric_tx_id = None means the TX is queued/retry pending
- Admin key NEVER logged
"""
from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from typing import Optional

from backend.core.config import settings

logger = logging.getLogger(__name__)

_FABRIC_TIMEOUT = 30  # seconds per TX


class FabricError(Exception):
    """Raised when Fabric TX fails and caller must handle gracefully."""


class FabricService:
    """
    Wraps Hyperledger Fabric 2.5 chaincode invocations.
    Uses subprocess to call the Fabric peer CLI; swap to hfc/gateway SDK when stable.
    """

    def __init__(self) -> None:
        self.channel = settings.FABRIC_CHANNEL_NAME
        self.policy_cc = settings.FABRIC_POLICY_CHAINCODE
        self.claim_cc = settings.FABRIC_CLAIM_CHAINCODE
        self.wallet_path = settings.FABRIC_WALLET_PATH
        self.connection_profile = settings.FABRIC_CONNECTION_PROFILE_PATH

    # ── Policy operations ────────────────────────────────────

    async def create_policy_on_chain(self, policy_data: dict) -> dict:
        """
        Invoke PolicyContract.CreatePolicy.
        Returns: { tx_id, block_number }
        On failure: returns { tx_id: None, block_number: None, error: str }
        """
        args = json.dumps([
            str(policy_data["id"]),
            str(policy_data["user_id"]),
            str(policy_data["agent_id"]),
            policy_data["insurer_name"],
            policy_data["product_code"],
            str(policy_data["premium_monthly"]),
            str(policy_data["sum_insured"]),
            str(policy_data["start_date"]),
            str(policy_data["end_date"]),
        ])

        result = await self._invoke(
            chaincode=self.policy_cc,
            function="CreatePolicy",
            args=args,
        )
        return result

    async def get_policy_from_chain(self, policy_id: str) -> Optional[dict]:
        """Query PolicyContract.GetPolicy. Returns None if not found or Fabric down."""
        try:
            result = await self._query(
                chaincode=self.policy_cc,
                function="GetPolicy",
                args=json.dumps([policy_id]),
            )
            return json.loads(result) if result else None
        except FabricError as exc:
            logger.error("Fabric GetPolicy failed for %s: %s", policy_id, exc)
            return None

    async def update_policy_status_on_chain(self, policy_id: str, new_status: str) -> dict:
        """Invoke PolicyContract.UpdatePolicyStatus."""
        return await self._invoke(
            chaincode=self.policy_cc,
            function="UpdatePolicyStatus",
            args=json.dumps([policy_id, new_status]),
        )

    # ── Claim operations ─────────────────────────────────────

    async def submit_claim_on_chain(self, claim_data: dict) -> dict:
        """Invoke ClaimContract.SubmitClaim."""
        args = json.dumps([
            str(claim_data["id"]),
            str(claim_data["policy_id"]),
            str(claim_data["user_id"]),
            claim_data["claim_type"],
            str(claim_data["claim_amount"]),
        ])
        return await self._invoke(
            chaincode=self.claim_cc,
            function="SubmitClaim",
            args=args,
        )

    async def approve_claim_on_chain(self, claim_id: str, ai_score: float) -> dict:
        """Invoke ClaimContract.ApproveClaim (admin MSP only)."""
        return await self._invoke(
            chaincode=self.claim_cc,
            function="ApproveClaim",
            args=json.dumps([claim_id, str(round(ai_score, 4))]),
        )

    async def trigger_payout_on_chain(self, claim_id: str, tx_hash: str) -> dict:
        """Invoke ClaimContract.TriggerPayout — marks claim as paid on Fabric."""
        return await self._invoke(
            chaincode=self.claim_cc,
            function="TriggerPayout",
            args=json.dumps([claim_id, tx_hash]),
        )

    # ── Internal helpers ─────────────────────────────────────

    async def _invoke(self, chaincode: str, function: str, args: str) -> dict:
        """
        Call peer chaincode invoke via subprocess.
        Returns { tx_id, block_number } on success.
        Returns { tx_id: None, block_number: None, error: str } on failure — never raises.
        """
        cmd = self._build_invoke_cmd(chaincode, function, args)
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(self._run_peer_cmd, cmd),
                timeout=_FABRIC_TIMEOUT,
            )
            return self._parse_invoke_result(result)
        except asyncio.TimeoutError:
            logger.error("Fabric invoke timeout after %ds: %s.%s", _FABRIC_TIMEOUT, chaincode, function)
            return {"tx_id": None, "block_number": None, "error": "Fabric timeout"}
        except Exception as exc:
            logger.error("Fabric invoke error %s.%s: %s", chaincode, function, exc)
            return {"tx_id": None, "block_number": None, "error": str(exc)}

    async def _query(self, chaincode: str, function: str, args: str) -> Optional[str]:
        """Call peer chaincode query. Returns raw string or None."""
        cmd = self._build_query_cmd(chaincode, function, args)
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(self._run_peer_cmd, cmd),
                timeout=_FABRIC_TIMEOUT,
            )
            return result.stdout.decode("utf-8").strip()
        except Exception as exc:
            raise FabricError(f"Query failed: {exc}") from exc

    def _build_invoke_cmd(self, chaincode: str, function: str, args: str) -> list[str]:
        return [
            "peer", "chaincode", "invoke",
            "-C", self.channel,
            "-n", chaincode,
            "-c", json.dumps({"function": function, "Args": json.loads(args)}),
            "--tls",
            "--cafile", f"{self.wallet_path}/tlsca.pem",
        ]

    def _build_query_cmd(self, chaincode: str, function: str, args: str) -> list[str]:
        return [
            "peer", "chaincode", "query",
            "-C", self.channel,
            "-n", chaincode,
            "-c", json.dumps({"function": function, "Args": json.loads(args)}),
        ]

    @staticmethod
    def _run_peer_cmd(cmd: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            cmd,
            capture_output=True,
            timeout=_FABRIC_TIMEOUT,
            check=True,
        )

    @staticmethod
    def _parse_invoke_result(result: subprocess.CompletedProcess) -> dict:
        """Parse peer CLI output to extract txID and block number."""
        output = result.stderr.decode("utf-8") + result.stdout.decode("utf-8")
        tx_id = None
        block_number = None

        for line in output.splitlines():
            if "txid" in line.lower():
                parts = line.split()
                for i, part in enumerate(parts):
                    if "txid" in part.lower() and i + 1 < len(parts):
                        tx_id = parts[i + 1].strip("[],")
                        break
            if "block" in line.lower() and "number" in line.lower():
                parts = line.split()
                for part in parts:
                    if part.isdigit():
                        block_number = int(part)
                        break

        return {"tx_id": tx_id, "block_number": block_number, "error": None}


# ── IPFS via Pinata ──────────────────────────────────────────

class PinataService:
    """Store policy PDF metadata on IPFS via Pinata API."""

    _BASE_URL = "https://api.pinata.cloud"

    def __init__(self) -> None:
        self._headers = {
            "pinata_api_key": settings.PINATA_API_KEY,
            "pinata_secret_api_key": settings.PINATA_SECRET_KEY,
        }

    async def pin_json(self, data: dict, name: str) -> Optional[str]:
        """Pin JSON metadata to IPFS. Returns CID string or None on failure."""
        import httpx

        payload = {
            "pinataContent": data,
            "pinataMetadata": {"name": name},
            "pinataOptions": {"cidVersion": 1},
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self._BASE_URL}/pinning/pinJSONToIPFS",
                    headers=self._headers,
                    json=payload,
                )
                resp.raise_for_status()
                return resp.json().get("IpfsHash")
        except Exception as exc:
            logger.error("Pinata pin failed for %s: %s", name, exc)
            return None
