import unittest
import shutil
from pathlib import Path
from knowledge_graph.tree_sitter_parser import TreeSitterParser
from knowledge_graph.graph_store import GraphStore
from knowledge_graph.schema import GraphSchema, Node, Edge
from unittest.mock import MagicMock, patch

class TestApexComponents(unittest.TestCase):
    def setUp(self):
        self.parser = TreeSitterParser()
        # self.store = GraphStore() # Mocked in test

    def tearDown(self):
        pass

    def test_parser_python(self):
        parser = TreeSitterParser()
        # Create a dummy python file
        dummy_file = Path("test_file.py")
        dummy_file.write_text("def hello():\n    pass\nclass World:\n    pass")
        
        try:
            definitions = parser.extract_definitions(dummy_file)
            self.assertEqual(len(definitions), 2)
            names = {d["name"] for d in definitions}
            self.assertIn("hello", names)
            self.assertIn("World", names)
        finally:
            dummy_file.unlink()

    def test_graph_store(self):
        with patch("knowledge_graph.graph_store.GraphDatabase") as mock_db:
            mock_driver = MagicMock()
            mock_session = MagicMock()
            mock_db.driver.return_value = mock_driver
            mock_driver.session.return_value.__enter__.return_value = mock_session
            
            store = GraphStore()
            
            # Add nodes
            nodes = [
                GraphSchema.file_node("test.py"),
                GraphSchema.function_node("main", "()", "test.py")
            ]
            store.add_nodes(nodes)
            
            # Verify session.run was called for nodes
            self.assertTrue(mock_session.run.called)
            
            # Add edge
            edges = [
                Edge(source="test.py", target="test.py::main", type=GraphSchema.DEFINES)
            ]
            store.add_edges(edges)
            
            # Verify session.run was called for edges
            self.assertTrue(mock_session.run.called)
            
            # Query
            mock_result = MagicMock()
            mock_record = MagicMock()
            mock_record.data.return_value = {"f.path": "test.py", "func.name": "main"}
            mock_result.__iter__.return_value = [mock_record]
            mock_session.run.return_value = mock_result
            
            results = store.query("MATCH (f:File)-[:DEFINES]->(func:Function) RETURN f.path, func.name")
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["f.path"], "test.py")
        
            store.close()

if __name__ == "__main__":
    unittest.main()
