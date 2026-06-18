"""Test that tool schemas are automatically injected into agent system prompts."""

from unittest.mock import MagicMock

from pipecat.adapters.schemas.function_schema import FunctionSchema

from api.services.workflow.pipecat_engine_context_composer import (
    compose_system_prompt_for_node,
)


def test_system_prompt_includes_tools_section():
    """System prompt should include AVAILABLE TOOLS section with tool schemas."""
    # Mock node and workflow
    node = MagicMock()
    node.prompt = "You are a helpful assistant."
    node.add_global_prompt = False

    workflow = MagicMock()

    def identity_format(text):
        return text

    # Create some test tool schemas
    tool_schemas = [
        FunctionSchema(
            name="mcp__weather_api__get_forecast",
            description="Get weather forecast for a location",
            properties={},
            required=[],
        ),
        FunctionSchema(
            name="calculator_add",
            description="Add two numbers",
            properties={},
            required=[],
        ),
        FunctionSchema(
            name="edge_next",  # Transition function - should be filtered out
            description="Move to next node",
            properties={},
            required=[],
        ),
    ]

    prompt = compose_system_prompt_for_node(
        node=node,
        workflow=workflow,
        format_prompt=identity_format,
        has_recordings=False,
        tool_schemas=tool_schemas,
    )

    # Verify tools section exists
    assert "AVAILABLE TOOLS:" in prompt
    assert "mcp__weather_api__get_forecast" in prompt
    assert "Get weather forecast for a location" in prompt
    assert "calculator_add" in prompt
    assert "Add two numbers" in prompt

    # Verify transition functions are filtered out
    assert "edge_next" not in prompt


def test_system_prompt_without_tools():
    """System prompt should work without tools (backward compatibility)."""
    node = MagicMock()
    node.prompt = "You are a helpful assistant."
    node.add_global_prompt = False

    workflow = MagicMock()

    def identity_format(text):
        return text

    prompt = compose_system_prompt_for_node(
        node=node,
        workflow=workflow,
        format_prompt=identity_format,
        has_recordings=False,
        tool_schemas=None,
    )

    # Should not include tools section
    assert "AVAILABLE TOOLS:" not in prompt
    assert "You are a helpful assistant." in prompt


def test_mcp_tools_highlighted_in_prompt():
    """MCP tools should have their full namespaced names clearly shown."""
    node = MagicMock()
    node.prompt = "Call the get_weather tool to check weather."
    node.add_global_prompt = False

    workflow = MagicMock()

    def identity_format(text):
        return text

    tool_schemas = [
        FunctionSchema(
            name="mcp__weather_server__get_weather",
            description="Retrieves current weather data",
            properties={},
            required=[],
        ),
    ]

    prompt = compose_system_prompt_for_node(
        node=node,
        workflow=workflow,
        format_prompt=identity_format,
        has_recordings=False,
        tool_schemas=tool_schemas,
    )

    # Verify the exact function name is shown
    assert "mcp__weather_server__get_weather" in prompt
    assert "Retrieves current weather data" in prompt
    assert "exact function names" in prompt.lower()


def test_tools_section_with_global_prompt():
    """Tools section should appear after both global and node prompts."""
    node = MagicMock()
    node.prompt = "Node-specific instructions."
    node.add_global_prompt = True

    global_node = MagicMock()
    global_node.prompt = "Global instructions."

    workflow = MagicMock()
    workflow.global_node_id = "global"
    workflow.nodes = {"global": global_node}

    def identity_format(text):
        return text

    tool_schemas = [
        FunctionSchema(
            name="test_tool",
            description="Test tool",
            properties={},
            required=[],
        ),
    ]

    prompt = compose_system_prompt_for_node(
        node=node,
        workflow=workflow,
        format_prompt=identity_format,
        has_recordings=False,
        tool_schemas=tool_schemas,
    )

    # Verify order: global -> node -> tools
    global_idx = prompt.index("Global instructions")
    node_idx = prompt.index("Node-specific instructions")
    tools_idx = prompt.index("AVAILABLE TOOLS")

    assert global_idx < node_idx < tools_idx
