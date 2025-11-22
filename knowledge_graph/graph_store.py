from __future__ import annotations

import logging
import os
from typing import List, Dict, Any, Optional

from neo4j import GraphDatabase
from neo4j.exceptions import ClientError
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
        self.database = os.environ.get("NEO4J_DATABASE")
        self._initialize_driver()

    def _initialize_driver(self):
        """
        Initialize the Neo4j driver.
        """
        try:
            self.driver = GraphDatabase.driver(self.uri, auth=(self.username, self.password))
            self.driver.verify_connectivity()
            self._ensure_database_exists()
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
        with self._session() as session:
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

        with self._session() as session:
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

        with self._session() as session:
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
            
        with self._session() as session:
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
        with self._session() as session:
            session.run("MATCH (n) DETACH DELETE n")

    def clear_layer(self, repo_slug: str, layer: str) -> None:
        """Remove all nodes for a given repo/layer combination."""
        if not self.driver:
            return
        try:
            with self._session() as session:
                session.run(
                    "MATCH (n {repo_slug: $repo_slug, layer: $layer}) DETACH DELETE n",
                    repo_slug=repo_slug,
                    layer=layer,
                )
        except Exception as exc:
            logger.error(
                "Failed to clear Neo4j layer '%s' for repo '%s': %s",
                layer,
                repo_slug,
                exc,
            )

    def _ensure_database_exists(self):
        if not self.database or not self.driver:
            return
        db_name = self.database
        try:
            with self.driver.session(database="system") as session:
                session.run(f"CREATE DATABASE `{db_name}` IF NOT EXISTS")
        except ClientError as exc:
            logger.warning(
                "Unable to ensure Neo4j database '%s' exists: %s",
                db_name,
                exc,
            )

    def _session(self):
        if not self.driver:
            raise RuntimeError("Neo4j driver is not initialized")
        if self.database:
            try:
                return self.driver.session(database=self.database)
            except ClientError as exc:
                if getattr(exc, "code", "") == "Neo.ClientError.Database.DatabaseNotFound":
                    logger.warning(
                        "Neo4j database '%s' not found; falling back to default.",
                        self.database,
                    )
                    self.database = None
                else:
                    raise
        return self.driver.session()
