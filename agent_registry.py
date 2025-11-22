from __future__ import annotations

import importlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

REGISTRY_DIR = Path("mongo") / "agents_registry"
LANGUAGE_EXTENSION_MAP = {
    "python": [".py"],
    "javascript": [".js", ".cjs", ".mjs", ".jsx"],
    "typescript": [".ts", ".tsx"],
    "java": [".java"],
    "go": [".go"],
    "ruby": [".rb"],
    "php": [".php", ".phtml", ".php5"],
    "c": [".c"],
    "cpp": [".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx", ".h"],
    "csharp": [".cs"],
    "rust": [".rs"],
    "kotlin": [".kt", ".kts"],
    "swift": [".swift"],
    "scala": [".scala"],
    "dart": [".dart"],
    "shell": [".sh", ".bash", ".zsh"],
    "powershell": [".ps1", ".psm1"],
    "objective-c": [".m", ".mm"],
    "solidity": [".sol"],
    "sql": [".sql"],
    "elixir": [".ex", ".exs"],
    "clojure": [".clj", ".cljs", ".cljc"],
    "haskell": [".hs"],
    "lua": [".lua"],
    "perl": [".pl", ".pm"],
    "r": [".r"],
    "groovy": [".groovy"],
    "erlang": [".erl"],
    "fsharp": [".fs", ".fsx"],
    "vbnet": [".vb"],
    "terraform": [".tf", ".tfvars"],
    "html": [".html", ".htm"],
    "css": [".css", ".scss", ".sass"],
}
IGNORE_DIRS = {".git", ".hg", ".svn", ".venv", "__pycache__", "node_modules"}


@dataclass
class AgentSpec:
    id: str
    languages: List[str]
    scope: str
    kind: str
    module: Optional[str]
    class_name: Optional[str]
    enabled: bool = True
    implemented: bool = True
    description: str = ""
    init_kwargs: Dict[str, Any] = field(default_factory=dict)


_REGISTRY_CACHE: Optional[List[AgentSpec]] = None


def _load_specs() -> List[AgentSpec]:
    global _REGISTRY_CACHE
    if _REGISTRY_CACHE is not None:
        return _REGISTRY_CACHE

    specs: List[AgentSpec] = []
    if not REGISTRY_DIR.exists():
        logger.warning("Agent registry directory %s not found.", REGISTRY_DIR)
        _REGISTRY_CACHE = specs
        return specs

    for path in sorted(REGISTRY_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            spec = AgentSpec(
                id=data["id"],
                languages=data.get("languages", []),
                scope=data.get("scope", "repo"),
                kind=data.get("kind", "tool"),
                module=data.get("module"),
                class_name=data.get("class_name"),
                enabled=data.get("enabled", True),
                implemented=data.get("implemented", True),
                description=data.get("description", ""),
                init_kwargs=data.get("init_kwargs", {}) or {},
            )
            specs.append(spec)
        except Exception as exc:
            logger.error("Failed to load agent spec %s: %s", path, exc)
    _REGISTRY_CACHE = specs
    return specs


def detect_languages(repo_path: Path) -> List[str]:
    repo_path = Path(repo_path)
    detected: set[str] = set()
    if not repo_path.exists():
        return ["python"]

    for path in repo_path.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORE_DIRS for part in path.parts):
            continue
        ext = path.suffix.lower()
        for language, extensions in LANGUAGE_EXTENSION_MAP.items():
            if ext in extensions:
                detected.add(language)
    if not detected:
        detected.add("python")
    return sorted(detected)


def _resolve_kwargs(raw_kwargs: Dict[str, Any], repo_reference: str, repo_path: Path) -> Dict[str, Any]:
    resolved: Dict[str, Any] = {}
    placeholders = {
        "__REPO_PATH__": Path(repo_path),
        "__REPO_REFERENCE__": repo_reference,
    }
    for key, value in raw_kwargs.items():
        if isinstance(value, str) and value in placeholders:
            resolved[key] = placeholders[value]
        else:
            resolved[key] = value
    return resolved


def get_tool_specs(languages: List[str], scope: Optional[str] = None) -> List[AgentSpec]:
    requested = {lang.lower() for lang in languages}
    matches: List[AgentSpec] = []
    for spec in _load_specs():
        if spec.kind.lower() != "tool":
            continue
        spec_languages = {lang.lower() for lang in spec.languages}
        if not spec_languages & requested:
            continue
        if scope and spec.scope != scope:
            continue
        matches.append(spec)
    return matches


def instantiate_tools(
    languages: List[str],
    scope: str,
    repo_reference: str,
    repo_path: Path,
) -> List[Any]:
    instances: List[Any] = []

    for spec in get_tool_specs(languages, scope=scope):
        if not spec.enabled:
            continue
        if not spec.implemented:
            logger.info("Agent '%s' is not implemented yet; skipping.", spec.id)
            continue
        if not spec.module or not spec.class_name:
            logger.warning("Agent '%s' missing module/class definition.", spec.id)
            continue

        try:
            module = importlib.import_module(spec.module)
            cls = getattr(module, spec.class_name)
        except Exception as exc:
            logger.error("Could not import %s.%s: %s", spec.module, spec.class_name, exc)
            continue

        kwargs = _resolve_kwargs(spec.init_kwargs, repo_reference, repo_path)
        try:
            instance = cls(**kwargs)
            if not hasattr(instance, "tool_id"):
                try:
                    setattr(instance, "tool_id", spec.id)
                except Exception:
                    pass
            setter = getattr(instance, "set_repo_reference", None)
            if callable(setter):
                setter(repo_reference)
            instances.append(instance)
        except Exception as exc:
            logger.error("Failed to instantiate agent '%s': %s", spec.id, exc)

    return instances
