from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class BaseLLM(ABC):
    @abstractmethod
    def get_tool_calls(
        self,
        question: str,
        redis_context: Dict[str, Any],
        tools: List[Dict[str, Any]],
        tool_history: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Determines which tools to call based on the user's question.
        Returns a list of dictionaries, each containing 'name' and 'arguments'.
        """
        pass

    @abstractmethod
    def generate_answer(
        self,
        question: str,
        redis_context: Dict[str, Any],
        tool_result: str,
        tool_history: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        Generates the final human-readable answer from the question and tool execution output.
        """
        pass
