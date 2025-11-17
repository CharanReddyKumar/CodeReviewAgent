# Using Azure OpenAI with the Agentic Reviewer

The reviewer can talk to Azure OpenAI instead of OpenAI/Ollama as long as you configure a deployment and set the relevant environment variables before running `agentic_reviewer.py`, the LangGraph app, or the FastAPI service.

## Required Azure settings

Create (or reuse) an Azure OpenAI resource and a chat completion deployment. For inexpensive experiments, Microsoft recommends `gpt-4o-mini` or `gpt-35-turbo` depending on availability in your region.

Take note of:
- The **endpoint URL** (e.g. `https://my-openai-resource.openai.azure.com`)
- The **API version** (e.g. `2024-06-01`)
- The **deployment name** (you assign this when creating the model)

## Environment variables

Set the following in your shell or `.env` file:

```
AZURE_OPENAI_API_KEY=<your azure key>
AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com
AZURE_OPENAI_API_VERSION=2024-06-01
AZURE_OPENAI_DEPLOYMENT=<default deployment name>
```

You can override the deployment on a per-task basis by exporting `AZURE_OPENAI_DEPLOYMENT_PLANNER`, `AZURE_OPENAI_DEPLOYMENT_CRITIC`, etc. (the suffix is the task name in uppercase).

With these variables set, the framework automatically instantiates `AzureChatOpenAI` for every agent. If the variables are missing it falls back to the standard OpenAI-compatible model configuration or your local Ollama host.
