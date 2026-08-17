from abc import ABC, abstractmethod


class BaseProvider(ABC):
    """Extended base class for all Company Brain context providers.

    Each provider exposes tools and instructions to agents.
    Pattern inspired by Agno Scout's ContextProvider.
    """

    @abstractmethod
    def get_tools(self) -> list:
        """Returns a list of tool functions to be added to the agent."""
        return []

    @abstractmethod
    def get_instructions(self) -> str:
        """Returns provider-specific system instructions for the agent."""
        return ""

    def is_available(self) -> bool:
        """Check if this provider's required configuration is present."""
        return True
