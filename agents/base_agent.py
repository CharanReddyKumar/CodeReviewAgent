from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Sequence

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from llm_utils import build_chat_model, extract_json_response

logger = logging.getLogger(__name__)


class BaseAutonomousAgent(ABC):
    """
    Base class for autonomous agents that implement a ReAct (Reasoning + Acting) loop.
    """

    MAX_STEPS = 10

    def __init__(
        self,
        name: str,
        role: str,
        *,
        model_name: str = "gemini-1.5-pro",
        tools: Optional[Sequence[Any]] = None,
    ):
        self.name = name
        self.role = role
        self.tools = {t.name: t for t in tools} if tools else {}
        self.chat = build_chat_model(task=name)
        self.memory: List[BaseMessage] = []

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return the system prompt for this agent."""
        pass

    def step(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute one step of the agent's loop.
        """
        self.memory = state.get("memory", [])
        
        # 1. Observe (Input)
        observation = self.observe(state)
        
        # 2. Think (Reasoning)
        thought = self.think(observation)
        
        # 3. Act (Tool Call or Finish)
        action = self.decide_action(thought)
        
        result = self.act(action)
        
        # Update state
        new_memory = self.memory + [
            HumanMessage(content=f"Observation: {observation}"),
            SystemMessage(content=f"Thought: {thought}\nAction: {action}\nResult: {result}")
        ]
        
        return {
            **state,
            "memory": new_memory,
            "last_action": action,
            "last_result": result,
            "done": action.get("type") == "finish"
        }

    def observe(self, state: Dict[str, Any]) -> str:
        """
        Process the current state into a text observation.
        """
        # Default implementation: just dump the state
        return str(state)

    def think(self, observation: str) -> str:
        """
        Ask the LLM to reason about the observation.
        """
        messages = [
            SystemMessage(content=self.get_system_prompt()),
            *self.memory,
            HumanMessage(content=f"Observation: {observation}\nWhat should I do next?")
        ]
        response = self.chat.invoke(messages)
        return response.content

    def decide_action(self, thought: str) -> Dict[str, Any]:
        """
        Parse the LLM's thought into a structured action.
        Expected format: JSON block with "type", "tool", "args", or "type": "finish", "output": ...
        """
        parsed = extract_json_response(thought)
        if not parsed:
            # Fallback: if no JSON, assume it's a final answer or a continuation
            return {"type": "finish", "output": thought}
        
        if isinstance(parsed, list):
            parsed = parsed[0]
            
        return parsed

    def act(self, action: Dict[str, Any]) -> Any:
        """
        Execute the chosen action.
        """
        action_type = action.get("type")
        
        if action_type == "finish":
            return action.get("output")
            
        if action_type == "tool":
            tool_name = action.get("tool")
            tool_args = action.get("args", {})
            tool = self.tools.get(tool_name)
            if tool:
                try:
                    return tool.invoke(tool_args)
                except Exception as e:
                    return f"Error executing tool {tool_name}: {e}"
            else:
                return f"Tool {tool_name} not found."
                
        return "Unknown action type."

    def run(self, initial_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run the agent loop until completion or max steps.
        """
        state = initial_state
        for _ in range(self.MAX_STEPS):
            state = self.step(state)
            if state.get("done"):
                break
        return state
