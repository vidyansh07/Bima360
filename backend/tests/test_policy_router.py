"""Integration tests for the /policies router using test client."""
import pytest


class TestPoliciesRouter:
    async def test_get_products(self, client):
        """GET /policies/products should return a list."""
        response = await client.get("/api/v1/policies/products")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_create_policy_missing_fields(self, client):
        """POST /policies/create with empty body should return 422."""
        response = await client.post("/api/v1/policies/create", json={})
        assert response.status_code == 422

    async def test_get_policy_not_found(self, client):
        """GET /policies/{id} with nonexistent UUID should return 404."""
        response = await client.get("/api/v1/policies/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404

    async def test_my_clients_returns_list(self, client):
        """GET /policies/my-clients should return a list (empty is fine)."""
        response = await client.get("/api/v1/policies/my-clients")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_health_endpoint(self, client):
        """GET /health should always return 200."""
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
