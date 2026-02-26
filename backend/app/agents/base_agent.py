"""
Base agent abstract class and shared data structures.
All OLAP agents inherit from BaseAgent and implement the execute() method.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class AgentInput:
    """Standardised input passed to every agent."""
    message: str                         # Original user question
    intent: str                          # Classified intent (slice/dice/etc.)
    entities: dict[str, Any]             # Extracted entities: regions, years, measures, etc.
    session_context: dict[str, Any]      # Merged sticky context from prior turns
    schema_summary: str                  # Brief schema description for LLM prompts
    page: int = 1                        # For drill-through pagination


@dataclass
class AgentOutput:
    """Standardised output returned by every agent."""
    sql_query: Optional[str] = None
    data: Optional[dict[str, Any]] = None   # {"columns": [...], "rows": [...], "row_count": N}
    narrative: str = ""
    visualization_hint: Optional[dict[str, Any]] = None
    follow_up_suggestions: list[str] = field(default_factory=list)
    agent_name: str = ""
    error: Optional[str] = None

    def is_success(self) -> bool:
        return self.error is None


class BaseAgent(ABC):
    """
    Abstract base class for all OLAP agents.

    Subclasses must implement execute().
    The name property should return a human-readable agent identifier.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable agent name (used in ChatResponse.agents_used)."""
        ...

    @abstractmethod
    def execute(self, agent_input: AgentInput) -> AgentOutput:
        """
        Process the agent input and return structured output.
        Must not raise exceptions — errors should be captured in AgentOutput.error.
        """
        ...

    def _make_data_payload(
        self, columns: list[str], rows: list[tuple]
    ) -> dict[str, Any]:
        """Helper to build a DataPayload-compatible dict."""
        return {
            "columns": columns,
            "rows": [list(row) for row in rows],
            "row_count": len(rows),
        }

    def _safe_execute(self, agent_input: AgentInput) -> AgentOutput:
        """Wraps execute() and catches all exceptions."""
        try:
            return self.execute(agent_input)
        except Exception as exc:
            return AgentOutput(
                agent_name=self.name,
                error=f"{self.name} failed: {exc}",
            )
