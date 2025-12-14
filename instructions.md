# Local AI Orchestrator
Repo name suggestion: `local-ai-orchestrator` (GitHub style, lowercase). Display name: **Local AI Orchestrator**.
Alt names that also read instantly: `local-llm-orchestrator`, `local-model-gateway`, `openai-local-orchestrator`.

## 1. What this is
A local HTTP gateway that exposes **OpenAI compatible endpoints** and routes requests to **local AI providers** (Ollama, LM Studio, llama.cpp server). It enforces a strict scheduler so **only one local model runs at a time** in v1, to control VRAM usage.

It also supports **route aliases** and an **opt in fallback mechanism** so a request can fail over to another model (including optional cloud models) using the same endpoint.

Primary platform for v1 testing: Windows.
Code must be written to run on macOS and Linux as well.

## 2. v1 deliverables
### Must ship in v1
- OpenAI compatible endpoints:
  - GET `/v1/models`
  - POST `/v1/chat/completions`
- Local providers fully working:
  - Ollama server (gateway-managed process supported)
  - LM Studio server (gateway-managed process supported)
  - llama.cpp server (gateway-managed process supported)
  - Include Faster Whisper server/service (gateway-managed process supported) for audio transcription
- Route aliases + fallback mechanism implemented:
  - Client may call by explicit model ID or by route alias `route:<name>`
  - Fallback is opt in and configurable
- Cloud adapters optional and disabled by default:
  - Provide example cloud provider config
  - No cloud dependency required to run v1

### Designed for v2+
- Multi resource concurrency (local serial, cloud concurrent)
- VRAM budgeting and multi GPU packing
- Streaming responses
- Auto measurement of penalties (load and runtime)
- Model comparison test mode (runs one prompt, or set of prompts from a file, across multiple models and compares results)

## 3. Non goals for v1
- No UI
- No full auto discovery beyond simple PATH and port probing
- No streaming responses
- No embeddings endpoint required (nice later)


## 4. Repo layout
Keep repo root minimal.

Required:
- `run_gateway.py`
- `config.yaml`
- `providers/`            (provider configs)
- `routes.yaml`           (route aliases and fallback rules)
- `models.yaml`           (optional per model scoring overrides)
- `src/`                  (implementation)
- `logs/`                 (jsonl logs, rotated)

Suggested `src/` layout:
- `src/app.py`                    FastAPI app and routes
- `src/config.py`                 config load and validation
- `src/registry.py`               model registry
- `src/scheduler.py`              queues and scheduling
- `src/routing.py`                route aliases and fallback resolution
- `src/process_manager.py`        start stop health lifecycle
- `src/providers/base.py`         provider adapter interface
- `src/providers/ollama.py`       ollama adapter (translate OpenAI to Ollama)
- `src/providers/openai_compat.py` generic adapter for OpenAI compatible providers
- `src/logging_json.py`           JSON logging helpers
- `src/types.py`                  Pydantic request models and internal Job types
- `src/errors.py`                 normalized error codes for fallback triggers

## 5. Core concepts and contracts

### Provider
A Provider is a backend that can serve model requests over HTTP.
Provider responsibilities:
- Start (optional, if gateway-owned)
- Stop (optional, if gateway-owned)
- Health check
- List models (or provide declared models)
- Forward chat completions request and return response

Provider modes:
- Gateway-owned (gateway starts and stops the process)
- External (gateway never starts it, only probes and uses it if reachable)

### Model
A Model is identified by a string ID.
Clients reference models by ID only. Clients do not select provider.
Gateway maps model_id to provider_id.

### Route alias
A Route alias is a stable name like `route:local_default` that resolves to:
- A primary model_id
- A list of fallback model_ids
- Conditions that trigger fallback

### Job
A Job is one `/v1/chat/completions` request.
Jobs are queued per model FIFO.

### Scheduler
v1 scheduling is local-serial.
Rules:
- Only one local job executes at a time globally.
- One model becomes active.
- Active model queue drains FIFO until empty.
- New jobs for the active model append to that model queue and will be processed before switching models.
- When switching models, choose next model using a scoring policy (priority and penalties based on load and runtimes).
- Provider switching must stop the prior gateway-owned provider (if any) before starting the next, to free VRAM.

### Resource groups (v2 planning, minimal v1 hooks)
Each provider belongs to a resource group.
v1: all providers use resource group `local_gpu` except cloud which uses `cloud`.
v1 still executes globally serial, but store resource group so v2 can unlock concurrency.

