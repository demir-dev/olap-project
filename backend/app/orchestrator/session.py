"""
In-memory session context store.

Each session tracks:
  - Conversation turns (message, intent, entities, result summary)
  - Resolved/sticky context (active dimension filters that persist between turns)
  - Timestamps for TTL-based eviction
"""

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from app.config import settings

logger = logging.getLogger(__name__)

_store: dict[str, "SessionContext"] = {}
_store_lock = threading.Lock()


@dataclass
class ConversationTurn:
    turn_id: int
    message: str
    intent: str
    entities: dict[str, Any]
    sql_query: str | None
    data_summary: str          # Abbreviated summary (not full rows — bounded memory)
    narrative: str
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class SessionContext:
    session_id: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_active: datetime = field(default_factory=datetime.utcnow)
    turns: list[ConversationTurn] = field(default_factory=list)
    resolved_context: dict[str, Any] = field(default_factory=dict)

    def add_turn(self, turn: ConversationTurn) -> None:
        self.turns.append(turn)
        if len(self.turns) > settings.max_session_turns:
            self.turns.pop(0)
        self.last_active = datetime.utcnow()

    def last_n_turns(self, n: int = 3) -> list[ConversationTurn]:
        return self.turns[-n:] if self.turns else []

    def update_context(self, entities: dict[str, Any]) -> None:
        """
        Merge new entities into the sticky context.
        Explicit new values override previous ones; empty lists do NOT clear old values.
        """
        overrideable = {
            "regions":           "region",
            "categories":        "category",
            "years":             "year",
            "quarters":          "quarter",
            "months":            "month",
            "customer_segments": "customer_segment",
            "measures":          "measure",
        }
        for entity_key, ctx_key in overrideable.items():
            val = entities.get(entity_key)
            if val:  # Only update if new value present
                # Take first value if it's a list, otherwise use the value directly
                if isinstance(val, list) and len(val) > 0:
                    self.resolved_context[ctx_key] = val[0]
                elif not isinstance(val, list):
                    self.resolved_context[ctx_key] = val

        # Track last dimension for drill-down/roll-up context
        dimensions = entities.get("dimensions")
        if dimensions:
            if isinstance(dimensions, list) and len(dimensions) > 0:
                self.resolved_context["last_dimension"] = dimensions[0]
            elif isinstance(dimensions, str):
                self.resolved_context["last_dimension"] = dimensions

        # Build active_filters from resolved_context - ensure all filters are included
        filter_map = {
            "region":           "region",
            "category":         "category",
            "year":             "year",
            "quarter":          "quarter",
            "month":            "month",
            "customer_segment": "customer_segment",
        }
        active_filters = {}
        for ctx_key, filter_key in filter_map.items():
            if ctx_key in self.resolved_context:
                active_filters[filter_key] = self.resolved_context[ctx_key]
        self.resolved_context["active_filters"] = active_filters

    def is_expired(self) -> bool:
        ttl = timedelta(minutes=settings.session_ttl_minutes)
        return datetime.utcnow() - self.last_active > ttl

    def get_context_summary(self, n_turns: int = 3) -> str:
        """Return a brief text summary of recent turns for LLM prompts."""
        if not self.turns:
            return ""
        lines = []
        for t in self.last_n_turns(n_turns):
            lines.append(f"- Turn {t.turn_id}: \"{t.message}\" (intent: {t.intent})")
        active = self.resolved_context.get("active_filters", {})
        if active:
            filter_str = ", ".join(f"{k}={v}" for k, v in active.items())
            lines.append(f"  Active filters: {filter_str}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_or_create_session(session_id: str | None = None) -> SessionContext:
    """Return an existing session or create a new one."""
    with _store_lock:
        if session_id and session_id in _store:
            ctx = _store[session_id]
            ctx.last_active = datetime.utcnow()
            return ctx
        new_id = session_id or str(uuid4())
        ctx = SessionContext(session_id=new_id)
        _store[new_id] = ctx
        return ctx


def active_session_count() -> int:
    with _store_lock:
        return len(_store)


def evict_expired_sessions() -> int:
    """Remove expired sessions. Returns the number evicted."""
    with _store_lock:
        expired = [sid for sid, ctx in _store.items() if ctx.is_expired()]
        for sid in expired:
            del _store[sid]
        if expired:
            logger.info("Evicted %d expired session(s)", len(expired))
        return len(expired)
