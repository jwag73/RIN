"""Unit tests for rin.formatter.

Covers:
- segregate_pre_fenced_blocks
- tokenize_unfenced_text
- reconstruct_markdown

The scenarios mirror the testing checklist provided by Johnny.
"""

import textwrap
import pytest

from src.rin.formatter import (
    segregate_pre_fenced_blocks,
    tokenize_unfenced_text,
    reconstruct_markdown,
    FencedBlock,
    Token,
)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _ids_are_sequential(tokens):
    """Utility assertion that token IDs are 0..n-1 in order."""
    ids = [t.id for t in tokens]
    assert ids == list(range(len(tokens))), "Token IDs are not sequential starting from 0"


# --------------------------------------------------------------------------- #
# Tests for segregate_pre_fenced_blocks
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "text, expected_text, expected_blocks",
    [
        ("", "", []),
        ("Just some simple text.", "Just some simple text.", []),
        ("Text with `inline` code but no blocks.", "Text with `inline` code but no blocks.", []),
    ],
)
def test_segregate_trivial_cases(text, expected_text, expected_blocks):
    new_text, blocks = segregate_pre_fenced_blocks(text)
    assert new_text == expected_text
    assert blocks == expected_blocks


def test_segregate_single_python_block():
    src = textwrap.dedent(
        """\
        Intro
        ```python
        print('hi')
        ```
        Outro
        """
    )
    new_text, blocks = segregate_pre_fenced_blocks(src)
    assert "⟦F_BLOCK_0⟧" in new_text
    assert len(blocks) == 1
    block = blocks[0]
    assert block.lang == "python"
    assert block.content == "print('hi')\n"
    assert block.index == 0


def test_segregate_multiple_blocks():
    src = textwrap.dedent(
        """\
        ```python
        a = 1
        ```
        text
        ```
        no_lang
        ```
        more
        ```javascript
        console.log('js')
        ```
        """
    )
    new_text, blocks = segregate_pre_fenced_blocks(src)
    # Placeholders present and ordered
    for idx in range(3):
        assert f"⟦F_BLOCK_{idx}⟧" in new_text
    # Blocks metadata
    assert blocks[0] == FencedBlock("python", "a = 1\n", 0)
    assert blocks[1] == FencedBlock("", "no_lang\n", 1)
    assert blocks[2] == FencedBlock("javascript", "console.log('js')\n", 2)


def test_segregate_block_with_newlines_and_special_chars():
    content = "def foo():\n    return '# → 42'\n"
    src = f"""```python\n{content}```"""
    new_text, blocks = segregate_pre_fenced_blocks(src)
    assert new_text == "⟦F_BLOCK_0⟧"
    assert blocks[0] == FencedBlock("python", content, 0)


@pytest.mark.parametrize(
    "src",
    [
        "```python\nprint('start')\n```text",  # fence at beginning
        "text```python\nprint('end')\n```",    # fence at end
    ],
)
def test_segregate_fences_at_edges(src):
    new_text, blocks = segregate_pre_fenced_blocks(src)
    # Exactly one placeholder should replace the fence.
    assert new_text.count("⟦F_BLOCK_0⟧") == 1
    assert len(blocks) == 1


def test_segregate_text_with_unmatched_backticks():
    src = """``` some code without end fence"""
    new_text, blocks = segregate_pre_fenced_blocks(src)
    # Nothing should be replaced.
    assert new_text == src
    assert blocks == []


# --------------------------------------------------------------------------- #
# Tests for tokenize_unfenced_text
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("text, expected_texts", [
    ("", []),
    ("Hello world!", ["Hello", " ", "world", "!"]),
])
def test_tokenize_basic(text, expected_texts):
    tokens = tokenize_unfenced_text(text)
    assert [t.text for t in tokens] == expected_texts
    _ids_are_sequential(tokens)


def test_tokenize_text_with_sentinels():
    text = "Pre ⟦F_BLOCK_0⟧ post."
    tokens = tokenize_unfenced_text(text)
    expected = ["Pre", " ", "⟦F_BLOCK_0⟧", " ", "post", "."]
    assert [t.text for t in tokens] == expected
    _ids_are_sequential(tokens)


