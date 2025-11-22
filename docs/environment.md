# Environment Configuration

The application expects a `.env` file in the project root. The default template (already generated) includes the following groups:

## Azure OpenAI

- `AZURE_OPENAI_ENDPOINT` – Base URL of your Azure OpenAI resource (no `/openai/deployments/...`).
- `AZURE_OPENAI_API_KEY` – Key from the Azure portal for the resource above.
- `AZURE_OPENAI_API_VERSION` – API version string (e.g. `2025-01-01-preview`).
- `AZURE_OPENAI_DEPLOYMENT*` – Name of the deployed model. Use task-specific overrides (e.g. `AZURE_OPENAI_DEPLOYMENT_PLANNER`) if you want different models per agent; leave blank to fall back to `AZURE_OPENAI_DEPLOYMENT`.

## LangSmith / LangChain tracing

- `LANGSMITH_API_KEY` / `LANGSMITH_PROJECT` – Enables automatic trace uploads. Optional `LANGSMITH_RUN_TAGS` and `LANGSMITH_RUN_NAME` help label runs.
- `LANGCHAIN_TRACING_V2`, `LANGCHAIN_ENDPOINT`, `LANGCHAIN_API_KEY` – Interop settings if you prefer LangChain’s tracing service.

## LLM controls / fallbacks

- `LLM_MODEL`, `CRITICAL_MODEL`, `PLANNER_MODEL`, etc. – Override default models when Azure settings are not present.
- `OLLAMA_HOST` – Local fallback endpoint if Azure credentials are missing.
- `LLM_REQUEST_TIMEOUT`, `LLM_TEMPERATURE`, `LLM_NUM_CTX` – Tuning knobs for `llm_utils.build_chat_model`.

## Repository settings

- `BEST_PRACTICES_DOCS` – Location of reference PDFs/Markdown used by `best_practices_docs.py`.
- `REFRESH_BEST_PRACTICES`, `REFRESH_ARTIFACTS`, `FORCE_ARTIFACTS` – Flags consumed by `review_runner` to control cache invalidation.

> **Tip:** keep secrets out of version control. Commit a `.env.example` if you need to share the structure without real keys.
