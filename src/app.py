from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse
import asyncio
import time
from typing import List, Dict, Any
from contextlib import asynccontextmanager
import yaml

from .types import ChatCompletionRequest, ChatCompletionResponse, Job
from .config import global_config
from .registry import global_registry
from .queuing.scheduler import global_scheduler
from .routing import global_router
from .logging_json import logger_instance
from .errors import GatewayError

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger_instance.logger.info("Starting Local AI Orchestrator...")
    global_config.load_config()
    global_registry.load_providers_from_disk()
    await global_registry.detect_and_register_models()
    yield
    # Shutdown
    logger_instance.logger.info("Shutting down...")
    # Stop any active providers?
    # Scheduler might leave things running, but registry cleanup could happen here.

app = FastAPI(title="Local AI Orchestrator", lifespan=lifespan)

from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "active_model": global_scheduler.active_model_id,
        "active_provider": global_scheduler.active_provider_id,
        "registry_models": list(global_registry.model_map.keys())
    }

@app.get("/v1/models")
async def list_models():
    models = []
    # Real models
    for m_id, p_id in global_registry.model_map.items():
        models.append({
            "id": m_id,
            "object": "model",
            "owned_by": "local-ai-orchestrator",
            "permission": []
        })
    # Add routes as "models"?? OpenAI clients might need to see them to select them.
    routes = global_config.load_routes()
    for r_name in routes:
        models.append({
            "id": f"route:{r_name}",
            "object": "model",
            "owned_by": "local-ai-orchestrator-route",
            "permission": []
        })
    
    return {"object": "list", "data": models}

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    # 1. Resolve Route
    primary_model, route_name, fallback_models, fallback_triggers = global_router.resolve_model(request.model)
    
    # 2. Setup Loop for Fallback
    candidates = [primary_model] + fallback_models
    last_error = None
    attempts_log = []

    for i, model_id in enumerate(candidates):
        # Check if model exists in registry
        # If auto_refresh is on and missing, try refresh
        if model_id not in global_registry.model_map:
             if global_config.config.runtime.auto_refresh_on_miss:
                 # Check cooldown? Registry handles it
                 await global_registry.refresh()
        
        if model_id not in global_registry.model_map:
            # Skip this candidate if missing
            error_msg = f"Model {model_id} not found"
            attempts_log.append({"model": model_id, "error": error_msg})
            last_error = error_msg
            continue

        # Create Job
        job = Job(
            original_model_id=request.model,
            resolved_model_id=model_id,
            route_name=route_name,
            request=request, # Note: request.model is still original, provider adapter might need to patch it?
                             # Actually provider adapter usually ignores request.model or we should update it.
                             # Let's update it in a copy.
        )
        # Patch request model to actual resolved model for the provider
        job.request.model = model_id 

        await global_scheduler.enqueue_job(job)

        # Wait for completion
        # Efficient polling
        while job.status in ["pending", "running"]:
            await asyncio.sleep(0.1)
        
        if job.status == "completed" and job.response:
            return job.response
        else:
            # Error
            last_error = job.error
            norm_error = job.normalized_error or "other"
            attempts_log.append({
                "model": model_id, 
                "error": job.error, 
                "normalized": norm_error
            })
            
            # Check fallback conditions
            if i < len(candidates) - 1:
                if global_config.config.routing.enable_fallback and norm_error in fallback_triggers:
                    logger_instance.logger.warning(f"Fallback triggered: {norm_error} on {model_id}, trying next.")
                    continue
                else:
                    # Fallback not enabled or error not in triggers
                    break
            else:
                break
    
    # If we got here, all failed
    raise HTTPException(status_code=500, detail=f"Request failed. Attempts: {attempts_log}")

@app.post("/refresh")
async def refresh_registry():
    await global_registry.refresh()
    return {"status": "refreshed", "models": len(global_registry.model_map)}

# --- Admin / UI Endpoints ---

from fastapi.staticfiles import StaticFiles
import os

