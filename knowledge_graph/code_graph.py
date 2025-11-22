from __future__ import annotations

import ast
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx

from graph_defination import normalize_repo_reference, repo_slug, should_skip_path
from .graph_store import GraphStore
from .schema import Edge, GraphSchema, Node
from .store import save_layer_graph


SymbolInfo = Tuple[str, str]  # (symbol_id, qualified_name)

logger = logging.getLogger(__name__)


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


def build_code_structure_graph(
    repo_path: str | Path,
    repo_reference: str,
    graph_store: GraphStore | None = None,
) -> nx.MultiDiGraph:
    repo_root = Path(repo_path).resolve()
    canonical = normalize_repo_reference(repo_reference)
    slug = repo_slug(canonical)

    graph = nx.MultiDiGraph()
    graph.graph.update({"layer": "code_structure", "repo_reference": canonical, "repo_slug": slug})

    file_nodes: Dict[str, str] = {}
    module_symbols: Dict[str, Dict[str, SymbolInfo]] = {}
    
    # Initialize TreeSitterParser
    from .tree_sitter_parser import TreeSitterParser
    ts_parser = TreeSitterParser()
    supported_extensions = set(ts_parser.get_supported_extensions())

    # Walk all files
    for file_path in repo_root.rglob("*"):
        if file_path.is_dir():
            continue
        if should_skip_path(file_path.parts):
            continue
        
        ext = file_path.suffix.lower()
        if ext not in supported_extensions and ext != '.py':
            continue

        rel_path = file_path.relative_to(repo_root).as_posix()
        file_id = f"file::{rel_path}"
        module_name = rel_path.replace("/", ".").rsplit(ext, 1)[0]
        is_test = "tests" in file_path.parts or rel_path.startswith("tests/") or file_path.name.startswith("test_")
        
        try:
            file_hash = _file_hash(file_path)
        except Exception as exc:
            logger.warning(f"Failed to hash {rel_path}: {exc}")
            continue

        graph.add_node(
            file_id,
            type="file",
            path=rel_path,
            module=module_name,
            sha256=file_hash,
            is_test=is_test,
            language=ts_parser._get_language_for_file(file_path) or "python"
        )
        file_nodes[rel_path] = file_id

        # Python specific AST parsing (keeps existing rich features)
        if ext == '.py':
            try:
                source_text = file_path.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(source_text, filename=str(file_path))
                symbol_nodes, symbol_index = _collect_symbols(tree, module_name, file_id, rel_path)
                module_symbols[module_name] = symbol_index
                for node_id, attrs in symbol_nodes:
                    graph.add_node(node_id, **attrs)
                    graph.add_edge(file_id, node_id, kind="defines")
            except Exception as exc:
                print(f"[knowledge_graph] Skipping Python parse for {rel_path}: {exc}")
                continue
        
        # Other languages using TreeSitter
        elif ts_parser.is_supported(file_path):
            try:
                definitions = ts_parser.extract_definitions(file_path)
                for defn in definitions:
                    node_name = defn['name']
                    # Construct a symbol ID similar to Python ones
                    symbol_id = f"symbol::{module_name}.{node_name}"
                    
                    attrs = {
                        "type": defn['type'], # e.g. function_definition, class_declaration
                        "name": node_name,
                        "qualified_name": f"{module_name}.{node_name}",
                        "file_path": rel_path,
                        "module": module_name,
                        "span": (defn['start_line'], defn['end_line']),
                        "defined_in": file_id,
                        "language": defn['language']
                    }
                    
                    graph.add_node(symbol_id, **attrs)
                    graph.add_edge(file_id, symbol_id, kind="defines")
            except Exception as exc:
                print(f"[knowledge_graph] Skipping TreeSitter parse for {rel_path}: {exc}")
                continue

    # Build call edges (Python only for now)
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
    try:
        _persist_graph_to_store(graph, canonical, slug, repo_root, graph_store)
    except Exception as exc:
        logger.warning("Neo4j sync failed for %s: %s", canonical, exc)
    print(
        f"[knowledge_graph] Code graph for {canonical} -> "
        f"{graph.number_of_nodes()} nodes / {graph.number_of_edges()} edges"
    )
    return graph


