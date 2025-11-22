from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class Node:
    id: str
    type: str
    properties: dict = field(default_factory=dict)

@dataclass
class Edge:
    source: str
    target: str
    type: str
    properties: dict = field(default_factory=dict)

class GraphSchema:
    """
    Defines the unified graph schema for code structure.
    """
    
    # Node Labels
    FILE = "File"
    MODULE = "Module"
    CLASS = "Class"
    FUNCTION = "Function"
    VARIABLE = "Variable"
    TYPE = "Type"
    
    # Edge Types
    IMPORTS = "IMPORTS"
    DEFINES = "DEFINES"
    HAS_METHOD = "HAS_METHOD"
    CALLS = "CALLS"
    READS = "READS"
    WRITES = "WRITES"
    IS_TYPE = "IS_TYPE"
    INHERITS = "INHERITS"

    @staticmethod
    def file_node(path: str) -> Node:
        return Node(id=path, type=GraphSchema.FILE, properties={"path": path})

    @staticmethod
    def function_node(name: str, signature: str, file_path: str) -> Node:
        node_id = f"{file_path}::{name}"
        return Node(
            id=node_id, 
            type=GraphSchema.FUNCTION, 
            properties={"name": name, "signature": signature, "file": file_path}
        )

    @staticmethod
    def class_node(name: str, file_path: str) -> Node:
        node_id = f"{file_path}::{name}"
        return Node(
            id=node_id, 
            type=GraphSchema.CLASS, 
            properties={"name": name, "file": file_path}
        )
