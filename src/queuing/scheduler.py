import asyncio
import time
import logging
from collections import deque
from typing import Dict, Deque, Optional, List, Set
from datetime import datetime

from ..config import global_config
from ..types import Job, ChatCompletionResponse
from ..registry import global_registry
from ..logging_json import logger_instance
from ..errors import GatewayError
from ..concurrency.manager import ConcurrencyManager
from ..concurrency.builtins import ExclusiveModelRule, ResourceLimitRule, MaxConcurrencyRule

logger = logging.getLogger(__name__)

class Scheduler:
    def __init__(self):
        self.queues: Dict[str, Deque[Job]] = {} # model_id -> deque[Job]
        self.active_jobs: List[Job] = [] # Jobs currently executing (awaiting response)
        
        # Concurrency & Logic
        self.concurrency_manager = ConcurrencyManager()
        self._setup_default_rules()
        
        self.processing_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        self._job_complete_event = asyncio.Event()
        self._new_job_event = asyncio.Event()

    def _setup_default_rules(self):
        # Add the standard rules
        self.concurrency_manager.add_rule(ExclusiveModelRule())
        self.concurrency_manager.add_rule(ResourceLimitRule())
        # Optional: Global concurrency limit (e.g., 10 concurrent requests max)
        self.concurrency_manager.add_rule(MaxConcurrencyRule(10))

    async def enqueue_job(self, job: Job):
        if job.resolved_model_id not in self.queues:
            self.queues[job.resolved_model_id] = deque()
        
        self.queues[job.resolved_model_id].append(job)
        logger.info(f"Job {job.job_id} enqueued for {job.resolved_model_id}")
        
        # Wake up processor
        self._new_job_event.set()
        
        # Ensure processor is running
        if not self.processing_task or self.processing_task.done():
            self.processing_task = asyncio.create_task(self.run_process_loop())

    async def run_process_loop(self):
        logger.info("Scheduler loop started.")
        while not self._shutdown_event.is_set():
            # Clear events so we can wait on them later
            self._new_job_event.clear()
            self._job_complete_event.clear()
            
            # 1. Try to schedule as many jobs as possible
            scheduled_count = await self._schedule_pending_jobs()
            
            # 2. If nothing happened and we have no active jobs, await new work
            if scheduled_count == 0 and not self.active_jobs:
                logger.debug("Scheduler idling, waiting for jobs...")
                await self._new_job_event.wait()
            elif scheduled_count == 0 and self.active_jobs:
                 # We have active jobs but couldn't schedule new ones (blocked by concurrency?)
                 # Wait for a job to finish OR a new job to arrive
                 done, pending = await asyncio.wait(
                     [self._job_complete_event.wait(), self._new_job_event.wait()],
                     return_when=asyncio.FIRST_COMPLETED
                 )

    async def _schedule_pending_jobs(self) -> int:
        """
        Iterates through queues and attempts to start jobs that pass checks.
        Returns number of jobs started.
        """
        started = 0
        
        # 1. Identify Candidate Models (Queues with items)
        candidate_models = [m for m, q in self.queues.items() if q]
        if not candidate_models:
            return 0

        # 2. Sort Candidates (Heuristics: "Sticky" - prefer models already running)
        # This implements the "runs empties THAT runtimes queue" logic via preference
        active_models = {j.resolved_model_id for j in self.active_jobs}
        
        def sort_key(model_id):
            # Primary: Is it already running? (Sticky) -> 0 (first)
            # Secondary: Priority Score -> -Score (descending)
            is_active = 0 if model_id in active_models else 1
            
            # Basic Score Lookup
            score_config = global_config.load_models().get(model_id, global_config.config.scheduling.default_model_score)
            prio = score_config.base_priority
            
            return (is_active, -prio)

        candidate_models.sort(key=sort_key)

        # 3. Try to schedule heads of queues
        # We loop multiple times or just once per pass. 
        # To fill available slots, we can loop until no job can be started or we hit a limit.
        for model_id in candidate_models:
            queue = self.queues[model_id]
            if not queue: 
                continue
                
            job = queue[0] # Peek
            
            # ASK THE GATES
            if self.concurrency_manager.can_run(job, self.active_jobs):
                # GO!
                queue.popleft() # Commit remove
                self.active_jobs.append(job)
                asyncio.create_task(self._execute_job(job))
                started += 1
            else:
                # Blocked. 
                # Optimization: Should we check the NEXT item in queue? 
                # Usually queues are FIFO, so if head is blocked, queue is blocked.
                pass
                
        return started

    async def _execute_job(self, job: Job):
        job.status = "running"
        start_time = time.time()
        provider = None
        
        try:
            # Resolve Provider (Just-In-Time)
            provider = global_registry.get_provider_for_model(job.resolved_model_id)
            if not provider:
                raise GatewayError(f"No provider found for {job.resolved_model_id}", 500)
            
            job.provider_id = provider.provider_id
            
            # Ensure Running
            # Note: We rely on the implicit assumption that if Concurrency said "OK", 
            # we are physically allowed to start.
            if not await provider.health_check():
                 logger.info(f"Starting provider {provider.provider_id} for job {job.job_id}")
                 await provider.start()
                 # Brief wait for warming
                 await asyncio.sleep(1)

            # Execution
            logger.info(f"Executing Job {job.job_id} on {job.resolved_model_id} (Concurrent: {len(self.active_jobs)})")
            response = await provider.chat_completion(job.request)
            job.response = response
            job.status = "completed"

        except Exception as e:
            logger.error(f"Job {job.job_id} execution failed: {e}")
            job.status = "error"
            job.error = str(e)
            if hasattr(e, "normalized_code"):
                job.normalized_error = e.normalized_code
        finally:
            # Cleanup
            active_duration = (time.time() - start_time) * 1000
            if job in self.active_jobs:
                self.active_jobs.remove(job)
            
            # Log
            logger_instance.log_request(job.job_id, {
                "job_id": job.job_id,
                "model": job.resolved_model_id,
                "provider": job.provider_id if provider else "none",
                "status": job.status,
                "runtime_ms": active_duration,
                "error": job.error
            })
            
            # Signal completion to loop
            self._job_complete_event.set()

global_scheduler = Scheduler()
