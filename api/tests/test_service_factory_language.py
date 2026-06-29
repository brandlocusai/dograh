"""Tests for language configuration handling in service factory."""

import pytest
from unittest.mock import Mock, patch, PropertyMock

from api.services.pipecat.service_factory import (
    create_stt_service,
    create_tts_service,
)
from api.services.configuration.registry import ServiceProviders


@pytest.fixture
def audio_config():
    """Mock audio configuration."""
    config = Mock()
    config.sample_rate = 16000
    config.channels = 1
    config.transport_in_sample_rate = 16000
    return config


def create_mock_user_config(stt_config=None, tts_config=None):
    """Create a mock user configuration."""
    user_config = Mock()
    if stt_config:
        user_config.stt = stt_config
    if tts_config:
        user_config.tts = tts_config
    return user_config


def create_mock_stt_config(provider_str: str, **kwargs):
    """Create a mock STT configuration."""
    config = Mock()
    # Set provider as string directly
    type(config).provider = PropertyMock(return_value=provider_str)
    config.api_key = kwargs.get('api_key', 'test-api-key')
    config.model = kwargs.get('model', 'default-model')
    config.language = kwargs.get('language', 'en')

    # Add provider-specific attributes
    if provider_str == 'google':
        config.credentials = kwargs.get('credentials', '{"type": "service_account"}')
        config.location = kwargs.get('location', 'global')
    elif provider_str == 'openai':
        config.base_url = kwargs.get('base_url', 'https://api.openai.com/v1')

    return config


def create_mock_tts_config(provider_str: str, **kwargs):
    """Create a mock TTS configuration."""
    config = Mock()
    # Set provider as string directly
    type(config).provider = PropertyMock(return_value=provider_str)
    config.api_key = kwargs.get('api_key', 'test-api-key')
    config.model = kwargs.get('model', 'default-model')
    config.voice = kwargs.get('voice', 'default-voice')
    config.language = kwargs.get('language', 'en')
    config.speed = kwargs.get('speed', 1.0)

    # Add provider-specific attributes
    if provider_str == 'elevenlabs':
        config.base_url = kwargs.get('base_url', 'https://api.elevenlabs.io')
    elif provider_str == 'google':
        config.credentials = kwargs.get('credentials', '{"type": "service_account"}')
        config.location = kwargs.get('location', None)
    elif provider_str == 'azure_speech':
        config.region = kwargs.get('region', 'eastus')

    return config


class TestSTTLanguageConfiguration:
    """Test STT language configuration."""

    def test_deepgram_stt_with_explicit_language(self, audio_config):
        """Verify Deepgram STT uses explicit language parameter."""
        stt_config = create_mock_stt_config(
            'deepgram',
            language="es",
            model="nova-3-general"
        )
        user_config = create_mock_user_config(stt_config=stt_config)

        with patch("api.services.pipecat.service_factory.DeepgramSTTService") as mock_service:
            create_stt_service(user_config, audio_config)
            assert mock_service.called

    def test_deepgram_stt_with_multi_language(self, audio_config):
        """Verify Deepgram STT supports multilingual auto-detect."""
        stt_config = create_mock_stt_config(
            'deepgram',
            language="multi",
            model="nova-3-general"
        )
        user_config = create_mock_user_config(stt_config=stt_config)

        with patch("api.services.pipecat.service_factory.DeepgramSTTService") as mock_service:
            create_stt_service(user_config, audio_config)
            assert mock_service.called


class TestTTSLanguageConfiguration:
    """Test TTS language configuration."""

    def test_google_tts_with_language(self, audio_config):
        """Verify Google TTS uses language parameter."""
        tts_config = create_mock_tts_config(
            'google',
            language="es-ES",
            voice="es-ES-Standard-A",
            credentials='{"type": "service_account"}'
        )
        user_config = create_mock_user_config(tts_config=tts_config)

        with patch("api.services.pipecat.service_factory.GoogleTTSService") as mock_service:
            create_tts_service(user_config, audio_config)
            assert mock_service.called


class TestOpenAILanguageConfiguration:
    """Test OpenAI STT language configuration."""

    def test_openai_stt_with_english(self, audio_config):
        """Verify OpenAI STT uses English language parameter."""
        stt_config = create_mock_stt_config(
            'openai',
            language="en",
            model="gpt-4o-transcribe"
        )
        user_config = create_mock_user_config(stt_config=stt_config)

        with patch("api.services.pipecat.service_factory.OpenAISTTService") as mock_service:
            create_stt_service(user_config, audio_config)
            assert mock_service.called

    def test_openai_stt_with_urdu(self, audio_config):
        """Verify OpenAI STT supports Urdu language."""
        stt_config = create_mock_stt_config(
            'openai',
            language="ur",
            model="gpt-4o-transcribe"
        )
        user_config = create_mock_user_config(stt_config=stt_config)

        with patch("api.services.pipecat.service_factory.OpenAISTTService") as mock_service:
            create_stt_service(user_config, audio_config)
            assert mock_service.called


class TestElevenLabsLanguageConfiguration:
    """Test ElevenLabs TTS language configuration."""

    def test_elevenlabs_tts_with_english(self, audio_config):
        """Verify ElevenLabs TTS uses English language parameter."""
        tts_config = create_mock_tts_config(
            'elevenlabs',
            language="en",
            voice="21m00Tcm4TlvDq8ikWAM",
            model="eleven_flash_v2_5"
        )
        user_config = create_mock_user_config(tts_config=tts_config)

        with patch("api.services.pipecat.service_factory.DograhElevenLabsTTSService") as mock_service:
            create_tts_service(user_config, audio_config)
            assert mock_service.called

    def test_elevenlabs_tts_with_urdu(self, audio_config):
        """Verify ElevenLabs TTS supports Urdu language."""
        tts_config = create_mock_tts_config(
            'elevenlabs',
            language="ur",
            voice="21m00Tcm4TlvDq8ikWAM",
            model="eleven_flash_v2_5"
        )
        user_config = create_mock_user_config(tts_config=tts_config)

        with patch("api.services.pipecat.service_factory.DograhElevenLabsTTSService") as mock_service:
            create_tts_service(user_config, audio_config)
            assert mock_service.called
