import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_user(client: AsyncClient):
    """Test user registration flow."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "developer@inquira.ai",
            "password": "SecurePassword123!",
            "full_name": "Senior Developer"
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "developer@inquira.ai"
    assert data["full_name"] == "Senior Developer"
    assert "id" in data


@pytest.mark.asyncio
async def test_duplicate_registration_fails(client: AsyncClient):
    """Test that registering duplicate email returns 400."""
    payload = {
        "email": "duplicate@inquira.ai",
        "password": "SecurePassword123!",
        "full_name": "Duplicate Test"
    }
    res1 = await client.post("/api/v1/auth/register", json=payload)
    assert res1.status_code == 201

    res2 = await client.post("/api/v1/auth/register", json=payload)
    assert res2.status_code == 400
    assert "already exists" in res2.json()["detail"]


@pytest.mark.asyncio
async def test_login_and_access_profile(client: AsyncClient):
    """Test user login and fetching profile with bearer token."""
    # 1. Register
    await client.post(
        "/api/v1/auth/register",
        json={"email": "login_test@inquira.ai", "password": "Password12345!"}
    )

    # 2. Login via JSON
    login_res = await client.post(
        "/api/v1/auth/login/json",
        json={"email": "login_test@inquira.ai", "password": "Password12345!"}
    )
    assert login_res.status_code == 200
    tokens = login_res.json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens

    # 3. Access protected /me endpoint
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    me_res = await client.get("/api/v1/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "login_test@inquira.ai"
