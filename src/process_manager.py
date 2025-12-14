import subprocess
import os
import signal
import time
import logging
import psutil
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)

class ProcessManager:
    def __init__(self):
        self.processes: Dict[str, subprocess.Popen] = {}

    def start_process(self, 
                      id: str, 
                      command: str, 
                      args: List[str], 
                      cwd: Optional[str] = None, 
                      env: Optional[Dict[str, str]] = None) -> bool:
        
        if id in self.processes:
            if self.is_running(id):
                logger.info(f"Process {id} already running.")
                return True
            else:
                self.stop_process(id) # Cleanup dead handle

        full_cmd = [command] + args
        logger.info(f"Starting process {id}: {' '.join(full_cmd)}")
        
        try:
            # Merge current env with provided env
            current_env = os.environ.copy()
            if env:
                current_env.update(env)

            # Use shell=False for security and better control, unless necessary
            # For windows, shell=True might be needed for some commands, but try False first.
            # However, for 'python' or 'ollama' it should be fine.
            process = subprocess.Popen(
                full_cmd,
                cwd=cwd,
                env=current_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
            )
            self.processes[id] = process
            return True
        except Exception as e:
            logger.error(f"Failed to start process {id}: {e}")
            return False

    def stop_process(self, id: str, force: bool = False):
        if id not in self.processes:
            return

        process = self.processes[id]
        if process.poll() is not None:
             del self.processes[id]
             return

        logger.info(f"Stopping process {id}...")
        try:
            if os.name == 'nt':
                # Windows: send CTRL_BREAK_EVENT or terminate
                # process.terminate() is usually enough
                process.terminate()
            else:
                process.terminate()
            
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning(f"Process {id} did not stop, killing...")
                process.kill()
                process.wait()
        except Exception as e:
            logger.error(f"Error stopping process {id}: {e}")
        
        # Cleanup
        if id in self.processes:
            del self.processes[id]

    def is_running(self, id: str) -> bool:
        if id not in self.processes:
            return False
        process = self.processes[id]
        return process.poll() is None

global_process_manager = ProcessManager()
