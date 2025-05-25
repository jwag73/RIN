"""Unit‑tests for src.rin.model_client.ModelClient.

Focus areas
-----------
1. Construction / context‑manager behaviour
2. Prompt builders produce expected scaffolding strings
3. Command parsing helpers
4. High‑level request_* methods (with _make_api_call monkey‑patched)

The real HTTP layer is stubbed, so no network traffic occurs.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import List, Tuple

import pytest

from src.rin.config import RinConfig
from src.rin.model_client import ModelClient, ModelCommand

# --------------------------------------------------------------------------------------
# Test helpers
# --------------------------------------------------------------------------------------

class DummySession:  # Minimal stand‑in for aiohttp.ClientSession
    def __init__(self):
        self.closed: bool = False
        self.close_called: bool = False

    async def close(self):
        self.close_called = True
        self.closed = True

    # Support `async with DummySession(): ...` signature if needed (not used here)
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()


@pytest.fixture()
def sample_tokens() -> List[Tuple[str, str]]:
    """Return a minimal tokenised stream for prompts / parsing."""
    return [
        ("00000", "bad"),
        ("00001", " "),
        ("00002", "python"),
        ("00003", " code"),
        ("00004", " here"),
        ("00005", "\n"),
    ]


@pytest.fixture()
def default_config() -> RinConfig:
    return RinConfig()  # relies on defaults inside config.py


# --------------------------------------------------------------------------------------
# 1. Construction & context management
# --------------------------------------------------------------------------------------


def test_model_client_instantiation(default_config):
    client = ModelClient(default_config)
    assert client.config is default_config
    assert client._session is None
    assert client._owns_session is True


def test_model_client_external_session(default_config):
    ext_session = DummySession()
    client = ModelClient(default_config, session=ext_session)
    assert client._session is ext_session
    assert client._owns_session is False


@pytest.mark.asyncio
async def test_model_client_async_context_manager_owns_session(monkeypatch, default_config):
    created_sessions = []

    async def fake_session_ctor():
        sess = DummySession()
        created_sessions.append(sess)
        return sess

    # Patch aiohttp.ClientSession to our dummy factory
    # Suggested change
    monkeypatch.setattr("src.rin.model_client.aiohttp.ClientSession", lambda: DummySession())

    async with ModelClient(default_config) as client:
        # The client should now have a session created
        assert client._session is not None
        assert isinstance(client._session, DummySession)
        assert client._session.closed is False

    # On exit the session should have been closed because the client owned it.
    created = client._session  # type: ignore
    assert created.close_called is True
    assert created.closed is True


@pytest.mark.asyncio
async def test_model_client_async_context_manager_external_session(default_config):
    ext_session = DummySession()
    async with ModelClient(default_config, session=ext_session) as client:
        assert client._session is ext_session
    # external session must **not** be closed by client
    assert ext_session.close_called is False
    assert ext_session.closed is False


# --------------------------------------------------------------------------------------
# 2. Prompt construction helpers
# --------------------------------------------------------------------------------------


def test_construct_shot0_prompt_format(default_config, sample_tokens):
    client = ModelClient(default_config)
    prompt = client._construct_shot0_prompt(sample_tokens)
    assert isinstance(prompt, str)
    # Check token rendering and sentinel strings
    assert "System Prompt (Shot-0)" in prompt
    for token_id, token_text in sample_tokens:
        assert f"[{token_id}]" in prompt
        # only check token id presence – text may contain spaces / newlines
    assert "OUTPUT RULES" in prompt


def test_construct_shot1_prompt_includes_context(default_config, sample_tokens):
    client = ModelClient(default_config)
    prev_cmds = [
        {"command": "INSERT_FENCE_START", "token_id": "00000", "lang": "python"},
        {"command": "INSERT_FENCE_END", "token_id": "00005"},
    ]
    err_ctx = "Fence parity mismatch: expected 2, got 1."
    prompt = client._construct_shot1_prompt(sample_tokens, prev_cmds, err_ctx)
    assert "System Prompt (Shot-1)" in prompt
    # the previous commands should appear as strings
    for cmd in prev_cmds:
        assert client._model_command_to_str(cmd) in prompt
    assert err_ctx in prompt
    assert "OUTPUT RULES" in prompt


def test_construct_big_model_prompt_structure(default_config, sample_tokens):
    client = ModelClient(default_config)
    prompt = client._construct_big_model_prompt(sample_tokens)
    assert "System Prompt (Big Model)" in prompt
    assert "OUTPUT RULES" in prompt


# --------------------------------------------------------------------------------------
# 3. Parsing helpers
# --------------------------------------------------------------------------------------


def test_parse_valid_commands():
    raw = (
        "INSERT_FENCE_START 00001 python\n"
        "INSERT_FENCE_END 00005\n"
        "INSERT_FENCE_START 00010 javascript with spaces\n"
    )
    cmds = ModelClient._parse_model_commands(raw)
    assert cmds == [
        {"command": "INSERT_FENCE_START", "token_id": "00001", "lang": "python"},
        {"command": "INSERT_FENCE_END", "token_id": "00005"},
        {
            "command": "INSERT_FENCE_START",
            "token_id": "00010",
            "lang": "javascript with spaces",
        },
    ]


def test_parse_empty_string():
    assert ModelClient._parse_model_commands("") == []


def test_parse_string_with_whitespace():
    raw = "\n  \nINSERT_FENCE_START 00001 python\n  "
    cmds = ModelClient._parse_model_commands(raw)
    assert cmds == [{"command": "INSERT_FENCE_START", "token_id": "00001", "lang": "python"}]


def test_parse_malformed_commands():
    raw = (
        "INSERT_FENCE_START 00001\n"  # missing lang
        "INVALID_COMMAND 123\n"
        "INSERT_FENCE_END\n"  # missing token id
    )
    assert ModelClient._parse_model_commands(raw) == []


def test_parse_mixed_valid_and_invalid():
    raw = (
        "INSERT_FENCE_START 00002 text\n"
        "INSERT_FENCE_START 00001\n"  # invalid (no lang)
        "INSERT_FENCE_END 00003\n"
        "GARBAGE LINE\n"
    )
    cmds = ModelClient._parse_model_commands(raw)
    assert cmds == [
        {"command": "INSERT_FENCE_START", "token_id": "00002", "lang": "text"},
        {"command": "INSERT_FENCE_END", "token_id": "00003"},
    ]


# --------------------------------------------------------------------------------------
# 4. _model_command_to_str
# --------------------------------------------------------------------------------------


def test_model_command_to_str_start_fence():
    cmd = {"command": "INSERT_FENCE_START", "token_id": "00012", "lang": "python"}
    out = ModelClient._model_command_to_str(cmd)
    assert out == "INSERT_FENCE_START 00012 python"


def test_model_command_to_str_start_fence_no_lang():
    cmd = {"command": "INSERT_FENCE_START", "token_id": "00012", "lang": ""}
    assert ModelClient._model_command_to_str(cmd) == "INSERT_FENCE_START 00012"


def test_model_command_to_str_end_fence():
    cmd = {"command": "INSERT_FENCE_END", "token_id": "00020"}
    assert ModelClient._model_command_to_str(cmd) == "INSERT_FENCE_END 00020"


def test_model_command_to_str_empty_dict_raises_keyerror():
    """An empty dict lacks the required 'command' key → KeyError."""
    import pytest
    with pytest.raises(KeyError):
        ModelClient._model_command_to_str({})


def test_model_command_to_str_unknown_opcode_returns_empty_string():
    """Unknown command opcode should serialize to an empty string."""
    unknown_cmd = {"command": "FLY_TO_THE_MOON", "token_id": "00007"}
    assert ModelClient._model_command_to_str(unknown_cmd) == ""




# --------------------------------------------------------------------------------------
# 5. High‑level request_* helpers (monkey‑patch _make_api_call)
# --------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_shot0_flow(monkeypatch, default_config, sample_tokens):
    expected_raw = "INSERT_FENCE_START 00000 python\nINSERT_FENCE_END 00005"
    # Capture call args via closure
    called = {}

    async def fake_api(self, model_name: str, prompt: str):  # noqa: ANN001
        called["model_name"] = model_name
        called["prompt_contains"] = "System Prompt (Shot-0)" in prompt
        return expected_raw

    monkeypatch.setattr(ModelClient, "_make_api_call", fake_api)

    async with ModelClient(default_config) as client:
        result = await client.request_shot0(sample_tokens)

    assert called["model_name"] == default_config.shot0_model
    assert called["prompt_contains"] is True
    assert result == [
        {"command": "INSERT_FENCE_START", "token_id": "00000", "lang": "python"},
        {"command": "INSERT_FENCE_END", "token_id": "00005"},
    ]


@pytest.mark.asyncio
async def test_request_shot1_flow(monkeypatch, default_config, sample_tokens):
    expected_raw = "INSERT_FENCE_START 00000 python\nINSERT_FENCE_END 00005"
    called = {}

    async def fake_api(self, model_name: str, prompt: str):  # noqa: ANN001
        called["model_name"] = model_name
        called["prompt_contains"] = "System Prompt (Shot-1)" in prompt
        return expected_raw

    monkeypatch.setattr(ModelClient, "_make_api_call", fake_api)

    previous_cmds = [
        {"command": "INSERT_FENCE_START", "token_id": "00000", "lang": "python"},
    ]

    async with ModelClient(default_config) as client:
        result = await client.request_shot1(sample_tokens, previous_cmds, "error msg")

    assert called["model_name"] == default_config.shot1_model
    assert called["prompt_contains"] is True
    assert result and result[0]["command"] == "INSERT_FENCE_START"


@pytest.mark.asyncio
async def test_request_big_model_flow(monkeypatch, default_config, sample_tokens):
    expected_raw = "INSERT_FENCE_START 00000 python\nINSERT_FENCE_END 00005"
    called = {}

    async def fake_api(self, model_name: str, prompt: str):  # noqa: ANN001
        called["model_name"] = model_name
        called["prompt_contains"] = "System Prompt (Big Model)" in prompt
        return expected_raw

    monkeypatch.setattr(ModelClient, "_make_api_call", fake_api)

    async with ModelClient(default_config) as client:
        cmds = await client.request_big_model(sample_tokens)

    assert called["model_name"] == default_config.big_model
    assert called["prompt_contains"] is True
    assert len(cmds) == 2
