import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional

import chromadb
from chromadb.config import Settings
import ast

from agent_registry import LANGUAGE_EXTENSION_MAP
from graph_defination import (
    chroma_collection_name,
    normalize_repo_reference,
    repo_slug,
    should_skip_path,
)

CHROMA_DIR = os.environ.get("LOCAL_VECTOR_DIR", ".local_vectorstore")

_CODE_SUFFIXES = {
    suffix.lower()
    for extensions in LANGUAGE_EXTENSION_MAP.values()
    for suffix in extensions
}
CODE_EXTENSIONS = tuple(sorted(_CODE_SUFFIXES))
DOC_EXTENSIONS = (".md", ".rst", ".txt")
SPECIAL_DOC_FILENAMES = {"readme", "readme.md", "readme.rst", "contributing.md"}
CHUNK_MAX_LINES = 80
CHUNK_OVERLAP_LINES = 10

LANGUAGE_BY_SUFFIX: Dict[str, str] = {
    suffix.lower(): language
    for language, extensions in LANGUAGE_EXTENSION_MAP.items()
    for suffix in extensions
}
LANGUAGE_BY_SUFFIX.update(
    {
        ".md": "markdown",
        ".rst": "rst",
        ".txt": "text",
    }
)

RISK_HINTS = {
    "security": ("auth", "token", "secret", "crypto", "password", "pii", "oauth"),
    "performance": ("perf", "cache", "latency", "throughput", "optimiz"),
    "tests": ("test", "fixture", "pytest"),
    "docs": ("readme", "docs", "guide", "api"),
}


def _language_for_suffix(suffix: str) -> str:
    return LANGUAGE_BY_SUFFIX.get(suffix.lower(), "text")


def _is_test_path(path: Path) -> bool:
    lowered = path.as_posix().lower()
    if "tests/" in lowered or lowered.startswith("tests"):
        return True
    if path.name.startswith("test_") or path.name.endswith("_test.py"):
        return True
    return False


def _infer_risk_domain(relative_path: str, chunk_text: str) -> str:
    lowered_path = relative_path.lower()
    lowered_text = (chunk_text or "").lower()
    for domain, hints in RISK_HINTS.items():
        if any(hint in lowered_path or hint in lowered_text for hint in hints):
            return domain
    return "general"


def _build_tags(*, kind: str, module: str, risk: str, is_test: bool) -> List[str]:
    tags = [f"kind:{kind}", f"risk:{risk}"]
    if module:
        tags.append(f"module:{module}")
    if is_test:
        tags.append("scope:tests")
    return tags


def get_code_collection(repo_reference: str):
    client = chromadb.PersistentClient(
        path=CHROMA_DIR,
        settings=Settings(allow_reset=False),
    )
    name = chroma_collection_name(repo_reference)
    return client.get_or_create_collection(name=name)


def _iter_files(repo_path: Path, *, suffixes: Iterable[str]) -> Iterator[Path]:
    for path in repo_path.rglob("*"):
        if not path.is_file():
            continue
        if should_skip_path(path.parts):
            continue
        if path.suffix.lower() in suffixes:
            yield path


def iter_code_files(repo_path: Path) -> Iterator[Path]:
    return _iter_files(repo_path, suffixes=CODE_EXTENSIONS)


def _iter_doc_files(repo_path: Path) -> Iterator[Path]:
    for path in repo_path.rglob("*"):
        if not path.is_file():
            continue
        if should_skip_path(path.parts):
            continue
        suffix = path.suffix.lower()
        lower_name = path.name.lower()
        if suffix in DOC_EXTENSIONS or lower_name in SPECIAL_DOC_FILENAMES:
            yield path


@dataclass
class Chunk:
    text: str
    start_line: Optional[int]
    end_line: Optional[int]
    chunk_index: int


def _chunk_text(
    text: str,
    *,
    max_lines: int = CHUNK_MAX_LINES,
    overlap_lines: int = CHUNK_OVERLAP_LINES,
) -> Iterator[Chunk]:
    lines = text.splitlines()
    if not lines:
        return
    start = 0
    chunk_index = 0
    total_lines = len(lines)
    while start < total_lines:
        end = min(total_lines, start + max_lines)
        chunk_text = "\n".join(lines[start:end]).strip()
        chunk_data = Chunk(
            text=chunk_text,
            start_line=start + 1,
            end_line=end,
            chunk_index=chunk_index,
        )
        if chunk_text:
            yield chunk_data
        chunk_index += 1
        if end == total_lines:
            break
        start = max(0, end - overlap_lines)
        if start >= end:
            start = end