## 6. Configuration

### 6.1 config.yaml (global)
Example schema:

server:
  host: "127.0.0.1"
  port: 8000

runtime:
  auto_refresh_on_miss: true
  refresh_cooldown_seconds: 30
  request_timeout_seconds: 600

routing:
  enable_fallback: true
  default_route_if_model_missing: null   # optional, keep null in v1
  max_fallback_attempts: 2

scheduling:
  mode: "global_serial"                  # v1 only
  pick_next_strategy: "score_then_age"
  aging_bonus_per_second: 0.01
  default_model_score:
    base_priority: 0
    load_penalty: 0
    runtime_penalty: 0
    always_run_last: false

logging:
  keep_last_n_requests_in_memory: 500
  log_dir: "logs"
  keep_days: 14

providers:
  config_dir: "providers"

### 6.2 providers/*.yaml
Provider config schema:

provider_id: "string"
provider_type: "ollama" | "openai_compat"
resource_group: "local_gpu" | "cloud"

api:
  base_url: "http://127.0.0.1:PORT"
  health:
    method: "GET"
    path: "/path"
    success_codes: [200]
    timeout_seconds: 2
  models:
    method: "GET"
    path: "/path"
    declared_models: []   # optional list, used when discovery is not possible

detect:
  method: "path_or_probe" | "probe_only" | "none"
  binary_name: "optional"
  probe_url: "optional full url"

start:
  enabled: true | false
  command: "string"
  args: ["list","of","strings"]
  cwd: null
  env: {}
  startup_grace_seconds: 20

stop:
  method: "terminate_process" | "kill_process" | "http_request" | "none"
  http:
    method: "POST"
    path: "/shutdown"

policy:
  keep_warm: false
  idle_shutdown_seconds: 60
  max_start_attempts: 2
  restart_on_failure: false

Notes:
- If start.enabled is false, gateway never starts the provider.
- If stop.method is none, gateway never stops the provider.
- For cloud providers in v1, use `declared_models` and disable discovery unless implemented.

### 6.3 models.yaml (optional)
Override scoring for specific model IDs:

models:
  "gemma3:12b_it_qat":
    base_priority: 2
    load_penalty: 6
    runtime_penalty: 4
    always_run_last: false
  "qwen2.5-coder-tools:7b":
    base_priority: 7
    load_penalty: 2
    runtime_penalty: 2
    always_run_last: false
  "chatterbox-tts":
    base_priority: -5
    load_penalty: 10
    runtime_penalty: 10
    always_run_last: true

### 6.4 routes.yaml (route aliases and fallback)
Schema:

routes:
  local_default:
    primary_model: "gemma3:12b_it_qat"
    fallback_models: ["gpt-4.1-mini"]    # cloud example, optional
    fallback_on: ["unreachable","timeout","oom","context_length"]
  planner:
    primary_model: "gemini-2.0-flash"
    fallback_models: ["gpt-4.1"]
    fallback_on: ["unreachable","timeout"]

Behavior:
- Client uses `model: "route:local_default"` in the OpenAI request.
- Gateway resolves to primary model and attempts it.
- If it fails with a normalized error in fallback_on and routing.enable_fallback is true, try next fallback model.
- Stop when success or max_fallback_attempts reached.

## 7. Provider templates and required example configs

### 7.1 providers/ollama.yaml (gateway-managed)
provider_id: "ollama_local"
provider_type: "ollama"
resource_group: "local_gpu"
api:
  base_url: "http://127.0.0.1:11434"
  health:
    method: "GET"
    path: "/api/tags"
    success_codes: [200]
    timeout_seconds: 2
  models:
    method: "GET"
    path: "/api/tags"
detect:
  method: "path_or_probe"
  binary_name: "ollama"
  probe_url: "http://127.0.0.1:11434/api/tags"
start:
  enabled: true
  command: "ollama"
  args: ["serve"]
  startup_grace_seconds: 20
stop:
  method: "terminate_process"
policy:
  keep_warm: false
  idle_shutdown_seconds: 60
  max_start_attempts: 2
  restart_on_failure: false

### 7.2 providers/lmstudio.yaml (external by default, OpenAI compatible)
provider_id: "lmstudio_local"
provider_type: "openai_compat"
resource_group: "local_gpu"
api:
  base_url: "http://127.0.0.1:1234"
  health:
    method: "GET"
    path: "/v1/models"
    success_codes: [200]
    timeout_seconds: 2
  models:
    method: "GET"
    path: "/v1/models"
