import yaml
import os
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000

class RuntimeConfig(BaseModel):
    auto_refresh_on_miss: bool = True
    refresh_cooldown_seconds: int = 30
    request_timeout_seconds: int = 600

class RoutingConfig(BaseModel):
    enable_fallback: bool = True
    default_route_if_model_missing: Optional[str] = None
    max_fallback_attempts: int = 2

class ModelResourceConfig(BaseModel):
    cpu_usage: float = 0.0 # 0-100
    gpu_usage: float = 0.0 # 0-100
    vram_usage: float = 0.0 # 0-100 (Abstract units or percent)
    exclusive: bool = False # If true, runs alone

class ModelScoreConfig(BaseModel):
    base_priority: int = 0
    load_penalty: int = 0
    runtime_penalty: int = 0
    always_run_last: bool = False
    resources: ModelResourceConfig = Field(default_factory=ModelResourceConfig)

class SchedulingConfig(BaseModel):
    mode: str = "global_serial"
    pick_next_strategy: str = "score_then_age"
    aging_bonus_per_second: float = 0.01
    default_model_score: ModelScoreConfig = Field(default_factory=ModelScoreConfig)

class LoggingConfig(BaseModel):
    keep_last_n_requests_in_memory: int = 500
    log_dir: str = "logs"
    keep_days: int = 14

class ProvidersConfig(BaseModel):
    config_dir: str = "providers"

class AppConfig(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    scheduling: SchedulingConfig = Field(default_factory=SchedulingConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)

class RouteConfig(BaseModel):
    primary_model: str
    fallback_models: List[str] = []
    fallback_on: List[str] = []

class ConfigLoader:
    def __init__(self, config_path: str = "config.yaml", routes_path: str = "routes.yaml", models_path: str = "models.yaml"):
        self.config_path = config_path
        self.routes_path = routes_path
        self.models_path = models_path
        self._config: Optional[AppConfig] = None
        self._routes: Dict[str, RouteConfig] = {}
        self._models: Dict[str, ModelScoreConfig] = {}

    def load_config(self) -> AppConfig:
        if not os.path.exists(self.config_path):
             return AppConfig() # Defaults
        
        with open(self.config_path, 'r') as f:
            data = yaml.safe_load(f)
            self._config = AppConfig(**data)
        return self._config

    def load_routes(self) -> Dict[str, RouteConfig]:
        if not os.path.exists(self.routes_path):
            return {}
        
        with open(self.routes_path, 'r') as f:
            data = yaml.safe_load(f)
            routes_data = data.get('routes', {})
            self._routes = {k: RouteConfig(**v) for k, v in routes_data.items()}
        return self._routes

    def load_models(self) -> Dict[str, ModelScoreConfig]:
       if not os.path.exists(self.models_path):
           return {}
       
       with open(self.models_path, 'r') as f:
           data = yaml.safe_load(f)
           models_data = data.get('models', {})
           self._models = {k: ModelScoreConfig(**v) for k, v in models_data.items()}
       return self._models

    @property
    def config(self) -> AppConfig:
        if self._config is None:
            self.load_config()
        return self._config

global_config = ConfigLoader()
