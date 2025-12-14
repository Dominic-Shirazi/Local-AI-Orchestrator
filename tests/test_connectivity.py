import pytest
import httpx
import asyncio

BASE_URL = "http://127.0.0.1:8000"

@pytest.mark.asyncio
async def test_health():
    print("\n[INFO] Testing /health endpoint...")
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        try:
            response = await client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert "active_model" in data
            assert "active_provider" in data
            print("[SUCCESS] /health check passed.")
        except httpx.ConnectError:
            print("[FAIL] Could not connect to gateway.")
            pytest.fail("Could not connect to gateway. Is it running?")

@pytest.mark.asyncio
async def test_list_models():
    print("\n[INFO] Testing /v1/models endpoint...")
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        response = await client.get("/v1/models")
        assert response.status_code == 200
        data = response.json()
        assert data["object"] == "list"
        assert isinstance(data["data"], list)
        print(f"[SUCCESS] Found {len(data['data'])} models.")

@pytest.mark.asyncio
async def test_config_endpoint():
    print("\n[INFO] Testing /health/config endpoint...")
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        response = await client.get("/health/config")
        assert response.status_code == 200
        data = response.json()
        assert "config" in data
        assert "routes" in data
        assert "providers" in data
        print("[SUCCESS] Config endpoint loaded correctly.")
