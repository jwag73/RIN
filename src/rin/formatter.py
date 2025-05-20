import re
from collections import namedtuple
from typing import List, Tuple

FencedBlock = namedtuple("FencedBlock", ["lang", "content", "index"])
Token = namedtuple("Token", ["id", "text"])

# Regex for ```lang\n … ``` (DOTALL so new-lines are captured)
FENCE_RE = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)

# --- MODIFIED TOKEN_RE and tokenize_unfenced_text ---
# Define the sentinel pattern text
_SENTINEL_PATTERN_TEXT = r"⟦F_BLOCK_\d+⟧"

# Update TOKEN_RE to treat sentinels as whole tokens.
# Each alternative is a capturing group.
TOKEN_RE = re.compile(
    rf"({_SENTINEL_PATTERN_TEXT})|(\s+)|(\w+)|(\W)", re.UNICODE
)

def tokenize_unfenced_text(text: str) -> List[Token]:
    """Tokenise text, ensuring sentinels are preserved as single tokens."""
    tokens: List[Token] = []
    for i, match_groups in enumerate(TOKEN_RE.findall(text)):
        # findall with multiple groups returns tuples like ('match_g1', '', '') or ('', 'match_g2', '')
        # We need to find which group actually matched and take its content.
        token_text = next(g for g in match_groups if g) 
        tokens.append(Token(i, token_text))
    return tokens
# --- END OF MODIFICATIONS ---


def segregate_pre_fenced_blocks(text: str) -> Tuple[str, List[FencedBlock]]:
    """Replace each pre-existing fenced block with ⟦F_BLOCK_n⟧ placeholders."""
    blocks: List[FencedBlock] = []

    def _replacer(match: re.Match) -> str:
        idx = len(blocks)
        lang = match.group(1)
        content = match.group(2)
        blocks.append(FencedBlock(lang, content, idx))
        return f"⟦F_BLOCK_{idx}⟧" # Uses the same sentinel format

    new_text = FENCE_RE.sub(_replacer, text)
    return new_text, blocks


def reconstruct_markdown(tokens: List[Token], blocks: List[FencedBlock]) -> str:
    """Swap placeholders back to real fences and glue tokens together."""
    out: List[str] = []
    # This regex needs to match the sentinel format exactly
    placeholder_re = re.compile(r"⟦F_BLOCK_(\d+)⟧") 

    for token in tokens:
        m = placeholder_re.fullmatch(token.text) # Now token.text can be "⟦F_BLOCK_0⟧"
        if m:
            idx = int(m.group(1))
            block = blocks[idx]
            out.append(f"```{block.lang}\n{block.content}```")
        else:
            out.append(token.text)

    return "".join(out)