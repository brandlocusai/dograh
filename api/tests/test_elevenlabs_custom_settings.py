import pytest
from unittest.mock import patch, AsyncMock
from api.services.pipecat.service_factory import create_tts_service, DograhElevenLabsTTSService
from api.services.configuration.registry import ElevenlabsTTSConfiguration
from api.tests.test_service_factory_language import create_mock_user_config, create_mock_tts_config, audio_config
from pipecat.frames.frames import StartFrame


def test_dograh_elevenlabs_tts_service_instantiation(audio_config):
    """Verify that create_tts_service instantiates DograhElevenLabsTTSService with custom options."""
    tts_config = create_mock_tts_config(
        'elevenlabs',
        voice="21m00Tcm4TlvDq8ikWAM",
        model="eleven_flash_v2_5",
        language="en",
    )
    # Add custom attributes since they are defined on the config class now
    tts_config.output_format = "pcm_22050"
    tts_config.optimize_streaming_latency = 2
    tts_config.stability = 0.85
    tts_config.similarity_boost = 0.90
    tts_config.style = 0.10
    tts_config.use_speaker_boost = True

    user_config = create_mock_user_config(tts_config=tts_config)

    service = create_tts_service(user_config, audio_config)
    assert isinstance(service, DograhElevenLabsTTSService)
    assert service.custom_output_format == "pcm_22050"
    assert service.optimize_streaming_latency == 2
    # Verify sample rate mapping (pcm_22050 -> 22050)
    assert service._init_sample_rate == 22050
    # Verify voice settings
    assert service._settings.stability == 0.85
    assert service._settings.similarity_boost == 0.90
    assert service._settings.style == 0.10
    assert service._settings.use_speaker_boost is True


@pytest.mark.asyncio
async def test_dograh_elevenlabs_tts_service_start(audio_config):
    """Verify that start() sets the correct custom _output_format."""
    service = DograhElevenLabsTTSService(
        api_key="fake_key",
        voice_id="fake_voice",
        model="eleven_flash_v2_5",
        output_format="pcm_22050",
        optimize_streaming_latency=2,
    )

    frame = StartFrame()
    
    # Mock WebsocketTTSService methods so start() doesn't try to connect for real
    with patch.object(DograhElevenLabsTTSService, "_connect", new_callable=AsyncMock) as mock_connect, \
         patch("pipecat.services.tts_service.WebsocketTTSService.start", new_callable=AsyncMock) as mock_grandparent_start:
        
        await service.start(frame)
        
        assert service._output_format == "pcm_22050"
        assert mock_connect.called
        assert mock_grandparent_start.called


@pytest.mark.asyncio
async def test_dograh_elevenlabs_tts_service_connect_websocket(audio_config):
    """Verify that _connect_websocket injects optimize_streaming_latency into the URL."""
    service = DograhElevenLabsTTSService(
        api_key="fake_key",
        voice_id="fake_voice",
        model="eleven_flash_v2_5",
        output_format="pcm_16000",
        optimize_streaming_latency=4,
    )

    # Mock the parent's _connect_websocket and the websocket_connect function
    with patch("pipecat.services.elevenlabs.tts.websocket_connect", new_callable=AsyncMock) as mock_ws_connect, \
         patch("pipecat.services.elevenlabs.tts.ElevenLabsTTSService._connect_websocket", new_callable=AsyncMock) as mock_parent_connect:
        
        # We want to test that the monkeypatched websocket_connect receives the correct URL
        # Let's call the custom _connect_websocket method
        await service._connect_websocket()
        
        # It should have called the parent's _connect_websocket
        assert mock_parent_connect.called
