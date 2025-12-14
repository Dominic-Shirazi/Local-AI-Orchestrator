import uvicorn
import os
import yaml
from src.config import global_config

def main():
    # Load config early to get port
    config_path = "config.yaml"
    port = 8000
    host = "127.0.0.1"
    
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            data = yaml.safe_load(f)
            server = data.get("server", {})
            port = server.get("port", 8000)
            host = server.get("host", "127.0.0.1")

    print(f"Starting Gateway on {host}:{port}...")
    uvicorn.run("src.app:app", host=host, port=port, reload=False)

if __name__ == "__main__":
    main()
