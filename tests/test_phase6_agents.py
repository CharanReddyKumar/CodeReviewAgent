import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open
from agents.conversation_agent import ConversationAgent
from agents.autofix_agent import AutofixAgent
from agents.test_generator_agent import TestGeneratorAgent
from knowledge_graph.custom_rules import CustomRuleEngine, CustomRule


class TestPhase6Agents(unittest.TestCase):
    """Test suite for Phase 6 functional supremacy features."""
    
    def setUp(self):
        self.repo_path = Path("/tmp/test_repo")
        self.test_finding = {
            'id': 'test-1',
            'file_path': 'test.py',
            'span': '10',
            'severity': 'medium',
            'category': 'security',
            'message': 'Potential SQL injection',
            'code_line': 'cursor.execute(f"SELECT * FROM users WHERE id={user_id}")',
            'recommended_fix': 'Use parameterized queries',
            'references': {'OWASP': 'SQL Injection Prevention'}
        }

    def test_conversation_agent_initialization(self):
        """Test ConversationAgent can be initialized."""
        agent = ConversationAgent(self.repo_path)
        self.assertEqual(agent.repo_path, self.repo_path)
        self.assertEqual(agent.name, "conversation")
        self.assertIsNotNone(agent.get_system_prompt())

    @patch('agents.conversation_agent.build_chat_model')
    def test_conversation_agent_answer_question(self, mock_chat):
        """Test ConversationAgent can answer questions."""
        # Mock LLM response
        mock_response = MagicMock()
        mock_response.content = "This is flagged because it uses string formatting in SQL queries."
        mock_chat.return_value.invoke.return_value = mock_response
        
        agent = ConversationAgent(self.repo_path)
        answer = agent.answer_question(
            question="Why is this flagged?",
            finding=self.test_finding
        )
        
        self.assertIn("SQL", answer)
        self.assertEqual(len(agent.conversation_history), 1)

    def test_autofix_agent_initialization(self):
        """Test AutofixAgent can be initialized."""
        agent = AutofixAgent(self.repo_path)
        self.assertEqual(agent.repo_path, self.repo_path)

    @patch('builtins.open', new_callable=mock_open, read_data='print("Hello")\nprint("World")')
    @patch('pathlib.Path.exists', return_value=True)
    def test_autofix_agent_llm_guided_fix(self, mock_exists, mock_file):
        """Test AutofixAgent can generate LLM-guided fixes."""
        agent = AutofixAgent(self.repo_path)
        
        finding = {
            'file_path': 'test.py',
            'span': '1',
            'category': 'print',
            'message': 'Avoid print statements',
            'recommended_fix': 'Use logging'
        }
        
        with patch.object(agent, '_llm_guided_fix', return_value={
            'patch': 'diff content',
            'confidence': 0.7,
            'description': 'Replaced print with logging',
            'method': 'llm_guided'
        }):
            fix = agent.generate_fix(finding)
            
            self.assertIsNotNone(fix)
            self.assertEqual(fix['confidence'], 0.7)
            self.assertIn('patch', fix)

    def test_test_generator_initialization(self):
        """Test TestGeneratorAgent can be initialized."""
        agent = TestGeneratorAgent(self.repo_path)
        self.assertEqual(agent.repo_path, self.repo_path)

    def test_test_generator_parse_test_cases(self):
        """Test TestGeneratorAgent can parse test code."""
        agent = TestGeneratorAgent(self.repo_path)
        
        test_code = """
def test_addition():
    assert 1 + 1 == 2

def test_subtraction():
    assert 2 - 1 == 1
"""
        
        test_cases = agent._parse_test_cases(test_code)
        self.assertEqual(len(test_cases), 2)
        self.assertIn('test_addition', test_cases)
        self.assertIn('test_subtraction', test_cases)

    def test_custom_rule_engine_initialization(self):
        """Test CustomRuleEngine can be initialized."""
        engine = CustomRuleEngine(self.repo_path)
        self.assertEqual(engine.repo_path, self.repo_path)

    def test_custom_rule_engine_add_rule(self):
        """Test CustomRuleEngine can add rules."""
        engine = CustomRuleEngine(self.repo_path)
        
        rule = CustomRule(
            id="test-rule",
            name="Test Rule",
            pattern="test_pattern",
            message="Test message",
            severity="high"
        )
        
        result = engine.add_rule(rule)
        self.assertTrue(result)
        self.assertEqual(len(engine.rules), 1)
        
        # Test duplicate prevention
        result = engine.add_rule(rule)
        self.assertFalse(result)
        self.assertEqual(len(engine.rules), 1)

    def test_custom_rule_engine_check_file(self):
        """Test CustomRuleEngine can check files against rules."""
        engine = CustomRuleEngine(self.repo_path)
        
        rule = CustomRule(
            id="no-print",
            name="No Print",
            pattern="print(",
            message="Don't use print",
            severity="medium",
            languages=["python"]
        )
        engine.add_rule(rule)
        
        content = """
def hello():
    print("Hello")
    return "world"
"""
        
        findings = engine.check_file("test.py", content)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]['rule_id'], 'no-print')
        self.assertEqual(findings[0]['line'], 3)

    def test_custom_rule_engine_summary(self):
        """Test CustomRuleEngine provides correct summary."""
        engine = CustomRuleEngine(self.repo_path)
        
        engine.add_rule(CustomRule(
            id="rule-1", name="R1", pattern="p1", message="m1", severity="high"
        ))
        engine.add_rule(CustomRule(
            id="rule-2", name="R2", pattern="p2", message="m2", severity="medium"
        ))
        
        summary = engine.get_rules_summary()
        self.assertEqual(summary['total_rules'], 2)
        self.assertEqual(summary['by_severity']['high'], 1)
        self.assertEqual(summary['by_severity']['medium'], 1)


if __name__ == "__main__":
    unittest.main()
