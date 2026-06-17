# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

@AGENTS.md

## Common Development Commands

### Backend (Python/FastAPI)

```bash
# Activate virtual environment (always do this first)
source venv/bin/activate

# Run tests (use test environment)
set -a && source api/.env.test && set +a && python -m pytest api/tests/
set -a && source api/.env.test && set +a && python -m pytest api/tests/test_specific.py -v

# Run single test function
set -a && source api/.env.test && set +a && python -m pytest api/tests/test_file.py::test_function_name -v

# Format code
bash scripts/format.sh

# Lint code
bash scripts/lint.sh

# Database migrations
bash scripts/makemigrate.sh "migration description"
bash scripts/migrate.sh

# Start backend in dev mode (auto-reload)
bash scripts/start_services_dev.sh

# Alternative: Manual uvicorn start
set -a && source api/.env && set +a && uvicorn api.app:app --reload --port 8000
```

### Frontend (Next.js/TypeScript)

```bash
cd ui

# Install dependencies
npm install

# Start dev server
npm run dev

# Format and lint
npm run fix-lint
npm run lint

# Generate API client from OpenAPI spec (after backend changes)
npm run generate-client

# Build for production
npm run build
```

### Docker Deployment

```bash
# Local development services (PostgreSQL, Redis, MinIO)
docker compose -f docker-compose-local.yaml up -d

# Full stack deployment (use prebuilt images)
REGISTRY=ghcr.io/dograh-hq docker compose up --pull always

# Rebuild and deploy after code changes
docker compose build api ui
docker compose up -d --no-deps --force-recreate api ui

# Health check
curl -X GET localhost:8000/api/v1/health
```

## Architecture Overview

### High-Level System Architecture

Dograh is a voice AI platform with three main components:

1. **Backend (api/)** - FastAPI service handling business logic, database, and voice pipeline orchestration
2. **Frontend (ui/)** - Next.js application with drag-and-drop workflow builder
3. **Infrastructure** - PostgreSQL, Redis (task queue), MinIO (S3-compatible storage)

### Key Subsystems

#### Voice Pipeline Runtime (api/services/pipecat/)

The heart of the live voice call execution. Powered by the pipecat framework (git submodule):

- `run_pipeline.py` - Main pipeline orchestration and lifecycle
- `pipeline_builder.py` - Constructs pipecat pipeline from workflow definition
- `service_factory.py` - Creates LLM/TTS/STT service instances based on configuration
- `event_handlers.py` - Processes pipeline events, handles state transitions
- `realtime/` - Provider-specific implementations for realtime voice (OpenAI, Gemini, Ultravox, etc.)

The pipeline converts a workflow graph (nodes + edges) into a live voice conversation with dynamic node transitions.

#### Workflow System (api/services/workflow/)

Defines the workflow graph structure and execution model:

- `dto.py` - Core workflow data models (RFNodeDTO, RFEdgeDTO, ReactFlowDTO)
- `workflow_graph.py` - Graph traversal, validation, and constraint checking
- `node_specs/` - Node type definitions and specifications
- `pipecat_engine.py` - Bridge between workflow nodes and pipecat pipeline
- `pipecat_engine_callbacks.py` - Handles node transitions during calls
- `text_chat_runner.py` - Text-based workflow execution (non-voice)

Each workflow is a directed graph where nodes represent conversation states (greeting, qualification, etc.) and edges represent transitions with conditions.

#### Telephony System (api/services/telephony/)

Provider abstraction for phone/SIP integration:

- `base.py` - Abstract telephony provider interface
- `factory.py` - Provider instantiation and registry
- `providers/` - Concrete implementations (Twilio, Telnyx, Vonage, ARI, etc.)
  - Each provider has: `provider.py`, `transport.py`, `routes.py`, `config.py`, `serializers.py`
- `call_transfer_manager.py` - Handles call transfer coordination

Telephony providers are self-contained packages. See `api/services/telephony/providers/AGENTS.md`.

#### Integration System (api/services/integrations/)

Plugin architecture for third-party integrations (Tuner, MCP tools, etc.):

- `registry.py` - Central registration of integration nodes
- `loader.py` - Auto-discovers and imports integration packages
- `base.py` - Base classes for integration lifecycle hooks
- Each integration package: `node.py`, `runtime.py`, `completion.py`, `routes.py`

Integrations self-register via `register_package()`. See `api/services/integrations/AGENTS.md`.

#### Campaign System (api/services/campaign/)

Manages bulk outbound calling:

- `campaign_orchestrator.py` - Coordinates campaign execution
- `campaign_call_dispatcher.py` - Dispatches individual calls
- `source_sync.py` - Syncs contact lists from CSV/integrations
- `rate_limiter.py` + `circuit_breaker.py` - Call pacing and failure protection

#### Background Tasks (api/tasks/)

ARQ-based async job processing:

- `arq.py` - Task queue setup
- `run_integrations.py` - Post-call integration delivery (webhooks, QA, etc.)
- `campaign_tasks.py` - Campaign-related background work
- `knowledge_base_processing.py` - Document embedding and vectorization
- `s3_upload.py` - Async file uploads to MinIO/S3

