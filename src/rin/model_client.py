
"""
Model client for RIN project.

This version integrates asynchronous HTTP handling via ``aiohttp``, detailed
prompt construction for Shot 0 (initial fencing), Shot 1 (self‑fix), and the
Big‑Model fallback as well as parsing of model output into structured
``ModelCommand`` dictionaries.

For Sprint 1 the ``_make_api_call`` method is still a stub returning mock
responses so unit‑tests never touch the network.
"""
from __future__ import annotations

import asyncio
from typing import List, Dict, Optional, Tuple

import aiohttp

from .config import RinConfig

# Placeholder for expected command structure
# Example: {"command": "INSERT_FENCE_START", "token_id": "00003", "lang": "python"}
# Example: {"command": "INSERT_FENCE_END", "token_id": "00014"}
ModelCommand = Dict[str, str]


class ModelClient:
    """Client for interacting with AI models asynchronously."""

    # ---------------------------------------------------------------------
    # Construction / context‑manager helpers
    # ---------------------------------------------------------------------

    def __init__(
        self,
        config: RinConfig,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> None:
        """
        Parameters
        ----------
        config:
            Project‑wide configuration instance giving model names and API keys.
        session:
            Optional externally‑managed :class:`aiohttp.ClientSession`.
            When *None* the client creates (and later closes) a private session.
        """
        self.config: RinConfig = config
        self._session: Optional[aiohttp.ClientSession] = session
        self._owns_session: bool = session is None

    async def __aenter__(self) -> "ModelClient":
        if self._owns_session:
            # Lazily create session only when entering context.
            if self._session is None or self._session.closed:
                self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        # Close the privately‑owned session.
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()

    # ---------------------------------------------------------------------
    # Public high‑level request helpers
    # ---------------------------------------------------------------------

    async def request_shot0(
        self,
        tokenized_text_with_ids: List[Tuple[str, str]],
    ) -> List[ModelCommand]:
        """Initial fencing pass (Shot 0)."""
        prompt = self._construct_shot0_prompt(tokenized_text_with_ids)
        raw = await self._make_api_call(self.config.shot0_model, prompt)
        return self._parse_model_commands(raw)

    async def request_shot1(
        self,
        tokenized_text_with_ids: List[Tuple[str, str]],
        previous_commands: List[ModelCommand],
        error_context: str,
    ) -> List[ModelCommand]:
        """
        Self‑fix pass (Shot 1) executed when Shot 0 produced invalid / mismatched
        fences.  The model receives the original tokens, the commands it
        produced previously and a concise error description so it can repair
        its answer.
        """
        prompt = self._construct_shot1_prompt(
            tokenized_text_with_ids, previous_commands, error_context
        )
        raw = await self._make_api_call(self.config.shot1_model, prompt)
        return self._parse_model_commands(raw)

    async def request_big_model(
        self,
        tokenized_text_with_ids: List[Tuple[str, str]],
    ) -> List[ModelCommand]:
        """Fallback request using a larger model for tricky examples."""
        prompt = self._construct_big_model_prompt(tokenized_text_with_ids)
        raw = await self._make_api_call(self.config.big_model, prompt)
        return self._parse_model_commands(raw)

    # ---------------------------------------------------------------------
    # Low‑level helpers
    # ---------------------------------------------------------------------


    async def _make_api_call(self, model_name: str, prompt: str) -> str:
        """
        Placeholder for making an actual API call.
        ...
        """
        await asyncio.sleep(0.01)

        # Mock responses differentiated by prompt type ---------------------
        if "Shot-0" in prompt:
            # Let's make Shot-0 produce valid fences around "bad python code here"
            # Assuming input "bad python code here\n"
            # Tokens: "bad"(0) " "(1) "python"(2) " "(3) "code"(4) " "(5) "here"(6) "\n"(7)
            # We'll fence the whole "bad python code here" part.
            return "INSERT_FENCE_START 00000 python\nINSERT_FENCE_END 00007" # Fence tokens 0 through 6

        if "Shot-1" in prompt: # This is the self-fix attempt
            # For now, let Shot-1 also produce valid fences for "fixed code"
            # (or keep its existing complex response to see what happens)
            # Let's try to make it "fix" the code by just fencing it again,
            # possibly with different token IDs if the prompt indicates changes.
            # For simplicity in testing the call, let's use a new valid set.
            # This assumes the "fixed" code might be token 0 to 4 for example.
            return "INSERT_FENCE_START 00000 python\nINSERT_FENCE_END 00005" # Example valid fence

        if "Big Model" in prompt:
            # If Shot-0 initially fails parity, Big Model could also provide valid fences
            # For this test, we're focusing on Shot-0 passing G0, then failing G1.
            # So, this path might not be hit if Shot-0 passes G0.
            # If it IS hit, let's make it produce bad parity to ensure G0 fallback also gets tested if needed.
            return "INSERT_FENCE_START 00001 python\nINSERT_FENCE_END 00020" # Keeps original bad parity for fallback test

        return f"```python\\n# echoed by fake model\\n{prompt}\\n```"
# ...

    # ---------------------------------------------------------------------
    # Parse helpers
    # ---------------------------------------------------------------------

    @staticmethod
    def _parse_model_commands(model_output: str) -> List[ModelCommand]:
        """
        Parse the raw string response from the model into a structured list.

        Returns
        -------
        List[ModelCommand]
            Each command is a mapping with keys ``command`` and ``token_id`` as
            well as ``lang`` when applicable.
        """
        commands: List[ModelCommand] = []
        for raw_line in model_output.strip().splitlines():
            parts = raw_line.strip().split()
            if not parts:
                continue

            opcode = parts[0]
            if opcode == "INSERT_FENCE_START" and len(parts) >= 3:
                commands.append(
                    {
                        "command": opcode,
                        "token_id": parts[1],
                        "lang": " ".join(parts[2:]),
                    }
                )
            elif opcode == "INSERT_FENCE_END" and len(parts) >= 2:
                commands.append({"command": opcode, "token_id": parts[1]})
            # else: silently ignore malformed lines – alternatively one could
            # raise or log here depending on overall error handling strategy.
        return commands

    # ---------------------------------------------------------------------
    # Prompt construction helpers
    # ---------------------------------------------------------------------

    # read‑only property because we use it multiple times inside prompt methods
    _SUPPORTED_LANGS: str = (
        "python, json, bash, javascript, typescript, java, csharp, cpp, go, "
        "rust, php, ruby, sql, html, css, text"
    )

    def _construct_shot0_prompt(
        self, tokenized_text_with_ids: List[Tuple[str, str]]
    ) -> str:
        """Prompt for the initial fencing pass."""
        tokens_str = "\n".join(
            f"[{token_id}]{token_text}" for token_id, token_text in tokenized_text_with_ids
        )

        system_prompt = (
            "You are MarkdownFenceBot v1, an AI assistant specialised in "
            "identifying code blocks within a stream of text tokens and "
            "inserting appropriate language‑specific Markdown fences. "
            "Your goal is to accurately demarcate code snippets."
        )

        output_rules = (
            "OUTPUT RULES:\n"
            "- To insert a fence start: INSERT_FENCE_START <token_id> <language_tag>\n"
            "  (Insert a start fence *before* the token with ID <token_id>.)\n"
            "- To insert a fence end: INSERT_FENCE_END <token_id>\n"
            "  (Insert an end fence *before* the token with ID <token_id>.)\n"
            f"Supported language_tag values: {self._SUPPORTED_LANGS}.\n"
            "If unsure about the language, use 'text'.\n"
            "Ensure every INSERT_FENCE_START has a corresponding INSERT_FENCE_END.\n"
            "Return only one command per line."
        )

        return (
            "System Prompt (Shot-0):\n"
            f"{system_prompt}\n\n"
            "User Prompt:\n"
            "TEXT (numbered tokens from input):\n"
            f"{tokens_str}\n\n"
            f"{output_rules}"
        )

    def _construct_shot1_prompt(
        self,
        tokenized_text_with_ids: List[Tuple[str, str]],
        previous_commands: List[ModelCommand],
        error_context: str,
    ) -> str:
        """Prompt for self‑fix pass (Shot 1)."""
        tokens_str = "\n".join(
            f"[{token_id}]{token_text}" for token_id, token_text in tokenized_text_with_ids
        )
        prev_cmds_str = "\n".join(
            self._model_command_to_str(cmd) for cmd in previous_commands
        )

        system_prompt = (
            "You are MarkdownFenceBot v1 running in self‑repair mode. "
            "You previously attempted to fence the provided tokens, but "
            "the command list you produced failed validation.\n"
            "Analyse the error context, then return a corrected list of "
            "commands following the same OUTPUT RULES."
        )

        output_rules = (
            "OUTPUT RULES (same as before):\n"
            "- INSERT_FENCE_START <token_id> <language_tag>\n"
            "- INSERT_FENCE_END <token_id>\n"
            f"Supported languages: {self._SUPPORTED_LANGS}.\n"
            "Only one command per line."
        )

        return (
            "System Prompt (Shot-1):\n"
            f"{system_prompt}\n\n"
            "PREVIOUS COMMANDS:\n"
            f"{prev_cmds_str or '[none]'}\n\n"
            "ERROR CONTEXT:\n"
            f"{error_context or 'n/a'}\n\n"
            "TEXT (numbered tokens from input):\n"
            f"{tokens_str}\n\n"  # Use tokens_str and add newlines
            f"{output_rules}"    # Add the output rules
        )



    @staticmethod
    def _model_command_to_str(command: ModelCommand) -> str:
        """Convert a ModelCommand dict to its string representation for prompts."""
        if command["command"] == "INSERT_FENCE_START":
            return f"{command['command']} {command['token_id']} {command.get('lang', '')}".strip()
        elif command["command"] == "INSERT_FENCE_END":
            return f"{command['command']} {command['token_id']}"
        return "" # Should not happen for valid commands

    def _construct_big_model_prompt(
        self, tokenized_text_with_ids: List[Tuple[str, str]]
    ) -> str:
        """Prompt for the Big Model fallback."""
        tokens_str = "\n".join(
            f"[{token_id}]{token_text}" for token_id, token_text in tokenized_text_with_ids
        )

        system_prompt = (
            "You are MarkdownFenceBot v1 (Big Model instance), an AI assistant "
            "specialised in identifying code blocks within a stream of text "
            "tokens and inserting appropriate language‑specific Markdown fences. "
            "A previous attempt by a smaller model resulted in errors, so you "
            "are being called as a more capable fallback. "
            "Your goal is to accurately demarcate code snippets."
        )

        output_rules = (
            "OUTPUT RULES:\n"
            "- To insert a fence start: INSERT_FENCE_START <token_id> <language_tag>\n"
            "  (Insert a start fence *before* the token with ID <token_id>.)\n"
            "- To insert a fence end: INSERT_FENCE_END <token_id>\n"
            "  (Insert an end fence *before* the token with ID <token_id>.)\n"
            f"Supported language_tag values: {self._SUPPORTED_LANGS}.\n"
            "If unsure about the language, use 'text'.\n"
            "Ensure every INSERT_FENCE_START has a corresponding INSERT_FENCE_END.\n"
            "Return only one command per line."
        )

        return (
            "System Prompt (Big Model):\n"  # Added a unique identifier for this prompt type
            f"{system_prompt}\n\n"
            "User Prompt:\n"
            "TEXT (numbered tokens from input):\n"
            f"{tokens_str}\n\n"
            f"{output_rules}"
        )