import httpx
from typing import List, Dict, Any
import time
from .base import BaseProvider
from ..types import ChatCompletionRequest, ChatCompletionResponse, Choice, ChatMessage, ChatCompletionUsage
from ..errors import ProviderUnreachableError, ProviderTimeoutError, GatewayError
from ..process_manager import global_process_manager
import logging
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)

class OllamaProvider(BaseProvider):
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
        path = self.config["api"]["models"]["path"]
        try:
            response = await self.client.get(path)
            if response.status_code == 200:
                data = response.json()
                # Ollama returns list of models in 'models' key
                return [m["name"] for m in data.get("models", [])]
            else:
                logger.error(f"Failed to list models for {self.provider_id}: {response.status_code}")
                return []
        except Exception as e:
            logger.error(f"Error listing models for {self.provider_id}: {e}")
            return []

    async def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        url = f"{self.base_url}/api/chat"
        timeout = 600
        
        # Translate OpenAI Request to Ollama Request
        ollama_req = {
            "model": request.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "top_p": request.top_p,
                "num_predict": request.max_tokens,
            }
        }
        # Remove None values
        ollama_req["options"] = {k: v for k, v in ollama_req["options"].items() if v is not None}

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=ollama_req)
                
                if response.status_code != 200:
                    raise GatewayError(f"Ollama error: {response.status_code} - {response.text}")
                
                ollama_res = response.json()
                
                # Translate Ollama Response to OpenAI Response
                return ChatCompletionResponse(
                    id=f"chatcmpl-{uuid.uuid4()}",
                    created=int(datetime.now().timestamp()),
                    model=request.model,
                    choices=[
                        Choice(
                            index=0,
                            message=ChatMessage(
                                role=ollama_res.get("message", {}).get("role", "assistant"),
                                content=ollama_res.get("message", {}).get("content", "")
                            ),
                            finish_reason="stop" if ollama_res.get("done") else "length"
                        )
                    ],
                    usage=ChatCompletionUsage(
                        prompt_tokens=ollama_res.get("prompt_eval_count", 0),
                        completion_tokens=ollama_res.get("eval_count", 0),
                        total_tokens=ollama_res.get("prompt_eval_count", 0) + ollama_res.get("eval_count", 0)
                    )
                )

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
