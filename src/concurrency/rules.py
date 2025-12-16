from abc import ABC, abstractmethod
from typing import List, Dict, Any
from ..types import Job

class ConcurrencyRule(ABC):
    """
    Abstract base class for all concurrency rules.
    """
    
    @abstractmethod
    def can_run(self, job: Job, active_jobs: List[Job]) -> bool:
        """
        Determines if the 'job' can run alongside the currently 'active_jobs'.
        Returns True if allowed, False otherwise.
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name for this rule strategy."""
        pass
