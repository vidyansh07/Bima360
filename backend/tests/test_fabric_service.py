"""Tests for FabricService and PinataService."""
import json
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.fabric_service import FabricService, PinataService


@pytest.fixture
def fabric_service():
    return FabricService()


@pytest.fixture
def pinata_service():
    return PinataService()


# ── FabricService ─────────────────────────────────────────────────────────────

class TestFabricService:
    async def test_invoke_returns_tx_id_on_success(self, fabric_service):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b"txid-abc123"
        mock_result.stderr = b""

        with patch("subprocess.run", return_value=mock_result):
            result = await fabric_service.invoke_chaincode(
                chaincode="policy",
                function="CreatePolicy",
                args=["POL-001", json.dumps({"product": "health"})],
            )

        assert result["tx_id"] is not None
        assert result["error"] is None

    async def test_invoke_returns_none_tx_on_failure(self, fabric_service):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = b""
        mock_result.stderr = b"Error: endorsement failed"

        with patch("subprocess.run", return_value=mock_result):
            result = await fabric_service.invoke_chaincode(
                chaincode="policy",
                function="CreatePolicy",
                args=["POL-001"],
            )

        assert result["tx_id"] is None
        assert result["error"] is not None

    async def test_query_returns_payload(self, fabric_service):
        payload = {"id": "POL-001", "status": "active"}
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(payload).encode()
        mock_result.stderr = b""

        with patch("subprocess.run", return_value=mock_result):
            result = await fabric_service.query_chaincode(
                chaincode="policy",
                function="GetPolicy",
                args=["POL-001"],
            )

        assert result["id"] == "POL-001"

    async def test_subprocess_exception_is_non_blocking(self, fabric_service):
        with patch("subprocess.run", side_effect=FileNotFoundError("peer not found")):
            result = await fabric_service.invoke_chaincode(
                chaincode="claim",
                function="SubmitClaim",
                args=["CLM-001"],
            )

        assert result["tx_id"] is None
        assert "peer not found" in result["error"]


# ── PinataService ─────────────────────────────────────────────────────────────

class TestPinataService:
    async def test_pin_json_returns_cid(self, pinata_service):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"IpfsHash": "QmTestHash123"}

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            cid = await pinata_service.pin_json({"policy_id": "POL-001"})

        assert cid == "QmTestHash123"

    async def test_pin_json_returns_none_on_error(self, pinata_service):
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=Exception("network error")):
            cid = await pinata_service.pin_json({"policy_id": "POL-002"})

        assert cid is None