def _iter_python_blocks(text: str) -> List[Chunk]:
    lines = text.splitlines()
    total_lines = len(lines)
    try:
        tree = ast.parse(text)
    except Exception:
        return [
            Chunk(
                text=text.strip(),
                start_line=1,
                end_line=total_lines,
                chunk_index=0,
            )
        ]

    blocks: List[Chunk] = []
    chunk_index = 0

    def add_block(start: int, end: int):
        nonlocal chunk_index
        if start < 1 or end < start:
            return
        snippet = "\n".join(lines[start - 1 : end]).strip()
        if not snippet:
            return
        blocks.append(
            Chunk(
                text=snippet,
                start_line=start,
                end_line=end,
                chunk_index=chunk_index,
            )
        )
        chunk_index += 1

    covered_ranges: List[tuple[int, int]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = getattr(node, "lineno", None)
            end = getattr(node, "end_lineno", None)
            if start is None or end is None:
                continue
            add_block(start, end)
            covered_ranges.append((start, end))

    covered_ranges.sort()

    def add_module_segment(start_line: int, end_line: int):
        nonlocal chunk_index
        segment_lines = lines[start_line - 1 : end_line]
        if not segment_lines:
            return
        local_start = start_line
        while local_start <= end_line:
            local_end = min(end_line, local_start + CHUNK_MAX_LINES - 1)
            snippet = "\n".join(lines[local_start - 1 : local_end]).strip()
            if snippet:
                blocks.append(
                    Chunk(
                        text=snippet,
                        start_line=local_start,
                        end_line=local_end,
                        chunk_index=chunk_index,
                    )
                )
                chunk_index += 1
            local_start = local_end + 1

    cursor = 1
    for start, end in covered_ranges:
        if start > cursor:
            add_module_segment(cursor, start - 1)
        cursor = max(cursor, end + 1)
    if cursor <= total_lines:
        add_module_segment(cursor, total_lines)

    return blocks or [
        Chunk(
            text=text.strip(),
            start_line=1,
            end_line=total_lines,
            chunk_index=0,
        )
    ]


def _iter_code_chunks(path: Path, text: str) -> Iterable[Chunk]:
    if path.suffix.lower() == ".py":
        return _iter_python_blocks(text)
    return _chunk_text(text)


def _sanitize_id_component(value: str) -> str:
    return value.replace("/", "_").replace(":", "_")


def _build_chunk_records(
    *,
    file_path: Path,
    repo_path: Path,
    repo_reference: str,
    repo_slug_value: str,
    content_type: str,
    chunks: Iterable[Chunk],
) -> Iterator[Dict]:
    rel_path = file_path.relative_to(repo_path).as_posix()
    module_name = ""
    if content_type == "code" and file_path.suffix == ".py":
        module_name = ".".join(file_path.relative_to(repo_path).with_suffix("").parts)
    is_test = content_type == "code" and _is_test_path(file_path)
    for chunk in chunks:
        chunk_id = f"{repo_slug_value}:{content_type}:{_sanitize_id_component(rel_path)}:{chunk.chunk_index}"
        metadata: Dict = {
            "repo_reference": repo_reference,
            "repo_slug": repo_slug_value,
            "relative_path": rel_path,
            "content_type": content_type,
            "chunk_index": chunk.chunk_index,
            "language": _language_for_suffix(file_path.suffix),
            "kind": "code" if content_type == "code" else "doc",
        }
        risk_domain = _infer_risk_domain(rel_path, chunk.text)
        metadata["risk_domain"] = risk_domain
        metadata["tags"] = ",".join(
            _build_tags(
                kind=metadata["kind"],
                module=module_name,
                risk=risk_domain,
                is_test=is_test,
            )
        )
        if content_type == "code":
            metadata["start_line"] = chunk.start_line
            metadata["end_line"] = chunk.end_line
            metadata["module"] = module_name
            metadata["is_test"] = is_test
        yield {
            "id": chunk_id,
            "text": chunk.text,
            "metadata": metadata,
            "content_type": content_type,
        }


def index_repository(repo_path: Path, repo_reference: str):
    canonical_repo = normalize_repo_reference(repo_reference)
    slug = repo_slug(canonical_repo)
    collection = get_code_collection(canonical_repo)

    docs: List[str] = []
    metadatas: List[Dict] = []
    ids: List[str] = []

    def flush_batch():
        if not docs:
            return
        collection.add(documents=docs, metadatas=metadatas, ids=ids)
        docs.clear()
        metadatas.clear()
        ids.clear()

    counts = {"code": 0, "doc": 0}
    batch_size = 500

    def process_file(path: Path, content_type: str):
        nonlocal docs, metadatas, ids
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:
            rel = path.relative_to(repo_path).as_posix()
            print(f"[vector_store] Skipping {rel}: {exc}")
            return
        if content_type == "code":
            chunks = _iter_code_chunks(path, text)
        else:
            chunks = _chunk_text(text)
        for record in _build_chunk_records(
            file_path=path,
            repo_path=repo_path,
            repo_reference=canonical_repo,
            repo_slug_value=slug,
            content_type=content_type,
            chunks=chunks,
        ):
            if not record["text"]:
                continue
            docs.append(record["text"])
            metadatas.append(record["metadata"])
            ids.append(record["id"])
            counts[content_type] += 1
            if len(docs) >= batch_size:
                flush_batch()

    for code_file in iter_code_files(repo_path):
        process_file(code_file, "code")

    for doc_file in _iter_doc_files(repo_path):
        process_file(doc_file, "doc")

    flush_batch()

    total_chunks = counts["code"] + counts["doc"]
    if total_chunks == 0:
        print("[vector_store] No assets found to index.")
        return

    print(
        "[vector_store] ✅ Indexed "
        f"{counts['code']} code chunks and {counts['doc']} documentation chunks."
    )


def index_repo_code(repo_path: Path, repo_url: str):
    """
    Backwards-compatible entrypoint expected by older scripts.
    """
    index_repository(repo_path, repo_url)
