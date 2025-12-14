from typing import Tuple, List, Optional
from .config import global_config

class RouteResolver:
    def resolve_model(self, model_input: str) -> Tuple[str, str, List[str], List[str]]:
        """
        Resolves a model string (possibly a route) to:
        - resolved_model_id (primary)
        - route_name (or None)
        - fallback_models (list of IDs)
        - fallback_triggers (list of error codes)
        """
        if model_input.startswith("route:"):
            route_name = model_input[6:]
            routes = global_config.load_routes()
            route_config = routes.get(route_name)
            
            if route_config:
                return (
                    route_config.primary_model,
                    route_name,
                    route_config.fallback_models,
                    route_config.fallback_on
                )
            else:
                # Route not found, return input as model_id basically (will 404 later)
                return model_input, None, [], []
        else:
            # Direct model ID
            return model_input, None, [], []

global_router = RouteResolver()
