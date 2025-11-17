from __future__ import annotations

import logging
import os
from typing import Optional


logger = logging.getLogger(__name__)

DEFAULT_MODEL = "llama3.1:8b"
MODEL_ALIASES = {
    "llama3.1:8b-instruct": "llama3.1:8b",
}
TASK_ENV_MAP = {
    "planner": "PLANNER_MODEL",
    "critic_draft": "CRITIC_MODEL",
    "critic_verifier": "VERIFIER_MODEL",
    "verifier": "VERIFIER_MODEL",
}


def _normalize_model_name(model_name: str) -> str:
    alias = MODEL_ALIASES.get(model_name)
    if alias:
        logger.debug("Normalizing Ollama model name from %s to %s", model_name, alias)
        return alias
    return model_name


def pick_model(task: str, severity: Optional[str] = None) -> str:
    env_key = TASK_ENV_MAP.get(task.lower())
    if env_key:
        model = os.environ.get(env_key)
        if model:
            return _normalize_model_name(model)
    if severity and severity.lower() in {"blocker", "high"}:
        override = os.environ.get("CRITICAL_MODEL")
        if override:
            return _normalize_model_name(override)
    return _normalize_model_name(os.environ.get("LLM_MODEL", DEFAULT_MODEL))


def build_chat_model(task: str = "general", *, temperature: Optional[float] = None):
    model_name = pick_model(task)
    temp = temperature if temperature is not None else float(os.environ.get("LLM_TEMPERATURE", "0.1"))
    base_url = os.environ.get("OPENAI_BASE_URL")

    try:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model_name=model_name,
            temperature=temp,
            base_url=base_url,
        )
    except Exception:
        from langchain_community.chat_models import ChatOllama  # type: ignore

        num_ctx = int(os.environ.get("LLM_NUM_CTX", "8192"))
        ollama_host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
        return ChatOllama(
            model=model_name,
            temperature=temp,
            num_ctx=num_ctx,
            base_url=ollama_host,
        )
