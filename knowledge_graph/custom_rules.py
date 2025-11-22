from __future__ import annotations

import yaml
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class CustomRule:
    """Represents a custom review rule."""
    id: str
    name: str
    pattern: str
    message: str
    severity: str = "medium"
    category: str = "custom"
    languages: List[str] = field(default_factory=lambda: ["*"])
    enabled: bool = True
    auto_fix: Optional[str] = None


class CustomRuleEngine:
    """
    Engine for loading and applying custom code review rules.
    Supports user-defined style guides and team-specific standards.
    """

    def __init__(self, repo_path: Path):
        self.repo_path = Path(repo_path)
        self.rules: List[CustomRule] = []
        self.config_file = self._find_config_file()
        
        if self.config_file:
            self.load_rules()

    def _find_config_file(self) -> Optional[Path]:
        """Find custom rules configuration file in repo."""
        # Check for various config file names
        candidates = [
            '.coderabbit.yaml',
            '.coderabbit.yml',
            '.codereview.yaml',
            '.codereview.yml',
            'code-review-rules.yaml',
            'code-review-rules.yml'
        ]
        
        for candidate in candidates:
            config_path = self.repo_path / candidate
            if config_path.exists():
                logger.info(f"Found custom rules config: {config_path}")
                return config_path
        
        return None

    def load_rules(self) -> int:
        """
        Load custom rules from configuration file.
        
        Returns:
            Number of rules loaded
        """
        if not self.config_file:
            logger.warning("No custom rules config file found")
            return 0
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                if self.config_file.suffix in ['.yaml', '.yml']:
                    config = yaml.safe_load(f)
                else:
                    config = json.load(f)
            
            # Parse rules
            rules_data = config.get('rules', [])
            self.rules = []
            
            for rule_data in rules_data:
                try:
                    rule = CustomRule(
                        id=rule_data['id'],
                        name=rule_data.get('name', rule_data['id']),
                        pattern=rule_data['pattern'],
                        message=rule_data['message'],
                        severity=rule_data.get('severity', 'medium'),
                        category=rule_data.get('category', 'custom'),
                        languages=rule_data.get('languages', ['*']),
                        enabled=rule_data.get('enabled', True),
                        auto_fix=rule_data.get('auto_fix')
                    )
                    
                    if rule.enabled:
                        self.rules.append(rule)
                except KeyError as exc:
                    logger.warning(f"Invalid rule definition (missing {exc}): {rule_data}")
                    continue
            
            logger.info(f"Loaded {len(self.rules)} custom rules from {self.config_file}")
            return len(self.rules)
        except Exception as exc:
            logger.error(f"Failed to load custom rules: {exc}")
            return 0

    def check_file(self, file_path: str, content: str) -> List[Dict[str, Any]]:
        """
        Check a file against all applicable custom rules.
        
        Args:
            file_path: Path to the file being checked
            content: File content
            
        Returns:
            List of findings (violations)
        """
        findings = []
        
        # Determine file language
        file_ext = Path(file_path).suffix
        
        for rule in self.rules:
            # Check if rule applies to this file type
            if not self._rule_applies_to_file(rule, file_ext):
                continue
            
            # Apply rule
            violations = self._apply_rule(rule, file_path, content)
            findings.extend(violations)
        
        return findings

    def _rule_applies_to_file(self, rule: CustomRule, file_ext: str) -> bool:
        """Check if a rule applies to a file based on its extension."""
        if '*' in rule.languages:
            return True
        
        # Map extensions to languages
        ext_to_lang = {
            '.py': 'python',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.java': 'java',
            '.go': 'go',
            '.rb': 'ruby',
            '.php': 'php'
        }
        
        lang = ext_to_lang.get(file_ext, 'unknown')
        return lang in rule.languages

    def _apply_rule(
        self,
        rule: CustomRule,
        file_path: str,
        content: str
    ) -> List[Dict[str, Any]]:
        """
        Apply a single rule to file content.
        
        Args:
            rule: The rule to apply
            file_path: Path to the file
            content: File content
            
        Returns:
            List of violations found
        """
        violations = []
        
        # Simple string pattern matching
        # TODO: Support regex, AST patterns, etc.
        lines = content.splitlines()
        
        for line_num, line in enumerate(lines, start=1):
            if rule.pattern in line:
                violations.append({
                    'rule_id': rule.id,
                    'file_path': file_path,
                    'line': line_num,
                    'severity': rule.severity,
                    'category': rule.category,
                    'message': rule.message,
                    'code_line': line.strip(),
                    'suggested_fix': rule.auto_fix if rule.auto_fix else None
                })
        
        return violations

    def get_rules_summary(self) -> Dict[str, Any]:
        """Get summary of loaded rules."""
        return {
            'total_rules': len(self.rules),
            'enabled_rules': len([r for r in self.rules if r.enabled]),
            'by_severity': self._count_by_severity(),
            'by_category': self._count_by_category(),
            'rules': [
                {
                    'id': rule.id,
                    'name': rule.name,
                    'severity': rule.severity,
                    'category': rule.category
                }
                for rule in self.rules
            ]
        }

    def _count_by_severity(self) -> Dict[str, int]:
        """Count rules by severity."""
        counts = {}
        for rule in self.rules:
            counts[rule.severity] = counts.get(rule.severity, 0) + 1
        return counts

    def _count_by_category(self) -> Dict[str, int]:
        """Count rules by category."""
        counts = {}
        for rule in self.rules:
            counts[rule.category] = counts.get(rule.category, 0) + 1
        return counts

    def add_rule(self, rule: CustomRule) -> bool:
        """
        Add a new rule to the engine.
        
        Args:
            rule: The rule to add
            
        Returns:
            True if added successfully
        """
        # Check for duplicate IDs
        if any(r.id == rule.id for r in self.rules):
            logger.warning(f"Rule with ID {rule.id} already exists")
            return False
        
        self.rules.append(rule)
        logger.info(f"Added custom rule: {rule.id}")
        return True

    def remove_rule(self, rule_id: str) -> bool:
        """
        Remove a rule by ID.
        
        Args:
            rule_id: ID of the rule to remove
            
        Returns:
            True if removed successfully
        """
        original_count = len(self.rules)
        self.rules = [r for r in self.rules if r.id != rule_id]
        
        if len(self.rules) < original_count:
            logger.info(f"Removed custom rule: {rule_id}")
            return True
        
        return False

    def save_rules(self, output_path: Optional[Path] = None) -> bool:
        """
        Save current rules to configuration file.
        
        Args:
            output_path: Optional path to save to (defaults to config_file)
            
        Returns:
            True if saved successfully
        """
        target_path = output_path or self.config_file or  (self.repo_path / '.coderabbit.yaml')
        
        try:
            rules_data = {
                'rules': [
                    {
                        'id': rule.id,
                        'name': rule.name,
                        'pattern': rule.pattern,
                        'message': rule.message,
                        'severity': rule.severity,
                        'category': rule.category,
                        'languages': rule.languages,
                        'enabled': rule.enabled,
                        **(('auto_fix', rule.auto_fix) if rule.auto_fix else {})
                    }
                    for rule in self.rules
                ]
            }
            
            with open(target_path, 'w', encoding='utf-8') as f:
                yaml.dump(rules_data, f, default_flow_style=False, sort_keys=False)
            
            logger.info(f"Saved {len(self.rules)} rules to {target_path}")
            return True
        except Exception as exc:
            logger.error(f"Failed to save rules: {exc}")
            return False
