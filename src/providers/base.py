from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from ..types import ChatCompletionRequest, ChatCompletionResponse

class BaseProvider(ABC):
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.provider_id = config.get("provider_id")
        self.resource_group = config.get("resource_group", "local_gpu")

    @abstractmethod
    async def health_check(self) -> bool:
        pass

    @abstractmethod
    async def list_models(self) -> List[str]:
        pass

    @abstractmethod
    async def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        pass

    @abstractmethod
    async def start(self) -> bool:
        """
        Start the provider process if managed.
        Returns True if started or already running.
        """
        pass

    @abstractmethod
    async def stop(self):
        """
        Stop the provider process if managed.
        """
        pass
    
    def is_managed(self) -> bool:
        return self.config.get("start", {}).get("enabled", False)
