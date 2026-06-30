import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException, status
from types import SimpleNamespace
from datetime import datetime, UTC

from api.routes.billing import (
    create_checkout_session,
    stripe_webhook,
    get_balance,
    get_transactions,
    CheckoutSessionRequest,
)
from api.services.quota_service import check_dograh_quota
from api.db.models import UserModel, OrganizationModel, BillingTransactionModel
from api.db.organization_usage_client import OrganizationUsageClient


@pytest.fixture
def mock_user():
    return UserModel(
        id=1,
        provider_id="user_provider_id",
        selected_organization_id=42,
    )


@pytest.fixture
def mock_org():
    return OrganizationModel(
        id=42,
        provider_id="org_provider_id",
        balance_usd=10.0,
        price_per_second_usd=0.0025,
        quota_enabled=False,
    )


@pytest.mark.asyncio
async def test_create_checkout_session_success(mock_user, mock_org, monkeypatch):
    req = CheckoutSessionRequest(amount_usd=25.0)

    # Mock DB calls
    get_org_mock = AsyncMock(return_value=mock_org)
    monkeypatch.setattr("api.db.db_client.get_organization_by_id", get_org_mock)

    # Mock Stripe Checkout Session creation
    mock_stripe_session = MagicMock()
    mock_stripe_session.id = "cs_test_123"
    mock_stripe_session.url = "https://checkout.stripe.com/pay/cs_test_123"
    
    stripe_create_mock = MagicMock(return_value=mock_stripe_session)
    monkeypatch.setattr("stripe.checkout.Session.create", stripe_create_mock)

    res = await create_checkout_session(req, user=mock_user)

    assert res.url == "https://checkout.stripe.com/pay/cs_test_123"
    stripe_create_mock.assert_called_once()


@pytest.mark.asyncio
async def test_create_checkout_session_invalid_amount(mock_user):
    req = CheckoutSessionRequest(amount_usd=0.50)
    with pytest.raises(HTTPException) as exc_info:
        await create_checkout_session(req, user=mock_user)
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "Minimum top-up amount" in exc_info.value.detail


@pytest.mark.asyncio
async def test_stripe_webhook_completed_payment(mock_org, monkeypatch):
    payload = b"test_payload"
    sig = "t=123,v1=abc"
    
    mock_event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_123",
                "client_reference_id": "42",
                "amount_total": 2500,  # $25.00 in cents
            }
        }
    }

    # Mock Stripe Webhook signature verification
    monkeypatch.setattr("stripe.Webhook.construct_event", MagicMock(return_value=mock_event))

    # Mock Request
    mock_request = AsyncMock()
    mock_request.body = AsyncMock(return_value=payload)

    # Mock DB session
    mock_db_session = MagicMock()
    session = AsyncMock()
    
    # Mock transaction query (first select)
    mock_tx_result = MagicMock()
    mock_tx_result.scalar_one_or_none.return_value = None  # No existing completed transaction
    
    # Mock organization query (second select with_for_update)
    mock_org_result = MagicMock()
    mock_org_result.scalar_one_or_none.return_value = mock_org

    session.execute = AsyncMock(side_effect=[mock_tx_result, mock_org_result])
    
    # Setup async context manager
    mock_db_session.__aenter__ = AsyncMock(return_value=session)
    mock_db_session.__aexit__ = AsyncMock()
    
    monkeypatch.setattr("api.db.db_client.async_session", MagicMock(return_value=mock_db_session))

    res = await stripe_webhook(mock_request, stripe_signature=sig)
    
    assert res == {"status": "success"}
    assert mock_org.balance_usd == 35.0  # Initial 10.0 + 25.0
    session.add.assert_called_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_balance(mock_user, mock_org, monkeypatch):
    get_org_mock = AsyncMock(return_value=mock_org)
    monkeypatch.setattr("api.db.db_client.get_organization_by_id", get_org_mock)

    res = await get_balance(user=mock_user)
    assert res.balance_usd == 10.0
    assert res.price_per_second_usd == 0.0025


@pytest.mark.asyncio
async def test_quota_check_blocks_low_balance(mock_user, mock_org, monkeypatch):
    # Set balance below $0.10 threshold
    mock_org.balance_usd = 0.05
    get_org_mock = AsyncMock(return_value=mock_org)
    monkeypatch.setattr("api.db.db_client.get_organization_by_id", get_org_mock)

    result = await check_dograh_quota(mock_user)
    assert result.has_quota is False
    assert result.error_code == "insufficient_balance"
    assert "balance is too low" in result.error_message


@pytest.mark.asyncio
async def test_quota_check_allows_sufficient_balance(mock_user, mock_org, monkeypatch):
    mock_org.balance_usd = 5.0
    get_org_mock = AsyncMock(return_value=mock_org)
    monkeypatch.setattr("api.db.db_client.get_organization_by_id", get_org_mock)

    # Mock get_user_configurations to avoid checking Dograh API keys
    mock_config = SimpleNamespace(llm=None, stt=None, tts=None)
    monkeypatch.setattr("api.db.db_client.get_user_configurations", AsyncMock(return_value=mock_config))

    result = await check_dograh_quota(mock_user)
    assert result.has_quota is True


@pytest.mark.asyncio
async def test_update_usage_after_run_deducts_balance(mock_org, monkeypatch):
    # Test atomic deduction in update_usage_after_run
    client = OrganizationUsageClient()

    mock_cycle = SimpleNamespace(
        id=100,
        used_dograh_tokens=1000.0,
        total_duration_seconds=60,
        used_amount_usd=0.0,
    )

    mock_db_session = MagicMock()
    session = AsyncMock()
    mock_db_session.__aenter__ = AsyncMock(return_value=session)
    mock_db_session.__aexit__ = AsyncMock()
    
    # Mock get_or_create_current_cycle implementation
    monkeypatch.setattr(client, "_get_or_create_current_cycle_impl", AsyncMock(return_value=mock_cycle))

    # Mock cycle lock query (first select)
    mock_cycle_result = MagicMock()
    mock_cycle_result.scalar_one.return_value = mock_cycle

    # Mock organization query (second select with_for_update)
    mock_org_result = MagicMock()
    mock_org_result.scalar_one_or_none.return_value = mock_org

    session.execute = AsyncMock(side_effect=[mock_cycle_result, mock_org_result])
    monkeypatch.setattr(client, "async_session", MagicMock(return_value=mock_db_session))

    # Call with duration only (no charge_usd, should calculate based on default rate if not specified)
    # mock_org.price_per_second_usd is 0.0025. Duration 20s. Cost = 20 * 0.0025 = 0.05
    await client.update_usage_after_run(
        organization_id=42,
        actual_tokens=500.0,
        duration_seconds=20.0,
        charge_usd=None,
    )

    assert mock_org.balance_usd == 9.95  # 10.0 - 0.05
    assert mock_cycle.used_amount_usd == 0.05
    assert mock_cycle.used_dograh_tokens == 1500.0
    assert mock_cycle.total_duration_seconds == 80
    session.commit.assert_awaited_once()