detect:
  method: "probe_only"
  probe_url: "http://127.0.0.1:1234/v1/models"
start:
  enabled: false
stop:
  method: "none"
policy:
  keep_warm: true

### 7.3 providers/llama_cpp.yaml (gateway-managed, OpenAI compatible)
provider_id: "llamacpp_local"
provider_type: "openai_compat"
resource_group: "local_gpu"
api:
  base_url: "http://127.0.0.1:8001"
  health:
    method: "GET"
    path: "/v1/models"
    success_codes: [200]
    timeout_seconds: 2
  models:
    method: "GET"
    path: "/v1/models"
detect:
  method: "none"
start:
  enabled: true
  command: "python"
  args: ["-m","llama_cpp.server","--host","127.0.0.1","--port","8001","--model","REPLACE_WITH_MODEL_PATH"]
  startup_grace_seconds: 30
stop:
  method: "terminate_process"
policy:
  keep_warm: false
  idle_shutdown_seconds: 60
  max_start_attempts: 2
  restart_on_failure: false

### 7.4 providers/cloud_openai_example.yaml (optional, disabled by default)
provider_id: "openai_cloud"
provider_type: "openai_compat"
resource_group: "cloud"
api:
  base_url: "https://api.openai.com"
  health:
    method: "GET"
    path: "/v1/models"
    success_codes: [200]
    timeout_seconds: 5
  models:
    method: "GET"
    path: "/v1/models"
    declared_models: ["gpt-4.1-mini","gpt-4.1"]   # keep declared in v1 to avoid depending on cloud listing
detect:
  method: "none"
start:
  enabled: false
stop:
  method: "none"
policy:
  keep_warm: true

Auth handling requirement:
- Cloud adapters must support an API key via environment variable or config.yaml.
- Implement in v1 but keep disabled by default.
- If no key present and a cloud model is requested, fail with a clear error.

## 8. Registry behavior
On startup:
- Load provider configs.
- For each provider:
  - If detect.method includes PATH, check binary exists.
  - Probe health endpoint.
  - If not healthy and start.enabled is true, start it and wait for health.
  - If healthy, list models using provider api.models.
- Build mapping model_id -> provider_id.
- If duplicate model_id appears across providers:
  - If config.yaml defines provider precedence list, use it.
  - Else fail with a clear error and list duplicates.

Refresh:
- POST `/refresh` triggers a rebuild, obeying refresh cooldown.

Auto refresh on miss:
- If requested model_id not in registry and runtime.auto_refresh_on_miss is true:
  - If cooldown passed, refresh once, then re-check.
  - If still missing, return 404.

## 9. Scheduler details

### 9.1 Core data structures
- `queues`: dict model_id -> deque[Job]
- `active_model`: optional model_id
- `active_provider`: optional provider_id
- `global_execution_lock`: asyncio lock

Job fields:
- job_id
- request_id
- model_id (resolved model or route result)
- route_name (optional)
- provider_id (resolved)
- request_json (original OpenAI request)
- created_at
- attempt_index (for fallback)
- status, error
- response_json

### 9.2 Picking next model
When no active_model or its queue empty:
- candidates = all models with non-empty queue
- apply always_run_last rule
- compute score:
  base_priority - load_penalty - runtime_penalty + aging_bonus
  aging_bonus = (now - oldest_job_created_at) * aging_bonus_per_second
- pick highest score, tie break oldest job created_at
- set active_model and drain FIFO

### 9.3 Local provider switching
Before executing a job:
- Determine provider for the model_id.
- If provider differs from active_provider:
  - If active_provider is gateway-owned, stop it.
  - Start new provider if gateway-owned and not healthy.
  - Wait for healthcheck.
  - Set active_provider.

Then forward the request.

## 10. Routing and fallback behavior (v1)

### 10.1 Explicit model selection
If request.model does not start with `route:`:
- Treat it as a model_id.
- Resolve provider from registry.
- Enqueue job for that model_id.

### 10.2 Route alias selection
If request.model starts with `route:`:
- Resolve route name in routes.yaml.
- Use route.primary_model as model_id for the first attempt.
- Store route_name and fallback list in job metadata.

### 10.3 Normalized errors for fallback triggers
Implement error normalization.
Adapters must map provider failures into one of:
- unreachable
- timeout
- oom
- context_length
- other

