import pytest
from unittest.mock import AsyncMock, patch
from decimal import Decimal

from api.services.pricing.workflow_run_cost import _build_usage_cost_snapshot
from api.db.models import OrganizationModel


@pytest.fixture
def sample_openrouter_usage_info():
    return {
        "llm": {
            "OpenRouterLLMService#0|||meta-llama/llama-3.3-70b-instruct": {
                "prompt_tokens": 1000,
                "completion_tokens": 500,
                "total_tokens": 1500,
            }
        },
        "tts": {
            "ElevenLabsTTSService#0|||elevenlabs_default": 1000,  # 1000 characters
        },
        "stt": {
            "DeepgramSTTService#0|||nova-2": 60.0,  # 60 seconds
        },
        "call_duration_seconds": 60,
    }


@pytest.mark.asyncio
async def test_build_usage_cost_snapshot_openrouter_dynamic_from_api(
    sample_openrouter_usage_info,
):
    # Mocking fetching prices from OpenRouter models endpoint
    mock_or_prices = {
        "meta-llama/llama-3.3-70b-instruct": {
            "prompt_token_price": Decimal("0.00000060"),  # $0.60 per 1M tokens
            "completion_token_price": Decimal("0.00000240"),  # $2.40 per 1M tokens
        }
    }

    mock_org = OrganizationModel(
        id=1,
        provider_id="org_1",
        balance_usd=100.0,
        price_per_second_usd=0.0025,
    )

    custom_pricing = {"llm": {}}

    # Calculate expected raw service costs:
    # LLM prompt: 1000 * 0.0000006 = 0.0006
    # LLM completion: 500 * 0.0000024 = 0.0012
    # LLM total: 0.0018
    # TTS cost: 1000 * 0.00010 = 0.10
    # STT cost: 60 * (0.0058 / 60) = 0.0058
    # Raw total = 0.0018 + 0.10 + 0.0058 = 0.1076
    # Platform Cost = (60 / 60) * 0.055 = 0.055
    # Total charge = 0.1076 + 0.055 = 0.1626

    with patch(
        "api.services.pricing.workflow_run_cost.db_client.get_global_configuration_value",
        AsyncMock(return_value=custom_pricing),
    ), patch(
        "api.services.pricing.openrouter_pricing.fetch_openrouter_prices",
        return_value=mock_or_prices,
    ):

        cost_info = await _build_usage_cost_snapshot(
            sample_openrouter_usage_info,
            organization=mock_org,
            calculated_at="2026-07-01T12:00:00Z",
        )

        assert cost_info is not None
        assert cost_info["charge_usd"] == pytest.approx(0.1626)
        assert cost_info["platform_infra_rate"] == 0.055

        # Verify raw breakdown values
        breakdown = cost_info["cost_breakdown"]
        assert breakdown["llm_cost"] == pytest.approx(0.0018)
        assert breakdown["tts_cost"] == pytest.approx(0.10)
        assert breakdown["stt_cost"] == pytest.approx(0.0058)
        assert breakdown["platform_cost"] == pytest.approx(0.055)
        assert breakdown["total"] == pytest.approx(0.1076)


@pytest.mark.asyncio
async def test_build_usage_cost_snapshot_openrouter_with_db_override(
    sample_openrouter_usage_info,
):
    mock_or_prices = {
        "meta-llama/llama-3.3-70b-instruct": {
            "prompt_token_price": Decimal("0.00000060"),
            "completion_token_price": Decimal("0.00000240"),
        }
    }

    mock_org = OrganizationModel(
        id=1,
        provider_id="org_1",
        balance_usd=100.0,
    )

    # Override LLM price in database override pricing config
    # Set platform_infra_rate to 0.10 and markup is removed
    custom_pricing = {
        "platform_infra_rate": 0.10,
        "llm": {
            "openrouter": {
                "meta-llama/llama-3.3-70b-instruct": {
                    "prompt_token_price": 0.0000020,  # Custom override ($2 per 1M)
                    "completion_token_price": 0.0000080,  # Custom override ($8 per 1M)
                }
            }
        },
    }

    # Expected Override Cost:
    # LLM prompt: 1000 * 0.0000020 = 0.002
    # LLM completion: 500 * 0.0000080 = 0.004
    # LLM total: 0.006
    # TTS cost: 1000 * 0.00010 = 0.10
    # STT cost: 60 * (0.0058 / 60) = 0.0058
    # Raw total = 0.006 + 0.10 + 0.0058 = 0.1118
    # Platform Cost = (60 / 60) * 0.10 = 0.10
    # Total charge = 0.1118 + 0.10 = 0.2118

    with patch(
        "api.services.pricing.workflow_run_cost.db_client.get_global_configuration_value",
        AsyncMock(return_value=custom_pricing),
    ), patch(
        "api.services.pricing.openrouter_pricing.fetch_openrouter_prices",
        return_value=mock_or_prices,
    ):

        cost_info = await _build_usage_cost_snapshot(
            sample_openrouter_usage_info,
            organization=mock_org,
            calculated_at="2026-07-01T12:00:00Z",
        )

        assert cost_info is not None
        assert cost_info["charge_usd"] == pytest.approx(0.2118)
        assert cost_info["platform_infra_rate"] == 0.10

        # Verify raw breakdown values
        breakdown = cost_info["cost_breakdown"]
        assert breakdown["llm_cost"] == pytest.approx(0.006)
        assert breakdown["tts_cost"] == pytest.approx(0.10)
        assert breakdown["stt_cost"] == pytest.approx(0.0058)
        assert breakdown["platform_cost"] == pytest.approx(0.10)
        assert breakdown["total"] == pytest.approx(0.1118)
