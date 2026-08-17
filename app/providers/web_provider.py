from agno.tools.duckduckgo import DuckDuckGoTools

from app.providers.base_provider import BaseProvider


class WebProvider(BaseProvider):
    """Web search and scraping provider.

    Uses DuckDuckGo for free web search (no API key required).
    Can be upgraded to Firecrawl for scraping if FIRECRAWL_API_KEY is provided.
    """

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

    async def search_web(self, query: str, max_results: int = 5) -> str:
        """Search the web for information.

        Args:
            query: The search query string.
            max_results: Maximum number of results to return.

        Returns:
            Formatted search results with titles, URLs, and snippets.
        """
        try:
            tools = DuckDuckGoTools()
            results = await tools.search(query, max_results=max_results)
            if not results or isinstance(results, str):
                return f"Search results for '{query}':\n{results}" if results else f"No results found for '{query}'."
            return f"Search results for '{query}':\n{str(results)}"
        except Exception as e:
            return f"Web search error: {str(e)}"
