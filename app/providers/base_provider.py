"""Company Brain provider layer on top of Agno's real ContextProvider.

Agno 2.7 ships ``agno.context.provider.ContextProvider`` with lifecycle
support Agno already provides for free:

- ``id`` / ``name`` identity (dedupe key for registries)
- ``status()`` / ``astatus()`` health reporting returning ``Status(ok, detail)``
- ``asetup()`` / ``aclose()`` for connection/session management (both no-op by
  default, idempotent, and safe to call on never-initialized providers)
- a natural-language query surface (``query`` / ``aquery`` -> ``Answer``) that
  powers Agno's ``query_<id>`` meta-tool when providers are wired through
  Agno's own context pipeline

Company Brain providers are *tool-first*: their tool functions are extended
directly onto agents in ``app/teams/company_brain_team.py``, and we never
register Agno's ``query_<id>`` meta-tool. So this base keeps our classic
``get_tools()`` / ``get_instructions()`` surface as the required interface,
implements ``query``/``aquery`` as honest stubs, maps ``is_available()`` onto
``status().ok`` (kept because existing code — team wiring, chat, workflows —
still calls it), and lets Gmail/Twilio override ``asetup()``/``aclose()``.
"""

from __future__ import annotations

import logging
from abc import abstractmethod

from agno.context.mode import ContextMode
from agno.context.provider import Answer, ContextProvider, Status

logger = logging.getLogger("company-brain.providers")


class BaseProvider(ContextProvider):
    """Base class for all Company Brain context providers.

    Subclasses ``agno.context.provider.ContextProvider`` while keeping Company
    Brain's tool/instruction wiring surface.
    """

    def __init__(self, provider_id: str, name: str | None = None) -> None:
        # mode=tools: our subclasses expose their underlying tools directly
        # (extended onto agents at build time), not Agno's query_<id> wrapper.
        super().__init__(id=provider_id, name=name or provider_id, mode=ContextMode.tools)

    # ------------------------------------------------------------------
    # Company Brain surface (required)
    # ------------------------------------------------------------------

    @abstractmethod
    def get_tools(self) -> list:
        """Returns a list of tool functions to be added to the agent."""

    @abstractmethod
    def get_instructions(self) -> str:
        """Returns provider-specific system instructions for the agent."""

    # ------------------------------------------------------------------
    # Health (is_available kept as a thin wrapper over status())
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Check if this provider is usable.

        Thin wrapper over :meth:`status` so existing call sites
        (company_brain_team wiring, chat, workflows) keep working.
        """
        return self.status().ok

    async def ais_available(self) -> bool:
        """Async variant of :meth:`is_available`."""
        return (await self.astatus()).ok

    # ------------------------------------------------------------------
    # NL query surface (stubs — Company Brain wires tools directly)
    # ------------------------------------------------------------------

    def _query_hint(self) -> str:
        try:
            names = ", ".join(getattr(t, "__name__", str(t)) for t in self.get_tools())
        except Exception:  # pragma: no cover - defensive
            names = "the provider tools"
        return f"{self.name} exposes direct tools ({names}); call them instead of querying."

    def query(self, question: str, **_) -> Answer:
        """Not used by Company Brain wiring; honest fallback."""
        return Answer(text=self._query_hint())

    async def aquery(self, question: str, **_) -> Answer:
        """Not used by Company Brain wiring; honest fallback."""
        return Answer(text=self._query_hint())
