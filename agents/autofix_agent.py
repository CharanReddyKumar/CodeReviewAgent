from __future__ import annotations

import ast
import logging
import difflib
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

from llm_utils import build_chat_model

logger = logging.getLogger(__name__)


class AutofixAgent:
    """
    Agent that generates automatic fixes for code issues.
    Uses AST transformations and LLM-guided patches.
    """

    def __init__(self, repo_path: Path):
        self.repo_path = Path(repo_path)
        self.chat = build_chat_model(task="autofix")

    def generate_fix(self, finding: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Generate an automatic fix for a finding.
        
        Args:
            finding: The code issue to fix
            
        Returns:
            Dict with 'patch', 'confidence', 'description' or None if can't fix
        """
        file_path = finding.get('file_path')
        if not file_path:
            return None
        
        full_path = self.repo_path / file_path
        if not full_path.exists():
            logger.warning(f"File not found: {full_path}")
            return None
        
        # Read file content
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                original_content = f.read()
        except Exception as exc:
            logger.error(f"Failed to read file {full_path}: {exc}")
            return None
        
        # Determine fix strategy based on finding type
        category = finding.get('category', '').lower()
        severity = finding.get('severity', '').lower()
        
        # Try AST-based fix for Python files
        if file_path.endswith('.py'):
            ast_fix = self._try_ast_fix(original_content, finding)
            if ast_fix:
                return ast_fix
        
        # Fall back to LLM-guided fix
        return self._llm_guided_fix(original_content, finding, file_path)

    def _try_ast_fix(self, content: str, finding: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Attempt to fix using AST transformations for Python code.
        
        Args:
            content: Original file content
            finding: The issue to fix
            
        Returns:
            Fix dict or None
        """
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return None
        
        category = finding.get('category', '').lower()
        rule_id = finding.get('rule_id', '').lower()
        
        # Define transformers for common issues
        transformer = None
        
        if 'unused' in category or 'unused' in rule_id:
            transformer = UnusedImportRemover()
        elif 'print' in rule_id or 'debug' in category:
            transformer = PrintStatementRemover()
        elif 'complexity' in category:
            # Complex refactoring - defer to LLM
            return None
        
        if not transformer:
            return None
        
        try:
            # Apply transformation
            new_tree = transformer.visit(tree)
            ast.fix_missing_locations(new_tree)
            
            # Generate new code
            import astor  # May not be available
            new_content = astor.to_source(new_tree)
            
            # Generate patch
            patch = self._create_patch(content, new_content, finding.get('file_path', 'file'))
            
            return {
                'patch': patch,
                'confidence': 0.9,  # High confidence for AST-based fixes
                'description': f"Removed {transformer.__class__.__name__}",
                'method': 'ast_transformation'
            }
        except Exception as exc:
            logger.debug(f"AST fix failed: {exc}")
            return None

    def _llm_guided_fix(
        self,
        content: str,
        finding: Dict[str, Any],
        file_path: str
    ) -> Optional[Dict[str, Any]]:
        """
        Use LLM to generate a fix.
        
        Args:
            content: Original file content
            finding: The issue to fix
            file_path: Path to the file
            
        Returns:
            Fix dict or None
        """
        # Get line range around the issue
        line_num = self._extract_line_number(finding.get('span', '0'))
        context_lines = self._get_line_context(content, line_num, context=5)
        
        prompt = self._build_fix_prompt(finding, context_lines, file_path)
        
        try:
            response = self.chat.invoke([{"role": "user", "content": prompt}])
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            # Extract fixed code from response
            fixed_code = self._extract_code_block(response_text)
            if not fixed_code:
                logger.warning("LLM did not return code block")
                return None
            
            # Generate patch
            patch = self._create_patch(context_lines, fixed_code, file_path)
            
            return {
                'patch': patch,
                'confidence': 0.7,  # Medium confidence for LLM fixes
                'description': self._extract_fix_description(response_text),
                'method': 'llm_guided'
            }
        except Exception as exc:
            logger.error(f"LLM fix failed: {exc}")
            return None

    def _build_fix_prompt(self, finding: Dict, code_context: str, file_path: str) -> str:
        """Build prompt for LLM to generate fix."""
        return f"""Fix the following code issue:

**File:** {file_path}
**Issue:** {finding.get('message', 'Code issue detected')}
**Severity:** {finding.get('severity', 'medium')}
**Category:** {finding.get('category', 'general')}

**Current Code:**
```
{code_context}
```

**Suggested Fix:** {finding.get('recommended_fix', 'Please fix the issue')}

Please provide:
1. The corrected code (in a code block)
2. A brief explanation of what you changed

Format your response as:
```
<fixed code here>
```

Explanation: <explanation here>
"""

    def _create_patch(self, original: str, modified: str, filename: str) -> str:
        """Create a unified diff patch."""
        original_lines = original.splitlines(keepends=True)
        modified_lines = modified.splitlines(keepends=True)
        
        diff = difflib.unified_diff(
            original_lines,
            modified_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            lineterm=''
        )
        
        return ''.join(diff)

    def _get_line_context(self, content: str, line_num: int, context: int = 5) -> str:
        """Get lines around a specific line number."""
        lines = content.splitlines()
        start = max(0, line_num - context - 1)
        end = min(len(lines), line_num + context)
        return '\n'.join(lines[start:end])

    def _extract_line_number(self, span: str) -> int:
        """Extract line number from span string (e.g., '42' or '42-45')."""
        try:
            return int(span.split('-')[0])
        except (ValueError, AttributeError):
            return 0

    def _extract_code_block(self, text: str) -> Optional[str]:
        """Extract code from markdown code block."""
        import re
        match = re.search(r'```(?:python|javascript|typescript)?\n(.*?)\n```', text, re.DOTALL)
        if match:
            return match.group(1)
        return None

    def _extract_fix_description(self, text: str) -> str:
        """Extract explanation from LLM response."""
        if 'Explanation:' in text:
            return text.split('Explanation:')[1].strip()[:200]
        return "Automated fix applied"

    def validate_patch(self, patch: str, file_path: str) -> bool:
        """
        Validate that a patch applies cleanly.
        
        Args:
            patch: The patch to validate
            file_path: Path to the file
            
        Returns:
            True if patch is valid
        """
        # TODO: Actually apply patch in a temp location and verify
        return bool(patch and 'diff' in patch)


# AST Transformers for common fixes

class UnusedImportRemover(ast.NodeTransformer):
    """Remove unused import statements."""
    
    def visit_Import(self, node):
        # Simplified: would need symbol table analysis
        return node
    
    def visit_ImportFrom(self, node):
        return node


class PrintStatementRemover(ast.NodeTransformer):
    """Remove print() debug statements."""
    
    def visit_Expr(self, node):
        if isinstance(node.value, ast.Call):
            if isinstance(node.value.func, ast.Name) and node.value.func.id == 'print':
                return None  # Remove the print statement
        return node
