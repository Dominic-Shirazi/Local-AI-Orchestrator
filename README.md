# ConductorAPI

**Your Central Hub for Local AI Intelligence.**

![Screenshot of ConductorAPI](logs/Screenshot%202025-12-13%20182900.png)

The **ConductorAPI** is a powerful organization layer for your local AI API traffic. Think of it as the air traffic controller for your local AI runtimes (Ollama, LM Studio, llama.cpp, and more). It provides a **single, unified OpenAI-compatible endpoint** that intelligently routes your requests to the right model, spinning runtimes and models up and down automatically.

## Key Features

- **Advanced Concurrency Control**: Define "Levers" for your models.
    - **Exclusive Mode**: DeepSeek-67B runs? Everything else pauses.
    - **Resource Budgeting**: Assign CPU/GPU costs (e.g., "This model takes 30%"). Run multiple lightweight models simultaneously until the budget is full.
- **Unified Front Door**: Point all your apps to `http://127.0.0.1:8000`.
- **Intelligent Resource Management**: The system automatically unloads idle models to free up VRAM.
- **Route Aliases**: Use stable names like `route:coding` or `route:chat`.

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
Open your browser and navigate to `http://127.0.0.1:8000` to view the **Dashboard**.

## Configuration Logic

The system is controlled by three main YAML files in the root directory. They are heavily commented to help you get started.

### 1. `routes.yaml` (The "Phonebook")
Define aliases for your models.
```yaml
routes:
  daily_driver:
    primary_model: "gemma3:12b_it_qat"
    fallback_models: ["llama3"]
```

### 2. `models.yaml` (The "Rules")
Define how your models behave and importantly, their **Resource Usage**.
```yaml
models:
  "deepseek-coder:67b":
    base_priority: 10
    resources:
      exclusive: true   # Runs alone.
      vram_usage: 100.0

  "gemma3:12b":
    resources:
      cpu_usage: 20.0   # Runs nicely with others up to 100% total.
```

### 3. `config.yaml` (The "Brain")
Global settings for timeouts, logging, and default scheduling strategies.

## Providers & Extensibility

**"Just a YAML file away."**

Add any OpenAI-compatible provider (Groq, custom RAG APIs, etc) by dropping a YAML file in the `providers/` folder.

### Built-in Support:
- **Ollama**: Auto-starts `ollama serve`.
- **llama.cpp**: Auto-starts internal server.
- **LM Studio**: Can auto-start via `lms` CLI.