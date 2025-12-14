import asyncio
import time
import logging
from collections import deque
from typing import Dict, Deque, Optional
from datetime import datetime

from .config import global_config
from .types import Job, ChatCompletionResponse
from .registry import global_registry
from .logging_json import logger_instance
from .errors import GatewayError

logger = logging.getLogger(__name__)

class Scheduler:
    def __init__(self):
        self.queues: Dict[str, Deque[Job]] = {} # model_id -> deque[Job]
        self.active_model_id: Optional[str] = None
        self.active_provider_id: Optional[str] = None
        self.global_lock = asyncio.Lock()
        self.processing_task: Optional[asyncio.Task] = None

    async def enqueue_job(self, job: Job):
        if job.resolved_model_id not in self.queues:
            self.queues[job.resolved_model_id] = deque()
        
        self.queues[job.resolved_model_id].append(job)
        logger.info(f"Job {job.job_id} enqueued for {job.resolved_model_id}")
        
        # Trigger processing loop if not running
        if not self.processing_task or self.processing_task.done():
             self.processing_task = asyncio.create_task(self.process_queue())

    async def process_queue(self):
        async with self.global_lock:
            while True:
                # 1. Determine active model (keep current if has jobs, else switch)
                if not self.active_model_id or not self.queues.get(self.active_model_id):
                    self.active_model_id = self.pick_next_model()
                
                if not self.active_model_id:
                    # No work left
                    self.active_provider_id = None
                    return

                # 2. Get next job
                queue = self.queues[self.active_model_id]
                if not queue:
                    continue
                
                job = queue[0] # Peek

                # 3. Resolve provider
                provider = global_registry.get_provider_for_model(self.active_model_id)
                if not provider:
                    job.status = "error"
                    job.error = f"No provider for model {self.active_model_id}"
                    queue.popleft()
                    # We can't complete the future here easily as it's not stored in Job, 
                    # but the App waits on polling or event. 
                    # Ideally Job should have an asyncio.Future or we loop in App.
                    # For simplicity, we'll assume the App polls job status or we add an event to Job.
                    continue

                # 4. Switch Provider if needed
                if self.active_provider_id != provider.provider_id:
                    logger.info(f"Switching provider from {self.active_provider_id} to {provider.provider_id}")
                    if self.active_provider_id:
                        prev_provider = global_registry.providers.get(self.active_provider_id)
                        if prev_provider:
                            await prev_provider.stop()
                    
                    self.active_provider_id = provider.provider_id
                    if not await provider.health_check():
                         logger.info(f"Starting provider {provider.provider_id}")
                         await provider.start()
                         # Wait for clean startup? Start should handle it or we poll health here.
                         await asyncio.sleep(2) # Grace
                         if not await provider.health_check():
                             job.status = "error"
                             job.error = "Provider failed to start"
                             queue.popleft()
                             continue

                # 5. Execute Job
                job.status = "running"
                job.provider_id = provider.provider_id
                start_time = time.time()
                
                try:
                    logger.info(f"Executing job {job.job_id} on {self.active_model_id}")
                    response = await provider.chat_completion(job.request)
                    job.response = response
                    job.status = "completed"
                except Exception as e:
                    logger.error(f"Job {job.job_id} failed: {e}")
                    job.status = "error"
                    job.error = str(e)
                    # Mapping to normalized error happens in caller or via exception type
                    if hasattr(e, "normalized_code"):
                         job.normalized_error = e.normalized_code
                finally:
                    runtime = (time.time() - start_time) * 1000
                    logger_instance.log_request(job.job_id, {
                        "job_id": job.job_id,
                        "model": job.resolved_model_id,
                        "provider": job.provider_id,
                        "status": job.status,
                        "runtime_ms": runtime,
                        "error": job.error
                    })
                    queue.popleft() # Remove done job


    def pick_next_model(self) -> Optional[str]:
        candidates = [m for m, q in self.queues.items() if q]
        if not candidates:
            return None
        
        # Scoring strategy implementation
        # For now, simple FIFO of models or just pick first
        # Implement the scoring logic from instructions later or roughly now.
        config = global_config.config.scheduling
        
        best_model = None
        best_score = -float('inf')

        now = time.time()

        for m in candidates:
             # Get overrides
             score_config = global_config.load_models().get(m, config.default_model_score)
             
             if score_config.always_run_last:
                 score = -1000
             else:
                 # Aging bonus
                 oldest_job = self.queues[m][0]
                 age = now - oldest_job.created_at
                 bonus = age * config.aging_bonus_per_second
                 
                 score = score_config.base_priority - score_config.load_penalty + bonus
             
             if score > best_score:
                 best_score = score
                 best_model = m
        
        return best_model

global_scheduler = Scheduler()
