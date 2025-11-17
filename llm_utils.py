from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from langchain_core.messages import BaseMessage

from telemetry.langsmith import LangSmithTracer

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


def _azure_deployment(task: str) -> Optional[str]:
    task_key = f"AZURE_OPENAI_DEPLOYMENT_{task.upper()}"
    return os.environ.get(task_key) or os.environ.get("AZURE_OPENAI_DEPLOYMENT") or os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME")


def _request_timeout() -> float:
    try:
        return float(os.environ.get("LLM_REQUEST_TIMEOUT", "120"))
    except ValueError:
        return 120.0


def build_chat_model(task: str = "general", *, temperature: Optional[float] = None):
    model_name = pick_model(task)
    temp = temperature if temperature is not None else float(os.environ.get("LLM_TEMPERATURE", "0.1"))
    base_url = os.environ.get("OPENAI_BASE_URL")
    timeout = _request_timeout()

    try:
        azure_api_key = os.environ.get("AZURE_OPENAI_API_KEY")
        azure_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
        azure_deployment = _azure_deployment(task)
        if azure_api_key and azure_endpoint and azure_deployment:
            from langchain_openai import AzureChatOpenAI

            chat = AzureChatOpenAI(
                azure_endpoint=azure_endpoint.rstrip("/"),
                api_key=azure_api_key,
                api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-06-01"),
                azure_deployment=azure_deployment,
                temperature=1.0,
                request_timeout=timeout,
            )
            return _instrument_chat_model(chat, task)

        from langchain_openai import ChatOpenAI

        chat = ChatOpenAI(
            model_name=model_name,
            temperature=temp,
            base_url=base_url,
            request_timeout=timeout,
        )
        return _instrument_chat_model(chat, task)
    except Exception:
        from langchain_community.chat_models import ChatOllama  # type: ignore

        num_ctx = int(os.environ.get("LLM_NUM_CTX", "8192"))
        ollama_host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
        chat = ChatOllama(
            model=model_name,
            temperature=temp,
            num_ctx=num_ctx,
            base_url=ollama_host,
        )
        return _instrument_chat_model(chat, task)


_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]+?)\s*```", re.DOTALL)


def _parse_json_snippet(snippet: str) -> Optional[Any]:
    try:
        return json.loads(snippet.strip())
    except json.JSONDecodeError:
        return None


def _slice_enclosed(text: str, opener: str, closer: str) -> Optional[str]:
    start = text.find(opener)
    end = text.rfind(closer)
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start : end + 1]


def extract_json_response(text: str) -> Optional[Any]:
    """
    Best-effort parser for LLM responses that may wrap JSON in prose or code fences.
    Returns the parsed object if successful, otherwise None.
    """
    if not text:
        return None
    stripped = text.strip()
    parsed = _parse_json_snippet(stripped)
    if parsed is not None:
        return parsed

    block_match = _JSON_BLOCK_RE.search(text)
    if block_match:
        parsed_block = _parse_json_snippet(block_match.group(1))
        if parsed_block is not None:
            return parsed_block

    for opener, closer in (("{", "}"), ("[", "]")):
        section = _slice_enclosed(text, opener, closer)
        if not section:
            continue
        parsed_section = _parse_json_snippet(section)
        if parsed_section is not None:
            return parsed_section

    return None


def _instrument_chat_model(chat, task: str):
    tracer = LangSmithTracer.current()
    if not tracer or not getattr(tracer, "enabled", False):
        return chat
    return _InstrumentedChat(chat, task, tracer)


class _InstrumentedChat:
    def __init__(self, chat, task: str, tracer: LangSmithTracer):
        self._chat = chat
        self._task = task
        self._tracer = tracer

    def invoke(self, messages: List[BaseMessage], **kwargs):
        tracer = self._tracer
        parent_run = tracer.current_run() if tracer else None
        llm_run = None
        if tracer:
            summary = _summarize_messages(messages)
            run_inputs = {"messages": summary, "model": getattr(self._chat, "model_name", getattr(self._chat, "model", "chat"))}
            if parent_run:
                llm_run = tracer.child_run(
                    parent_run,
                    name=f"llm:{self._task}",
                    run_type="llm",
                    inputs=run_inputs,
                )
            else:
                llm_run = tracer.start_run(
                    name=f"llm:{self._task}",
                    run_type="llm",
                    inputs=run_inputs,
                )
        try:
            response = self._chat.invoke(messages, **kwargs)
        except Exception as exc:
            if llm_run:
                tracer.end_run(llm_run, error=str(exc))
            raise
        if llm_run:
            outputs = {"text": str(getattr(response, "content", response))[:400]}
            usage = _extract_usage(response)
            if usage:
                outputs["token_usage"] = usage
            tracer.end_run(llm_run, outputs=outputs)
        return response

    def __getattr__(self, item):
        return getattr(self._chat, item)


def _summarize_messages(messages: List[BaseMessage], *, limit: int = 4, max_chars: int = 400) -> List[Dict[str, str]]:
    summary: List[Dict[str, str]] = []
    for msg in messages[-limit:]:
        content = msg.content
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, dict) and "text" in part:
                    text_parts.append(str(part["text"]))
                else:
                    text_parts.append(str(part))
            content = "\n".join(text_parts)
        text = str(content)[:max_chars]
        summary.append({"role": getattr(msg, "type", msg.__class__.__name__), "content": text})
    return summary


def _extract_usage(message: Any) -> Optional[Dict[str, Any]]:
    usage = getattr(message, "usage_metadata", None)
    if usage:
        return usage
    metadata = getattr(message, "response_metadata", {}) or {}
    token_usage = metadata.get("token_usage")
    if token_usage:
        return token_usage
    additional = getattr(message, "additional_kwargs", {}) or {}
    if "token_usage" in additional:
        return additional["token_usage"]
    return None
