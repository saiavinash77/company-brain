"""Local chat loop — talk to the Top Agent from your terminal.

No Docker, no Postgres, no AgentOS needed. Uses SuperMemory's LocalBackend.
Run:  .venv/Scripts/python -m app.chat
"""
import asyncio
import logging
import sys

from app.agents.top_agent import create_top_agent
from app.memory.super_memory import SuperMemory
from app.providers.memory_provider import MemoryProvider

BANNER = """
==========================================================
  COMPANY BRAIN — local chat (type 'exit' to quit)
==========================================================
"""


async def main() -> None:
    logging.basicConfig(level=logging.WARNING)

    memory = SuperMemory()
    agent = create_top_agent()
    provider = MemoryProvider(memory=memory)
    agent.tools.extend(provider.get_tools())
    agent.instructions.append(provider.get_instructions())

    print(BANNER)
    while True:
        try:
            user_input = input("you > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye!")
            break
        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit", "q"}:
            print("bye!")
            break

        try:
            response = await agent.arun(input=user_input)
            content = getattr(response, "content", None) or response
            print(f"\nbrain > {content}\n")
        except Exception as exc:  # keep the loop alive on errors
            print(f"\n[error] {exc}\n")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
