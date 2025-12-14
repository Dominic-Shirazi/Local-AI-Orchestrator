# Local AI Orchestrator

**Your Central Hub for Local AI Intelligence.**

The **Local AI Orchestrator** is a powerful organization layer for your local AI API traffic. Think of it as the air traffic controller for your local LLMs (Ollama, LM Studio, llama.cpp, and more). It provides a **single, unified OpenAI-compatible endpoint** that intelligently routes your requests to the right model, spinning providers up and down automatically to ensure you never run out of VRAM.

**Why you want this:**
- **Run Multiple Automation Tasks**: Execute coding agents, chat bots, and summarizers simultaneously without conflict. The orchestrator queues them and switches models instantly.
- **Intelligent Resource Management**: Only one VRAM-heavy model runs at a time. The system automatically unloads idle models and loads the next one required.
- **Unified Front Door**: Point all your apps to `http://127.0.0.1:8000`. No more juggling port numbers (11434, 1234, 8080...).
- **Route Aliases**: Use stable names like `route:coding` or `route:chat`. If your primary model is down or overloaded, the system can automatically fall back to another model (local or cloud).
- **Plug-and-Play Extensibility**: Add any OpenAI-compatible provider (Groq, weak-to-strong-generalization rigs, custom RAG APIs) just by dropping a YAML file in the `providers/` folder.

## Setup

1.  **Install Python 3.11+**
2.  **Create Virtual Environment**:
    ```bash
    python -m venv venv
    .\venv\Scripts\activate
    ```
3.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

## Running the Gateway

```bash
python conductorAPI.py
```
Run `python conductorAPI.py` to start the server on `http://127.0.0.1:8000`.

## Configuration

- `config.yaml`: Main settings (port, logging, etc).
- `routes.yaml`: Define route aliases (e.g., `route:planner` -> `gemini-2.0-flash`).
- `models.yaml`: Override detailed scoring/priority for specific models.
- `providers/*.yaml`: Define your backend providers.

## Providers & Extensibility

**"Just a YAML file away."**

The system is designed to be fully extensible. Each "provider" is defined by a config file in the `providers/` directory. You can share these files like extensions.

### Built-in Support:
- **Ollama**: Auto-starts `ollama serve`.
- **llama.cpp**: Auto-starts internal server.
- **LM Studio**: Can auto-start via `lms` CLI (see `providers/lmstudio.yaml`).

### Adding a Custom Provider (e.g., Grok, specialized RAG API):
Create a file `providers/my_custom_api.yaml`:

```yaml
provider_id: "my_rag_api"
provider_type: "openai_compat"
api:
  base_url: "http://localhost:9090"
  health:
    method: "GET"
    path: "/health"
    success_codes: [200]
start:
  enabled: true
  command: "python"
  args: ["run_my_rag.py"]
```
The Orchestrator will now manage this process and route requests to it!