### Data Flow

**Inbound Call:**
1. Telephony provider webhook → `routes/telephony.py`
2. Resolve workflow configuration
3. `services/pipecat/run_pipeline.py` creates pipeline
4. Live conversation executes via pipecat
5. `event_handlers.py` captures events and transitions
6. On completion → ARQ task → `tasks/run_integrations.py`

**Outbound Call:**
1. User triggers workflow run via UI or API
2. Campaign orchestrator or direct trigger
3. Telephony provider initiates call
4. Same pipeline execution as inbound
5. Post-call processing via background tasks

**Workflow Editing:**
1. UI sends ReactFlowDTO to `routes/workflow.py`
2. Validation in `services/workflow/dto.py`
3. Persisted to `workflow_run.workflow_definition` (pinned snapshot)
4. Runtime loads pinned definition, not live workflow

### Critical Concepts

#### Organization Scoping (Security)

**Every database query for organization-scoped resources MUST filter by `organization_id`**. This is tenant isolation:

- Reading: Always pass `organization_id=user.selected_organization_id` to DB client
- Writing foreign keys: Validate referenced resource belongs to user's org (e.g., setting `inbound_workflow_id` on phone number)
- Never trust IDs from request body to imply ownership

Missing org checks allow cross-tenant data access.

#### Cross-Worker State Sync

With multiple FastAPI workers, in-memory state updates (cached credentials, config) only affect one worker. Use `WorkerSyncManager` (`services/worker_sync/`) to broadcast via Redis pub/sub.

#### Workflow Definition Versioning

Workflows have a "live" editable version and "pinned" execution versions:

- Each workflow run captures `workflow_definition` as immutable snapshot
- Runtime always loads the pinned definition from the run
- This ensures deterministic replay and prevents mid-call changes

#### Sensitive Fields and Masking

Integration nodes can declare `sensitive_fields` in their registration. The masking system (`services/configuration/masking.py`) replaces secrets with `MASKED_*` placeholders on read and preserves original values on round-trip save.

#### Pipecat Submodule

The `pipecat/` directory is a git submodule pointing to `dograh-hq/pipecat`. Changes to pipecat should be made in that repository, not here.

```bash
# Update pipecat to latest
cd pipecat && git pull origin main && cd ..
git add pipecat && git commit -m "chore: update pipecat submodule"
```

## Testing Strategy

### Test Environment Isolation

**CRITICAL**: Tests must use `api/.env.test`, never `api/.env`:

```bash
# Correct - uses test DB
set -a && source api/.env.test && set +a && python -m pytest api/tests/...

# Wrong - uses dev/prod DB
set -a && source api/.env && set +a && python -m pytest api/tests/...  # DON'T DO THIS
```

`api/.env.test` points to a separate test database to avoid polluting development data.

### Test Organization

- `api/tests/` - Backend tests
  - `conftest.py` - Shared fixtures (test client, async DB, mock services)
  - `test_*.py` - Test files named by feature/module
  - `integrations/` - Integration test helpers
  - `telephony/` - Provider-specific tests
  - `dto_fixtures/` - Sample workflow JSON files

Tests use pytest with async support (`asyncio_mode = auto`).

### Common Test Patterns

**Database tests:** Use the `async_db` fixture which provides a clean DB session per test.

**API endpoint tests:** Use `async_client` fixture:

```python
async def test_create_workflow(async_client, user_fixture):
    response = await async_client.post("/api/v1/workflows", json={...})
    assert response.status_code == 200
```

**Pipeline tests:** Mock pipecat components and verify event sequences.

## MCP Server

Dograh exposes an MCP (Model Context Protocol) server at `api/mcp_server/`:

- `server.py` - MCP server implementation
- `tools/` - MCP tool definitions (create workflow, save workflow, docs search, etc.)
- `ts_validator/` - TypeScript validator for workflow schemas
- `auth.py` - MCP authentication

The MCP server allows AI assistants (Claude, etc.) to interact with Dograh programmatically.

## SDK Development

Two SDKs are auto-generated from the OpenAPI spec:

- `sdk/python/` - Python SDK
- `sdk/typescript/` - TypeScript SDK

Both provide typed workflow builders. Generate after API changes:

```bash
bash scripts/generate_sdk.sh
```

The SDK validates node fields against fetched node-type specs at runtime.

## Deployment Modes

- **Local Development** - `docker-compose-local.yaml` (services only) + local backend/frontend
- **Docker OSS** - `docker-compose.yaml` (full stack in containers)
- **Remote Server** - `scripts/setup_remote.sh` for production deployment
- **Rolling Updates** - `scripts/rolling_update.sh` for zero-downtime deploys on VM

Current Docker deployment uses blue-green bands with nginx upstream switching.

## Git Submodule

Pipecat is a git submodule. After cloning:

```bash
git submodule update --init --recursive
```

Update pipecat:

```bash
cd pipecat && git pull origin main && cd ..
git add pipecat && git commit -m "chore: update pipecat"
```

