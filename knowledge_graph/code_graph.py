from __future__ import annotations

import ast
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import networkx as nx

from graph_defination import normalize_repo_reference, repo_slug, should_skip_path
from .store import save_layer_graph


SymbolInfo = Tuple[str, str]  # (symbol_id, qualified_name)


def _file_hash(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest()


def _doc_summary(text: Optional[str]) -> str:
    if not text:
        return ""
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines:
        return ""
    return lines[0][:200]


def _contracts_from_doc(text: Optional[str]) -> Dict[str, str]:
    if not text:
        return {}
    contracts: Dict[str, str] = {}
    lowered = text.lower()
    if "raises" in lowered:
        contracts["raises"] = "Documents exceptions."
    if "returns" in lowered or "yield" in lowered:
        contracts["returns"] = "Documents return value."
    if "precondition" in lowered or "requires" in lowered:
        contracts["precondition"] = "Referenced in docstring."
    if "postcondition" in lowered or "ensures" in lowered:
        contracts["postcondition"] = "Referenced in docstring."
    return contracts


def _symbol_name(module: str, qualifier: str, name: str) -> str:
    base = qualifier + "." + name if qualifier else name
    return f"{module}.{base}" if module else base


def _collect_symbols(
    tree: ast.AST,
    module: str,
    file_id: str,
    rel_path: str,
) -> Tuple[List[Tuple[str, Dict]], Dict[str, SymbolInfo]]:
    symbol_nodes: List[Tuple[str, Dict]] = []
    symbol_index: Dict[str, SymbolInfo] = {}

    def visit(node: ast.AST, qualifier: str = ""):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbol_id = f"symbol::{_symbol_name(module, qualifier, node.name)}"
            doc = ast.get_docstring(node)
            symbol_nodes.append(
                (
                    symbol_id,
                    {
                        "type": "async_function" if isinstance(node, ast.AsyncFunctionDef) else "function",
                        "name": node.name,
                        "qualified_name": _symbol_name(module, qualifier, node.name),
                        "file_path": rel_path,
                        "module": module,
                        "span": (getattr(node, "lineno", None), getattr(node, "end_lineno", None)),
                        "docstring": doc,
                        "summary": _doc_summary(doc),
                        "contracts": _contracts_from_doc(doc),
                        "defined_in": file_id,
                    },
                )
            )
            symbol_index[node.name] = (symbol_id, _symbol_name(module, qualifier, node.name))
            for child in node.body:
                visit(child, qualifier)
        elif isinstance(node, ast.ClassDef):
            class_symbol_id = f"symbol::{_symbol_name(module, qualifier, node.name)}"
            doc = ast.get_docstring(node)
            symbol_nodes.append(
                (
                    class_symbol_id,
                    {
                        "type": "class",
                        "name": node.name,
                        "qualified_name": _symbol_name(module, qualifier, node.name),
                        "file_path": rel_path,
                        "module": module,
                        "span": (getattr(node, "lineno", None), getattr(node, "end_lineno", None)),
                        "docstring": doc,
                        "summary": _doc_summary(doc),
                        "contracts": _contracts_from_doc(doc),
                        "defined_in": file_id,
                    },
                )
            )
            symbol_index[node.name] = (class_symbol_id, _symbol_name(module, qualifier, node.name))
            for child in node.body:
                visit(child, qualifier=node.name)
        else:
            for child in ast.iter_child_nodes(node):
                visit(child, qualifier)

    visit(tree)
    return symbol_nodes, symbol_index


def _call_name(node: ast.Call) -> Optional[str]:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def build_code_structure_graph(repo_path: str | Path, repo_reference: str) -> nx.MultiDiGraph:
    repo_root = Path(repo_path).resolve()
    canonical = normalize_repo_reference(repo_reference)
    slug = repo_slug(canonical)

    graph = nx.MultiDiGraph()
    graph.graph.update({"layer": "code_structure", "repo_reference": canonical, "repo_slug": slug})

    file_nodes: Dict[str, str] = {}
    module_symbols: Dict[str, Dict[str, SymbolInfo]] = {}

    for file_path in repo_root.rglob("*.py"):
        if should_skip_path(file_path.parts):
            continue
        rel_path = file_path.relative_to(repo_root).as_posix()
        file_id = f"file::{rel_path}"
        module_name = rel_path.replace("/", ".").rsplit(".py", 1)[0]
        is_test = "tests" in file_path.parts or rel_path.startswith("tests/") or file_path.name.startswith("test_")
        try:
            file_hash = _file_hash(file_path)
            source_text = file_path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(source_text, filename=str(file_path))
        except Exception as exc:
            print(f"[knowledge_graph] Skipping {rel_path}: {exc}")
            continue

        graph.add_node(
            file_id,
            type="file",
            path=rel_path,
            module=module_name,
            sha256=file_hash,
            is_test=is_test,
        )
        file_nodes[rel_path] = file_id

        symbol_nodes, symbol_index = _collect_symbols(tree, module_name, file_id, rel_path)
        module_symbols[module_name] = symbol_index
        for node_id, attrs in symbol_nodes:
            graph.add_node(node_id, **attrs)
            graph.add_edge(file_id, node_id, kind="defines")

    # Build call edges
    for file_path in repo_root.rglob("*.py"):
        if should_skip_path(file_path.parts):
            continue
        rel_path = file_path.relative_to(repo_root).as_posix()
        module_name = rel_path.replace("/", ".").rsplit(".py", 1)[0]
        file_id = f"file::{rel_path}"
        symbol_index = module_symbols.get(module_name, {})
        try:
            source_text = file_path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(source_text, filename=str(file_path))
        except Exception:
            continue

        current_symbol: Optional[str] = None

        class CallVisitor(ast.NodeVisitor):
            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                nonlocal current_symbol
                info = symbol_index.get(node.name)
                if info:
                    current_symbol = info[0]
                    self.generic_visit(node)
                    current_symbol = None
                else:
                    self.generic_visit(node)

            visit_AsyncFunctionDef = visit_FunctionDef

            def visit_ClassDef(self, node: ast.ClassDef) -> None:
                self.generic_visit(node)

            def visit_Call(self, node: ast.Call) -> None:
                if current_symbol:
                    callee = _call_name(node)
                    if callee:
                        for mod, symbols in module_symbols.items():
                            info = symbols.get(callee)
                            if info:
                                graph.add_edge(current_symbol, info[0], kind="calls")
                                break
                self.generic_visit(node)

        CallVisitor().visit(tree)

    save_layer_graph(graph, repo_reference=canonical, layer="code")
    print(
        f"[knowledge_graph] Code graph for {canonical} -> "
        f"{graph.number_of_nodes()} nodes / {graph.number_of_edges()} edges"
    )
    return graph
