from typing import List, Dict, Optional
import logging
from .rules import ConcurrencyRule
from ..types import Job
from ..config import global_config

logger = logging.getLogger(__name__)

class ExclusiveModelRule(ConcurrencyRule):
    """
    Ensures that if an 'exclusive' model is running, nothing else runs.
    And if an 'exclusive' model wants to run, nothing else can be running.
    """
    @property
    def name(self) -> str:
        return "ExclusiveModelRule"
        
    def _is_exclusive(self, model_id: str) -> bool:
        # Load latest config for the model
        model_cfg = global_config.load_models().get(model_id)
        if model_cfg:
            return model_cfg.resources.exclusive
        return False

    def can_run(self, job: Job, active_jobs: List[Job]) -> bool:
        # 1. Check if the incoming job is exclusive
        if self._is_exclusive(job.resolved_model_id):
            if active_jobs:
                return False # Must wait for empty system
        
        # 2. Check if any currently running job is exclusive
        for active_job in active_jobs:
            if self._is_exclusive(active_job.resolved_model_id):
                return False # An exclusive job is already running
                
        return True

class ResourceLimitRule(ConcurrencyRule):
    """
    Ensures total filtered resource usage (CPU/GPU) does not exceed 100%.
    """
    @property
    def name(self) -> str:
        return "ResourceLimitRule"
    
    def _get_resources(self, model_id: str):
        model_cfg = global_config.load_models().get(model_id)
        if model_cfg:
            return model_cfg.resources
        # Return default 0 usage if not defined
        from ..config import ModelResourceConfig
        return ModelResourceConfig()

    def can_run(self, job: Job, active_jobs: List[Job]) -> bool:
        # Get Candidate Costs
        candidate_res = self._get_resources(job.resolved_model_id)
        
        # Sum Active Costs
        total_cpu = 0.0
        total_gpu = 0.0
        
        for active_job in active_jobs:
            res = self._get_resources(active_job.resolved_model_id)
            total_cpu += res.cpu_usage
            total_gpu += res.gpu_usage
            
        # Check Limits
        # If adding this job pushes us over 100 on any metric, block it.
        # (Using > 100.0 + epsilon for float safety, or just > 100)
        
        if (total_cpu + candidate_res.cpu_usage) > 100.0:
            logger.debug(f"Block: CPU limit would be exceeded ({total_cpu} + {candidate_res.cpu_usage} > 100)")
            return False
            
        if (total_gpu + candidate_res.gpu_usage) > 100.0:
            logger.debug(f"Block: GPU limit would be exceeded ({total_gpu} + {candidate_res.gpu_usage} > 100)")
            return False
            
        return True

class MaxConcurrencyRule(ConcurrencyRule):
    """
    Hard cap on total concurrent jobs.
    """
    def __init__(self, max_concurrent: int):
        self.max_concurrent = max_concurrent
        
    @property
    def name(self) -> str:
        return f"MaxConcurrencyRule({self.max_concurrent})"

    def can_run(self, job: Job, active_jobs: List[Job]) -> bool:
        return len(active_jobs) < self.max_concurrent
