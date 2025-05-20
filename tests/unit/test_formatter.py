from rin.formatter import (
    segregate_pre_fenced_blocks,
    tokenize_unfenced_text,
    reconstruct_markdown,
)
from rin.validators import fence_parity_ok # Make sure validators.py is also good!

# This was the SAMPLE_DOC construction that seemed to paste best for you:
sample_doc_lines = [
    "Here is some explanation.",
    "",
    "```python",
    "print(\"hello world\")",
    "And here is more text with inline_code.", # This line is part of the python block in this sample
    "```",
    ""
]
SAMPLE_DOC = "\n".join(sample_doc_lines)

def test_round_trip_segmentation_and_reconstruction():
    stripped, blocks = segregate_pre_fenced_blocks(SAMPLE_DOC)
    tokens = tokenize_unfenced_text(stripped)
    rebuilt = reconstruct_markdown(tokens, blocks)
    assert rebuilt == SAMPLE_DOC

def test_fence_parity():
    assert fence_parity_ok(SAMPLE_DOC)
    assert not fence_parity_ok(SAMPLE_DOC + "```")  # odd fence count
    # You could add: assert fence_parity_ok(SAMPLE_DOC + "```\n```")