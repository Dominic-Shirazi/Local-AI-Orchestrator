import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Deque
from collections import deque
from .config import global_config

class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name
        }
        if hasattr(record, "props"):
             log_record.update(record.props)
        return json.dumps(log_record)

class RequestLogger:
    def __init__(self):
        self.logger = logging.getLogger("gateway")
        self.logger.setLevel(logging.INFO)
        self.setup_handlers()
        
        # Memory buffer for recent requests
        self.memory_buffer: Deque[Dict[str, Any]] = deque(
            maxlen=global_config.config.logging.keep_last_n_requests_in_memory
        )

    def setup_handlers(self):
        log_dir = global_config.config.logging.log_dir
        os.makedirs(log_dir, exist_ok=True)
        
        # File handler (JSONL)
        file_handler = logging.FileHandler(os.path.join(log_dir, "gateway.jsonl"))
        file_handler.setFormatter(JsonFormatter())
        self.logger.addHandler(file_handler)
        
        # Console handler (Standard)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        self.logger.addHandler(console_handler)

    def log_request(self, job_id: str, props: Dict[str, Any]):
        """
        Log a completed request (success or error).
        """
        # Ensure timestamp is present
        if "timestamp" not in props:
             props["timestamp"] = datetime.now().isoformat()
        
        self.memory_buffer.append(props)
        
        # Log to file with extra properties
        self.logger.info(f"Request {job_id} completed", extra={"props": props})

    def get_recent_requests(self) -> list[Dict[str, Any]]:
        return list(self.memory_buffer)

logger_instance = RequestLogger()
