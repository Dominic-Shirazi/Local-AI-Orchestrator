from typing import List, Dict
import logging
from .rules import ConcurrencyRule
from ..types import Job

logger = logging.getLogger(__name__)

class ConcurrencyManager:
    def __init__(self):
        self.rules: List[ConcurrencyRule] = []

    def add_rule(self, rule: ConcurrencyRule):
        self.rules.append(rule)
        logger.info(f"Added concurrency rule: {rule.name}")

    def can_run(self, job: Job, active_jobs: List[Job]) -> bool:
        """
        Checks if a job can run against ALL registered rules.
        If ANY rule says 'No', the job cannot run.
        """
        for rule in self.rules:
            if not rule.can_run(job, active_jobs):
                logger.debug(f"Job {job.job_id} blocked by rule: {rule.name}")
                return False
        return True
