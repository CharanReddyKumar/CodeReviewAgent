from __future__ import annotations

from unittest.mock import MagicMock

from knowledge_graph.code_graph import build_code_structure_graph


def test_build_code_structure_graph_persists_nodes(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "sample.py"
    source.write_text(
        """
def alpha():
    return beta()

def beta():
    return 42
"""
    )

    mock_store = MagicMock()
    mock_store.driver = object()

    build_code_structure_graph(repo, "https://github.com/example/project", graph_store=mock_store)

    mock_store.clear_layer.assert_called_once()
    assert mock_store.add_nodes.called, "expected nodes to be persisted to Neo4j"
    assert mock_store.add_edges.called, "expected relationships to be persisted to Neo4j"

    persisted_nodes = mock_store.add_nodes.call_args[0][0]
    node_ids = {node.id for node in persisted_nodes}
    assert any(id_part.endswith("file::sample.py") for id_part in node_ids)

    file_node = next(node for node in persisted_nodes if node.type == "File")
    assert file_node.properties["repo_reference"] == "github.com/example/project"
