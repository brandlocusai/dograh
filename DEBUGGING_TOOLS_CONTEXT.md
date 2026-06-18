# How to Check Tools Context Provided to Agent

This guide shows you how to verify that the agent is receiving the correct tool names and context, especially important for MCP tools with namespaced names.

## Method 1: Check Server Logs (Real-time)

When running the backend locally, you'll see debug logs showing the system prompt and tools.

### Start backend with debug logging:

```bash
# Set log level to DEBUG or TRACE
export LOGURU_LEVEL=DEBUG  # or TRACE for full system prompt

bash scripts/start_services_dev.sh
```

### Look for these log messages:

When an agent node activates, you'll see:

```
2026-06-18 | DEBUG | Updating LLM context - System prompt length: 1234 chars, Tools: 5 (mcp__weather_api__get_forecast, calculator_add, ...)
```

With `LOGURU_LEVEL=TRACE`, you'll also see:

```
2026-06-18 | TRACE | Full system prompt:
You are a helpful weather assistant.

AVAILABLE TOOLS:
You have access to the following tools. Use the exact function names shown below:

- mcp__weather_api__get_forecast
  Description: Get weather forecast for a location
- mcp__weather_api__get_current
  Description: Get current weather conditions
- calculator_add: Add two numbers

IMPORTANT: Always use the exact function names listed above. Do not modify or simplify the names.
```

## Method 2: Inspect Workflow Run via API

After a call completes, you can fetch the run details which includes logs.

### Using curl:

```bash
# Get your access token first (from browser devtools or login)
ACCESS_TOKEN="your_token_here"

# Fetch workflow run
curl -X GET "http://localhost:8000/api/v1/workflows/{workflow_id}/runs/{run_id}" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

### Using the UI:

1. Navigate to your workflow
2. Click on "Runs" or "History" tab
3. Click on a specific run
4. The run details will show in the UI (current UI may not display logs - see Method 3)

### Response includes:

```json
{
  "id": 123,
  "name": "Test Call",
  "logs": {
    "realtime_feedback_events": [
      {
        "type": "user_transcription",
        "text": "What's the weather?",
        ...
      },
      ...
    ]
  },
  "gathered_context": { ... },
  ...
}
```

## Method 3: Check PostgreSQL Database Directly

If you have direct database access, you can query the workflow runs table:

```sql
-- Get the latest run for a workflow
SELECT
    id,
    name,
    created_at,
    logs,
    gathered_context
FROM workflow_runs
WHERE workflow_id = YOUR_WORKFLOW_ID
ORDER BY created_at DESC
LIMIT 1;

-- Pretty print the logs JSON
SELECT
    id,
    name,
    jsonb_pretty(logs::jsonb) as formatted_logs
FROM workflow_runs
WHERE id = YOUR_RUN_ID;
```

## Method 4: Text Chat Mode (Easiest for Testing)

Text chat mode is perfect for debugging because you can see all interactions in real-time.

### Steps:

1. In your workflow, use "Text Chat" mode instead of voice
2. Start a conversation
3. Watch the agent's responses
4. If agent says "I don't have access to that tool", the tools context wasn't loaded correctly

### Check backend logs while testing:

Terminal running the backend will show:

```
DEBUG | Updating LLM context - System prompt length: 856 chars, Tools: 3 (mcp__server__tool_name, ...)
```

If you don't see your MCP tool in the list, it means:
- MCP server connection failed
- Tool filters excluded it
- Credentials were invalid

## Method 5: Add Diagnostic Logging to Your Code

You can temporarily add logging to see exactly what the agent receives:

```python
# In api/services/workflow/pipecat_engine.py, in set_node_by_id method

# After this line:
system_prompt = compose_system_prompt_for_node(...)

# Add:
logger.info(f"[TOOLS DEBUG] System prompt for node {node.name}:\n{system_prompt}")
logger.info(f"[TOOLS DEBUG] Functions: {[f.get('name') for f in functions]}")
```

## Common Issues and Solutions

### Issue: MCP tool not appearing in logs

**Possible causes:**
1. MCP server connection failed (check server is running)
2. Invalid credentials
3. Tool filter excluding the tool
4. Headers missing (if server requires custom headers)

**Debug:**
```bash
# Check MCP server directly
curl -X POST https://your-mcp-server.com/mcp \
  -H "Content-Type: application/json" \
  -H "X-Custom-Header: value" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
```

### Issue: Agent says it can't call a tool you added

**Check:**
1. Tool appears in the debug logs with correct namespaced name
2. System prompt includes "AVAILABLE TOOLS" section
3. Tool description is clear and accurate

**Example of good vs bad:**

❌ **Bad prompt:** "Call the get_weather tool"
- Agent tries to call `get_weather`, but actual name is `mcp__weather_api__get_weather`

✅ **Good prompt:** "Call the weather forecasting tool to get weather data"
- Agent sees in AVAILABLE TOOLS section and calls `mcp__weather_api__get_forecast` correctly

## Automated Testing

You can write tests to verify tools are properly registered:

```python
# In api/tests/

async def test_mcp_tools_in_system_prompt():
    """Verify MCP tools appear in agent system prompt."""
    # Create test workflow with MCP tool
    # ...

    # Start a run and capture system prompt from logs
    # Assert tool names appear correctly
```

## Best Practices

1. **Always check logs first** - Fastest way to verify tools are loaded
2. **Use descriptive tool names** - Helps in logs: "Weather API Server" vs "MCP 1"
3. **Test with text chat** - Easier to debug than voice calls
4. **Enable DEBUG logging in development** - Catch issues early
5. **Document your MCP tool names** - Keep a reference of actual vs. friendly names

## Need More Help?

If tools still aren't working after checking these methods:

1. Share the debug logs showing tool registration
2. Share your MCP server configuration (URL, headers, filters)
3. Share a sample system prompt from the logs
4. Check if the MCP server itself is responding (use curl/postman)
