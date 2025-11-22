from __future__ import annotations

import logging
import os
from typing import List, Dict, Any, Optional

from neo4j import GraphDatabase
from knowledge_graph.schema import GraphSchema, Node, Edge

logger = logging.getLogger(__name__)

class GraphStore:
    """
    Adapter for Neo4j GraphDB.
    """

    def __init__(self):
        self.uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        self.username = os.environ.get("NEO4J_USERNAME", "neo4j")
        self.password = os.environ.get("NEO4J_PASSWORD", "password")
        self.driver = None
        self._initialize_driver()

    def _initialize_driver(self):
        """
        Initialize the Neo4j driver.
        """
        try:
            self.driver = GraphDatabase.driver(self.uri, auth=(self.username, self.password))
            # Verify connection
            self.driver.verify_connectivity()
            self._create_constraints()
        except Exception as e:
            logger.error(f"Failed to initialize Neo4j driver: {e}")

    def _create_constraints(self):
        """
        Create constraints to ensure data integrity and performance.
        """
        constraints = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:File) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Function) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Class) REQUIRE n.id IS UNIQUE",
        ]
        with self.driver.session() as session:
            for query in constraints:
                try:
                    session.run(query)
                except Exception as e:
                    logger.warning(f"Failed to create constraint: {e}")

    def close(self):
        if self.driver:
            self.driver.close()

    def add_nodes(self, nodes: List[Node]):
        """
        Batch insert nodes.
        """
        if not nodes:
            return

        query = """
        UNWIND $batch AS row
        CALL {
            WITH row
            MERGE (n:Node {id: row.id})
            SET n += row.properties
            WITH n, row
            CALL apoc.create.addLabels(n, [row.type]) YIELD node
            RETURN count(*) as c
        }
        RETURN count(*)
        """
        # Simplified version without APOC for standard Neo4j
        # We'll split by type for standard Cypher
        nodes_by_type = {}
        for node in nodes:
            if node.type not in nodes_by_type:
                nodes_by_type[node.type] = []
            nodes_by_type[node.type].append({"id": node.id, **node.properties})

        with self.driver.session() as session:
            for label, batch in nodes_by_type.items():
                cypher = f"""
                UNWIND $batch AS row
                MERGE (n:{label} {{id: row.id}})
                SET n += row
                """
                try:
                    session.run(cypher, batch=batch)
                except Exception as e:
                    logger.error(f"Error adding nodes of type {label}: {e}")

    def add_edges(self, edges: List[Edge]):
        """
        Batch insert edges.
        """
        if not edges:
            return

        # Group by type for efficient batching
        edges_by_type = {}
        for edge in edges:
            if edge.type not in edges_by_type:
                edges_by_type[edge.type] = []
            edges_by_type[edge.type].append({
                "source": edge.source,
                "target": edge.target,
                **edge.properties
            })

        with self.driver.session() as session:
            for rel_type, batch in edges_by_type.items():
                cypher = f"""
                UNWIND $batch AS row
                MATCH (a {{id: row.source}}), (b {{id: row.target}})
                MERGE (a)-[r:{rel_type}]->(b)
                SET r += row
                """
                try:
                    session.run(cypher, batch=batch)
                except Exception as e:
                    logger.error(f"Error adding edges of type {rel_type}: {e}")

    def query(self, cypher_query: str, params: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        Execute a raw Cypher query.
        """
        if not self.driver:
            return []
            
        with self.driver.session() as session:
            try:
                result = session.run(cypher_query, parameters=params or {})
                return [record.data() for record in result]
            except Exception as e:
                logger.error(f"Query failed: {e}")
                return []

    def clear(self):
        """
        Nuke the DB.
        """
        if not self.driver:
            return
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
