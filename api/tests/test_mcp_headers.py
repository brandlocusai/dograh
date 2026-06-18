"""Test MCP tool headers functionality."""

import pytest

from api.schemas.tool import McpToolConfig
from api.services.workflow.mcp_tool_session import build_streamable_http_params
from unittest.mock import MagicMock


def test_mcp_config_with_headers():
    """McpToolConfig accepts headers field."""
    config = McpToolConfig(
        transport="streamable_http",
        url="https://mcp.example.com",
        headers={"X-API-Version": "v2"},
        tools_filter=[],
    )
    assert config.headers == {"X-API-Version": "v2"}


def test_mcp_config_without_headers():
    """McpToolConfig works without headers (backward compat)."""
    config = McpToolConfig(
        transport="streamable_http",
        url="https://mcp.example.com",
        tools_filter=[],
    )
    assert config.headers is None


def test_headers_merge_with_auth():
    """Custom headers merge with auth headers (auth wins conflicts)."""
    mock_cred = MagicMock()
    mock_cred.credential_type = "bearer_token"
    mock_cred.credential_data = {"token": "test-token"}

    params = build_streamable_http_params(
        url="https://mcp.example.com",
        credential=mock_cred,
        custom_headers={"X-Custom": "value"},
        timeout_secs=30,
        sse_read_timeout_secs=300,
    )

    assert params.headers["Authorization"] == "Bearer test-token"
    assert params.headers["X-Custom"] == "value"


def test_headers_without_auth():
    """Custom headers work without auth credential."""
    params = build_streamable_http_params(
        url="https://mcp.example.com",
        credential=None,
        custom_headers={"X-Custom": "value", "X-Another": "header"},
        timeout_secs=30,
        sse_read_timeout_secs=300,
    )

    assert params.headers == {"X-Custom": "value", "X-Another": "header"}


def test_auth_overrides_custom_header_on_conflict():
    """Auth header takes precedence over custom header with same name."""
    mock_cred = MagicMock()
    mock_cred.credential_type = "bearer_token"
    mock_cred.credential_data = {"token": "auth-token"}

    params = build_streamable_http_params(
        url="https://mcp.example.com",
        credential=mock_cred,
        custom_headers={"Authorization": "Bearer custom-token"},
        timeout_secs=30,
        sse_read_timeout_secs=300,
    )

    # Auth credential should win
    assert params.headers["Authorization"] == "Bearer auth-token"
