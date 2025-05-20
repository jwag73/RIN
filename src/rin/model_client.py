"""
Thin wrapper around OpenAI calls.
For Sprint 1 we stub it out so tests never touch the network.
"""

import asyncio
from typing import Any, Dict

class ModelClient:
    def __init__(self, config: "RinConfig | None" = None) -> None:
        # Keep the config around for later use (real model calls, retries, etc.)
        self.config = config

    async def complete(self, prompt: str, **kwargs: Dict[str, Any]) -> str:
        """
        Return a canned response that our tests can rely on.
        Later we’ll swap this out (or subclass) to make real OpenAI calls.
        """
        await asyncio.sleep(0)  # keeps the signature truly async
        # A silly deterministic response: just echoes the prompt with fences.
        return f"```python\\n# echoed by fake model\\n{prompt}\\n```"