def test_tokenize_only_sentinels():
    tokens = tokenize_unfenced_text("⟦F_BLOCK_0⟧⟦F_BLOCK_1⟧")
    assert [t.text for t in tokens] == ["⟦F_BLOCK_0⟧", "⟦F_BLOCK_1⟧"]
    _ids_are_sequential(tokens)


def test_tokenize_sentinels_with_adjacent_text():
    tokens = tokenize_unfenced_text("Word⟦F_BLOCK_0⟧Word")
    assert [t.text for t in tokens] == ["Word", "⟦F_BLOCK_0⟧", "Word"]
    _ids_are_sequential(tokens)


def test_tokenize_mixed_content():
    text = "A  b\n⟦F_BLOCK_2⟧!\tZ"
    tokens = tokenize_unfenced_text(text)
    # Verify sentinel is intact and whitespace/punctuation captured separately
    assert "⟦F_BLOCK_2⟧" in [t.text for t in tokens]
    _ids_are_sequential(tokens)


def test_tokenize_unicode_text():
    text = "π = 3.14 — 測試"
    tokens = tokenize_unfenced_text(text)
    assert "π" in [t.text for t in tokens]
    assert "測試" in [t.text for t in tokens]
    _ids_are_sequential(tokens)


# --------------------------------------------------------------------------- #
# Tests for reconstruct_markdown
# --------------------------------------------------------------------------- #

def test_reconstruct_empty_tokens_and_blocks():
    assert reconstruct_markdown([], []) == ""


def test_reconstruct_tokens_no_placeholders():
    tokens = [Token(0, "Hello"), Token(1, " "), Token(2, "world")]
    assert reconstruct_markdown(tokens, []) == "Hello world"


def test_reconstruct_single_placeholder():
    tokens = [Token(0, "⟦F_BLOCK_0⟧")]
    blocks = [FencedBlock("python", "print(\"hi\")\n", 0)]
    expected = "```python\nprint(\"hi\")\n```"
    assert reconstruct_markdown(tokens, blocks) == expected


def test_reconstruct_multiple_placeholders():
    tokens = [
        Token(0, "⟦F_BLOCK_0⟧"), Token(1, " "),
        Token(2, "and"), Token(3, " "), Token(4, "⟦F_BLOCK_1⟧")
    ]
    blocks = [
        FencedBlock("", "code0\n", 0),
        FencedBlock("bash", "echo ok\n", 1),
    ]
    expected = "```\ncode0\n``` and ```bash\necho ok\n```"
    assert reconstruct_markdown(tokens, blocks) == expected


def test_reconstruct_text_around_placeholders():
    tokens = [
        Token(0, "Code:"), Token(1, " "), Token(2, "⟦F_BLOCK_0⟧"), Token(3, ". Done.")
    ]
    blocks = [FencedBlock("python", "pass\n", 0)]
    expected = "Code: ```python\npass\n```. Done."
    assert reconstruct_markdown(tokens, blocks) == expected


def test_reconstruct_block_no_lang():
    tokens = [Token(0, "⟦F_BLOCK_0⟧")]
    blocks = [FencedBlock("", "text\n", 0)]
    expected = "```\ntext\n```"  # note the newline after opening fence
    assert reconstruct_markdown(tokens, blocks) == expected


def test_reconstruct_placeholder_out_of_bounds_raises():
    tokens = [Token(0, "⟦F_BLOCK_0⟧")]
    with pytest.raises(IndexError):
        reconstruct_markdown(tokens, [])  # no blocks provided


def test_reconstruct_malformed_placeholder_token_literal():
    tokens = [Token(0, "⟦F_BLOCK_A⟧")]
    result = reconstruct_markdown(tokens, [])
    assert result == "⟦F_BLOCK_A⟧"


def test_reconstruct_placeholder_partial_match_literal():
    tokens = [Token(0, "⟦F_BLOCK_0⟧X")]
    result = reconstruct_markdown(tokens, [])
    assert result == "⟦F_BLOCK_0⟧X"
