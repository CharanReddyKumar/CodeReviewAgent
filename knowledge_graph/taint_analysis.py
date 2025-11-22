from __future__ import annotations

from typing import List, Dict, Any, Optional
from knowledge_graph.graph_store import GraphStore

class TaintAnalyzer:
    """
    Performs taint analysis on the code graph.
    """

    def __init__(self, graph_store: GraphStore):
        self.store = graph_store

    def find_paths(self, source_pattern: str, sink_pattern: str, max_depth: int = 10) -> List[Dict[str, Any]]:
        """
        Find all paths from nodes matching source_pattern to nodes matching sink_pattern.
        """
        # Cypher query to find paths
        # Note: Kuzu supports recursive path matching with -[*]->
        query = f"""
        MATCH p = (source:Function)-[:CALLS*1..{max_depth}]->(sink:Function)
        WHERE source.name CONTAINS $source_pattern
          AND sink.name CONTAINS $sink_pattern
        RETURN p
        """
        
        # Since Kuzu's Python API might return paths differently, we might need to parse them.
        # For now, we'll assume it returns a list of paths.
        results = self.store.query(query.replace("$source_pattern", f"'{source_pattern}'").replace("$sink_pattern", f"'{sink_pattern}'"))
        
        paths = []
        for row in results:
            # Kuzu returns paths as a special object or list of nodes/rels
            # We need to serialize this for the agent
            paths.append({"path": str(row)}) 
            
        return paths

    def check_taint(self, source_var: str, sink_func: str) -> List[str]:
        """
        Check if a specific variable flows into a specific function sink.
        This is a simplified version; real taint tracking requires data flow analysis (READS/WRITES edges).
        """
        query = f"""
        MATCH p = (v:Variable {{name: '{source_var}'}})<-[:READS]-(f1:Function)-[:CALLS*]->(f2:Function {{name: '{sink_func}'}})
        RETURN p
        """
        results = self.store.query(query)
        return [str(row) for row in results]
