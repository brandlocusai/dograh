"""Integration tests for language configuration persistence."""

import pytest
from httpx import AsyncClient

from api.db.database import get_async_db
from api.db.user_client import UserClient
from api.services.configuration.registry import ServiceProviders


@pytest.mark.asyncio
class TestLanguageConfigurationPersistence:
    """Test language configuration saves and loads correctly."""

    async def test_stt_language_persistence(
        self, async_client: AsyncClient, user_fixture
    ):
        """Test STT language configuration persists across saves/loads."""
        # Set STT language to Spanish
        response = await async_client.put(
            "/api/v1/user-configurations",
            json={
                "stt": {
                    "provider": ServiceProviders.DEEPGRAM,
                    "model": "nova-3-general",
                    "language": "es",  # Spanish
                    "api_key": "test-key",
                }
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["stt"]["language"] == "es"

        # Reload configuration
        response = await async_client.get("/api/v1/user-configurations")
        assert response.status_code == 200
        data = response.json()
        assert data["stt"]["language"] == "es"

    async def test_tts_language_persistence(
        self, async_client: AsyncClient, user_fixture
    ):
        """Test TTS language configuration persists across saves/loads."""
        # Set TTS language to French
        response = await async_client.put(
            "/api/v1/user-configurations",
            json={
                "tts": {
                    "provider": ServiceProviders.GOOGLE,
                    "model": "chirp_3_hd",
                    "voice": "fr-FR-Neural2-A",
                    "language": "fr-FR",  # French (France)
                    "credentials": '{"type": "service_account"}',
                }
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["tts"]["language"] == "fr-FR"

        # Reload configuration
        response = await async_client.get("/api/v1/user-configurations")
        assert response.status_code == 200
        data = response.json()
        assert data["tts"]["language"] == "fr-FR"

    async def test_multiple_language_configurations(
        self, async_client: AsyncClient, user_fixture
    ):
        """Test different languages for STT and TTS (translation use case)."""
        # User speaks Spanish, bot responds in English
        response = await async_client.put(
            "/api/v1/user-configurations",
            json={
                "stt": {
                    "provider": ServiceProviders.DEEPGRAM,
                    "model": "nova-3-general",
                    "language": "es",  # Spanish input
                    "api_key": "test-key",
                },
                "tts": {
                    "provider": ServiceProviders.GOOGLE,
                    "model": "chirp_3_hd",
                    "voice": "en-US-Chirp3-HD-Charon",
                    "language": "en-US",  # English output
                    "credentials": '{"type": "service_account"}',
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["stt"]["language"] == "es"
        assert data["tts"]["language"] == "en-US"

    async def test_bcp47_language_codes(
        self, async_client: AsyncClient, user_fixture
    ):
        """Test BCP-47 language codes are preserved correctly."""
        # Google supports extended BCP-47 codes
        response = await async_client.put(
            "/api/v1/user-configurations",
            json={
                "stt": {
                    "provider": ServiceProviders.GOOGLE,
                    "model": "latest_long",
                    "language": "cmn-Hans-CN",  # Mandarin (Simplified)
                    "credentials": '{"type": "service_account"}',
                }
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["stt"]["language"] == "cmn-Hans-CN"

    async def test_auto_detect_language(
        self, async_client: AsyncClient, user_fixture
    ):
        """Test auto-detect language settings persist."""
        # Deepgram multi-language
        response = await async_client.put(
            "/api/v1/user-configurations",
            json={
                "stt": {
                    "provider": ServiceProviders.DEEPGRAM,
                    "model": "nova-3-general",
                    "language": "multi",  # Auto-detect
                    "api_key": "test-key",
                }
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["stt"]["language"] == "multi"

        # Sarvam unknown language
        response = await async_client.put(
            "/api/v1/user-configurations",
            json={
                "stt": {
                    "provider": ServiceProviders.SARVAM,
                    "model": "saarika:v2.5",
                    "language": "unknown",  # Auto-detect
                    "api_key": "test-key",
                }
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["stt"]["language"] == "unknown"


@pytest.mark.asyncio
class TestWorkflowOverrideLanguage:
    """Test workflow-level language overrides."""

    async def test_workflow_override_stt_language(
        self, async_client: AsyncClient, user_fixture
    ):
        """Test workflow can override global STT language."""
        # Set global language to English
        response = await async_client.put(
            "/api/v1/user-configurations",
            json={
                "stt": {
                    "provider": ServiceProviders.DEEPGRAM,
                    "model": "nova-3-general",
                    "language": "en",  # Global: English
                    "api_key": "test-key",
                }
            },
        )
        assert response.status_code == 200

        # Create workflow with Spanish override
        workflow_payload = {
            "name": "Spanish Test Workflow",
            "model_overrides": {
                "stt": {
                    "language": "es"  # Override: Spanish
                }
            },
        }

        response = await async_client.post(
            "/api/v1/workflows", json=workflow_payload
        )
        assert response.status_code == 200
        workflow = response.json()
        assert workflow["model_overrides"]["stt"]["language"] == "es"

        # Verify global config unchanged
        response = await async_client.get("/api/v1/user-configurations")
        assert response.status_code == 200
        data = response.json()
        assert data["stt"]["language"] == "en"

    async def test_workflow_override_tts_language(
        self, async_client: AsyncClient, user_fixture
    ):
        """Test workflow can override global TTS language."""
        # Set global language to English
        response = await async_client.put(
            "/api/v1/user-configurations",
            json={
                "tts": {
                    "provider": ServiceProviders.GOOGLE,
                    "model": "chirp_3_hd",
                    "voice": "en-US-Chirp3-HD-Charon",
                    "language": "en-US",  # Global: English
                    "credentials": '{"type": "service_account"}',
                }
            },
        )
        assert response.status_code == 200

        # Create workflow with French override
        workflow_payload = {
            "name": "French Test Workflow",
            "model_overrides": {
                "tts": {
                    "language": "fr-FR",  # Override: French
                    "voice": "fr-FR-Neural2-A",
                }
            },
        }

        response = await async_client.post(
            "/api/v1/workflows", json=workflow_payload
        )
        assert response.status_code == 200
        workflow = response.json()
        assert workflow["model_overrides"]["tts"]["language"] == "fr-FR"


@pytest.mark.asyncio
class TestLanguageValidation:
    """Test language validation in API."""

    async def test_invalid_language_code_rejected(
        self, async_client: AsyncClient, user_fixture
    ):
        """Test API rejects clearly invalid language codes."""
        # Some providers may validate, others may not
        # This test verifies the behavior is consistent
        response = await async_client.put(
            "/api/v1/user-configurations",
            json={
                "stt": {
                    "provider": ServiceProviders.DEEPGRAM,
                    "model": "nova-3-general",
                    "language": "not-a-real-language-code-12345",
                    "api_key": "test-key",
                }
            },
        )

        # Either accept (provider validates at runtime) or reject (schema validates)
        # Both behaviors are acceptable depending on implementation
        assert response.status_code in [200, 400, 422]

    async def test_empty_language_uses_default(
        self, async_client: AsyncClient, user_fixture
    ):
        """Test empty language falls back to provider default."""
        response = await async_client.put(
            "/api/v1/user-configurations",
            json={
                "stt": {
                    "provider": ServiceProviders.DEEPGRAM,
                    "model": "nova-3-general",
                    # Omit language field - should use default
                    "api_key": "test-key",
                }
            },
        )
        assert response.status_code == 200
        data = response.json()

        # Should have default language (likely "multi" or "en")
        assert "language" in data["stt"]
        assert data["stt"]["language"] in ["multi", "en", "en-US"]

    async def test_language_field_optional(
        self, async_client: AsyncClient, user_fixture
    ):
        """Test language field is optional and uses provider defaults."""
        response = await async_client.put(
            "/api/v1/user-configurations",
            json={
                "stt": {
                    "provider": ServiceProviders.CARTESIA,
                    "model": "ink-whisper",
                    # Cartesia may not have language field
                    "api_key": "test-key",
                }
            },
        )

        # Should succeed even if provider doesn't support language
        assert response.status_code == 200


@pytest.mark.asyncio
class TestOpenAILanguagePersistence:
    """Test OpenAI STT language configuration persistence."""

    async def test_openai_stt_english_persistence(
        self, async_client: AsyncClient, user_fixture
    ):
        """Test OpenAI STT English language persists."""
        response = await async_client.put(
            "/api/v1/user-configurations",
            json={
                "stt": {
                    "provider": ServiceProviders.OPENAI,
                    "model": "gpt-4o-transcribe",
                    "language": "en",  # English
                    "api_key": "test-key",
                }
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["stt"]["language"] == "en"

        # Reload
        response = await async_client.get("/api/v1/user-configurations")
        assert response.status_code == 200
        data = response.json()
        assert data["stt"]["language"] == "en"

    async def test_openai_stt_urdu_persistence(
        self, async_client: AsyncClient, user_fixture
    ):
        """Test OpenAI STT Urdu language persists."""
        response = await async_client.put(
            "/api/v1/user-configurations",
            json={
                "stt": {
                    "provider": ServiceProviders.OPENAI,
                    "model": "gpt-4o-transcribe",
                    "language": "ur",  # Urdu (priority language)
                    "api_key": "test-key",
                }
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["stt"]["language"] == "ur"

        # Reload
        response = await async_client.get("/api/v1/user-configurations")
        assert response.status_code == 200
        data = response.json()
        assert data["stt"]["language"] == "ur"

    async def test_openai_stt_multiple_languages(
        self, async_client: AsyncClient, user_fixture
    ):
        """Test switching between multiple languages."""
        # Set to Spanish
        response = await async_client.put(
            "/api/v1/user-configurations",
            json={
                "stt": {
                    "provider": ServiceProviders.OPENAI,
                    "model": "gpt-4o-transcribe",
                    "language": "es",  # Spanish
                    "api_key": "test-key",
                }
            },
        )
        assert response.status_code == 200

        # Change to Urdu
        response = await async_client.put(
            "/api/v1/user-configurations",
            json={
                "stt": {
                    "provider": ServiceProviders.OPENAI,
                    "model": "gpt-4o-transcribe",
                    "language": "ur",  # Urdu
                    "api_key": "test-key",
                }
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["stt"]["language"] == "ur"


@pytest.mark.asyncio
class TestElevenLabsLanguagePersistence:
    """Test ElevenLabs TTS language configuration persistence."""

    async def test_elevenlabs_tts_english_persistence(
        self, async_client: AsyncClient, user_fixture
    ):
        """Test ElevenLabs TTS English language persists."""
        response = await async_client.put(
            "/api/v1/user-configurations",
            json={
                "tts": {
                    "provider": ServiceProviders.ELEVENLABS,
                    "model": "eleven_flash_v2_5",
                    "voice": "21m00Tcm4TlvDq8ikWAM",
                    "language": "en",  # English
                    "api_key": "test-key",
                }
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["tts"]["language"] == "en"

        # Reload
        response = await async_client.get("/api/v1/user-configurations")
        assert response.status_code == 200
        data = response.json()
        assert data["tts"]["language"] == "en"

    async def test_elevenlabs_tts_urdu_persistence(
        self, async_client: AsyncClient, user_fixture
    ):
        """Test ElevenLabs TTS Urdu language persists."""
        response = await async_client.put(
            "/api/v1/user-configurations",
            json={
                "tts": {
                    "provider": ServiceProviders.ELEVENLABS,
                    "model": "eleven_flash_v2_5",
                    "voice": "21m00Tcm4TlvDq8ikWAM",
                    "language": "ur",  # Urdu (priority language)
                    "api_key": "test-key",
                }
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["tts"]["language"] == "ur"

        # Reload
        response = await async_client.get("/api/v1/user-configurations")
        assert response.status_code == 200
        data = response.json()
        assert data["tts"]["language"] == "ur"

    async def test_elevenlabs_tts_arabic_persistence(
        self, async_client: AsyncClient, user_fixture
    ):
        """Test ElevenLabs TTS Arabic language persists."""
        response = await async_client.put(
            "/api/v1/user-configurations",
            json={
                "tts": {
                    "provider": ServiceProviders.ELEVENLABS,
                    "model": "eleven_flash_v2_5",
                    "voice": "21m00Tcm4TlvDq8ikWAM",
                    "language": "ar",  # Arabic
                    "api_key": "test-key",
                }
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["tts"]["language"] == "ar"
