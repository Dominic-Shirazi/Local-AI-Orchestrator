import os
import yaml
import logging
import asyncio
from typing import Dict, List, Optional
from shutil import which

from .config import global_config
from .providers.base import BaseProvider
from .providers.ollama import OllamaProvider
from .providers.openai_compat import OpenAICompatProvider

logger = logging.getLogger(__name__)

class Registry:
    def __init__(self):
        self.providers: Dict[str, BaseProvider] = {}
        self.model_map: Dict[str, str] = {} # model_id -> provider_id
        self.last_refresh_timestamp: float = 0

    def load_providers_from_disk(self):
        providers_dir = global_config.config.providers.config_dir
        if not os.path.exists(providers_dir):
            logger.warning(f"Providers directory not found: {providers_dir}")
            return

        for filename in os.listdir(providers_dir):
            if filename.endswith(".yaml") or filename.endswith(".yml"):
                try:
                    with open(os.path.join(providers_dir, filename), 'r') as f:
                        config = yaml.safe_load(f)
                        self._register_provider(config)
                except Exception as e:
                    logger.error(f"Error loading provider config {filename}: {e}")

    def _register_provider(self, config: Dict):
        p_type = config.get("provider_type")
        p_id = config.get("provider_id")
        
        if not p_id:
             return

        provider = None
        if p_type == "ollama":
            provider = OllamaProvider(config)
        elif p_type == "openai_compat":
            provider = OpenAICompatProvider(config)
        else:
            logger.error(f"Unknown provider type {p_type} for {p_id}")
            return

        self.providers[p_id] = provider

    async def detect_and_register_models(self):
        self.model_map.clear()
        
        for p_id, provider in self.providers.items():
            logger.info(f"Probing provider {p_id}...")
            
            # Detect
            detect_method = provider.config.get("detect", {}).get("method", "none")
            
            if "path" in detect_method: # path_or_probe
                binary = provider.config.get("detect", {}).get("binary_name")
                if binary and not which(binary):
                     logger.info(f"Provider {p_id} binary {binary} not found in PATH.")
                     # If binary missing, skip trying to start it.
                     # But if it's external, we might still probe.
                     if provider.is_managed():
                         continue

            # Probe Health
            is_healthy = await provider.health_check()
            if not is_healthy and provider.is_managed():
                logger.info(f"Provider {p_id} not healthy, attempting start...")
                if await provider.start():
                    # Wait for grace period or poll health
                    grace = provider.config["start"].get("startup_grace_seconds", 5)
                    await asyncio.sleep(grace) 
                    is_healthy = await provider.health_check()
            
            if is_healthy:
                models = await provider.list_models()
                logger.info(f"Provider {p_id} healthy, found models: {models}")
                for m in models:
                    if m in self.model_map:
                        logger.warning(f"Duplicate model {m} found in {p_id}, ignoring (first winner: {self.model_map[m]})")
                    else:
                        self.model_map[m] = p_id
            
                # If managed and policy says don't keep warm, stop it after discovery?
                # Actually, discovery might be best done lazily or we stop after list.
                # For v1, let's stop it if it was started just for discovery?
                # Using the scheduler rules: "Provider switching must stop the prior..."
                # So here, we probably should leave it running OR stop it.
                # If we stop it, we save resources.
                if provider.is_managed() and not provider.config.get("policy", {}).get("keep_warm", False):
                     await provider.stop()
            else:
                 logger.warning(f"Provider {p_id} is not healthy.")

    async def refresh(self):
        now = asyncio.get_event_loop().time()
        # Cooldown check could go here or in app
        self.providers.clear()
        self.load_providers_from_disk()
        await self.detect_and_register_models()
        self.last_refresh_timestamp = now

    def get_provider_for_model(self, model_id: str) -> Optional[BaseProvider]:
        p_id = self.model_map.get(model_id)
        if p_id:
            return self.providers.get(p_id)
        return None

global_registry = Registry()
