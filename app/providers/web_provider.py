from __future__ import annotations

import logging
import os

import aiohttp
from agno.context.provider import Status

from app.providers.base_provider import BaseProvider

logger = logging.getLogger("company-brain.web")

SERPER_URL = "https://google.serper.dev/search"
SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "")


class WebProvider(BaseProvider):
    """Web search provider.

    Primary: Serper (https://serper.dev — Google results, 2,500 free
    queries/month). Fallback: DuckDuckGo when SERPER_API_KEY is not set, so
    local dev and a missing/empty key never break web search.

    Holds no long-lived connection: inherits the no-op ``asetup()``/``aclose()``
    lifecycle from ContextProvider.
    """

    def __init__(self):
        super().__init__(provider_id="web", name="Web Search")

    def status(self) -> Status:
        if SERPER_API_KEY:
            return Status(ok=True, detail="Serper web search ready (Google results)")
        return Status(ok=True, detail="DuckDuckGo fallback (SERPER_API_KEY not set)")

    async def astatus(self) -> Status:
        return self.status()

    def get_tools(self) -> list:
        return [self.search_web]

    def get_instructions(self) -> str:
        return (
            "You have access to web search capabilities.\n"
            "- Use search_web to find information about competitors, trends, "
            "companies, or any topic that requires up-to-date data.\n"
            "- Always cite your sources when presenting web research results.\n"
            "- For market research, search for both the specific company/topic "
            "and broader industry trends."
        )

    async def _serper_search(self, query: str, max_results: int) -> list[dict]:
        """POST the query to Serper and return organic results."""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                SERPER_URL,
                json={"q": query, "num": max_results},
                headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as res:
                res.raise_for_status()
                data = await res.json()
        organic = data.get("organic") or []
        results = []
        for r in organic[:max_results]:
            results.append(
                {
                    "title": r.get("title", ""),
                    "link": r.get("link", ""),
                    "snippet": r.get("snippet", ""),
                    "date": r.get("date", ""),
                }
            )
        # "answer box"/"knowledge graph" bits are often the juiciest summary
        extras = []
        if data.get("answerBox"):
            extras.append(f"Answer box: {data['answerBox'].get('answer') or data['answerBox'].get('snippet', '')}")
        if data.get("knowledgeGraph"):
            kg = data["knowledgeGraph"]
            extras.append(f"Knowledge graph: {kg.get('title', '')} — {kg.get('description', '')}")
        if extras:
            results.append({"title": "Overview", "link": "", "snippet": " | ".join(extras), "date": ""})
        return results

    async def _ddg_search(self, query: str, max_results: int) -> str:
        from agno.tools.duckduckgo import DuckDuckGoTools

        tools = DuckDuckGoTools()
        # DuckDuckGoTools.web_search is a plain (sync) function in this Agno
        # version — await would raise "object str can't be used in 'await'"
        results = tools.web_search(query, max_results=max_results)
        return f"Search results for '{query}':\n{results}" if results else ""

    async def search_web(self, query: str, max_results: int = 5) -> str:
        """Search the web for information.

        Args:
            query: The search query string.
            max_results: Maximum number of results to return.

        Returns:
            Formatted search results with titles, URLs, and snippets.
        """
        if SERPER_API_KEY:
            try:
                results = await self._serper_search(query, max_results)
                if not results:
                    return f"No results found for '{query}'."
                lines = [f"Search results for '{query}':"]
                for i, r in enumerate(results, 1):
                    lines.append(f"{i}. {r['title']}")
                    if r["link"]:
                        lines.append(f"   URL: {r['link']}")
                    if r["snippet"]:
                        lines.append(f"   {r['snippet']}")
                    if r["date"]:
                        lines.append(f"   Date: {r['date']}")
                return "\n".join(lines)
            except Exception as e:
                logger.warning("Serper search failed (%s) — falling back to DuckDuckGo", e)
        # no key, or Serper errored: DuckDuckGo keeps the agents working
        try:
            fallback = await self._ddg_search(query, max_results)
            return fallback or f"No results found for '{query}'."
        except Exception as e:
            return f"Web search error: {str(e)}"
