# Runtime Configuration

The project now has one editable runtime configuration file:

```text
runtime/config.json
```

This file contains source lists, step settings, classification settings, and paper attach settings.

Secrets and machine-specific directories are not stored in JSON.

## Directory Layout

Directory locations are controlled by environment variables with hard-coded defaults:

```text
MODNEWS_RUNTIME_DIR     default: runtime/
MODNEWS_OUTPUT_DIR      default: output/
MODNEWS_PROCESS_DIR     default: var/process/
MODNEWS_CACHE_DIR       default: var/cache/
MODNEWS_AGENT_WORK_DIR  default: .agent_work/
```

Recommended meaning:

- `output/`: final user-facing outputs.
- `var/process/`: intermediate process files and checkpoints.
- `var/cache/`: reusable caches such as sqlite model caches and NewsNow cache.
- `.agent_work/`: Codex repair tasks, web extraction jobs, logs, and generated extractor candidates.
- `runtime/config.json`: editable runtime behavior.

API keys still come from environment variables such as `LLM_API_KEY`.

## Frontend

The WebUI "运行设置" page can edit runtime parameters that are safe to change at runtime. Directory paths are displayed read-only because they are deployment/environment concerns.

## Legacy Files

`runtime/source_config.json` is now a migration source only. Runtime code reads and writes `runtime/config.json`.

`config.example.json` and `config.bailian.example.json` no longer define paths. They are optional override examples for runtime behavior and model provider settings.
