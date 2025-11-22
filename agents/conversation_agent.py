from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from pathlib import Path

from agents.base_agent import BaseAutonomousAgent
from llm_utils import build_chat_model, safe_parse_json
from memory import session_memory

logger = logging.getLogger(__name__)


class ConversationAgent(BaseAutonomousAgent):
    """
    Conversational AI agent that allows developers to ask questions about findings.
    Maintains context across PR comments and uses graph reasoning for evidence.
    """

    def __init__(self, repo_path: Path, graph_store=None):
        super().__init__(
            name="conversation",
            role="Interactive code review assistant"
        )
        self.repo_path = repo_path
        self.graph_store = graph_store
        self.conversation_history: List[Dict[str, str]] = []

    def get_system_prompt(self) -> str:
        return (
            "You are an expert code review assistant with deep knowledge of the codebase. "
            "Your role is to answer developer questions about code review findings, explain why "
            "issues were flagged, and provide context-aware guidance.\n\n"
            "When answering:\n"
            "1. Be concise but thorough\n"
            "2. Reference specific code lines and files\n"
            "3. Use graph evidence when available\n"
            "4. Explain the 'why' behind findings\n"
            "5. Suggest alternatives when appropriate\n\n"
            "If you don't have enough context, ask clarifying questions."
        )

    def answer_question(
        self,
        question: str,
        finding: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        repo_reference: Optional[str] = None
    ) -> str:
        """
        Answer a developer's question about a finding or code review.
        
        Args:
            question: The developer's question
            finding: Optional finding dict that the question is about
            context: Optional additional context (file contents, graph data)
            repo_reference: Repository reference for memory lookup
            
        Returns:
            Natural language answer
        """
        # Build conversation context
        messages = [{"role": "system", "content": self.get_system_prompt()}]
        
        # Add conversation history
        for exchange in self.conversation_history[-5:]:  # Last 5 exchanges
            messages.append({"role": "user", "content": exchange["question"]})
            messages.append({"role": "assistant", "content": exchange["answer"]})
        
        # Build current question context
        question_context = f"Question: {question}\n\n"
        
        if finding:
            question_context += self._format_finding_context(finding)
        
        if context:
            if "graph_evidence" in context:
                question_context += f"\n### Graph Evidence:\n{context['graph_evidence']}\n"
            if "file_content" in context:
                question_context += f"\n### Relevant Code:\n```\n{context['file_content']}\n```\n"
        
        # Add recent review memory
        if repo_reference:
            recent_memory = session_memory.load_recent(repo_reference, limit=3)
            if recent_memory:
                question_context += "\n### Recent Review History:\n"
                for mem in recent_memory:
                    question_context += f"- {mem.get('type', 'review')}: {str(mem)[:100]}...\n"
        
        messages.append({"role": "user", "content": question_context})
        
        # Get answer from LLM
        chat = build_chat_model(task="conversation")
        try:
            response = chat.invoke(messages)
            answer = response.content if hasattr(response, 'content') else str(response)
            
            # Store in conversation history
            self.conversation_history.append({
                "question": question,
                "answer": answer,
                "finding_id": finding.get("id") if finding else None
            })
            
            return answer
        except Exception as exc:
            logger.error(f"Failed to generate answer: {exc}")
            return f"I encountered an error while processing your question: {exc}"

    def _format_finding_context(self, finding: Dict[str, Any]) -> str:
        """Format a finding for inclusion in conversation context."""
        context = "### Finding Context:\n"
        context += f"**File:** {finding.get('file_path', 'unknown')}\n"
        context += f"**Line:** {finding.get('span', 'unknown')}\n"
        context += f"**Severity:** {finding.get('severity', 'info')}\n"
        context += f"**Category:** {finding.get('category', 'general')}\n"
        context += f"**Message:** {finding.get('message', '')}\n"
        
        if finding.get('code_line'):
            context += f"**Code:** `{finding['code_line']}`\n"
        
        if finding.get('recommended_fix'):
            context += f"**Suggested Fix:** {finding['recommended_fix']}\n"
        
        if finding.get('references'):
            context += "**References:**\n"
            for ref_name, ref_value in finding['references'].items():
                context += f"  - {ref_name}: {ref_value}\n"
        
        return context

    def fetch_graph_evidence(self, finding: Dict[str, Any]) -> Optional[str]:
        """
        Query the graph store for evidence related to a finding.
        
        Args:
            finding: The finding to investigate
            
        Returns:
            Formatted graph evidence or None
        """
        if not self.graph_store:
            return None
        
        file_path = finding.get('file_path')
        if not file_path:
            return None
        
        try:
            # Query for related nodes
            query = f"""
            MATCH (f:File {{path: $file_path}})
            OPTIONAL MATCH (f)-[:DEFINES]->(class:Class)
            OPTIONAL MATCH (class)-[:HAS_METHOD]->(method:Function)
            OPTIONAL MATCH (f)-[:DEFINES]->(func:Function)
            OPTIONAL MATCH (func)-[:CALLS]->(called:Function)
            RETURN f, class, method, func, called
            LIMIT 10
            """
            
            results = self.graph_store.query(query, {"file_path": file_path})
            
            if not results:
                return None
            
            # Format results
            evidence = "Graph shows:\n"
            for record in results:
                if record.get('class'):
                    evidence += f"- Class: {record['class'].get('name', 'unknown')}\n"
                if record.get('method'):
                    evidence += f"  - Method: {record['method'].get('name', 'unknown')}\n"
                if record.get('func'):
                    evidence += f"- Function: {record['func'].get('name', 'unknown')}\n"
                if record.get('called'):
                    evidence += f"  - Calls: {record['called'].get('name', 'unknown')}\n"
            
            return evidence
        except Exception as exc:
            logger.error(f"Failed to fetch graph evidence: {exc}")
            return None

    def clear_history(self):
        """Clear conversation history."""
        self.conversation_history = []

    def get_history(self) -> List[Dict[str, str]]:
        """Get conversation history."""
        return self.conversation_history.copy()
