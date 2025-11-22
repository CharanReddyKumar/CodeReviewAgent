from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import tree_sitter
import tree_sitter_python
import tree_sitter_javascript
import tree_sitter_typescript

logger = logging.getLogger(__name__)

class TreeSitterParser:
    """
    A robust, polyglot parser using Tree-sitter.
    Handles Python, JavaScript, and TypeScript.
    """

    def __init__(self):
        self.languages = {
            "python": tree_sitter.Language(tree_sitter_python.language()),
            "javascript": tree_sitter.Language(tree_sitter_javascript.language()),
            "typescript": tree_sitter.Language(tree_sitter_typescript.language_typescript()),
            "tsx": tree_sitter.Language(tree_sitter_typescript.language_tsx()),
        }
        self.parsers = {}
        for lang_name, lang_obj in self.languages.items():
            parser = tree_sitter.Parser()
            parser.language = lang_obj
            self.parsers[lang_name] = parser

    def _get_language_for_file(self, file_path: Path) -> Optional[str]:
        ext = file_path.suffix.lower()
        if ext == ".py":
            return "python"
        elif ext == ".js" or ext == ".mjs" or ext == ".cjs":
            return "javascript"
        elif ext == ".ts":
            return "typescript"
        elif ext == ".tsx":
            return "tsx"
        return None

    def parse_file(self, file_path: Path) -> Optional[tree_sitter.Tree]:
        """
        Parse a file and return the syntax tree.
        """
        lang = self._get_language_for_file(file_path)
        if not lang:
            return None
        
        try:
            content = file_path.read_bytes()
            return self.parsers[lang].parse(content)
        except Exception as e:
            logger.error(f"Failed to parse {file_path}: {e}")
            return None

    def extract_definitions(self, file_path: Path) -> List[Dict[str, str]]:
        """
        Extract class and function definitions from the file.
        Returns a list of nodes with type, name, and location.
        """
        tree = self.parse_file(file_path)
        if not tree:
            return []
            
        definitions = []
        cursor = tree.walk()
        
        # Simple traversal to find definitions
        # In a real implementation, we would use queries for better precision
        visited_children = False
        while True:
            if not visited_children:
                node = cursor.node
                if node.type in ("class_definition", "function_definition", "method_definition"):
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        definitions.append({
                            "type": node.type,
                            "name": name_node.text.decode("utf-8"),
                            "start_line": node.start_point[0] + 1,
                            "end_line": node.end_point[0] + 1,
                        })
                
                if cursor.goto_first_child():
                    visited_children = False
                    continue

            if cursor.goto_next_sibling():
                visited_children = False
                continue
            
            if cursor.goto_parent():
                visited_children = True
                continue
            
            break
                
        return definitions
