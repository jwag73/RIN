import re
from typing import List

def fence_parity_ok(text: str) -> bool:
    """Check that the number of triple backtick fences is even."""
    return text.count("```") % 2 == 0

def extract_code_blocks(text: str) -> List[str]:
    """Extract code blocks between fences. For later linting."""
    return re.findall(r"```(?:\\w+)?\\n(.*?)```", text, re.DOTALL)
