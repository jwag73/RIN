from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class RinConfig:
    """
    Configuration for RIN project. This should be passed around explicitly.
    """
    model_name: str = "gpt-3.5-turbo"
    max_tokens: int = 6000
    temperature: float = 0.2
    top_p: float = 1.0
    stop_sequences: List[str] = field(default_factory=lambda: ["\n```", "\n\n"])

    # Linter config: map from language name to validation function name
    linter_map: Dict[str, str] = field(default_factory=lambda: {
        "python": "validate_python_code",
    })

    # Timeouts in seconds
    api_timeout: float = 15.0
    self_fix_timeout: float = 3.0

    # Gate thresholds (used in later sprints)
    fence_parity_required: bool = True
    run_linter_gate: bool = True

    def as_dict(self):
        return self.__dict__
