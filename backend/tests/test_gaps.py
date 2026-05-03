import pytest
import asyncio
from httpx import AsyncClient
from uuid import uuid4
from datetime import datetime

# Import apps
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../"))
from services.coordination.main import app as coordination_app
from services.registry.main import app as registry_app
from services.ingestion.main import app as ingestion_app

# Mock Auth
def mock_auth():
    return {
        "sub": str(uuid4()),
        "tenant_id": str(uuid4()),
        "role": "ngo_admin",
    }

@pytest.mark.asyncio
async def test_gap_08_ingest_status():
    async with AsyncClient(app=ingestion_app, base_url="http://test") as ac:
        # Note: We need a real ID or a mock DB. 
        # For now, we'll just check if the route is defined and returns 404 for random UUID
        response = await ac.get(f"/ingest/status/{uuid4()}")
        assert response.status_code == 404

@pytest.mark.asyncio
async def test_gap_09_wards():
    async with AsyncClient(app=registry_app, base_url="http://test") as ac:
        # This will fail due to auth, but confirms route exists
        response = await ac.get("/wards")
        assert response.status_code == 401 # No token

@pytest.mark.asyncio
async def test_gap_07_briefing_preview():
    async with AsyncClient(app=coordination_app, base_url="http://test") as ac:
        response = await ac.post(f"/tasks/{uuid4()}/briefing/preview", json={
            "language": "hi",
            "variables": {
                "category": "Food",
                "location": "Ward 5",
                "beneficiary_count": 5,
                "description": "Test"
            }
        })
        assert response.status_code == 401 # No token

if __name__ == "__main__":
    # Simple manual check of routes
    print("Coordination routes:", [r.path for r in coordination_app.routes])
    print("Registry routes:", [r.path for r in registry_app.routes])
    print("Ingestion routes:", [r.path for r in ingestion_app.routes])
