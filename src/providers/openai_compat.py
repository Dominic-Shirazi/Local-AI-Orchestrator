import httpx
from typing import List, Dict, Any
from .base import BaseProvider
from ..types import ChatCompletionRequest, ChatCompletionResponse
from ..errors import ProviderUnreachableError, ProviderTimeoutError, GatewayError
from ..process_manager import global_process_manager
import logging

logger = logging.getLogger(__name__)

class OpenAICompatProvider(BaseProvider):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.base_url = self.config["api"]["base_url"]
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=self.config["api"]["health"]["timeout_seconds"])

    async def health_check(self) -> bool:
        path = self.config["api"]["health"]["path"]
        try:
            response = await self.client.get(path)
            return response.status_code in self.config["api"]["health"]["success_codes"]
        except Exception:
            return False

    async def list_models(self) -> List[str]:
        # If declared_models is present, return it without querying
        declared = self.config["api"].get("models", {}).get("declared_models")
        if declared:
            return declared

        path = self.config["api"]["models"]["path"]
        try:
            response = await self.client.get(path)
            if response.status_code == 200:
                data = response.json()
                return [m["id"] for m in data["data"]]
            else:
                logger.error(f"Failed to list models for {self.provider_id}: {response.status_code}")
                return []
        except Exception as e:
            logger.error(f"Error listing models for {self.provider_id}: {e}")
            return []

    async def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        # Pass through locally, but we need to respect the provider's URL
        # We use a new client with the request specific timeout? 
        # Or just use the shared client? The shared client has short timeout for health.
        # Create a new client or request with proper timeout.
        
        # Note: request.model at this point is the model_id. 
        # OpenAI providers usually expect the model_id to match.

        url = f"{self.base_url}/v1/chat/completions"
        timeout = 600 # Default huge timeout, or from config
        
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    url,
                    json=request.model_dump(exclude_none=True),
                    headers={"Authorization": f"Bearer {os.environ.get('OPENAI_API_KEY', 'dummy')}"} 
                )
                if response.status_code != 200:
                    # TODO: Normalized errors based on status code
                    error_text = response.text
                    raise GatewayError(f"Provider error: {response.status_code} - {error_text}")
                
                return ChatCompletionResponse(**response.json())
        except httpx.ConnectError:
             raise ProviderUnreachableError(self.provider_id)
        except httpx.ReadTimeout:
             raise ProviderTimeoutError(self.provider_id)
        except GatewayError:
            raise
        except Exception as e:
             raise GatewayError(f"Unknown error: {e}")

    async def start(self) -> bool:
        if not self.is_managed():
            return True
        
        start_config = self.config["start"]
        return global_process_manager.start_process(
            self.provider_id,
            start_config["command"],
            start_config["args"],
            cwd=start_config.get("cwd"),
            env=start_config.get("env")
        )

    async def stop(self):
        if not self.is_managed():
            return
        
        method = self.config["stop"]["method"]
        if method == "terminate_process":
            global_process_manager.stop_process(self.provider_id)
        # TODO: Implement other stop methods if needed

import os
