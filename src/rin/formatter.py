import re
from collections import namedtuple
from typing import List, Tuple

FencedBlock = namedtuple("FencedBlock", ["lang", "content", "index"])
Token = namedtuple("Token", ["id", "text"])

# Regex for ```lang\n … ``` (DOTALL so new-lines are captured)
FENCE_RE = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)

# Tokenise into whitespace, word-chars, or everything else
TOKEN_RE = re.compile(r"(\s+|\w+|\W)", re.UNICODE)


def segregate_pre_fenced_blocks(text: str) -> Tuple[str, List[FencedBlock]]:
    """Replace each pre-existing fenced block with ⟦F_BLOCK_n⟧ placeholders."""
    blocks: List[FencedBlock] = []

    def _replacer(match: re.Match) -> str:
        idx = len(blocks)
        lang = match.group(1)
        content = match.group(2)
        blocks.append(FencedBlock(lang, content, idx))
        return f"⟦F_BLOCK_{idx}⟧"

    new_text = FENCE_RE.sub(_replacer, text)
    return new_text, blocks


def tokenize_unfenced_text(text: str) -> List[Token]:
    return [Token(i, t) for i, t in enumerate(TOKEN_RE.findall(text))]


def reconstruct_markdown(tokens: List[Token], blocks: List[FencedBlock]) -> str:
    """Swap placeholders back to real fences and glue tokens together."""
    out: List[str] = []
    placeholder_re = re.compile(r"⟦F_BLOCK_(\d+)⟧")

    for token in tokens:
        m = placeholder_re.fullmatch(token.text)
        if m:
            idx = int(m.group(1))
            block = blocks[idx]
            out.append(f"```{block.lang}\n{block.content}```")
        else:
            out.append(token.text)

    return "".join(out)
