from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import tree_sitter

logger = logging.getLogger(__name__)

class TreeSitterParser:
    """
    A robust, polyglot parser using Tree-sitter.
    Supports all major programming languages.
    """

    def __init__(self):
        # Initialize all language parsers
        self.languages = {}
        
        # Helper to safely load languages
        def load_lang(name, module_name, func_name='language'):
            try:
                mod = __import__(module_name)
                # Handle nested modules if necessary (e.g. tree_sitter_typescript.language_typescript)
                if '.' in func_name:
                    parts = func_name.split('.')
                    obj = mod
                    for part in parts:
                        obj = getattr(obj, part)
                    lang_obj = obj()
                else:
                    lang_obj = getattr(mod, func_name)()
                self.languages[name] = tree_sitter.Language(lang_obj)
            except (ImportError, AttributeError) as e:
                logger.debug(f"Could not load tree-sitter language {name}: {e}")

        # Load languages
        load_lang("python", "tree_sitter_python")
        load_lang("javascript", "tree_sitter_javascript")
        load_lang("typescript", "tree_sitter_typescript", "language_typescript")
        load_lang("tsx", "tree_sitter_typescript", "language_tsx")
        load_lang("java", "tree_sitter_java")
        load_lang("go", "tree_sitter_go")
        load_lang("rust", "tree_sitter_rust")
        load_lang("c", "tree_sitter_c")
        load_lang("cpp", "tree_sitter_cpp")
        load_lang("csharp", "tree_sitter_c_sharp")
        load_lang("ruby", "tree_sitter_ruby")
        load_lang("php", "tree_sitter_php", "language_php")
        load_lang("swift", "tree_sitter_swift")
        load_lang("kotlin", "tree_sitter_kotlin")
        
        self.parsers = {}
        for lang_name, lang_obj in self.languages.items():
            parser = tree_sitter.Parser()
            parser.language = lang_obj
            self.parsers[lang_name] = parser
        
        logger.info(f"TreeSitterParser initialized with {len(self.languages)} languages")

    def _get_language_for_file(self, file_path: Path) -> Optional[str]:
        """Map file extension to language."""
        ext = file_path.suffix.lower()
        
        # Comprehensive extension mapping
        ext_map = {
            ".py": "python",
            ".js": "javascript",
            ".mjs": "javascript",
            ".cjs": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "tsx",
            ".java": "java",
            ".go": "go",
            ".rs": "rust",
            ".c": "c",
            ".h": "c",
            ".cpp": "cpp",
            ".cc": "cpp",
            ".cxx": "cpp",
            ".hpp": "cpp",
            ".hh": "cpp",
            ".hxx": "cpp",
            ".cs": "csharp",
            ".rb": "ruby",
            ".php": "php",
            ".swift": "swift",
            ".kt": "kotlin",
            ".kts": "kotlin",
        }
        
        return ext_map.get(ext)

    def parse_file(self, file_path: Path) -> Optional[tree_sitter.Tree]:
        """
        Parse a file and return the syntax tree.
        """
        lang = self._get_language_for_file(file_path)
        if not lang:
            logger.debug(f"Unsupported file extension: {file_path.suffix}")
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
        
        lang = self._get_language_for_file(file_path)
        if not lang:
            return []
            
        definitions = []
        cursor = tree.walk()
        
        # Language-specific node types for definitions
        definition_types = self._get_definition_types(lang)
        
        # Traverse the tree
        visited_children = False
        while True:
            if not visited_children:
                node = cursor.node
                if node.type in definition_types:
                    name = self._extract_name(node, lang)
                    if name:
                        definitions.append({
                            "type": node.type,
                            "name": name,
                            "start_line": node.start_point[0] + 1,
                            "end_line": node.end_point[0] + 1,
                            "language": lang
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

    def _get_definition_types(self, lang: str) -> Set[str]:
        """Get the node types that represent definitions for a given language."""
        type_map = {
            "python": {"class_definition", "function_definition", "method_definition"},
            "javascript": {"class_declaration", "function_declaration", "method_definition"},
            "typescript": {"class_declaration", "function_declaration", "method_definition", "interface_declaration"},
            "tsx": {"class_declaration", "function_declaration", "method_definition", "interface_declaration"},
            "java": {"class_declaration", "method_declaration", "interface_declaration", "enum_declaration"},
            "go": {"function_declaration", "method_declaration", "type_declaration"},
            "rust": {"function_item", "struct_item", "enum_item", "trait_item", "impl_item"},
            "c": {"function_definition", "struct_specifier"},
            "cpp": {"function_definition", "class_specifier", "struct_specifier"},
            "csharp": {"class_declaration", "method_declaration", "interface_declaration", "struct_declaration"},
            "ruby": {"class", "method", "module"},
            "php": {"class_declaration", "method_declaration", "function_definition"},
            "swift": {"class_declaration", "function_declaration", "struct_declaration", "protocol_declaration"},
            "kotlin": {"class_declaration", "function_declaration", "object_declaration", "interface_declaration"},
        }
        
        return type_map.get(lang, {"function", "class"})

    def _extract_name(self, node: tree_sitter.Node, lang: str) -> Optional[str]:
        """Extract the name from a definition node."""
        try:
            # Try standard "name" field first
            name_node = node.child_by_field_name("name")
            if name_node:
                return name_node.text.decode("utf-8")
            
            # Language-specific fallbacks
            if lang in ["rust"]:
                # Rust uses "identifier" instead of "name" sometimes
                for child in node.children:
                    if child.type == "identifier":
                        return child.text.decode("utf-8")
            
            # Generic fallback: find first identifier
            for child in node.children:
                if "identifier" in child.type.lower():
                    return child.text.decode("utf-8")
            
            return None
        except Exception as e:
            logger.debug(f"Failed to extract name: {e}")
            return None

    def get_supported_languages(self) -> List[str]:
        """Return list of all supported languages."""
        return list(self.languages.keys())

    def get_supported_extensions(self) -> List[str]:
        """Return list of all supported file extensions."""
        return [
            ".py", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx",
            ".java", ".go", ".rs", ".c", ".h", ".cpp", ".cc", ".cxx",
            ".hpp", ".hh", ".hxx", ".cs", ".rb", ".php", ".swift",
            ".kt", ".kts"
        ]

    def is_supported(self, file_path: Path) -> bool:
        """Check if a file is supported by the parser."""
        return self._get_language_for_file(file_path) is not None

