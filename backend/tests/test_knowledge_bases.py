import pytest
from httpx import AsyncClient


async def get_authenticated_headers(client: AsyncClient, email: str = "kb_user@inquira.ai") -> dict:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!"}
    )
    res = await client.post(
        "/api/v1/auth/login/json",
        json={"email": email, "password": "Password123!"}
    )
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_knowledge_base_crud(client: AsyncClient):
    headers = await get_authenticated_headers(client)

    # 1. Create KB
    create_res = await client.post(
        "/api/v1/knowledge-bases",
        headers=headers,
        json={"name": "Engineering Docs", "description": "Internal architecture documentation"}
    )
    assert create_res.status_code == 201
    kb_data = create_res.json()
    kb_id = kb_data["id"]
    assert kb_data["name"] == "Engineering Docs"

    # 2. List KBs
    list_res = await client.get("/api/v1/knowledge-bases", headers=headers)
    assert list_res.status_code == 200
    kbs = list_res.json()
    assert len(kbs) >= 1

    # 3. Get single KB
    get_res = await client.get(f"/api/v1/knowledge-bases/{kb_id}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["name"] == "Engineering Docs"

    # 4. Update KB
    update_res = await client.put(
        f"/api/v1/knowledge-bases/{kb_id}",
        headers=headers,
        json={"name": "Engineering Knowledge Base"}
    )
    assert update_res.status_code == 200
    assert update_res.json()["name"] == "Engineering Knowledge Base"

    # 5. Delete KB
    delete_res = await client.delete(f"/api/v1/knowledge-bases/{kb_id}", headers=headers)
    assert delete_res.status_code == 204
