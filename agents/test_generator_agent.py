from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

from llm_utils import build_chat_model

logger = logging.getLogger(__name__)


class TestGeneratorAgent:
    """
    Automatically generates unit tests for functions with low or no coverage.
    Uses graph analysis to identify edge cases and LLM to generate test code.
    """

    def __init__(self, repo_path: Path, graph_store=None):
        self.repo_path = Path(repo_path)
        self.graph_store = graph_store
        self.chat = build_chat_model(task="test_generation")

    def generate_tests_for_function(
        self,
        file_path: str,
        function_name: str,
        function_code: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate unit tests for a specific function.
        
        Args:
            file_path: Path to the file containing the function
            function_name: Name of the function
            function_code: Optional function source code
            
        Returns:
            Dict with 'test_code', 'test_cases', 'coverage_estimate'
        """
        # Read function code if not provided
        if not function_code:
            function_code = self._extract_function_code(file_path, function_name)
            if not function_code:
                return {'error': f'Could not find function {function_name} in {file_path}'}
        
        # Analyze function for edge cases using graph
        edge_cases = []
        if self.graph_store:
            edge_cases = self._identify_edge_cases(file_path, function_name)
        
        # Generate test code using LLM
        test_code = self._generate_test_code(
            file_path,
            function_name,
            function_code,
            edge_cases
        )
        
        if not test_code:
            return {'error': 'Failed to generate test code'}
        
        # Parse generated tests
        test_cases = self._parse_test_cases(test_code)
        
        return {
            'function_name': function_name,
            'file_path': file_path,
            'test_code': test_code,
            'test_cases': test_cases,
            'edge_cases_covered': len(edge_cases),
            'estimated_coverage': min(100, 60 + (len(test_cases) * 10))  # Rough estimate
        }

    def _extract_function_code(self, file_path: str, function_name: str) -> Optional[str]:
        """Extract source code for a specific function."""
        full_path = self.repo_path / file_path
        if not full_path.exists():
            return None
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                source = f.read()
            
            tree = ast.parse(source)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == function_name:
                    # Extract function code
                    return ast.get_source_segment(source, node)
            
            return None
        except Exception as exc:
            logger.error(f"Failed to extract function code: {exc}")
            return None

    def _identify_edge_cases(self, file_path: str, function_name: str) -> List[str]:
        """Use graph analysis to identify edge cases."""
        if not self.graph_store:
            return []
        
        try:
            # Query graph for function parameters and branches
            query = """
            MATCH (f:Function {name: $function_name})-[:DEFINED_IN]->(file:File {path: $file_path})
            OPTIONAL MATCH (f)-[:HAS_PARAMETER]->(param)
            OPTIONAL MATCH (f)-[:HAS_BRANCH]->(branch)
            RETURN 
                collect(param.name) as parameters,
                collect(branch.type) as branches
            """
            
            results = self.graph_store.query(query, {
                'function_name': function_name,
                'file_path': file_path
            })
            
            if not results:
                return []
            
            record = results[0]
            parameters = record.get('parameters', [])
            branches = record.get('branches', [])
            
            # Generate edge case descriptions
            edge_cases = []
            
            if parameters:
                edge_cases.append(f"Test with None for parameters: {', '.join(parameters)}")
                edge_cases.append(f"Test with empty values for parameters: {', '.join(parameters)}")
            
            if 'if' in branches:
                edge_cases.append("Test both if-branches (true and false)")
            
            if 'for' in branches or 'while' in branches:
                edge_cases.append("Test with empty collection")
                edge_cases.append("Test with single item collection")
            
            return edge_cases
        except Exception as exc:
            logger.error(f"Edge case identification failed: {exc}")
            return []

    def _generate_test_code(
        self,
        file_path: str,
        function_name: str,
        function_code: str,
        edge_cases: List[str]
    ) -> Optional[str]:
        """Use LLM to generate test code."""
        # Determine test framework
        test_framework = "pytest" if file_path.endswith('.py') else "jest"
        
        prompt = f"""Generate comprehensive unit tests for the following function:

**File:** {file_path}
**Function:** {function_name}

**Function Code:**
```python
{function_code}
```

**Edge Cases to Cover:**
{chr(10).join(f'- {case}' for case in edge_cases) if edge_cases else '- Standard happy path\n- Error cases\n- Boundary conditions'}

Generate {test_framework} tests that:
1. Cover all identified edge cases
2. Test happy path scenarios
3. Test error handling
4. Use descriptive test names
5. Include assertions for expected behavior

Provide only the test code, no explanations.
"""
        
        try:
            response = self.chat.invoke([{"role": "user", "content": prompt}])
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            # Extract code block
            import re
            match = re.search(r'```(?:python)?\n(.*?)\n```', response_text, re.DOTALL)
            if match:
                return match.group(1)
            
            # If no code block, assume entire response is code
            return response_text
        except Exception as exc:
            logger.error(f"Test code generation failed: {exc}")
            return None

    def _parse_test_cases(self, test_code: str) -> List[str]:
        """Extract test case names from generated code."""
        test_cases = []
        
        try:
            tree = ast.parse(test_code)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if node.name.startswith('test_'):
                        test_cases.append(node.name)
        except Exception as exc:
            logger.debug(f"Failed to parse test cases: {exc}")
        
        return test_cases

    def validate_tests(self, test_code: str, test_framework: str = "pytest") -> Dict[str, Any]:
        """
        Validate that generated tests are syntactically correct and runnable.
        
        Args:
            test_code: Generated test code
            test_framework: Testing framework (pytest/jest)
            
        Returns:
            Dict with 'valid', 'syntax_errors', 'warnings'
        """
        # Syntax check
        try:
            ast.parse(test_code)
            syntax_valid = True
            syntax_errors = []
        except SyntaxError as exc:
            syntax_valid = False
            syntax_errors = [str(exc)]
        
        # TODO: Actually run tests in isolated environment
        
        return {
            'valid': syntax_valid,
            'syntax_errors': syntax_errors,
            'warnings': [],
            'can_run': syntax_valid  # Would check actual execution
        }

    def generate_tests_for_file(self, file_path: str) -> Dict[str, Any]:
        """
        Generate tests for all functions in a file with
 low coverage.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Dict with generated tests for each function
        """
        full_path = self.repo_path / file_path
        if not full_path.exists():
            return {'error': f'File not found: {file_path}'}
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                source = f.read()
            
            tree = ast.parse(source)
            
            # Find all function definitions
            functions = []
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    # Skip private functions and test functions
                    if not node.name.startswith('_') and not node.name.startswith('test_'):
                        functions.append(node.name)
            
            # Generate tests for each function
            results = {}
            for func_name in functions:
                test_result = self.generate_tests_for_function(file_path, func_name)
                if 'error' not in test_result:
                    results[func_name] = test_result
            
            return {
                'file_path': file_path,
                'total_functions': len(functions),
                'tests_generated': len(results),
                'results': results
            }
        except Exception as exc:
            logger.error(f"Test generation for file failed: {exc}")
            return {'error': str(exc)}
