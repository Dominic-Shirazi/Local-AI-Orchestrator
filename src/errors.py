class GatewayError(Exception):
    def __init__(self, message: str, normalized_code: str = "other"):
        super().__init__(message)
        self.normalized_code = normalized_code

class ProviderUnreachableError(GatewayError):
    def __init__(self, provider_id: str, detail: str = ""):
        super().__init__(f"Provider {provider_id} unreachable. {detail}", "unreachable")

class ProviderTimeoutError(GatewayError):
    def __init__(self, provider_id: str):
        super().__init__(f"Provider {provider_id} timed out.", "timeout")

class ModelNotFoundError(GatewayError):
    def __init__(self, model_id: str):
        super().__init__(f"Model {model_id} not found.", "other")

class ConfigError(GatewayError):
    def __init__(self, message: str):
        super().__init__(message, "other")

class OOMError(GatewayError):
    def __init__(self, provider_id: str):
        super().__init__(f"Provider {provider_id} OOM.", "oom")

class ContextLengthError(GatewayError):
    def __init__(self, provider_id: str):
        super().__init__(f"Provider {provider_id} exceeded context length.", "context_length")
