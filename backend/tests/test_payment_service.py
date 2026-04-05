"""Tests for PaymentService — Razorpay order creation and signature verification."""
import hashlib
import hmac
from unittest.mock import MagicMock, patch

import pytest

from backend.services.payment_service import PaymentService


@pytest.fixture
def payment_service():
    return PaymentService()


class TestPaymentService:
    def test_verify_signature_valid(self, payment_service):
        order_id   = "order_test123"
        payment_id = "pay_test456"
        key_secret = "test_secret"

        body = f"{order_id}|{payment_id}"
        expected_sig = hmac.new(
            key_secret.encode(), body.encode(), hashlib.sha256
        ).hexdigest()

        with patch.object(payment_service, "_key_secret", key_secret):
            assert payment_service.verify_razorpay_signature(
                order_id, payment_id, expected_sig
            ) is True

    def test_verify_signature_invalid(self, payment_service):
        with patch.object(payment_service, "_key_secret", "test_secret"):
            assert payment_service.verify_razorpay_signature(
                "order_x", "pay_x", "bad_sig"
            ) is False

    async def test_create_order_calls_razorpay(self, payment_service):
        mock_order = {"id": "order_abc", "amount": 50000, "currency": "INR"}
        mock_client = MagicMock()
        mock_client.order.create.return_value = mock_order

        with patch.object(payment_service, "_razorpay_client", mock_client):
            order = await payment_service.create_razorpay_order(
                amount_paise=50000, receipt="REC-001"
            )

        assert order["id"] == "order_abc"
        mock_client.order.create.assert_called_once()

    async def test_trigger_cashfree_payout_success(self, payment_service):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "SUCCESS", "referenceId": "CF-REF-001"}

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            result = await payment_service.trigger_cashfree_payout(
                beneficiary_name="Ramesh Kumar",
                account_number="1234567890",
                ifsc="SBIN0001234",
                amount=5000.00,
                transfer_id="TRF-001",
            )

        assert result["status"] == "SUCCESS"