# Mount static files
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/dashboard", StaticFiles(directory=static_dir, html=True), name="static")

@app.get("/")
async def redirect_to_dashboard():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/dashboard")

@app.get("/health/config")
async def get_config():
    """Return current configuration for UI."""
    # Build provider cache from registry model_map
    provider_models = {}
    for m, p in global_registry.model_map.items():
        if p not in provider_models:
            provider_models[p] = []
        provider_models[p].append(m)

    return {
        "config": global_config.config.model_dump(),
        "routes": {k: v.model_dump() for k, v in global_config._routes.items()},
        "models": {k: v.model_dump() for k, v in global_config._models.items()},
        "providers": [
            {
                "id": p_id,
                "type": p.config.get("provider_type"),
                "status": "active" if p_id == global_scheduler.active_provider_id else "idle", # Simple status
                "managed": p.is_managed(),
                "models": provider_models.get(p_id, [])
            } 
            for p_id, p in global_registry.providers.items()
        ]
    }

@app.post("/health/config/routes")
async def update_routes(new_routes: Dict[str, Any]):
    """Update routes.yaml."""
    # Simplified: just overwrite the file
    try:
        with open("routes.yaml", "w") as f:
            yaml.dump({"routes": new_routes}, f)
        global_config.load_routes()
        return {"status": "updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/admin/providers/{provider_id}")
async def get_provider_config(provider_id: str):
    """Get raw YAML config for a provider."""
    # Security: validate provider_id to prevent path traversal
    if ".." in provider_id or "/" in provider_id:
        raise HTTPException(400, "Invalid provider ID")
    
    # We need to find the file. Current registry doesn't store filename map easily exposed.
    # We can scan the directory.
    providers_dir = global_config.config.providers.config_dir
    target_file = None
    
    if os.path.exists(providers_dir):
        for f in os.listdir(providers_dir):
            # Check if this file contains the provider_id? 
            # Or assume filename matches? The system loads all. 
            # Let's read and check ID.
            path = os.path.join(providers_dir, f)
            try:
                with open(path, 'r') as file:
                    content = file.read() # Read string first
                    data = yaml.safe_load(content)
                    if data.get("provider_id") == provider_id:
                        return JSONResponse(content=content, media_type="text/plain")
            except:
                continue
    
    raise HTTPException(404, "Provider config file not found")

@app.post("/admin/providers/{provider_id}")
async def save_provider_config(provider_id: str, request: Request):
    """Save raw YAML config."""
    if ".." in provider_id or "/" in provider_id:
         raise HTTPException(400, "Invalid ID")
         
    content = await request.body()
    yaml_text = content.decode("utf-8")
    
    # Validate YAML
    try:
        data = yaml.safe_load(yaml_text)
        if data.get("provider_id") != provider_id:
            raise HTTPException(400, "provider_id in YAML must match URL")
    except yaml.YAMLError:
        raise HTTPException(400, "Invalid YAML")

    # Determine filename
    # If exists, overwrite. If not, create new.
    providers_dir = global_config.config.providers.config_dir
    filename = f"{provider_id}.yaml"
    
    # Check if a different file already owns this ID? 
    # For now, simplistic approach: write to {provider_id}.yaml
    path = os.path.join(providers_dir, filename)
    
    with open(path, 'w') as f:
        f.write(yaml_text)
    
    return {"status": "saved"}

@app.get("/admin/logs")
async def get_logs(limit: int = 100):
    """Retrieve last N lines of logs."""
    log_file = os.path.join(global_config.config.logging.log_dir, "gateway.jsonl")
    if not os.path.exists(log_file):
        return {"logs": []}
    
    # Simple tail via python list
    # Not efficient for massive files but okay for v1
    try:
        with open(log_file, "r") as f:
            lines = f.readlines()
            return {"logs": lines[-limit:]}
    except Exception as e:
        logger_instance.logger.error(f"Error reading logs: {e}")
        return {"logs": []}
