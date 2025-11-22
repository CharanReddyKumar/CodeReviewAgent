import unittest
from unittest.mock import MagicMock, patch
from agents.base_agent import BaseAutonomousAgent
from agents.llm_repo_agent import LLMRepoAgent

class ConcreteTestAgent(BaseAutonomousAgent):
    def get_system_prompt(self) -> str:
        return "You are a test agent."

class TestBaseAutonomousAgent(unittest.TestCase):
    def setUp(self):
        self.agent = ConcreteTestAgent("TestAgent", "Tester")
        self.agent.chat = MagicMock()

    def test_step_cycle(self):
        # Mock LLM response
        self.agent.chat.invoke.return_value.content = '{"type": "finish", "output": "Done"}'
        
        state = {"memory": []}
        new_state = self.agent.step(state)
        
        self.assertTrue(new_state["done"])
        self.assertEqual(new_state["last_result"], "Done")

class TestLLMRepoAgent(unittest.TestCase):
    def setUp(self):
        self.agent = LLMRepoAgent(repo_path="/tmp", name="RepoAgent", specialty="Security")
        self.agent.chat = MagicMock()

    def test_observe(self):
        state = {"commit": MagicMock(summary="Fix bug"), "last_result": "Found issue"}
        obs = self.agent.observe(state)
        self.assertIn("Fix bug", obs)
        self.assertIn("Found issue", obs)

if __name__ == "__main__":
    unittest.main()
