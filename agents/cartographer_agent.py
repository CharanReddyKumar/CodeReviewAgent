from __future__ import annotations

import logging
from typing import Any, Dict, List, Set, Optional

from agents.base_agent import BaseAutonomousAgent
from knowledge_graph.graph_store import GraphStore
from knowledge_graph.taint_analysis import TaintAnalyzer

logger = logging.getLogger(__name__)

class CartographerAgent(BaseAutonomousAgent):
    """
    A specialist agent that explores the codebase structure using the Knowledge Graph.
    Enhanced with data flow tracing and blast radius analysis.
    """

    def __init__(self, graph_store: GraphStore, **kwargs):
        super().__init__(name="Cartographer", role="Explorer", **kwargs)
        self.store = graph_store
        self.analyzer = TaintAnalyzer(graph_store)

    def get_system_prompt(self) -> str:
        return (
            "You are the Cartographer. Your job is to answer structural questions about the codebase.\n"
            "You have access to a Knowledge Graph of the code.\n"
            "Use 'run_cypher' to execute direct queries.\n"
            "Use 'check_taint' to see if data flows from a source to a sink.\n"
            "Use 'trace_data_flow' to track how data moves through functions.\n"
            "Use 'calculate_blast_radius' to see what's affected by changes.\n"
            "Provide definitive answers based on graph evidence, not guesses."
        )

    def act(self, action: Dict[str, Any]) -> Any:
        """
        Handle graph-specific actions.
        """
        action_type = action.get("type")
        args = action.get("args", {})

        if action_type == "tool":
            tool_name = action.get("tool")
            
            if tool_name == "run_cypher":
                query = args.get("query")
                return self.store.query(query)
            
            if tool_name == "check_taint":
                source = args.get("source")
                sink = args.get("sink")
                return self.analyzer.check_taint(source, sink)
            
            if tool_name == "trace_data_flow":
                start_function = args.get("start_function")
                max_depth = args.get("max_depth", 5)
                return self.trace_data_flow(start_function, max_depth)
            
            if tool_name == "calculate_blast_radius":
                changed_items = args.get("changed_items", [])
                return self.calculate_blast_radius(changed_items)

        return super().act(action)

    def trace_data_flow(self, start_function: str, max_depth: int = 5) -> Dict[str, Any]:
        """
        Trace data flow from a starting function through the call graph.
        
        Args:
            start_function: Name or ID of the starting function
            max_depth: Maximum depth to traverse
            
        Returns:
            Dict with 'paths', 'nodes_visited', 'data_flow_summary'
        """
        try:
            query = """
            MATCH path = (start:Function {{name: $function_name}})
                -[:CALLS|READS|WRITES*1..$max_depth]->(related)
            RETURN path, nodes(path) as nodes, relationships(path) as rels
            LIMIT 100
            """
            
            results = self.store.query(query, {
                "function_name": start_function,
                "max_depth": max_depth
            })
            
            # Process results
            paths = []
            nodes_visited = set()
            
            for record in results:
                nodes = record.get('nodes', [])
                rels = record.get('rels', [])
                
                path_description = []
                for i, node in enumerate(nodes):
                    node_name = node.get('name', 'unknown')
                    nodes_visited.add(node_name)
                    
                    if i < len(rels):
                        rel_type = rels[i].get('type', 'RELATED')
                        path_description.append(f"{node_name} -{rel_type}->")
                    else:
                        path_description.append(node_name)
                
                paths.append(" ".join(path_description))
            
            return {
                'paths': paths,
                'nodes_visited': list(nodes_visited),
                'total_paths': len(paths),
                'data_flow_summary': f"Traced {len(paths)} paths from {start_function}"
            }
        except Exception as exc:
            logger.error(f"Data flow tracing failed: {exc}")
            return {
                'paths': [],
                'nodes_visited': [],
                'error': str(exc)
            }

    def calculate_blast_radius(self, changed_items: List[str]) -> Dict[str, Any]:
        """
        Calculate the blast radius of changes to specific items.
        Shows what files/functions will be affected by changes.
        
        Args:
            changed_items: List of file paths or function names that changed
            
        Returns:
            Dict with 'affected_files', 'affected_functions', 'impact_score'
        """
        affected_files = set()
        affected_functions = set()
        impact_details = []
        
        for item in changed_items:
            try:
                # Query for downstream dependencies
                query = """
                MATCH (changed {{name: $item_name}})
                OPTIONAL MATCH (changed)<-[:CALLS|IMPORTS|DEPENDS_ON*1..3]-(dependent)
                OPTIONAL MATCH (dependent)-[:DEFINED_IN]->(file:File)
                RETURN dependent, file, labels(dependent) as labels
                LIMIT 50
                """
                
                results = self.store.query(query, {"item_name": item})
                
                for record in results:
                    dependent = record.get('dependent')
                    file_node = record.get('file')
                    labels = record.get('labels', [])
                    
                    if dependent:
                        dep_name = dependent.get('name', 'unknown')
                        if 'Function' in labels or 'Method' in labels:
                            affected_functions.add(dep_name)
                        
                        impact_details.append({
                            'changed_item': item,
                            'affects': dep_name,
                            'type': labels[0] if labels else 'unknown'
                        })
                    
                    if file_node:
                        affected_files.add(file_node.get('path', 'unknown'))
                
            except Exception as exc:
                logger.error(f"Blast radius calculation failed for {item}: {exc}")
                continue
        
        # Calculate impact score (0-100)
        impact_score = min(100, (len(affected_files) * 10) + (len(affected_functions) * 2))
        
        return {
            'changed_items': changed_items,
            'affected_files': list(affected_files),
            'affected_functions': list(affected_functions),
            'total_affected_files': len(affected_files),
            'total_affected_functions': len(affected_functions),
            'impact_score': impact_score,
            'impact_level': self._categorize_impact(impact_score),
            'details': impact_details[:20]  # Limit to 20 most important
        }

    def _categorize_impact(self, score: int) -> str:
        """Categorize impact score into levels."""
        if score >= 80:
            return "CRITICAL"
        elif score >= 50:
            return "HIGH"
        elif score >= 20:
            return "MEDIUM"
        else:
            return "LOW"

    def find_cross_file_dependencies(self, file_path: str) -> Dict[str, Any]:
        """
        Find all cross-file dependencies for a specific file.
        
        Args:
            file_path: Path to the file to analyze
            
        Returns:
            Dict with 'imports', 'imported_by', 'calls_external', 'called_by_external'
        """
        try:
            query = """
            MATCH (f:File {path: $file_path})
            OPTIONAL MATCH (f)-[:IMPORTS]->(imported:File)
            OPTIONAL MATCH (f)<-[:IMPORTS]-(importing:File)
            OPTIONAL MATCH (f)-[:DEFINES]->(func:Function)-[:CALLS]->(external_func:Function)
                <-[:DEFINES]-(external_file:File)
            WHERE external_file.path <> $file_path
            RETURN 
                collect(DISTINCT imported.path) as imports,
                collect(DISTINCT importing.path) as imported_by,
                collect(DISTINCT external_file.path) as calls_files
            """
            
            results = self.store.query(query, {"file_path": file_path})
            
            if results:
                record = results[0]
                return {
                    'file': file_path,
                    'imports': [p for p in record.get('imports', []) if p],
                    'imported_by': [p for p in record.get('imported_by', []) if p],
                    'calls_external_files': [p for p in record.get('calls_files', []) if p],
                    'is_isolated': not any([
                        record.get('imports'),
                        record.get('imported_by'),
                        record.get('calls_files')
                    ])
                }
            
            return {'file': file_path, 'error': 'No data found'}
        except Exception as exc:
            logger.error(f"Cross-file dependency analysis failed: {exc}")
            return {'file': file_path, 'error': str(exc)}