Fallback triggers are matched against this normalized code.

### 10.4 Fallback algorithm
Only if routing.enable_fallback is true and route exists:
- Attempt primary model.
- If success, return response.
- If failure and normalized_error in route.fallback_on:
  - Attempt next fallback model in order until:
    - success, or
    - attempts exhausted, or
    - max_fallback_attempts reached
- If all fail, return the last error, including a structured list of attempted models and normalized errors.

Important:
- Fallback must never happen silently unless client used a route alias.
- If client requested an explicit model_id, do not auto fallback unless a separate config flag is enabled (keep it false in v1).

## 11. OpenAI compatible endpoints

### 11.1 GET /health
Return:
- ok status
- active_provider, active_model
- queue sizes summary (top N)
- registry timestamp
- provider statuses (healthy, owned, last_error)

### 11.2 GET /v1/models
Return OpenAI list format:
{
  "object": "list",
  "data": [
    { "id": "model_id", "object": "model", "owned_by": "local-ai-orchestrator" }
  ]
}

Return only model IDs. Do not expose provider IDs here.

### 11.3 POST /v1/chat/completions
Supported fields:
- model (required)
- messages (required)
- temperature, top_p, max_tokens (optional)
- stream (optional, if true return 501 in v1)

Behavior:
- Convert request to internal job.
- Enqueue and await completion.
- Return OpenAI chat completion response format.

Adapters:
- OpenAI compatible provider: pass through to provider `/v1/chat/completions`.
- Ollama provider: translate OpenAI chat completion request to Ollama `/api/chat`, then translate response back.

### 11.4 POST /refresh
Rebuild registry, obey cooldown, return summary:
- provider count
- model count
- duplicates if any
- timestamp

### 11.5 Admin endpoints (v1)
- GET `/admin/providers`
  - list providers with detected, healthy, owned, last_error
- GET `/admin/registry`
  - list model_id to provider_id mapping for debugging

## 12. Ollama translation rules (v1)
Request mapping:
- OpenAI: model, messages, temperature, top_p, max_tokens
- Ollama /api/chat:
  - model: same
  - messages: same roles and content
  - stream: false
  - options:
    - temperature
    - top_p
    - num_predict = max_tokens

Response mapping:
- Convert Ollama response to OpenAI chat completion response with:
  - choices[0].message.role = "assistant"
  - choices[0].message.content = assistant content
  - finish_reason best effort else "stop"

## 13. Logging
- Write JSON lines to `logs/gateway.jsonl`.
- Rotate daily or by size, keep keep_days.
- Maintain in-memory ring buffer of last N requests for debugging endpoints.

Each log record includes:
- request_id, job_id
- model, provider_id, route_name
- queue_wait_ms, runtime_ms
- status success or error
- normalized_error if error
- attempts list if route fallback used

## 14. Setup guidance (README requirements)
README must include:
- Install Python 3.11+
- Create venv and install requirements
- How to run gateway
- How to configure providers
- How to enable LM Studio server and set its port
- How to set llama.cpp server model path
- How to keep cloud disabled by default, and how to enable by adding key env var

## 15. Acceptance tests (manual)
1) Start gateway, call GET `/v1/models`, models list returns Ollama models when Ollama is installed.
2) Call POST `/v1/chat/completions` using an Ollama model, receive valid OpenAI style response.
3) Queue behavior:
   - enqueue 2 jobs for model A, then 1 for model B
   - scheduler drains A jobs FIFO before running B
   - if new job for A arrives while A active, it appends and runs before switching to B
4) Route fallback:
   - create a route alias with primary local model and fallback cloud model
   - simulate primary failure (stop provider or use invalid model)
   - gateway attempts fallback and returns response, with attempts reported
5) Provider switching:
   - request model on provider P1, then model on provider P2
   - gateway stops owned P1 and starts owned P2, confirmed by logs

## 16. v2 planning notes (do not implement in v1)
- Resource-group concurrency:
  - local_gpu serial
  - cloud concurrent with configurable max concurrency
- VRAM budget:
  - model metadata includes estimated VRAM
  - scheduler chooses a feasible set of concurrently loaded models
- Streaming:
  - support stream true for OpenAI style streaming
- Auto tuning:
  - record load time and runtime per model
  - update penalties automatically
- Test mode:
  - endpoint to run same prompt(s) across multiple models within one provider (ollama, llama.cpp, lmstudio, faster whisper, chatterbox-tts-server, others tbd) and return comparison report
