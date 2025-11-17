from __future__ import annotations

import os
from pathlib import Path
from typing import List

from chromadb.config import Settings
import chromadb

try:
    from PyPDF2 import PdfReader  # type: ignore
except Exception:  # pragma: no cover
    PdfReader = None

CHROMA_DIR = os.environ.get("LOCAL_VECTOR_DIR", ".local_vectorstore")
DOC_COLLECTION = "best_practices_docs"

_RISK_HINTS = {
    "policy": ("policy", "process", "compliance", "security", "privacy"),
    "security": ("auth", "token", "secret", "crypto", "password"),
}


def _infer_risk(text: str) -> str:
    lowered = (text or "").lower()
    for domain, hints in _RISK_HINTS.items():
        if any(hint in lowered for hint in hints):
            return domain
    return "general"


def _get_client():
    return chromadb.PersistentClient(
        path=CHROMA_DIR,
        settings=Settings(allow_reset=False),
    )


def get_best_practices_doc_collection():
    client = _get_client()
    return client.get_or_create_collection(name=DOC_COLLECTION)


def _read_text(path: Path) -> str:
    if path.suffix.lower() in {".md", ".txt"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix.lower() == ".pdf":
        if PdfReader is None:
            raise RuntimeError("PyPDF2 is required to ingest PDF files.")
        reader = PdfReader(str(path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        return text
    return ""


def ingest_best_practices_docs(folder: Path, source_name: str) -> None:
    folder = Path(folder)
    if not folder.exists():
        raise FileNotFoundError(folder)

    collection = get_best_practices_doc_collection()
    docs: List[str] = []
    metadatas: List[dict] = []
    ids: List[str] = []
    for file_path in folder.rglob("*"):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in {".pdf", ".md", ".txt"}:
            continue
        try:
            text = _read_text(file_path)
        except Exception as exc:
            print(f"[best_practices_docs] Skipping {file_path}: {exc}")
            continue
        if not text.strip():
            continue
        rel = file_path.relative_to(folder).as_posix()
        doc_id = f"{source_name}:{rel}"
        docs.append(text.strip())
        risk = _infer_risk(text)
        metadata = {
            "source": source_name,
            "path": rel,
            "kind": "policy",
            "risk_domain": risk,
            "tags": f"kind:policy,risk:{risk}",
        }
        metadatas.append(metadata)
        ids.append(doc_id)

    if not docs:
        print("[best_practices_docs] No documents found to ingest.")
        return

    collection.upsert(documents=docs, metadatas=metadatas, ids=ids)
    print(
        f"[best_practices_docs] Ingested {len(docs)} documents from {folder} into '{DOC_COLLECTION}'."
    )
