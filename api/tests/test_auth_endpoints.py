from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.auth import router


def _make_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


def test_send_magic_link():
    app = _make_test_app()
    client = TestClient(app)

    with patch("api.routes.auth.send_magic_link_email", new_callable=AsyncMock) as mock_send:
        response = client.post(
            "/auth/magic-link",
            json={"email": "user@example.com"},
        )

    assert response.status_code == 200
    assert response.json() == {"message": "Magic link sent successfully"}
    mock_send.assert_called_once()
    assert "user@example.com" in mock_send.call_args[0][0]


def test_verify_magic_link_success():
    app = _make_test_app()
    client = TestClient(app)

    mock_user = AsyncMock()
    mock_user.id = 42
    mock_user.email = "user@example.com"
    mock_user.provider_id = "provider-42"

    with patch("api.routes.auth.decode_magic_token", return_value="user@example.com"), \
         patch("api.routes.auth.get_or_create_user_and_org", new_callable=AsyncMock, return_value=(mock_user, 11)), \
         patch("api.routes.auth.create_jwt_token", return_value="mock-jwt-token"), \
         patch("api.routes.auth.capture_event"):
        
        response = client.post(
            "/auth/magic-link/verify",
            json={"token": "valid-magic-token"},
        )

    assert response.status_code == 200
    res_data = response.json()
    assert res_data["token"] == "mock-jwt-token"
    assert res_data["user"]["id"] == 42
    assert res_data["user"]["email"] == "user@example.com"
    assert res_data["user"]["organization_id"] == 11


def test_verify_magic_link_invalid_token():
    app = _make_test_app()
    client = TestClient(app)

    with patch("api.routes.auth.decode_magic_token", side_effect=Exception("Expired")):
        response = client.post(
            "/auth/magic-link/verify",
            json={"token": "expired-token"},
        )

    assert response.status_code == 400
    assert "Invalid or expired token" in response.json()["detail"]


@pytest.mark.asyncio
async def test_google_auth_success():
    app = _make_test_app()
    client = TestClient(app)

    mock_user = AsyncMock()
    mock_user.id = 99
    mock_user.email = "googleuser@example.com"
    mock_user.provider_id = "google_123456"

    mock_tokeninfo = {
        "aud": "mock-google-client-id",
        "email": "googleuser@example.com",
        "sub": "123456",
    }

    class MockResponse:
        def __init__(self, json_data, status_code):
            self.json_data = json_data
            self.status_code = status_code
        def json(self):
            return self.json_data
        def raise_for_status(self):
            pass

    with patch("api.routes.auth.GOOGLE_CLIENT_ID", "mock-google-client-id"), \
         patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=MockResponse(mock_tokeninfo, 200)), \
         patch("api.routes.auth.get_or_create_user_and_org", new_callable=AsyncMock, return_value=(mock_user, 22)), \
         patch("api.routes.auth.create_jwt_token", return_value="mock-jwt-token"), \
         patch("api.routes.auth.capture_event"):

        response = client.post(
            "/auth/google",
            json={"id_token": "valid-google-id-token"},
        )

    assert response.status_code == 200
    res_data = response.json()
    assert res_data["token"] == "mock-jwt-token"
    assert res_data["user"]["email"] == "googleuser@example.com"
    assert res_data["user"]["organization_id"] == 22