## Routes vs Service Layer

**Keep route handlers thin.** Route responsibilities:

- Parse/validate request (Pydantic schemas)
- Extract auth + `organization_id`
- Delegate to service layer
- Shape response

Business logic, orchestration, external calls, and DB access belong in `services/` and `db/`, not in route handlers.

## Node Spec System

Workflow nodes have both:

1. **Pydantic model** - Python data class with validation
2. **NodeSpec** - JSON schema for UI/external consumption

Integration nodes use `@node_spec` decorator + `spec_field()` to generate specs from models. Built-in nodes have specs in `services/workflow/node_specs/`.

Specs are served at `/api/v1/node-types` for the workflow builder UI.

## Adding a New Telephony Provider

1. Create package in `api/services/telephony/providers/<name>/`
2. Implement: `provider.py`, `transport.py`, `config.py`, `serializers.py`, `routes.py`
3. Register in telephony provider registry
4. Add enum value in `api/enums.py`
5. Update UI provider selection
6. Add tests in `api/tests/telephony/<name>/`

See existing providers (Twilio, Telnyx) as reference.

## Adding a New Integration

1. Create package in `api/services/integrations/<name>/`
2. Define node model with `@node_spec` and `spec_field()`
3. Implement optional lifecycle hooks: `runtime.py`, `completion.py`, `routes.py`
4. Call `register_package()` in `__init__.py`
5. Add tests for node validation, spec generation, and completion handler

Auto-discovery handles registration. See `api/services/integrations/AGENTS.md`.

## Configuration Resolution

Service configurations (LLM, TTS, STT) follow a hierarchy:

1. Node-level config (highest priority)
2. Global node config
3. Organization defaults
4. System defaults (lowest priority)

Resolution happens in `services/configuration/resolve.py`. Provider-specific options live in `services/configuration/options/`.

## Background Task Patterns

ARQ tasks should be:

- **Idempotent** - Safe to retry on failure
- **Organization-scoped** - Always validate org access
- **Bounded** - Set reasonable timeouts
- **Logged** - Capture failures for debugging

Task functions are decorated with `@arq_function` and registered in `tasks/arq.py`.

## Pre-commit Hooks

The `scripts/pre_commit.sh` script runs:

- `ruff` formatting check
- `mypy` type checking
- Tests (optional, controlled by environment)

**Never use `--no-verify` when committing** unless explicitly required.

## Environment Variables

Key environment variables:

**Backend (api/.env):**
- `DATABASE_URL` - PostgreSQL connection
- `REDIS_URL` - Redis connection
- `S3_ENDPOINT` / `S3_ACCESS_KEY` / `S3_SECRET_KEY` - MinIO/S3
- `OSS_JWT_SECRET` - JWT signing
- `AUTH_PROVIDER` - Authentication provider (oss/stack)
- `DEPLOYMENT_MODE` - local/remote

**Frontend (ui/.env):**
- `NEXT_PUBLIC_BACKEND_API_ENDPOINT` - API base URL
- `NEXT_PUBLIC_STACK_PROJECT_ID` - Stack Auth project

## Frontend Conventions

### File Upload Pattern

Always use hidden `<input type="file">` with visible `<Button>` trigger via ref:

```tsx
const fileInputRef = useRef<HTMLInputElement>(null);
<input type="file" ref={fileInputRef} className="hidden" onChange={handleFile} />
<Button onClick={() => fileInputRef.current?.click()}>Upload</Button>
```

Never use visible native file inputs.

### Authenticated API Calls

Guard fetches with auth ready state:

```tsx
const { user, loading: authLoading } = useAuth();
const hasFetched = useRef(false);

useEffect(() => {
  if (authLoading || !user || hasFetched.current) return;
  hasFetched.current = true;
  fetchData();
}, [authLoading, user]);
```

### API Error Handling

Generated client returns `{ data, error }`. Always check `error`:

```tsx
const response = await someApiCall({ ... });
if (response.error) {
  setError(detailFromError(response.error, "Failed to do thing"));
  return;
}
// Use response.data
```

Use `detailFromError` from `@/lib/apiError` to normalize FastAPI error formats (string or array).

## Documentation

Mintlify docs are in `docs/`:

- `docs.json` - Navigation and configuration
- `*.mdx` - Documentation pages with frontmatter

Generate OpenAPI spec for docs:

```bash
python scripts/dump_docs_openapi.py
```

## Useful Debugging Paths

**Backend:**
- Logs in `logs/latest/` (when using `scripts/start_services_dev.sh`)
- Trace requests with `LOGURU_LEVEL=DEBUG`
- Check pipeline events in `workflow_run.logs` column

**Frontend:**
- React DevTools + Network tab
- Check console for API errors (remember `error.detail` can be array or string)
- Workflow validation errors shown in UI toast

**Database:**
```bash
# Connect to local dev DB
psql $DATABASE_URL

# Common queries
SELECT * FROM workflows WHERE organization_id = '...';
SELECT * FROM workflow_runs WHERE workflow_id = '...' ORDER BY created_at DESC LIMIT 10;
```