def _persist_graph_to_store(
    graph: nx.MultiDiGraph,
    repo_reference: str,
    repo_slug_value: str,
    repo_root: Path,
    graph_store: GraphStore | None,
) -> None:
    store = graph_store
    close_store = False
    if store is None:
        store = GraphStore()
        close_store = True

    if not getattr(store, "driver", None):
        if close_store:
            store.close()
        logger.info("Neo4j driver unavailable; skipping graph sync.")
        return

    repo_context = {
        "repo_reference": repo_reference,
        "repo_slug": repo_slug_value,
        "repo_path": repo_root.as_posix(),
        "layer": "code",
    }

    store.clear_layer(repo_slug_value, "code")

    nodes = _build_nodes_for_store(graph, repo_context)
    if nodes:
        store.add_nodes(nodes)

    edges = _build_edges_for_store(graph, repo_context)
    if edges:
        store.add_edges(edges)

    _relink_vulnerabilities(store, repo_context)

    if close_store:
        store.close()


def _build_nodes_for_store(graph: nx.MultiDiGraph, repo_context: Dict[str, Any]) -> List[Node]:
    nodes: List[Node] = []
    base_id = repo_context["repo_slug"]
    for node_id, attrs in graph.nodes(data=True):
        label = _map_node_label(attrs.get("type"))
        if not label:
            continue
        properties = dict(repo_context)
        sanitized = _sanitize_properties({k: v for k, v in attrs.items() if k != "type"})
        properties.update(sanitized)
        properties["raw_id"] = node_id
        nodes.append(
            Node(
                id=f"{base_id}::{node_id}",
                type=label,
                properties=properties,
            )
        )
    return nodes


def _build_edges_for_store(graph: nx.MultiDiGraph, repo_context: Dict[str, Any]) -> List[Edge]:
    edges: List[Edge] = []
    base_id = repo_context["repo_slug"]
    for source, target, attrs in graph.edges(data=True):
        rel_type = _map_edge_type(attrs.get("kind"))
        if not rel_type:
            continue
        properties = dict(repo_context)
        sanitized = _sanitize_properties({k: v for k, v in attrs.items() if k != "kind"})
        properties.update(sanitized)
        properties["raw_kind"] = attrs.get("kind")
        properties["source_raw_id"] = source
        properties["target_raw_id"] = target
        edges.append(
            Edge(
                source=f"{base_id}::{source}",
                target=f"{base_id}::{target}",
                type=rel_type,
                properties=properties,
            )
        )
    return edges


def _map_node_label(node_type: Optional[str]) -> Optional[str]:
    mapping = {
        "file": GraphSchema.FILE,
        "function": GraphSchema.FUNCTION,
        "async_function": GraphSchema.FUNCTION,
        "class": GraphSchema.CLASS,
    }
    return mapping.get((node_type or "").lower()) if isinstance(node_type, str) else None


def _map_edge_type(kind: Optional[str]) -> Optional[str]:
    mapping = {
        "defines": GraphSchema.DEFINES,
        "calls": GraphSchema.CALLS,
    }
    key = (kind or "").lower()
    return mapping.get(key)


def _sanitize_properties(props: Dict[str, Any]) -> Dict[str, Any]:
    sanitized: Dict[str, Any] = {}
    for key, value in props.items():
        sanitized[key] = _sanitize_value(value)
    return sanitized


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_sanitize_value(v) for v in value]
    if isinstance(value, list):
        return [_sanitize_value(v) for v in value]
    if isinstance(value, dict):
        try:
            return json.dumps(value, sort_keys=True)
        except Exception:
            return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _relink_vulnerabilities(store: GraphStore, repo_context: Dict[str, Any]) -> None:
    repo_slug_value = repo_context["repo_slug"]
    try:
        store.query(
            """
            MATCH (v:Vulnerability {repo_slug: $repo_slug})
            MATCH (file:File {repo_slug: $repo_slug, path: v.file_path})
            MERGE (file)-[hv:HAS_VULNERABILITY]->(v)
            SET hv.layer = COALESCE(hv.layer, 'security')
            """,
            {"repo_slug": repo_slug_value},
        )
    except Exception as exc:
        logger.warning("Failed to relink vulnerabilities for %s: %s", repo_slug_value, exc)
