"""Coach-Agents: typisierte Spezialisten mit erzwungenem JSON-Schema."""
from .base import HAIKU, OPUS, SONNET, AgentError, call_agent, load_prompt

__all__ = ["AgentError", "call_agent", "load_prompt", "HAIKU", "SONNET", "OPUS"]
