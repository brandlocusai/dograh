"""
Cost Calculator for Workflow Runs

This module provides a comprehensive cost calculation system for workflow runs based on usage metrics
from different AI service providers (OpenAI, Groq, Deepgram, etc.).

Features:
- Token-based pricing for LLM services with cache optimization support
- Character-based pricing for TTS services
- Time-based pricing for STT services
- Configurable pricing models that can be updated
- Support for multiple providers and models
- Automatic provider inference from model names
- JSON serialization support for database storage

Usage:
    from api.tasks.cost_calculator import cost_calculator

    usage_info = {
        "llm": {
            "processor_name|||gpt-4o": {
                "prompt_tokens": 1000,
                "completion_tokens": 500,
                "total_tokens": 1500,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0
            }
        },
        "tts": {
            "processor_name|||aura-2-helena-en": 2000  # character count
        }
    }

    cost_breakdown = cost_calculator.calculate_total_cost(usage_info)
    print(f"Total cost: ${cost_breakdown['total']:.6f}")
"""

from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from api.services.configuration.registry import ServiceProviders
from api.services.pricing import PRICING_REGISTRY
from api.services.pricing.models import (
    PricingModel,
)


class CostCalculator:
    """Main cost calculator class"""

    def __init__(self, pricing_registry: Dict = None):
        self.pricing_registry = pricing_registry or PRICING_REGISTRY

    def get_pricing_model(
        self,
        service_type: str,
        provider: str,
        model: str,
        custom_pricing: Optional[Dict] = None,
    ) -> Optional[PricingModel]:
        """Get pricing model for a specific service, provider, and model"""
        # Special handling for OpenRouter dynamic pricing
        if service_type == "llm" and provider == "openrouter":
            # Check if there is an explicit database override first
            model_pricing = None
            if custom_pricing and "llm" in custom_pricing:
                model_pricing = custom_pricing.get("llm", {}).get("openrouter", {}).get(model)
            
            if model_pricing:
                try:
                    from api.services.pricing.models import TokenPricingModel
                    return TokenPricingModel(
                        prompt_token_price=Decimal(str(model_pricing.get("prompt_token_price", 0.0))),
                        completion_token_price=Decimal(str(model_pricing.get("completion_token_price", 0.0))),
                    )
                except Exception:
                    pass

            # If no manual database override, fetch dynamic rates from OpenRouter
            try:
                from api.services.pricing.openrouter_pricing import fetch_openrouter_prices
                prices = fetch_openrouter_prices()
                if model in prices:
                    from api.services.pricing.models import TokenPricingModel
                    return TokenPricingModel(
                        prompt_token_price=prices[model]["prompt_token_price"],
                        completion_token_price=prices[model]["completion_token_price"],
                    )
            except Exception:
                pass

        if custom_pricing and service_type in custom_pricing:
            service_pricing = custom_pricing.get(service_type, {})
            provider_pricing = service_pricing.get(provider, {})
            model_pricing = provider_pricing.get(model) or provider_pricing.get(
                "default"
            )
            if model_pricing:
                try:
                    if service_type == "llm":
                        from api.services.pricing.models import TokenPricingModel

                        return TokenPricingModel(
                            prompt_token_price=Decimal(
                                str(model_pricing.get("prompt_token_price", 0.0))
                            ),
                            completion_token_price=Decimal(
                                str(model_pricing.get("completion_token_price", 0.0))
                            ),
                        )
                    elif service_type == "tts":
                        from api.services.pricing.models import CharacterPricingModel

                        return CharacterPricingModel(
                            character_price=Decimal(
                                str(model_pricing.get("character_price", 0.0))
                            ),
                        )
                    elif service_type == "stt":
                        from api.services.pricing.models import TimePricingModel

                        return TimePricingModel(
                            second_price=Decimal(
                                str(model_pricing.get("second_price", 0.0))
                            ),
                        )
                except Exception:
                    pass

        try:
            service_pricing = self.pricing_registry.get(service_type, {})

            # Try to get pricing for the specific provider
            provider_pricing = service_pricing.get(provider, {})
            pricing_model = provider_pricing.get(model) or provider_pricing.get(
                "default"
            )

            if pricing_model:
                return pricing_model

            # If not found, try the "default" provider for this service type
            default_provider_pricing = service_pricing.get("default", {})
            return default_provider_pricing.get(model) or default_provider_pricing.get(
                "default"
            )

        except (KeyError, AttributeError):
            return None

    def calculate_llm_cost(
        self,
        provider: str,
        model: str,
        usage: Dict[str, int],
        custom_pricing: Optional[Dict] = None,
    ) -> Decimal:
        """Calculate cost for LLM usage"""
        pricing_model = self.get_pricing_model(
            "llm", provider, model, custom_pricing
        )
        if not pricing_model:
            return Decimal("0")
        return pricing_model.calculate_cost(usage)

    def calculate_tts_cost(
        self,
        provider: str,
        model: str,
        character_count: int,
        custom_pricing: Optional[Dict] = None,
    ) -> Decimal:
        """Calculate cost for TTS usage"""
        pricing_model = self.get_pricing_model(
            "tts", provider, model, custom_pricing
        )
        if not pricing_model:
            return Decimal("0")
        return pricing_model.calculate_cost(character_count)

    def calculate_stt_cost(
        self,
        provider: str,
        model: str,
        seconds: float,
        custom_pricing: Optional[Dict] = None,
    ) -> Decimal:
        """Calculate cost for STT usage"""
        pricing_model = self.get_pricing_model(
            "stt", provider, model, custom_pricing
        )
        if not pricing_model:
            return Decimal("0")
        return pricing_model.calculate_cost(seconds)

    def calculate_total_cost(
        self, usage_info: Dict, custom_pricing: Optional[Dict] = None
    ) -> Dict[str, Any]:
        llm_cost_total = Decimal("0")
        tts_cost_total = Decimal("0")
        stt_cost_total = Decimal("0")

        # Calculate LLM costs
        llm_usage = usage_info.get("llm", {})
        for key, usage in llm_usage.items():
            processor, model = self._parse_key(key)
            # Try to determine provider from processor name or model
            provider = self._infer_provider_from_model(model, "llm")
            cost = self.calculate_llm_cost(provider, model, usage, custom_pricing)
            llm_cost_total += cost

        # Calculate TTS costs
        tts_usage = usage_info.get("tts", {})
        for key, character_count in tts_usage.items():
            processor, model = self._parse_key(key)
            # Handle the case where model is "None" - infer from processor
            if model.lower() in ["none", "null", ""]:
                provider = self._infer_provider_from_processor(processor, "tts")
                model = "default"  # Use default model for the provider
            else:
                provider = self._infer_provider_from_model(model, "tts")
            cost = self.calculate_tts_cost(
                provider, model, character_count, custom_pricing
            )
            tts_cost_total += cost

        # Calculate STT costs from explicit stt usage
        stt_usage = usage_info.get("stt", {})
        for key, seconds in stt_usage.items():
            processor, model = self._parse_key(key)
            provider = self._infer_provider_from_model(model, "stt")
            cost = self.calculate_stt_cost(provider, model, seconds, custom_pricing)
            stt_cost_total += cost

        total_cost = llm_cost_total + tts_cost_total + stt_cost_total

        return {
            "llm_cost": float(llm_cost_total),
            "tts_cost": float(tts_cost_total),
            "stt_cost": float(stt_cost_total),
            "total": float(total_cost),
        }


    def _parse_key(self, key) -> Tuple[str, str]:
        """Parse key which is in format 'processor|||model'"""
        if isinstance(key, str) and "|||" in key:
            parts = key.split("|||", 1)
            return parts[0], parts[1]
        else:
            # Fallback for backwards compatibility or malformed keys
            return str(key), "unknown"

    def _infer_provider_from_model(self, model: str, service_type: str) -> str:
        """Infer provider from model name"""
        if not model:
            return "unknown"

        model_lower = model.lower()

        # OpenRouter models always contain a slash (e.g., vendor/model)
        if service_type == "llm" and "/" in model_lower:
            return ServiceProviders.OPENROUTER

        # OpenAI models
        if any(keyword in model_lower for keyword in ["gpt", "whisper", "openai"]):
            return ServiceProviders.OPENAI

        # Groq models
        if any(keyword in model_lower for keyword in ["groq"]):
            return ServiceProviders.GROQ

        # Elevenlabs models
        if any(keyword in model_lower for keyword in ["eleven"]):
            return ServiceProviders.ELEVENLABS

        # Deepgram models
        if any(
            keyword in model_lower
            for keyword in ["deepgram", "nova", "phonecall", "general"]
        ):
            return ServiceProviders.DEEPGRAM

        # Default to first available provider for the service type
        service_providers = self.pricing_registry.get(service_type, {})
        if service_providers:
            return list(service_providers.keys())[0]

        return "unknown"

    def _infer_provider_from_processor(self, processor: str, service_type: str) -> str:
        """Infer provider from processor name"""
        if not processor:
            return "unknown"

        processor_lower = processor.lower()

        # OpenAI processors
        if any(keyword in processor_lower for keyword in ["openai", "gpt"]):
            return ServiceProviders.OPENAI

        # Groq processors
        if any(keyword in processor_lower for keyword in ["groq"]):
            return ServiceProviders.GROQ

        # Deepgram processors
        if any(keyword in processor_lower for keyword in ["deepgram"]):
            return ServiceProviders.DEEPGRAM

        # Default to first available provider for the service type
        service_providers = self.pricing_registry.get(service_type, {})
        if service_providers:
            return list(service_providers.keys())[0]

        return "unknown"

    def update_pricing(
        self, service_type: str, provider: str, model: str, pricing_model: PricingModel
    ):
        """Update pricing for a specific service/provider/model combination"""
        if service_type not in self.pricing_registry:
            self.pricing_registry[service_type] = {}
        if provider not in self.pricing_registry[service_type]:
            self.pricing_registry[service_type][provider] = {}
        self.pricing_registry[service_type][provider][model] = pricing_model


# Global cost calculator instance
cost_calculator = CostCalculator()
